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

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import cleaning
import eda as eda_service
import models
import schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
CLEANED_DIR = "cleaned"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLEANED_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = 50

app = FastAPI(title="PredictWise AI", version="0.2.0")

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
