# PredictWise AI

An Explainable AutoML and Decision Intelligence Platform.
Final year specialization project — Hiten Mandhyan (24215117).

Upload a CSV/Excel dataset and get automated cleaning, EDA, AutoML model
training, explainable predictions (SHAP/LIME), and an AI-generated report.

## Current status

Working end-to-end: **upload → clean → explore**.

- **Module 2 — Dataset Upload:** validation, storage, schema detection
- **Module 3 — Data Cleaning:** configurable imputation, duplicate removal,
  whitespace normalisation, IQR outlier clipping, with every operation logged
  to the database for reproducibility
- **Module 4 — EDA:** column profiling, missing-value analysis, distributions,
  correlation heatmap, data preview

Next up: AutoML model builder (Module 5) and the model registry (Module 6).

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, pandas, NumPy (SQLite now, PostgreSQL later)
- **Frontend:** React + Vite + Tailwind CSS
- **Coming next:** scikit-learn/XGBoost AutoML, Optuna tuning, SHAP/LIME, LLM reports

## Getting started

### Backend

```bash
cd backend
python -m venv venv

# Windows (PowerShell):
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive API docs: http://localhost:8000/docs

### Frontend

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 — both servers must run at the same time.

## API endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Liveness check |
| POST | `/upload` | Upload + profile a CSV/Excel dataset |
| GET | `/datasets` | List uploaded datasets |
| GET | `/datasets/{id}` | One dataset's stored profile |
| POST | `/datasets/{id}/clean` | Run the preprocessing pipeline |
| GET | `/datasets/{id}/cleaning-log` | Operations applied to a dataset |
| GET | `/datasets/{id}/eda` | Full EDA profile |

## Project structure

```
predictwise-ai/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── cleaning.py      # Preprocessing pipeline
│   ├── eda.py           # Profiling / EDA computation
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── database.py      # DB engine/session
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx                     # 3-step workflow UI
│       ├── api.js                      # API client
│       └── components/
│           ├── CleaningPanel.jsx       # Cleaning options + operation log
│           ├── EDADashboard.jsx        # EDA results
│           └── Charts.jsx              # Bar / histogram / heatmap
└── README.md
```

## Progress log

- **Day 1:** Repo scaffolded. Backend `/health`, `/upload`, `/datasets` working
  with SQLite persistence and pandas profiling. Frontend upload form wired to
  the API end-to-end.
- **Day 2:** Added the data cleaning pipeline (Module 3) with configurable
  imputation, duplicate removal and IQR outlier clipping, persisting a
  `CleaningLog` row per operation. Added the EDA engine (Module 4) computing
  column profiles, missing-value summaries, correlation matrices and
  histograms. Frontend rebuilt into a 3-step workflow with a full EDA
  dashboard (dependency-free SVG/CSS charts).
  Fixed two pipeline bugs found while testing: duplicates were being dropped
  before whitespace normalisation (so `" Delhi "` and `"Delhi"` were missed),
  and `astype(str)` was converting `NaN` into the string `"nan"`, hiding
  missing values from imputation.
