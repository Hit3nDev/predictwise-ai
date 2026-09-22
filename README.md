# PredictWise AI

An Explainable AutoML and Decision Intelligence Platform.
Final year specialization project — Hiten Mandhyan (24215117).

Two experiences, one engine:

- **Simple Mode** — for someone with no data background (a shop owner, a small
  business). Ask a plain-English question or pick one from a library, and get
  a sentence back, not a leaderboard.
- **Technical Mode** — the full pipeline: cleaning options, EDA, cross-validated
  model comparison, permutation importance, raw metrics.

A toggle in the header switches between them at any point without losing the
selected dataset.

## What works today

Full pipeline end to end in both modes: **upload → clean → explore → model → predict.**

| Module | Status |
|---|---|
| 2 · Dataset upload & management | done |
| 3 · Data cleaning & preprocessing | done |
| 4 · Exploratory data analysis | done |
| 5 · AutoML model builder | done |
| 6 · Model registry & versioning | done |
| 7 · Prediction + feature attribution | done (permutation importance; SHAP next) |
| **10 · Plain-language insight engine (Simple Mode)** | **done** |
| 1 · Auth & roles | not started |
| 8 · Bias & fairness auditor | not started |
| 9 · LLM report generator | not started |
| 11 · Drift monitoring | not started |

### How Simple Mode works (`insights.py`)

A shop owner doesn't think in "target columns" — they think in questions. Four
templates cover most small-business questions:

- **"What does my data look like?"** — always-available plain-English profile
- **"Will this happen again?"** — classification on a detected yes/no column
  (purchased, churned, renewed, returned...)
- **"What number should I expect?"** — regression on a detected numeric target
  (price, revenue, sales...)
- **"What's doing best?"** — ranks categories/products/locations by a business
  number, no modelling involved

A free-text question is keyword-matched to the closest template; if it can't
be matched confidently, or the matched template isn't answerable on this
dataset (e.g. no yes/no column exists), it falls back to the profile and says
why. Columns are found by scanning names for business keywords, then by shape
(binary, high-variance, non-identifier) — this is a heuristic, not an LLM call,
and is written so swapping in a real LLM later (Module 9) is a small change to
`match_question()`, not a redesign.

Answers to predictable questions come with a mini form of just the 3–4 most
important fields (by permutation importance), with plain labels and a typical
value range — not the full column list Technical Mode's Predict stage shows.

### AutoML details

- Detects classification vs regression from the target column; a corrected
  identifier heuristic (name pattern + sequential-integer check, not just
  "all values unique") stops continuous targets like `price` from being
  mistaken for row IDs
- Trains 4–5 candidates inside one sklearn `Pipeline` so imputation/scaling
  fit on training folds only — no leakage
- **Selects the winner by cross-validated score**, reports held-out test
  metrics separately as an unbiased estimate (an earlier version selected on
  the test set itself, which leaks it into model choice — fixed)
- Computes permutation feature importance; saves the fitted pipeline with
  joblib so predictions can be served later

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, pandas, NumPy, scikit-learn, joblib
- **Frontend:** React, Vite, Tailwind — custom design system (Archivo +
  JetBrains Mono, hairline-rule aesthetic, no template-kit defaults)
- **Database:** SQLite in development; `database.py`'s connection string is
  the only change needed for PostgreSQL
- **Next:** SHAP/LIME, Optuna tuning, LLM-backed question matching, drift monitoring

## Running it

Two terminals.

**Backend**
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# Optional — enables real language understanding for Simple Mode free-text
# questions instead of the offline synonym-matching fallback:
# export ANTHROPIC_API_KEY=sk-ant-...        (macOS/Linux)
# $env:ANTHROPIC_API_KEY="sk-ant-..."        (Windows PowerShell)

uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 — `sample_customers.csv` and `sample_data.csv` are
included to try both modes with.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/upload` | Upload and profile a dataset |
| GET | `/datasets` | List datasets |
| POST | `/datasets/{id}/clean` | Run preprocessing |
| GET | `/datasets/{id}/eda` | Full EDA profile |
| POST | `/datasets/{id}/train` | Run AutoML (Technical Mode) |
| GET | `/datasets/{id}/question-templates` | Which Simple Mode questions this dataset can answer |
| POST | `/datasets/{id}/ask` | Ask a Simple Mode question |
| GET | `/experiments/{id}` | Leaderboard + importance |
| POST | `/models/{id}/predict` | Predict on new rows |

## Structure

```
backend/
  main.py       routes (incl. _persist_experiment, shared by /train and /ask)
  automl.py     task detection, training, leaderboard, importance
  insights.py   Simple Mode: question templates, column detection, narration
  llm_resolver.py  optional LLM-backed question understanding (needs ANTHROPIC_API_KEY)
  cleaning.py   preprocessing pipeline
  eda.py        profiling
  models.py     User, Dataset, CleaningLog, Experiment, MLModel, Prediction
frontend/src/
  App.jsx                    mode toggle + shared dataset state
  components/
    SimpleMode.jsx           3-step plain-language flow
    TechnicalMode.jsx        5-stage pipeline shell
    ui.jsx, charts.jsx, Leaderboard.jsx, stages.jsx, modelStages.jsx
  index.css, tailwind.config.js   design tokens (RGB-triplet CSS vars —
                                    required for Tailwind opacity modifiers
                                    to work with custom colors; see log)
