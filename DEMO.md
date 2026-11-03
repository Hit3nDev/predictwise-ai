# Demo runbook

How to show PredictWise in about fifteen minutes: six on Simple mode, seven on Technical mode, two for
the cloud if asked. Every click below was checked on the sample files the night before.

Two files were built for the demonstration and sit first in the sample list:

- **Sharma General Store: 16 months of bills** (`backend/samples/sharma_store.csv`, 39,621 lines, 13,862
  bills, 84 customers, 20 products). Every tool lights up on it: bills with a time of day, customers with
  phones and areas, cost prices, udhaar, last year's Diwali inside the file and this year's three days
  after it ends. Planted on purpose: Sunday busiest and Tuesday quietest; rush hours at 9 and 19; a wedding
  order and a typo for the anomaly finder; Candles stopped selling; Cold Drink fading for winter; Instant
  Coffee rising; cooking oil's cost up 9%; Bread with Butter and Tea with Sugar on the same bills; twelve
  udhaar households, one of whom has stopped coming; eight regulars gone quiet; four new customers;
  Raja Park buys the most atta.
- **Udhaar khata: who repays on time** (`backend/samples/udhaar_khata.csv`, 606 customers). The credit
  ledger as a table a model can learn from: area, gender, age, months as a customer, visits a month,
  average bill, the udhaar amount, earlier udhaar, times late before, days since the last visit, and whether
  they repaid on time (70% did). Blemishes for the Clean stage: 18 blank ages, 12 blank bills, 6 repeated
  rows, two absurd ₹90,000 amounts. Tilak Nagar repays less often than the other areas, so the fairness
  audit has something real to find; gender has no effect, so that audit comes out clean.

## Before you start

1. Double-click `start.bat` (or run the two terminals). Wait for the browser to open on `localhost:5173`.
2. The left column must say **AI assistant · on (Groq)**. If it says off, the key in `backend/.env` was not
   read: restart the backend terminal.
3. Open the **Sharma General Store** sample once before the audience arrives, so the first briefing is warm
   (the first one takes a few seconds; after that every screen is instant).
4. The free AI quota allows roughly two or three open-ended questions a minute; the app waits a few seconds
   or moves to another model by itself. The dashboard, look-up, What-if and toolkit never touch the quota.

## Simple mode (the shopkeeper's view)

| Step | Click | Say |
|---|---|---|
| 1 | *Sharma General Store* sample | "I asked nothing yet." The briefing: 16 months, ₹64 L, rising, 12 of 20 products bring 80%, 8 unusual rows, data health. |
| 2 | **Dashboard** tab | "Every tile is calculated from the shop's own bills." Point at the forecast, this week's actions (Cold Drink down 52%, stock up before Sunday), busiest days, udhaar ₹2.06 L owed by 12, what earns money (Milk sells a lot but earns little), the next festival (Dhanteras, Diwali: diyas, dry fruits, ghee), next week's order, unusual entries. |
| 3 | Udhaar tile → **Send reminders** | Hindi/English WhatsApp texts with each customer's number filled in. Tap *Send on WhatsApp*. |
| 4 | **Look up** → *Dinesh Sharma* | Spend, rank #5, 217 bills, owes ₹39,213, favourites, a year of months, the reminder to send. Then *Cold Drink 2L* (falling, margin, order) and *Candles* (stopped selling). |
| 5 | **What if** tab | "This is the new part: rehearse a decision before you make it." See the script below. |
| 6 | Chat: `What if I close on Sundays?` | The same engine answers inline with the ranges and a button into the What-if screen. |
| 7 | Chat: `which area buys the most atta?` | AI answer (Raja Park); open **How I worked this out** and the "figures traced" line. "The AI writes the query, my code runs it, every number is checked." Other good ones: `average tea sales on Sundays`, `UPI vs cash last month`, `do I sell more at the start of the month?` |
| 8 | Switch to **हिन्दी**, ask again; open What if | Same answer in Hindi; the What-if screen's labels and summary are in Hindi too. Tap **Share on WhatsApp**. |
| 9 | Toggle **Private mode**, ask something open-ended | "Nothing leaves this computer": it falls back to what it can compute offline and says so. |
| 10 | **Question library** (book icon) | Show the breadth: sales, customers, stock, money, messages, what if, data, AI. |

