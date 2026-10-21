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

# Optional — enables real language understanding for the chat, instead of
# just the offline query engine + synonym matching. Anthropic has no free
# API tier, so this defaults to Groq: free, no credit card, sign up at
# console.groq.com/keys.
# export GROQ_API_KEY=gsk_...        (macOS/Linux)
# $env:GROQ_API_KEY="gsk_..."        (Windows PowerShell)
#
# If you later get Anthropic access, ANTHROPIC_API_KEY also works — Groq
# takes priority if both are set, since it's the free path.

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
  llm_provider.py  Groq/Anthropic abstraction (Groq is free; see llm_chat.py, llm_resolver.py)
  llm_chat.py      LLM tool-use chat: the model queries the dataframe directly
  llm_resolver.py  LLM-backed question-intent resolver
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

- **Day 9** — The LLM integration only ever spoke Anthropic's Messages API
  format, and Anthropic has no free API tier — so "set an API key" was
  advice nobody could actually follow for free. Added `llm_provider.py`: a
  shared abstraction that defaults to **Groq** (free, no credit card,
  OpenAI-compatible chat completions with tool calling) and falls back to
  Anthropic if that's what's configured instead. `llm_chat.py` and
  `llm_resolver.py` were rewritten against this abstraction rather than
  calling `api.anthropic.com` directly.
  Also fixed two real bugs surfaced by a screenshot of the profile fallback:
  the "general overview" was describing `customer_id` as if it were
  meaningful data ("Customer id typically runs around 150.5") — identifier
  columns are now excluded from that narration. And the same ugly-decimal
  formatting bug from Day 2/3 turned up again in a code path the earlier
  fix didn't cover (the profile's own numeric summaries) — fixed with the
  same comma-formatting helper, applied here too.
  **Tested without a real key** (none available in this sandbox), using
  hand-built response payloads matching Groq's documented API shape: provider
  selection, the tool-schema conversion, and — most importantly — the full
  tool-call loop end-to-end through the actual `/chat` endpoint (mocked
  "model calls run_query" → sandboxed execution → mocked "model
  gives final answer" → correct response). That proves the integration
  logic is correct against Groq's real documented format; it does not prove
  Groq's actual model will always call the tool sensibly or terminate the
  loop cleanly on arbitrary real questions — test with a real free key
  before relying on this in a live demo.



- **Day 7** — Rebuilt Simple Mode's text box as an actual chatbot instead of
  a form that routed everything through 5 fixed answer shapes. New priority
  chain per message (`/datasets/{id}/chat`):
  1. **LLM tool-use** (`llm_chat.py`, needs `GROQ_API_KEY` — free, see setup above) — the model gets
     a `run_query` tool to execute a real pandas expression against the
     dataset, so it can answer combinations no fixed shape anticipated
     (multi-condition filters, correlations between named columns, a lookup
     combined with an explanation). Sandboxed via a regex blocklist plus a
     restricted `eval()` scope (only `df`/`pd`/`np` and a small safe-builtins
     whitelist — no imports, file I/O, or introspection).
  2. **Offline query engine** (`query_engine.py`, no key needed) — counts,
     filters, aggregates, and top-N rankings computed directly from the
     data. Filter detection is data-driven: it scans each categorical
     column's actual values for a literal match in the question ("Delhi"),
     rather than needing to know column semantics in advance.
  3. The existing prediction/drivers/compare resolver (`insights.py`).
  4. The profile fallback, honest when nothing else could answer it.

  Frontend rebuilt as a real chat: message history, inline rendering for
  ranking bars/tables/prediction forms, template cards now shown once as
  starter suggestions rather than a separate screen.

  **Bugs found and fixed while building this:**
  - `"total income"` rendered as `1.6985e+07` (scientific notation) with
    wrong grammar ("the sum income"). Added proper comma-formatting and an
    aggregate-word display map (sum → "total", not "the sum").
  - `"how many customers are over 50"` silently ignored the age filter
    entirely (matched 300/300, i.e. no filter applied) because the
    comparison parser required the column's own name to appear near the
    number, and nobody says "customers over 50 age". Added a common-sense
    default: a bare "over/under N" with no column named, where N reads as a
    plausible age, applies to an `age` column if one exists.
  - `llm_chat.py`'s sandbox originally set `__builtins__: {}`, which also
    blocked harmless functions like `len()` that Claude would routinely need
    — switched to a small explicit whitelist (`len`, `str`, `round`, `sum`,
    `min`, `max`, ...), re-verified the injection blocklist still catches
    every tested attack after loosening it.
  - The frontend was inferring classification (Yes/No) vs. regression (a
    number) by checking whether the predicted value was literally `1` or
    `0` — which breaks for any real regression prediction that happens to
    equal 1 (a price of $1, a score of 0). Added an explicit `task` field
    to the chat response so the frontend never has to guess.
  - Several UI strings used `\u2014`-style escapes directly inside raw JSX
    text and a plain JSX attribute value, where they are never interpreted
    as Unicode escapes (only inside real JS string literals) — they would
    have rendered as the literal six characters `\u2014` instead of an em
    dash. Replaced with the actual Unicode characters throughout.
  - **Not independently verified:** the live LLM tool-use round-trip — no
    API key was available in the sandbox this was built in. The sandboxing
    (blocklist + restricted eval scope) and the fallback-on-any-failure path
    are directly tested; the actual conversation with Claude, including
    whether its tool-call loop terminates cleanly on real questions, is not.
    Test with a real key before relying on this in a live demo.



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
     path. If `GROQ_API_KEY` (or `ANTHROPIC_API_KEY`) is set, free text is sent to the model to
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

- **Day 10: the trust layer.** Every answer now comes with the evidence to
  believe or question it.
  - **Why this answer:** per-prediction Monte-Carlo Shapley values
    (`trust.explain_row`). Contributions add up exactly to
    `output - base` (tested). Simple Mode words them as "tenure raised it by
    about 41 points".
  - **Out-of-range guard:** the training data is fingerprinted
    (`automl.build_reference`). Unseen cities, impossible numbers and blank
    fields are flagged high/medium/low trust with plain reasons and
    "did you mean" hints.
  - **What-if simulator:** vary one input and plot how the answer moves
    (`/models/{id}/whatif`).
  - **Fairness audit:** per-group selection rate, accuracy or error on the
    exact held-out rows, with the four-fifths rule. Saved as `FairnessAudit`.
  - **Monitoring:** every prediction logs trust and confidence. Drift is
    flagged when recent inputs leave the training data.
  - **Report:** `/models/{id}/report` gives a print-ready plain or technical
    report with a model card. Print it, then Save as PDF.
  - **Self-healing database:** `ensure_schema()` adds missing columns to an
    old `predictwise.db`, so `no column named cleaned_path` can't happen again.
  - **Bug found by the tests:** a blank form field crashed prediction (empty
    string in a numeric column). Fixed by coercing blanks to missing values.
  - `requirements.txt` now uses `>=` pins because exact old pins fail to build
    on Python 3.13.
  - Tests: `cd backend && python -m pytest tests -q` (7 tests, run in a temp
    directory so your real data is untouched).

- **Day 11: for everyone, not just analysts.**
  - **Try without a file:** one-click sample data (a kirana store's year of
    sales, and a customer list).
  - **Automatic briefing** on opening any file: size, data quality, sales
    trend with forecast band, best sellers, concentration risk.
  - **Ask in plain words:** "what will sales look like next month", "show my
    customer groups", "which rows look unusual" are answered by purpose-built
    engines (`analytics.py`) before any LLM is involved.
  - **Unusual rows judged fairly:** each row is compared with *its own*
    product/group, so a pricey product isn't flagged just for being pricey.
    Tiny gaps (Rs 533 vs Rs 521) are ignored. Regression-tested.
  - **Score a whole file:** upload a list of new customers, get every row
    scored and ranked with trust levels, then download the CSV.
  - **What would help most:** lever suggestions from the what-if engine.
  - **Hindi, Hinglish, voice in and out**, and **Share on WhatsApp** for any
    answer. Answers are translated by the LLM when a key is set.
  - **Download cleaned data** as CSV.
  - Tests: 18 passing (`cd backend && python -m pytest tests -q`).

- **Day 12: AI chat that explains its own failures.** Chat falls back to the
  data overview when the AI call fails; it now says *why* ("Groq rejected the
  API key", "free limit hit", "no internet"). `/health/llm?probe=true` makes one
  real test call and reports the exact reason. If Groq retires a model, the app
  tries the next one automatically. Stray quotes around a pasted key are
  stripped. Tests: 22 passing.

- **Day 13: self-selecting AI model.** Groq answered `model_not_found` for the
  hard-coded model. If a model is refused, the backend now asks Groq which chat
  models the key can use, picks the best one and remembers it. Tests: 23 passing.

- **Day 14: answers in rupees, no clarifying questions.** The AI prompt now
  states that money is in Indian rupees, forbids markdown and forbids asking
  the user a question back. A sanitizer converts any stray `$` to `₹` with
  Indian grouping and strips `**`. The built-in starter questions (e.g. "What
  number should I expect?") go to their dedicated prediction engines instead of
  the free-form LLM. Tests: 25 passing.

- **Day 15: pitch features.**
  - **Hindi fixed:** the AI prompt said "plain English", which fought the Hindi
    setting. It now says "simple everyday words", repeats the language in the
    question, and any answer that still comes back in the wrong script is
    translated (`lang.ensure`).
  - **Weekly playbook:** "What should I do this week?" gives up to six actions
    from the file (stock up before the busiest day, a product that fell 22%,
    never run out of the top sellers, which city to focus on, unusual entries).
    `/datasets/{id}/playbook`.
  - **Show your work:** every AI answer can show the exact calculations behind it.
  - **Private mode:** nothing about the question goes to any AI service.
  - **Why PredictWise?** in-app page comparing it honestly with a general chat
    assistant. `PITCH.md` has a 3-minute demo script and honest answers.
  - Tests: 31 passing.

- **Day 16: advanced tools.**
  - **Stock planner:** "How much should I order?" gives per-product order
    quantities for the next 7 days with a 15% safety buffer (`/datasets/{id}/stock-plan`).
  - **Chart on request:** "Show me sales by city as a chart" draws it.
  - **Customer value groups (RFM):** Best / Regular / New / At risk / Lost, plus a
    win-back call list.
  - **Compare with an older file:** what changed between two uploads.
  - **Share today's summary:** a short digest ready to send on WhatsApp.
  - **Sweet-shop sample dataset**, CSV download on every table, tidier header toolbar.
  - Tests: 39 passing.

- **Day 17: the shop toolkit.** Built for a neighbourhood shopkeeper who keeps bills, not spreadsheets.
  One click each (or just ask), all computed from the shop's own file, no AI service needed:
  - **What earns me money:** profit and margin per product, flags items that sell a lot but earn
    little (with what a 2% price rise is worth), and warns when a supplier's cost price has crept up.
  - **Udhaar tracker:** who owes how much, how old the credit is, who has stopped visiting
    (most likely to be forgotten). Repayment rows reduce the balance.
  - **Stopped / fading products:** money stuck on the shelf, with what to do.
  - **Festival planner:** the next festivals (Diwali, Dhanteras, Holi, Eid, Rakhi and more), what
    sold in the week before them last time, and how much to stock. Dates are approximate and
    the answer says so.
  - **Bought together:** pairs like Bread + Butter with how often, for shelf placement and combos.
  - **Busiest days:** weekday pattern with plain staffing and offer advice.
  - **WhatsApp messages:** udhaar reminders, win-back texts, festival broadcast and the weekly
    supplier order, in English or Hindi (fixed hand-written wording, so Hindi works without a key),
    editable, one tap to open WhatsApp with the customer's number filled in.
  - A new sample (provision store: bills, phone numbers, udhaar, a Diwali rush) and a
    "Shop toolkit" panel that only offers what the uploaded file can support.
  - Tests: 60 passing. Known limit: table column headings stay in English.

- **Day 18: evidence and engineering.** See `ARCHITECTURE.md`.
  - **Self-checking forecasts (`forecast.py`):** four methods replayed week by week over the shop's own
    history, best one chosen by replay error, order sized to "enough stock in 95% of weeks" (say "99%" in
    the question to change it), then tested on the latest six weeks that were kept out of the sizing and
    compared with a flat 15% cushion. It reports the cost too: more stock left over.
  - **Privacy shield (`privacy.py`):** customer names, phone numbers and emails are replaced with codes
    before a question, the chat history or any query result reaches the AI service, and restored in the
    answer. The "How I worked this out" panel says when it was used.
  - **Tested ranges on every prediction (`calibration.py` wired in):** a numeric prediction shows a likely
    range that held for X% of unseen rows; a yes/no prediction shows how often the model was right when it
    was this sure.
  - **Accuracy suite grown to 30 questions;** it exposed and fixed two real bugs (distinct customers/bills
    counted as rows; "top 3 products" ranked single bills instead of totals).
  - **Observability:** one JSON log line per request and Prometheus-format `/metrics` per route template.
  - Tests: 85+ passing.
