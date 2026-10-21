# Chat accuracy report

**30 of 30 answers matched an independently computed value** (100%).

Each question goes through the real chat endpoint with Private mode on (no AI service), and the answer is compared with a number or name computed separately with pandas from the same file. 'Honest' cases pass only if the app says it cannot answer.

| Group | Passed |
|---|---|
| shop tools | 12 / 12 |
| data questions | 13 / 13 |
| honest | 5 / 5 |

| | Dataset | Question | Result |
|---|---|---|---|
| ✅ | provision_store | Who owes me money? | matches |
| ✅ | provision_store | Who owes me the most? | matches |
| ✅ | provision_store | Which products give me the most profit? | matches |
| ✅ | provision_store | What is my overall profit margin? | matches |
| ✅ | provision_store | Which day is busiest? | matches |
| ✅ | provision_store | What is not selling? | matches |
| ✅ | provision_store | How much should I order? | first row 'Milk 1L', expected 'Milk 1L' |
| ✅ | provision_store | What do customers buy together? | matches |
| ✅ | provision_store | How accurate is the stock plan? | matches |
| ✅ | provision_store | Write a WhatsApp reminder for udhaar | matches |
| ✅ | provision_store | What should I stock for the next festival? | matches |
| ✅ | kirana_sales | What is the total sales? | matches |
| ✅ | kirana_sales | What is the average sales? | matches |
| ✅ | kirana_sales | How many rows are paid by UPI? | matches |
| ✅ | customers | How many customers are from Mumbai? | matches |
| ✅ | customers | How many customers are older than 40? | matches |
| ✅ | customers | What is the average income? | matches |
| ✅ | customers | What is the highest income? | matches |
| ✅ | sweet_shop | What is the total amount? | matches |
| ✅ | sweet_shop | How many orders were above 500? | matches |
| ✅ | provision_store | How many customers are there? | matches |
| ✅ | provision_store | How many bills? | matches |
| ✅ | kirana_sales | Top 3 products by sales | matches |
| ✅ | provision_store | Top 3 items by amount | matches |
| ✅ | provision_store | How much should I order? I want enough for 99% of weeks | matches |
| ✅ | kirana_sales | Which products give me the most profit? | matches |
| ✅ | customers | Who owes me money? | matches |
| ✅ | customers | How much should I order? | matches |
| ✅ | customers | How accurate is the stock plan? | matches |
| ✅ | kirana_sales | What do customers buy together? | matches |
