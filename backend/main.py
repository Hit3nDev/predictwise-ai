"""
PredictWise AI — Backend Entry Point

Implemented so far:
  GET  /health                     -> liveness check
  POST /upload                     -> upload a CSV/Excel dataset, store + profile it
  GET  /datasets                   -> list uploaded datasets
  GET  /datasets/{id}              -> one dataset's stored profile
  POST /datasets/{id}/clean        -> run the preprocessing pipeline, log every operation
  GET  /datasets/{id}/cleaning-log -> operations applied to this dataset
  GET  /datasets/{id}/eda          -> full EDA profile (stats, missing, correlation, histograms)

Run with:
    uvicorn main:app --reload
Then open http://localhost:8000/docs for interactive API docs.
"""

import json
import os
import shutil
import uuid

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import automl
import cleaning
import insights
import llm_resolver
import eda as eda_service
import models
import schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
CLEANED_DIR = "cleaned"
MODEL_DIR = "artifacts"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLEANED_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = 50

app = FastAPI(title="PredictWise AI", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _read_any(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _get_dataset_or_404(dataset_id: int, db: Session) -> models.Dataset:
    d = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return d


def _to_out(d: models.Dataset) -> schemas.DatasetOut:
    return schemas.DatasetOut(
        id=d.id,
        file_name=d.file_name,
        row_count=d.row_count,
        column_count=d.column_count,
        columns=json.loads(d.columns_json),
        uploaded_at=d.uploaded_at,
        is_cleaned=bool(d.cleaned_path),
    )


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=schemas.DatasetOut)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(storage_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size_mb = os.path.getsize(storage_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        os.remove(storage_path)
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.")

    try:
        df = _read_any(storage_path)
    except Exception as exc:
        os.remove(storage_path)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    if df.empty:
        os.remove(storage_path)
        raise HTTPException(status_code=400, detail="Uploaded file has no rows.")

    dataset = models.Dataset(
        file_name=file.filename,
        storage_path=storage_path,
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        columns_json=json.dumps(list(df.columns.astype(str))),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return _to_out(dataset)


@app.get("/datasets", response_model=list[schemas.DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    datasets = db.query(models.Dataset).order_by(models.Dataset.uploaded_at.desc()).all()
    return [_to_out(d) for d in datasets]


@app.get("/datasets/{dataset_id}", response_model=schemas.DatasetOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    return _to_out(_get_dataset_or_404(dataset_id, db))


@app.post("/datasets/{dataset_id}/clean", response_model=schemas.CleaningResult)
def clean_dataset(
    dataset_id: int,
    options: schemas.CleaningOptions = schemas.CleaningOptions(),
    db: Session = Depends(get_db),
):
    """Run the preprocessing pipeline and persist a log of every operation applied."""
    d = _get_dataset_or_404(dataset_id, db)

    try:
        df = _read_any(d.storage_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read stored file: {exc}")

    rows_before = int(df.shape[0])
    cleaned_df, operations = cleaning.clean_dataframe(
        df,
        drop_duplicates=options.drop_duplicates,
        numeric_strategy=options.numeric_strategy,
        categorical_strategy=options.categorical_strategy,
        outlier_method=options.outlier_method,
    )

    cleaned_path = os.path.join(CLEANED_DIR, f"{uuid.uuid4().hex}.csv")
    cleaned_df.to_csv(cleaned_path, index=False)

    # Replace any previous cleaning history for this dataset
    db.query(models.CleaningLog).filter(models.CleaningLog.dataset_id == d.id).delete()
    for op in operations:
        db.add(
            models.CleaningLog(
                dataset_id=d.id,
                operation=op["operation"],
                detail=op["detail"],
                rows_affected=op["rows_affected"],
            )
        )

    d.cleaned_path = cleaned_path
    db.commit()

    return schemas.CleaningResult(
        dataset_id=d.id,
        rows_before=rows_before,
        rows_after=int(cleaned_df.shape[0]),
        columns=int(cleaned_df.shape[1]),
        operations=[schemas.CleaningLogOut(**op) for op in operations],
    )


@app.get("/datasets/{dataset_id}/cleaning-log", response_model=list[schemas.CleaningLogOut])
def get_cleaning_log(dataset_id: int, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    logs = (
        db.query(models.CleaningLog)
        .filter(models.CleaningLog.dataset_id == dataset_id)
        .order_by(models.CleaningLog.id)
        .all()
    )
    return [
        schemas.CleaningLogOut(
            operation=l.operation, detail=l.detail, rows_affected=l.rows_affected
        )
        for l in logs
    ]


@app.get("/datasets/{dataset_id}/eda", response_model=schemas.EDAResult)
def get_eda(
    dataset_id: int,
    use_cleaned: bool = Query(True, description="Profile the cleaned file when available"),
    db: Session = Depends(get_db),
):
    """Full EDA profile: column stats, missing values, correlations and histograms."""
    d = _get_dataset_or_404(dataset_id, db)

    path, source = d.storage_path, "raw"
    if use_cleaned and d.cleaned_path and os.path.exists(d.cleaned_path):
        path, source = d.cleaned_path, "cleaned"

    try:
        df = _read_any(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    payload = eda_service.build_eda(df)
    return schemas.EDAResult(dataset_id=d.id, source=source, **payload)


# ----------------------------------------------------------------------------
# AutoML — training, leaderboard, prediction
# ----------------------------------------------------------------------------

def _persist_experiment(db: Session, dataset_id: int, result: dict):
    """
    Persist one AutoML run: an Experiment row, one MLModel row per candidate,
    and a saved joblib artifact for the winner. Shared by /train and /ask so
    a Simple Mode question and a Technical Mode training run produce the same
    kind of record and can both later serve predictions.
    """
    experiment = models.Experiment(
        dataset_id=dataset_id,
        target_column=result["target"],
        task_type=result["task"],
        status="completed",
        primary_metric=result["primary_metric"],
        n_train=result["n_train"],
        n_test=result["n_test"],
        cv_folds=result["cv_folds"],
        features_json=json.dumps(result["features"]),
    )
    db.add(experiment)
    db.flush()

    best_model_id = None
    entries: list[schemas.LeaderboardEntry] = []

    for entry in result["leaderboard"]:
        is_best = entry["algorithm"] == result["best_algorithm"] and entry["status"] == "ok"

        record = models.MLModel(
            experiment_id=experiment.id,
            algorithm=entry["algorithm"],
            rank=entry.get("rank"),
            is_best=1 if is_best else 0,
            cv_mean=entry.get("cv_mean"),
            cv_std=entry.get("cv_std"),
            train_seconds=entry.get("train_seconds"),
            metrics_json=json.dumps(entry.get("metrics", {})),
            status=entry["status"],
        )

        if is_best:
            record.importance_json = json.dumps(result["feature_importance"])
            record.classes_json = json.dumps(result["_classes"]) if result["_classes"] else None

        db.add(record)
        db.flush()

        if is_best:
            artifact_path = os.path.join(MODEL_DIR, f"model_{record.id}.joblib")
            joblib.dump(
                {
                    "pipeline": result["_pipeline"],
                    "features": result["features"],
                    "task": result["task"],
                    "target": result["target"],
                },
                artifact_path,
            )
            record.artifact_path = artifact_path
            best_model_id = record.id

        entries.append(
            schemas.LeaderboardEntry(
                rank=entry.get("rank"),
                algorithm=entry["algorithm"],
                cv_mean=entry.get("cv_mean"),
                cv_std=entry.get("cv_std"),
                train_seconds=entry.get("train_seconds"),
                metrics=entry.get("metrics", {}),
                status=entry["status"],
                is_best=is_best,
                model_id=record.id,
            )
        )

    db.commit()
    return experiment, best_model_id, entries


@app.post("/datasets/{dataset_id}/train", response_model=schemas.ExperimentResult)
def train_models(
    dataset_id: int,
    req: schemas.TrainRequest,
    db: Session = Depends(get_db),
):
    """
    Run the AutoML pipeline: train several candidate algorithms with
    cross-validation, rank them, persist every candidate and save the winner's
    fitted pipeline to disk so it can serve predictions later.
    """
    d = _get_dataset_or_404(dataset_id, db)

    # Always prefer the cleaned file when one exists.
    path = d.cleaned_path if (d.cleaned_path and os.path.exists(d.cleaned_path)) else d.storage_path
    try:
        df = _read_any(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read dataset: {exc}")

    try:
        result = automl.run_automl(
            df, target=req.target, test_size=req.test_size, cv_folds=req.cv_folds
        )
    except automl.TrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Training failed: {exc}")

    experiment, best_model_id, entries = _persist_experiment(db, d.id, result)

    return schemas.ExperimentResult(
        experiment_id=experiment.id,
        dataset_id=d.id,
        task=result["task"],
        target=result["target"],
        features=result["features"],
        dropped_columns=result["dropped_columns"],
        n_train=result["n_train"],
        n_test=result["n_test"],
        cv_folds=result["cv_folds"],
        primary_metric=result["primary_metric"],
        best_algorithm=result["best_algorithm"],
        best_metrics=result["best_metrics"],
        best_model_id=best_model_id,
        leaderboard=entries,
        feature_importance=[
            schemas.FeatureImportance(**fi) for fi in result["feature_importance"]
        ],
    )


@app.get("/datasets/{dataset_id}/experiments", response_model=list[dict])
def list_experiments(dataset_id: int, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    rows = (
        db.query(models.Experiment)
        .filter(models.Experiment.dataset_id == dataset_id)
        .order_by(models.Experiment.created_at.desc())
        .all()
    )
    out = []
    for e in rows:
        best = next((m for m in e.ml_models if m.is_best), None)
        out.append(
            {
                "experiment_id": e.id,
                "target": e.target_column,
                "task": e.task_type,
                "primary_metric": e.primary_metric,
                "best_algorithm": best.algorithm if best else None,
                "best_model_id": best.id if best else None,
                "best_metrics": json.loads(best.metrics_json) if best else {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )
    return out


@app.get("/experiments/{experiment_id}", response_model=schemas.ExperimentResult)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    e = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Experiment not found")

    best = next((m for m in e.ml_models if m.is_best), None)
    if not best:
        raise HTTPException(status_code=404, detail="Experiment has no successful model")

    entries = [
        schemas.LeaderboardEntry(
            rank=m.rank,
            algorithm=m.algorithm,
            cv_mean=m.cv_mean,
            cv_std=m.cv_std,
            train_seconds=m.train_seconds,
            metrics=json.loads(m.metrics_json or "{}"),
            status=m.status,
            is_best=bool(m.is_best),
            model_id=m.id,
        )
        for m in sorted(e.ml_models, key=lambda m: (m.rank is None, m.rank or 0))
    ]

    return schemas.ExperimentResult(
        experiment_id=e.id,
        dataset_id=e.dataset_id,
        task=e.task_type,
        target=e.target_column,
        features=json.loads(e.features_json or "[]"),
        n_train=e.n_train or 0,
        n_test=e.n_test or 0,
        cv_folds=e.cv_folds or 0,
        primary_metric=e.primary_metric or "",
        best_algorithm=best.algorithm,
        best_metrics=json.loads(best.metrics_json or "{}"),
        best_model_id=best.id,
        leaderboard=entries,
        feature_importance=[
            schemas.FeatureImportance(**fi)
            for fi in json.loads(best.importance_json or "[]")
        ],
    )


@app.post("/models/{model_id}/predict", response_model=schemas.PredictResponse)
def predict(model_id: int, req: schemas.PredictRequest, db: Session = Depends(get_db)):
    """Serve predictions from a saved model, logging each one for auditing."""
    m = db.query(models.MLModel).filter(models.MLModel.id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Model not found")
    if not m.artifact_path or not os.path.exists(m.artifact_path):
        raise HTTPException(
            status_code=400,
            detail="This model has no saved artifact — only the best model of each run is saved.",
        )
    if not req.rows:
        raise HTTPException(status_code=400, detail="Provide at least one row to predict.")

    bundle = joblib.load(m.artifact_path)
    pipeline, features = bundle["pipeline"], bundle["features"]
    task, target = bundle["task"], bundle["target"]

    # Build a frame with exactly the training feature columns, in order.
    frame = pd.DataFrame(req.rows)
    missing = [f for f in features if f not in frame.columns]
    for f in missing:
        frame[f] = np.nan
    frame = frame[features]

    try:
        preds = pipeline.predict(frame)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {exc}")

    probabilities = None
    if task == "classification" and hasattr(pipeline, "predict_proba"):
        try:
            probabilities = pipeline.predict_proba(frame)
        except Exception:
            probabilities = None

    classes = json.loads(m.classes_json) if m.classes_json else None

    results = []
    for i, row in enumerate(req.rows):
        value = preds[i]
        value = value.item() if hasattr(value, "item") else value

        confidence, proba_map = None, None
        if probabilities is not None and classes:
            proba_map = {
                str(cls): round(float(probabilities[i][j]), 4)
                for j, cls in enumerate(classes)
            }
            confidence = round(float(max(probabilities[i])), 4)

        results.append(
            schemas.PredictionOut(
                row=row,
                prediction=value,
                confidence=confidence,
                probabilities=proba_map,
            )
        )
        db.add(
            models.Prediction(
                model_id=m.id,
                input_json=json.dumps(row, default=str),
                output_json=json.dumps(
                    {"prediction": value, "confidence": confidence}, default=str
                ),
            )
        )

    db.commit()

    return schemas.PredictResponse(
        model_id=m.id,
        algorithm=m.algorithm,
        task=task,
        target=target,
        results=results,
    )


# ----------------------------------------------------------------------------
# Simple Mode — plain-language questions instead of columns and metrics
# ----------------------------------------------------------------------------

def _round_display(v):
    """Whole numbers for anything currency/count-scale; a little precision for small values."""
    if v is None:
        return None
    if abs(v) >= 100:
        return round(v)
    if abs(v) >= 1:
        return round(v, 1)
    return round(v, 3)


def _field_spec(df: pd.DataFrame, col: str) -> schemas.FieldSpec:
    if pd.api.types.is_numeric_dtype(df[col]):
        s = df[col].dropna()
        return schemas.FieldSpec(
            name=col, label=insights.pretty(col), type="number",
            min=_round_display(float(s.min())) if len(s) else None,
            max=_round_display(float(s.max())) if len(s) else None,
            typical=_round_display(float(s.median())) if len(s) else None,
        )
    options = sorted(df[col].dropna().astype(str).unique().tolist())[:8]
    return schemas.FieldSpec(name=col, label=insights.pretty(col), type="select", options=options)


@app.get("/datasets/{dataset_id}/question-templates", response_model=list[schemas.TemplateAvailability])
def question_templates(dataset_id: int, db: Session = Depends(get_db)):
    """Which plain-language questions this dataset can actually answer, and why not."""
    d = _get_dataset_or_404(dataset_id, db)
    path = d.cleaned_path if (d.cleaned_path and os.path.exists(d.cleaned_path)) else d.storage_path
    try:
        df = _read_any(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read dataset: {exc}")

    avail = insights.availability(df)
    return [
        schemas.TemplateAvailability(
            id=t["id"],
            label=t["label"],
            hint=t["hint"],
            available=avail[t["id"]]["available"],
            reason=avail[t["id"]]["reason"],
        )
        for t in insights.TEMPLATES
    ]


@app.post("/datasets/{dataset_id}/ask", response_model=schemas.AskResponse)
def ask_question(dataset_id: int, req: schemas.AskRequest, db: Session = Depends(get_db)):
    """
    The Simple Mode entry point. A template card click still goes through the
    fixed 4-template availability check, unchanged. Free text goes through
    insights.resolve_question, which honors a column the user actually named
    (so "what affects income" or "compare sales by city" get answered on
    their own terms) before ever falling back to coarse keyword scoring.
    """
    d = _get_dataset_or_404(dataset_id, db)
    path = d.cleaned_path if (d.cleaned_path and os.path.exists(d.cleaned_path)) else d.storage_path
    try:
        df = _read_any(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read dataset: {exc}")

    avail = insights.availability(df)

    if req.template_id:
        resolved = {"kind": req.template_id, "explicit": False}
        label = next(t["label"] for t in insights.TEMPLATES if t["id"] == req.template_id)
        if req.template_id != "profile" and not avail[req.template_id]["available"]:
            fallback_note = avail[req.template_id]["reason"]
            resolved, label = {"kind": "profile", "explicit": False}, "What does my data look like?"
            resolved["fallback_note"] = fallback_note
    else:
        columns = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
        resolved = llm_resolver.resolve(columns, req.question or "")
        used_llm = resolved is not None
        if not resolved:
            resolved = insights.resolve_question(df, req.question or "")

        # Self-correction: don't trust "repeat"/"drivers_repeat" if the target
        # isn't actually a two-value column — downgrade instead of letting it
        # fail training several layers down. Only relevant for the LLM path;
        # the heuristic resolver already only picks genuinely binary columns.
        if used_llm and resolved["kind"] in ("repeat", "drivers_repeat") and resolved.get("target"):
            if not insights._is_binary(df[resolved["target"]]):
                resolved["kind"] = "drivers_number" if resolved["kind"] == "drivers_repeat" else "predict_number"

        # The coarse keyword-matched fallback (no column was explicitly named)
        # can land on a template this dataset can't actually answer — same
        # situation the template_id path already guards against, so apply the
        # same check here rather than letting it crash downstream.
        if not resolved.get("explicit") and resolved["kind"] in ("repeat", "predict_number", "top_performers"):
            check = avail.get(resolved["kind"], {})
            if not check.get("available"):
                resolved = {"kind": "profile", "explicit": False, "fallback_note": check.get("reason")}
        label = _label_for(resolved)

    kind = resolved["kind"]

    # ---- profile: always available, the universal fallback -----------------
    if kind == "profile":
        eda = eda_service.build_eda(df)
        narrative = insights.narrate_profile(eda, df)
        note = resolved.get("fallback_note")
        if note:
            narrative.insert(0, f"I couldn't fully answer that ({note}) — here's an overview instead.")
        return schemas.AskResponse(
            matched_template="profile", matched_label=label, kind="profile", narrative=narrative,
        )

    # ---- ranking / compare: aggregation only, no modelling ------------------
    if kind == "top_performers":
        cat_col, metric_col = avail["top_performers"]["detected"]
        ranking = insights.top_performers(df, cat_col, metric_col)
        return schemas.AskResponse(
            matched_template="top_performers", matched_label=label, kind="ranking",
            narrative=[ranking["narrative"]], ranking=ranking["rows"],
        )

    if kind == "compare":
        try:
            outcome = insights.run_compare(df, resolved["cat_col"], resolved["metric_col"])
        except automl.TrainingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return schemas.AskResponse(
            matched_template="top_performers", matched_label=label, kind="ranking",
            narrative=outcome["narrative"], ranking=outcome["rows"],
        )

    # ---- repeat / predict_number / drivers_*: trains a model -----------------
    is_drivers = kind.startswith("drivers_")
    is_classification = kind in ("repeat", "drivers_repeat")
    target = resolved.get("target") or avail.get("repeat" if is_classification else "predict_number", {}).get("detected")
    if not target:
        raise HTTPException(status_code=400, detail="Couldn't find a suitable column to answer that.")

    try:
        outcome = (
            insights.run_repeat_question(df, target, lead_with_drivers=is_drivers)
            if is_classification
            else insights.run_number_question(df, target, lead_with_drivers=is_drivers)
        )
    except automl.TrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if resolved.get("explicit"):
        outcome["narrative"].insert(0, f"You asked about {insights.pretty(target)} — here's what the data shows.")

    experiment, best_model_id, _ = _persist_experiment(db, d.id, outcome["result"])
    top_features = [f["feature"] for f in outcome["result"]["feature_importance"][:4]]
    fields = [_field_spec(df, f) for f in top_features if f in df.columns]

    # Reuse the vocabulary the frontend already understands ("repeat" /
    # "predict_number") so a drivers-framed question renders with the exact
    # same mini-form and Yes/No translation, with no frontend changes needed.
    matched_template = "repeat" if is_classification else "predict_number"
    return schemas.AskResponse(
        matched_template=matched_template, matched_label=label, kind="predictable",
        narrative=outcome["narrative"], target=target,
        experiment_id=experiment.id, model_id=best_model_id, fields=fields,
    )


def _label_for(resolved: dict) -> str:
    """A human-readable heading reflecting what was actually resolved, for transparency."""
    kind = resolved["kind"]
    target = resolved.get("target")
    if kind == "compare":
        return f"Comparing {insights.pretty(resolved['metric_col'])} by {insights.pretty(resolved['cat_col'])}"
    if kind in ("drivers_repeat", "drivers_number") and target:
        return f"What affects {insights.pretty(target)}?"
    if kind == "repeat" and target:
        return f"Will {insights.pretty(target).lower()} happen?"
    if kind == "predict_number" and target:
        return f"Predicting {insights.pretty(target)}"
    # No explicitly-resolved target (the coarse keyword-matched fallback path) —
    # use the generic template label instead.
    return next((t["label"] for t in insights.TEMPLATES if t["id"] == kind), "What does my data look like?")