```

## Progress log

- **Day 6** — Diagnosed the actual reason "customised questions" still failed:
  column-mention detection required the *literal* column name to appear in
  the question. Natural phrasing ("will they buy again", "who's likely to
  spend the most") shares no vocabulary with a column literally called
  `purchased` or `income`, so it fell straight to the weak keyword fallback
  every time. Two changes:
  1. Added `SYNONYM_GROUPS` — hand-written sets of interchangeable business
     words (buy/purchase/order/sold, churn/cancel/leave, spend/cost/money...)
     so "buy again" now connects to a column named `purchased`. Broadened the
     "what affects X" trigger to catch bare words like "affect"/"drive"
     anywhere in the sentence, not just as a leading phrase.
  2. Added `llm_resolver.py` — an **optional** real-language-understanding
     path. If `ANTHROPIC_API_KEY` is set, free text is sent to Claude to
     resolve into the same structured intent, with every returned column
     name validated against the actual dataframe (an LLM can hallucinate a
     plausible-looking column that doesn't exist — this is caught, not
     trusted). Without a key, `resolve()` returns `None` immediately and
     nothing changes; this is additive, not a dependency.
  **Bugs found and fixed while building this:**
  - A synonym group covering "customer/person/user" collided with any
    `customer_id`-style column — "how much will a customer bring in" was
    hijacking the identifier column instead of falling back honestly.
    Removed that group entirely rather than trying to special-case it: it
    added collision risk for little real matching value.
  - Plural forms ("cities") didn't connect to their singular column name
    ("city") at all — added a small delemmatizer for the common cases.
  - The `_looks_like_id` exclusion was being fully bypassed for *any*
    mention, including a loose synonym collision. Now it's only bypassed for
    a literal, exact mention; a synonym-based guess still has to clear the
    identifier check.
  - **Not independently verified:** the live LLM call itself — no API key
    was available in the sandbox this was built in. The validation logic and
    the no-key fallback path are tested; the actual `httpx.post` round-trip
    to `api.anthropic.com` is not. Test with a real key before demoing it.



- **Day 5** — Fixed the actual complaint behind "why can't it answer my own
  question": free text was only ever keyword-scored into the 4 fixed
  templates and never looked at which columns the user actually named.
  Added `resolve_question()`: it now parses the question for column mentions
  (whole-word matched, so 'age' doesn't false-match inside 'average') and
  honors them directly, plus two new intents — "what affects X" (drivers-only
  framing of the same model) and "compare X by Y" (group-mean comparison,
  no modelling needed). Falls back to the old 4-template scoring only when
  nothing specific was named. A transparency line ("You asked about Income —
  here's what the data shows") makes it clear when a column was explicitly
  honored.
  **Bugs found and fixed during testing:**
  - The free-text fallback path could resolve to a template the dataset
    can't actually answer (e.g. no valid category+metric pair) without the
    same availability check the card-click path already had — crashed with
    an unhandled 500 instead of degrading to the profile. Added the missing
    guard.
  - The identifier-exclusion heuristic was being applied to *explicitly
    named* columns too, so a legitimately-numeric column that happened to
    look sequential (rare, but not impossible) would be silently dropped
    from consideration. Explicit mentions are now trusted as named; the
    identifier heuristic is reserved for auto-detection only.



- **Day 1** — Upload pipeline, SQLite persistence, basic React form.
- **Day 2** — Cleaning pipeline + EDA engine. Fixed a whitespace/duplicate
  ordering bug and a `NaN`→`"nan"` string bug that hid missing values from
  imputation.
- **Day 3** — AutoML engine: leak-free pipelines, cross-validated leaderboard,
  permutation importance, prediction API. Fixed a test-set-leakage bug in
  model selection. Frontend rebuilt around a custom design system.
- **Day 4** — Simple Mode: a plain-language insight engine so a non-technical
  user can ask a business question instead of picking a target column and
  reading a metrics table. Always-visible Simple/Technical toggle, shared
  dataset state across both.
  **Bugs found and fixed during testing:**
  - `top_performers` picked `age` as a ranking metric (summing ages across a
    city is meaningless) — added a demographic-column skip list.
  - The identifier-exclusion heuristic (`nunique == row count`) wrongly
    excluded genuine continuous targets like `price`, which are normally
    all-unique due to noise — replaced with a proper check (name pattern or
    sequential integers), applied consistently in both `automl.py` and
    `insights.py`.
  - Simple Mode showed raw `1`/`0` model output for yes/no questions —
    added plain-language translation ("Yes"/"No") scoped to that question type.
  - **The entire custom color system was silently broken:** CSS variables
    were defined as hex strings (`--ink: #2f7d6e`) and referenced directly in
    Tailwind's config, which cannot combine a variable it can't see inside of
    with an opacity modifier at build time. Every `bg-ink/70`, `text-slate/50`,
    `border-rule/70` class in the app — dozens of them — was rendering
    without its intended opacity. Fixed by switching to RGB-triplet variables
    (`--ink: 47 125 110`) with Tailwind's documented `rgb(var(--x) / <alpha-value>)`
    pattern. Caught by inspecting a chart that rendered as flat grey instead
    of colored bars, not by reading the code.
