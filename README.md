# PredictWise AI

An Explainable AutoML and Decision Intelligence Platform.
Final year specialization project — Hiten Mandhyan (24215117).

Upload a CSV/Excel dataset and get automated cleaning, EDA, AutoML model
training, explainable predictions (SHAP/LIME), and an AI-generated report.
See `docs/synopsis.pdf` for the full project synopsis.

## Current status

Day 1 slice: dataset upload end-to-end (frontend → API → validation →
storage → DB → response). Cleaning, EDA, and AutoML modules are next.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, pandas (SQLite for now, PostgreSQL later)
- **Frontend:** React + Vite + Tailwind CSS
- **Coming next:** data cleaning pipeline, EDA charts, AutoML (scikit-learn/XGBoost), SHAP/LIME, LLM report generation

## Getting started

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API docs available at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App available at http://localhost:5173

Run the backend and frontend in two separate terminals — both need to be
running at the same time for uploads to work.

## Project structure

```
predictwise-ai/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py        # Pydantic response schemas
│   ├── database.py       # DB engine/session setup
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx        # Upload UI
│       ├── api.js         # API client
│       └── main.jsx
└── README.md
```

## Progress log

- **Day 1:** Repo scaffolded. Backend `/health`, `/upload`, `/datasets` endpoints working with SQLite persistence and pandas-based file profiling. Frontend upload form wired to the API end-to-end, tested locally. Next: data cleaning module + EDA charts.