If time is short, do 1, 2, 5 and 7.

### The What-if script (two minutes)

The screen replays the next 30 days 2,000 times from the shop's own last 12 weeks, a Monday drawn from past
Mondays and so on, so the result is a range, not one number. Diwali falls in the period, so its week is taken
from last year's Diwali week scaled to this year's level (the shaded band on the chart). Every change is
applied to the same 2,000 futures, which is why the *change* column is tight even though the futures spread.

1. As things are: about ₹5.4 L in sales, nine times in ten between ₹4.9 L and ₹6.0 L; ₹67,000 profit.
2. Switch on **Close one day a week**. Tuesday (the quietest) with half the customers coming another day
   costs about ₹20,000 a month. Change the day to Sunday: about ₹46,000. "The day off has a price, and now
   he knows it."
3. Switch on **Change prices**, +5%, customers react moderately: sales barely move (−₹1,400) but profit
   rises about ₹22,000 (+34%). Click *Strongly* to show the assumption matters; it is shown and editable.
4. Switch on **Stop giving udhaar**: sales −₹8,000 but cash in hand +₹19,000. "A trade-off, in numbers."
5. Switch on **Message quiet customers**: +₹8,000 if one in five of the eight come back.
6. Point at *What each change does on its own*, then *Assumptions*. Say: "Rehearsals, not promises. Nothing
   here is guessed by the AI; it is the shop's own weeks, replayed."

## Technical mode (the evaluator's view)

Use the **Udhaar khata** sample (606 rows, trains in seconds). Load it from Simple mode first, then switch to
**Technical** in the header. The rail on the left is the pipeline; stages unlock as you go.

**01 Data.** The file list comes from the `datasets` table in the database (SQLite here, PostgreSQL on AWS).
Say: "Every upload is a row in the database with its stored path, row count and columns."

**02 Clean.** Choose how to fill missing numbers (median), missing text (most common), extreme values (IQR
cap), repeated rows. Click **Clean dataset**. The *What changed* panel is the cleaning log: 18 ages and 12
average bills filled, 6 repeated rows dropped, the two ₹90,000 udhaar amounts capped; every operation is
written to the `cleaning_logs` table. Say: "Preprocessing is logged, not hidden." (Simple mode cleans
automatically but never alters amounts: a ₹15,000 wedding order is flagged as unusual, not clipped.)

**03 Explore.** Click **Continue to exploration**. Shape tiles (rows, columns, missing, repeats),
distributions (histograms per number column), the correlation matrix (cobalt positive, red negative), the
column profile and the first rows. Say: "This is the EDA a data scientist would do by hand; here it is one
click, and it runs on the cleaned file."

**04 Model.** Column to predict: `repaid_on_time`. Click **Train models**. What happens, in order:
1. Identifier columns are dropped automatically (`customer_id`); the model never sees a name or a phone.
2. The task is inferred: two distinct values, so classification.
3. The rows are split 80/20. The 20% is held out and never used for choosing a model.
4. Four algorithms (Logistic Regression, Decision Tree, Random Forest, Gradient Boosting) are each trained
   inside one scikit-learn pipeline, so imputation, scaling and one-hot encoding are fitted on training folds
   only: no leakage.
5. Each is scored by 5-fold cross-validation on the training 80%. The **leaderboard** ranks them by that score
   (the bar behind the name). The winner is marked *selected*.
