# PredictWise AI

An Explainable AutoML and Decision Intelligence Platform.
Final year specialization project — Hiten Mandhyan (24215117).

Take a spreadsheet from raw file to a trained, explained, queryable model
without writing code.

## What works today

The full pipeline runs end to end: **upload → clean → explore → model → predict**.

| Module | Status |
|---|---|
| 2 · Dataset upload & management | done |
| 3 · Data cleaning & preprocessing | done |
| 4 · Exploratory data analysis | done |
| 5 · AutoML model builder | done |
| 6 · Model registry & versioning | done |
| 7 · Prediction + feature attribution | done (permutation importance; SHAP next) |
| 1 · Auth & roles | not started |
| 8 · Bias & fairness auditor | not started |
| 9 · LLM report generator | not started |
| 11 · Drift monitoring | not started |

### AutoML details

- Detects classification vs regression from the target column
- Trains 4–5 candidate algorithms (linear/logistic, tree, random forest,
  gradient boosting, ridge) inside a single sklearn `Pipeline`, so imputation
  and scaling are fitted on training folds only — no leakage
- **Selects the winner by cross-validated score on training data**, then
  reports held-out test metrics separately as an unbiased estimate
- Drops identifier-like columns automatically
- Computes permutation feature importance for the winner
- Saves the fitted pipeline with joblib so predictions can be served later
- Every candidate, metric and prediction is persisted

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, pandas, NumPy, scikit-learn, joblib
- **Frontend:** React, Vite, Tailwind
- **Database:** SQLite in development; the connection string in `database.py`
  is the only change needed for PostgreSQL
- **Next:** SHAP/LIME, Optuna tuning, LLM reports, drift monitoring

## Running it

Two terminals.

**Backend**

```bash
cd backend
python -m venv venv

# Windows (PowerShell)
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

API docs: http://localhost:8000/docs

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

`sample_data.csv` (messy, small) and `sample_customers.csv` (300 rows, real
signal — good for training) are included to try it with.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/upload` | Upload and profile a dataset |
| GET | `/datasets` | List datasets |
| GET | `/datasets/{id}` | One dataset's profile |
| POST | `/datasets/{id}/clean` | Run preprocessing |
| GET | `/datasets/{id}/cleaning-log` | Operations applied |
| GET | `/datasets/{id}/eda` | Full EDA profile |
| POST | `/datasets/{id}/train` | Run AutoML |
| GET | `/datasets/{id}/experiments` | Training history |
| GET | `/experiments/{id}` | Leaderboard + importance |
| POST | `/models/{id}/predict` | Predict on new rows |

## Structure

```
backend/
  main.py       routes
  automl.py     task detection, training, leaderboard, importance
  cleaning.py   preprocessing pipeline
  eda.py        profiling
  models.py     User, Dataset, CleaningLog, Experiment, MLModel, Prediction
  schemas.py    request/response contracts
  database.py   engine and session
frontend/src/
  App.jsx                 pipeline shell
  components/
    ui.jsx                interface primitives
    charts.jsx            histogram, heatmap, importance bars
    stages.jsx            data / clean / explore
    modelStages.jsx       model / predict
    Leaderboard.jsx       ranked models with score bars
```

## Progress log

- **Day 1** — Repo, FastAPI backend, upload endpoint with validation and
  pandas profiling, SQLite persistence, React upload form.
- **Day 2** — Cleaning pipeline (configurable imputation, duplicate removal,
  IQR clipping) with a `CleaningLog` row per operation. EDA engine: column
  profiles, missing-value summary, correlations, histograms.
  Fixed two pipeline bugs: duplicates were dropped before whitespace was
  normalised, so `" Delhi "` and `"Delhi"` never matched; and `astype(str)`
  turned `NaN` into the string `"nan"`, hiding missing values from imputation.
- **Day 3** — AutoML engine: task inference, leak-free preprocessing pipelines,
  multi-algorithm training with cross-validation, leaderboard, permutation
  importance, model persistence, and a prediction endpoint with class
  probabilities. Added Experiment / MLModel / Prediction tables.
  **Corrected a model-selection error:** the leaderboard originally ranked by
  test-set score, which leaks the held-out set into model choice and inflates
  the reported metric. Selection now uses cross-validated training scores and
  the test set is only reported afterwards.
  Frontend rebuilt around the five pipeline stages.
