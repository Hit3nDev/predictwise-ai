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

    experiment = models.Experiment(
        dataset_id=d.id,
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
    db.flush()  # assigns experiment.id without committing yet

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
            # Persist the fitted pipeline so /predict can load it later.
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