6. The winner is scored once more on the held-out 20%: the **Selected model** tiles (accuracy, F1, ROC AUC,
   rows trained on, rows held back). Say: "Selection by cross-validation, reporting on data the model never
   saw. Choosing on the test set would leak it into the choice and inflate the number."
7. **What drives the prediction**: permutation importance. Each column is shuffled in turn; the drop in score
   is how much the model relied on it. Expect times late before, visits a month, the udhaar amount and days
   since the last visit to lead.
8. The winning pipeline is saved with joblib (`backend/artifacts/model_<id>.joblib`) and recorded in the
   `experiments` and `ml_models` tables, so predictions can be served later without retraining.

**05 Predict.** "Should I give this customer udhaar?" Fill a row (blanks are imputed): visits 12, average
bill 400, udhaar amount 1,500, late before 0, days since last visit 3 → likely to repay, with the confidence.
Then late before 3 and days since last visit 90 → risky. Show:
- the **trust note**: inputs are checked against the training data's fingerprint. Type udhaar amount
  **99999** and predict again: *Outside the data*, with the reason. Say: "It knows what it doesn't know."
- the **track record**: "when the model was about this sure, it was right X% of the time on held-out rows."
- **Why this prediction**: Monte-Carlo Shapley values, contributions that add up exactly to output minus
  base; cobalt pushes the answer up, red down.
- **What-if**: vary the udhaar amount across its real range and watch the probability curve fall.
Every prediction is logged to the `predictions` table with its trust level.

**06 Audit.**
- **Fairness audit**: group by `area`. The held-out rows are reconstructed with the same split, and
  selection rate and accuracy are compared per group under the four-fifths rule: Tilak Nagar comes out
  lower, and the report says the gap is already in the data. Then group by `gender`: clean. The result
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
- *How does the What-if simulator work? Is it a model?* It is a Monte-Carlo bootstrap, not a fitted model:
  each of 2,000 futures re-draws every day of the next month from the last 12 weeks of the shop's own days,
  matched by weekday, so weekday patterns and ordinary variation are kept; a festival week inside the
  period is taken from last year's same week, scaled to the current level. A decision is applied to every
  future (a closed day's sales removed with a share moved to the neighbouring days; a price change with a
  stated elasticity; credit sales turned into cash with a stated loss), and the baseline and the scenario are
  compared future by future, which is why the change has a far tighter range than the totals. The three
  things a file cannot say (elasticity, offer uplift, how many quiet customers return) are shown as
  assumptions the shopkeeper can change. Code: `backend/simulate.py`, tests in `tests/test_simulate.py`.
- *How is the data stored?* SQLAlchemy models: users, datasets, cleaning_logs, experiments, ml_models,
  predictions, fairness_audits. SQLite locally; PostgreSQL on RDS in the cloud, chosen by one environment
  variable (`DATABASE_URL`).
- *How do you test it?* `python -m pytest tests -q` (unit and API tests, including the simulator, the
  look-up cards and the two demo files) and `python evals.py` (30 questions checked against independent
  pandas calculations), both in CI.
- *What does the AI actually do?* Only the open-ended chat. It is given a `run_query` tool; it writes a pandas
  expression, the backend runs it in a restricted sandbox and hands back the number. Names and phones are
  replaced by codes before anything is sent (privacy shield). A grounding check confirms every figure in the
  answer came out of a calculation.
- *Why would a shopkeeper have a CSV?* Billing apps and POS machines export one; the sample is the shape such
  an export has. The app reads CSV and Excel, and the column roles (date, product, amount, customer, phone,
  payment, cost) are detected from the headings, so no fixed template is needed.

## Cloud (if asked)

Say "connect it to AWS" to me before the session; it takes about ten minutes. Then: the header badge reads
**Live on AWS · S3 · RDS PostgreSQL**; refreshing `/health` shows which EC2 instance answered behind the load
balancer; the S3 console shows uploads, cleaned files and models; CloudWatch shows the dashboard, alarms and
the structured request logs. Tear it down straight after.
