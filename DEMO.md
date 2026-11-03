# Demo runbook

How to show PredictWise in about fifteen minutes: five on Simple mode, eight on Technical mode, two for
the cloud if asked. Every click below was checked on the sample files the night before.

## Before you start

1. Double-click `start.bat` (or run the two terminals). Wait for the browser to open on `localhost:5173`.
2. The left column must say **AI assistant · on (Groq)**. If it says off, the key in `backend/.env` was not
   read: restart the backend terminal.
3. Open the **Provision store** sample once before the audience arrives, so the first briefing is warm.
4. The free AI quota allows roughly two or three open-ended questions a minute; the app waits a few seconds
   or moves to another model by itself. Toolkit buttons, the dashboard and the look-up never touch the quota.

## Simple mode (the shopkeeper's view)

| Step | Click | Say |
|---|---|---|
| 1 | *Provision store* sample | "I asked nothing yet." The briefing appears: period, total, trend with forecast, best sellers, data health. |
| 2 | **Dashboard** tab | "Every tile is calculated from the shop's own bills." Point at udhaar, busiest day, next week's order, the next festival. |
| 3 | A tile's **Ask →** (e.g. Udhaar) | The same engine answers in the chat with a table and a CSV download. |
| 4 | Toolkit **Reminder message for udhaar** | Hindi/English WhatsApp texts with the customer's number filled in. Tap *Send on WhatsApp*. |
| 5 | **Look up** tab → *Geeta Chauhan* | One customer at a glance: spend, rank, last visit, udhaar, favourites, a year of months, the message to send. Then *Bread*: margin, companions, next week's order. |
| 6 | Type `which area buys the most atta?` | AI answer; open **How I worked this out** and the "figures traced" line. "The AI writes the query, my code runs it, every number is checked." |
| 7 | Switch to **हिन्दी**, ask again | Same answer in Hindi. Tap **Share on WhatsApp**. |
| 8 | Toggle **Private mode**, ask something open-ended | "Nothing leaves this computer": it falls back to what it can compute offline and says so. |
| 9 | **Question library** (book icon) | Show the breadth: sales, customers, stock, money, messages, data. |

If time is short, do 1, 2, 5 and 6.

## Technical mode (the evaluator's view)

Use the **Customers** sample (300 rows, trains in seconds). Load it from Simple mode first, then switch to
**Technical** in the header. The rail on the left is the pipeline; stages unlock as you go.

**01 Data.** The file list comes from the `datasets` table in the database (SQLite here, PostgreSQL on AWS).
Say: "Every upload is a row in the database with its stored path, row count and columns."

**02 Clean.** Choose how to fill missing numbers (median), missing text (most common), extreme values (IQR
cap), repeated rows. Click **Clean dataset**. The *What changed* panel is the cleaning log: every operation
is written to the `cleaning_logs` table. Say: "Preprocessing is logged, not hidden."

**03 Explore.** Click **Continue to exploration**. Shape tiles (rows, columns, missing, repeats),
distributions (histograms per number column), the correlation matrix (cobalt positive, red negative), the
column profile and the first rows. Say: "This is the EDA a data scientist would do by hand; here it is one
click, and it runs on the cleaned file."

**04 Model.** Column to predict: `purchased`. Click **Train models**. What happens, in order:
1. Identifier columns are dropped automatically (customer_id).
2. The task is inferred: two distinct values, so classification.
3. The rows are split 80/20. The 20% is held out and never used for choosing a model.
4. Four algorithms (Logistic Regression, Decision Tree, Random Forest, Gradient Boosting) are each trained
   inside one scikit-learn pipeline, so imputation and scaling are fitted on training folds only: no leakage.
5. Each is scored by 5-fold cross-validation on the training 80%. The **leaderboard** ranks them by that score
   (the bar behind the name). The winner is marked *selected*.
6. The winner is scored once more on the held-out 20%: the **Selected model** tiles (accuracy, F1, ROC AUC,
   rows trained on, rows held back). Say: "Selection by cross-validation, reporting on data the model never
   saw. Choosing on the test set would leak it into the choice and inflate the number."
7. **What drives the prediction**: permutation importance. Each column is shuffled in turn; the drop in score
   is how much the model relied on it. Here tenure and income lead.
8. The winning pipeline is saved with joblib (`backend/artifacts/model_<id>.joblib`) and recorded in the
   `experiments` and `ml_models` tables, so predictions can be served later without retraining.

**05 Predict.** Fill a row (or leave fields blank: blanks are imputed) and click **Predict**. Show:
- the prediction and its confidence (class probability);
- the **trust note**: inputs are checked against the training data's fingerprint. Type tenure **999** and
  predict again: *Outside the data*, with the reason. Say: "It knows what it doesn't know."
- the **track record**: "when the model was about this sure, it was right X% of the time on held-out rows."
- **Why this prediction**: Monte-Carlo Shapley values, contributions that add up exactly to output minus
  base; cobalt pushes the answer up, red down.
- **What-if**: vary one input across its real range and watch the probability curve move.
Every prediction is logged to the `predictions` table with its trust level.

**06 Audit.**
- **Fairness audit**: pick a group column (age in bands, city). The held-out rows are reconstructed with the
  same split, and selection rate and accuracy are compared per group under the four-fifths rule. The result
  is saved to `fairness_audits`. Say: "A screening tool, not a legal audit, and it says when a gap already
  exists in the data."
- **Live monitoring**: the prediction log, average confidence, how many predictions used unfamiliar inputs,
  and a drift status (healthy / watch / drifting).
- **Reports**: a print-ready plain-language report and a technical report with a model card. Print → Save as PDF.

Likely questions and short answers:
- *Why cross-validation and a held-out set?* Cross-validation picks the model fairly; the held-out set gives
  an unbiased estimate of real-world accuracy. Using one set for both would be optimistic.
- *Why permutation importance and Shapley, not just coefficients?* They are model-agnostic: the same
  explanation works for a tree ensemble and a linear model.
- *How is the data stored?* SQLAlchemy models: users, datasets, cleaning_logs, experiments, ml_models,
  predictions, fairness_audits. SQLite locally; PostgreSQL on RDS in the cloud, chosen by one environment
  variable (`DATABASE_URL`).
- *How do you test it?* `python -m pytest tests -q` (104 tests) and `python evals.py` (30 questions checked
  against independent pandas calculations), both in CI.
- *What does the AI actually do?* Only the open-ended chat. It is given a `run_query` tool; it writes a pandas
  expression, the backend runs it in a restricted sandbox and hands back the number. Names and phones are
  replaced by codes before anything is sent (privacy shield). A grounding check confirms every figure in the
  answer came out of a calculation.

## Cloud (if asked)

Say "connect it to AWS" to me before the session; it takes about ten minutes. Then: the header badge reads
**Live on AWS · S3 · RDS PostgreSQL**; refreshing `/health` shows which EC2 instance answered behind the load
balancer; the S3 console shows uploads, cleaned files and models; CloudWatch shows the dashboard, alarms and
the structured request logs. Tear it down straight after.
