"""
PredictWise AI — Backend Entry Point (Day 1 slice)

Implements:
  GET  /health            -> liveness check
  POST /upload             -> upload a CSV/Excel dataset, store it, return a quick profile
  GET  /datasets           -> list uploaded datasets
  GET  /datasets/{id}      -> get one dataset's stored profile

Run with:
    uvicorn main:app --reload
Then open http://localhost:8000/docs for interactive API docs.
"""

import json
import os
import shutil
import uuid

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db

# Create tables on startup (fine for SQLite/dev; use Alembic migrations later)
models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = 50

app = FastAPI(title="PredictWise AI", version="0.1.0")

# Allow the Vite dev server to call this API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    # Save the raw upload with a unique name so filenames never collide.
    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(storage_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size_mb = os.path.getsize(storage_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        os.remove(storage_path)
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.")

    # Basic validation + quick profile using pandas.
    try:
        if ext == ".csv":
            df = pd.read_csv(storage_path)
        else:
            df = pd.read_excel(storage_path)
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

    return schemas.DatasetOut(
        id=dataset.id,
        file_name=dataset.file_name,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        columns=json.loads(dataset.columns_json),
        uploaded_at=dataset.uploaded_at,
    )


@app.get("/datasets", response_model=list[schemas.DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    datasets = db.query(models.Dataset).order_by(models.Dataset.uploaded_at.desc()).all()
    return [
        schemas.DatasetOut(
            id=d.id,
            file_name=d.file_name,
            row_count=d.row_count,
            column_count=d.column_count,
            columns=json.loads(d.columns_json),
            uploaded_at=d.uploaded_at,
        )
        for d in datasets
    ]


@app.get("/datasets/{dataset_id}", response_model=schemas.DatasetOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    d = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return schemas.DatasetOut(
        id=d.id,
        file_name=d.file_name,
        row_count=d.row_count,
        column_count=d.column_count,
        columns=json.loads(d.columns_json),
        uploaded_at=d.uploaded_at,
    )
