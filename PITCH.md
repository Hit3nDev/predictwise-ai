# Pitching PredictWise AI

## The one-line problem
Small shopkeepers already keep sales records, but never use them, because asking
good questions of data is a skill. PredictWise asks the questions for them,
answers in their language, and shows how it got each number.

## 3-minute demo (do it in this order)
1. **Open "Why PredictWise?"** (top left, 20 seconds). Read the title line only.
2. **Click "Kirana store"** under "try without a file." The briefing appears by
   itself: sales trend with forecast, best sellers. *"I asked nothing yet."*
3. **Click "What should I do this week?"** Point at one card, for example
   "Stock up before Saturday." *"Built from their own numbers, no prompt written."*
4. **Ask something custom**, such as "average sales on Sundays for tea" (needs the
   Groq key). Open **"How I worked this out"**. *"Every number is calculated, not recalled."*
5. **Switch to हिन्दी**, ask the same question. Click **Share on WhatsApp**.
6. **Turn on Private mode**, ask again. *"Nothing leaves this computer."*
7. **Open the Customers sample**, ask "will they buy again", fill the form with a
   tenure of 999. The **"Outside the data"** warning appears. *"It knows what it doesn't know."*
8. **Switch to Technical** for evaluators: leaderboard, held-out score, Audit tab
   (fairness, monitoring, report).

## Likely questions, honest answers
**"Why not just use ChatGPT?"** It is better for open writing and brainstorming. Here
the job is narrower: records to decisions. This app (a) starts without being asked,
(b) shows each calculation, (c) trains and tests real models and reports an honest
score, (d) warns on inputs outside the data, (e) checks fairness, (f) can run
with nothing sent to any AI service, (g) is set up for Hindi, ₹ and WhatsApp.

**"Is the AI making up numbers?"** Numbers come from code run on the file. The
"How I worked this out" fold shows the exact calculation. Rupee formatting and
markdown are cleaned in code after the model answers.

**"What happens to my data?"** The file stays on the computer running the backend.
Normal mode sends the question, column names and calculation results to the AI
service. Private mode sends nothing.

**"Does it work without internet or a key?"** Counts, trends, forecasts, customer
groups, unusual rows, the weekly list and predictions all run offline. Only
open-ended questions and Hindi answers need the key.

## What not to claim
- It is not a replacement for an accountant or a business consultant.
- Forecasts are simple trend and seasonality, with a range shown, not a guarantee.
- The fairness check is a screening tool on a small held-out sample, not a legal audit.
- Hindi answers rely on the AI service; offline answers stay in English.

## Day 16 additions to mention
Stock planner, chart on request, customer groups with a win-back list, compare with last month's file, and a shareable daily summary: each runs on the shopkeeper's own file, in rupees, in Hindi or English.

## Day 17: what a general chat assistant cannot do for a shopkeeper
Ask "who owes me money?", "what should I stock for Diwali?", "which item looks busy but earns almost nothing?" on the provision-store sample. Then tap one button and a Hindi WhatsApp reminder opens for each customer with their number filled in. The numbers come from the shop's own bills and can be checked by hand; the customer list never has to leave the computer.

## Day 18: for a technical reviewer
- "How do you know the forecast is any good?" Open the stock answer: it shows each method's replayed error on the shop's own past weeks, and a held-back check against a flat 15% cushion.
- "Is customer data sent to an AI company?" No. Names, phones and emails become codes first; Private mode sends nothing. Show the "How I worked this out" panel.
- "How do you test an assistant?" `python evals.py`: 30 questions checked against independent pandas truth, wired into CI. It caught two real bugs during development.
- "Can I see it run in production?" `docker compose up --build`, then `/metrics` for counters and structured request logs.
