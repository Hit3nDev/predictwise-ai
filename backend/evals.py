"""
Accuracy checks for the chat.

Every case asks a real question through the real /chat endpoint (offline, no AI
service) and compares the answer with a number or name worked out separately
with plain pandas from the same file. A case passes only if the answer states
that independent value. Cases in the "honest" group pass only if the app says
it cannot answer, instead of making something up.

    python evals.py            # runs everything, prints a table, writes EVAL_REPORT.md
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
os.environ.setdefault("PW_TODAY", "2026-10-12")      # festival answers depend on today's date

import pandas as pd

sys.path.insert(0, HERE)
import query_engine  # noqa: E402  (after path setup)

inr = query_engine.inr


def sample(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(SAMPLES, f"{name}.csv"))


def blob(resp: dict) -> str:
    """Everything the user could read in the answer, flattened to text."""
    parts = list(resp.get("narrative", []))
    for b in resp.get("blocks", []) or []:
        parts.append(json.dumps(b, ensure_ascii=False))
    if resp.get("table"):
        parts.append(json.dumps(resp["table"], ensure_ascii=False))
    return " ".join(parts)


def has(resp, *needles):
    t = blob(resp)
    missing = [n for n in needles if n not in t]
    return (not missing, f"missing {missing}" if missing else "")


# ---- independent ground truth ---------------------------------------------------


def _prov():
    df = sample("provision_store")
    df["profit"] = df["amount"] - df["cost_price"] * df["quantity"]
    return df


def truth_udhaar_total():
    df = _prov()
    return df[df["payment"] == "Udhaar"]["amount"].sum()


def truth_udhaar_top():
    df = _prov()
    return df[df["payment"] == "Udhaar"].groupby("customer")["amount"].sum().idxmax()


def truth_top_profit_item():
    return _prov().groupby("item")["profit"].sum().idxmax()


def truth_overall_margin():
    df = _prov()
    return df["profit"].sum() / df["amount"].sum()


def truth_busiest_weekday():
    df = _prov()
    daily = df.groupby("date")["amount"].sum()
    daily.index = pd.to_datetime(daily.index)
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][int(daily.groupby(daily.index.dayofweek).mean().idxmax())]


def truth_stopped_items():
    df = _prov()
    df["d"] = pd.to_datetime(df["date"])
    end = df["d"].max()
    out = set()
    for name, g in df.groupby("item"):
        if g["d"].nunique() >= 8 and (end - g["d"].max()).days >= 14:
            out.add(name)
    return out


def truth_top_stock_item():
    df = _prov()
    df["d"] = pd.to_datetime(df["date"])
    last = df[df["d"] > df["d"].max() - pd.Timedelta(days=28)]
    return last.groupby("item")["quantity"].sum().idxmax()


def truth_pair_conf(a, b):
    df = _prov()
    bills = df.groupby("bill_no")["item"].agg(set)
    with_a = bills[bills.map(lambda s: a in s)]
    return sum(b in s for s in with_a) / len(with_a)


# ---- the cases ------------------------------------------------------------------


def cases():
    cs = []

    def add(cat, ds, q, check):
        cs.append({"category": cat, "dataset": ds, "question": q, "check": check})

    P = "provision_store"
    # money and credit
    add("shop tools", P, "Who owes me money?", _udhaar_total)
    add("shop tools", P, "Who owes me the most?", lambda r: has(r, truth_udhaar_top()))
    add("shop tools", P, "Which products give me the most profit?", lambda r: has(r, truth_top_profit_item()))
    add("shop tools", P, "What is my overall profit margin?", lambda r: has(r, f"about {truth_overall_margin():.0%} of every rupee"))
    add("shop tools", P, "Which day is busiest?", lambda r: has(r, f"{truth_busiest_weekday()} is your busiest day"))
    add("shop tools", P, "What is not selling?", lambda r: has(r, *sorted(truth_stopped_items())))
    add("shop tools", P, "How much should I order?", lambda r: _first_row_is(r, "Product", truth_top_stock_item()))
    add("shop tools", P, "What do customers buy together?",
        lambda r: has(r, f"{truth_pair_conf('Bread', 'Butter 100g'):.0%} of the bills with Bread also have Butter 100g"))
    add("shop tools", P, "How accurate is the stock plan?", lambda r: has(r, "I tested the stock plan on your own history"))
    add("shop tools", P, "Write a WhatsApp reminder for udhaar", lambda r: _message_for_top_debtor(r))
    add("shop tools", P, "What should I stock for the next festival?", lambda r: has(r, "Dussehra is in 8 days"))

    # plain questions answered by the offline engine
    add("data questions", "kirana_sales", "What is the total sales?",
        lambda r: has(r, inr(sample("kirana_sales")["sales"].sum())))
    add("data questions", "kirana_sales", "What is the average sales?",
        lambda r: has(r, inr(round(sample("kirana_sales")["sales"].mean(), 2))))
    add("data questions", "kirana_sales", "How many rows are paid by UPI?",
        lambda r: has(r, f"{int((sample('kirana_sales')['payment_mode'] == 'UPI').sum()):,}".replace(",", "")))
    add("data questions", "customers", "How many customers are from Mumbai?",
        lambda r: has(r, f"{int((sample('customers')['city'] == 'Mumbai').sum())} out of 300"))
    add("data questions", "customers", "How many customers are older than 40?",
        lambda r: has(r, f"{int((sample('customers')['age'] > 40).sum())} out of 300"))
    add("data questions", "customers", "What is the average income?",
        lambda r: has(r, inr(round(sample("customers")["income"].mean(), 2))))
    add("data questions", "customers", "What is the highest income?",
        lambda r: has(r, inr(float(sample("customers")["income"].max()))))
    add("data questions", "sweet_shop", "What is the total amount?",
        lambda r: has(r, inr(sample("sweet_shop")["amount"].sum())))
    add("data questions", "sweet_shop", "How many orders were above 500?",
        lambda r: has(r, f"{int((sample('sweet_shop')['amount'] > 500).sum())} out of"))

    # counting people or bills, not rows; ranking by totals, not single rows
    Pp = sample("provision_store")
    add("data questions", P, "How many customers are there?", lambda r: has(r, f"{Pp['customer'].nunique()} different customers"))
    add("data questions", P, "How many bills?", lambda r: has(r, f"{Pp['bill_no'].nunique()} different bills"))
    for ds, q, grp, col in (("kirana_sales", "Top 3 products by sales", "product", "sales"), (P, "Top 3 items by amount", "item", "amount")):
        tot = sample(ds).groupby(grp)[col].sum().sort_values(ascending=False)
        add("data questions", ds, q, lambda r, tot=tot: has(r, f"{tot.index[0]} {inr(float(tot.iloc[0]))}"))
    add("shop tools", P, "How much should I order? I want enough for 99% of weeks",
        lambda r: has(r, "99% of weeks", "Honest check"))

    # the app must say so when the file cannot support the question
    add("honest", "kirana_sales", "Which products give me the most profit?", lambda r: has(r, "cost price"))
    add("honest", "customers", "Who owes me money?", lambda r: has(r, "customer column"))
    add("honest", "customers", "How much should I order?", lambda r: has(r, "date column"))
    add("honest", "customers", "How accurate is the stock plan?", lambda r: has(r, "product column"))
    add("honest", "kirana_sales", "What do customers buy together?", lambda r: has(r, "bill or order number"))
    return cs


def _udhaar_total(r):
    t = truth_udhaar_total()
    ok = any(s in blob(r) for s in (query_engine.inr(t), _lakh(t)))
    return ok, "" if ok else f"expected total near {t:,.0f}"


def _lakh(v):
    import analytics
    return analytics.money(v)


def _first_row_is(r, col, expected):
    for b in r.get("blocks", []):
        if b.get("type") == "table" and b.get("rows"):
            got = b["rows"][0].get(col)
            return got == expected, f"first row {got!r}, expected {expected!r}"
    return False, "no table"


def _message_for_top_debtor(r):
    import re
    df = _prov()
    top = truth_udhaar_top()
    phone = re.sub(r"\D", "", df[df["customer"] == top]["phone"].iloc[0])
    msgs = [m for b in r.get("blocks", []) if b.get("type") == "messages" for m in b["messages"]]
    hit = [m for m in msgs if m["to"] == top]
    if not hit:
        return False, f"no message for {top}"
    ok = phone in hit[0]["link"] and "₹" in hit[0]["text"]
    return ok, "" if ok else "link or amount missing"


# ---- runner ---------------------------------------------------------------------


def run(chdir: bool = True) -> list[dict]:
    if chdir:                      # a throwaway folder, so the real database is never touched
        os.chdir(tempfile.mkdtemp(prefix="pw-eval-"))
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    ids = {}
    results = []
    for c in cases():
        if c["dataset"] not in ids:
            ids[c["dataset"]] = client.post(f"/samples/{c['dataset']}/load").json()["id"]
        resp = client.post(f"/datasets/{ids[c['dataset']]}/chat", json={"message": c["question"], "private": True}).json()
        try:
            ok, why = c["check"](resp)
        except Exception as exc:     # a crash in a check is a failure, not a pass
            ok, why = False, f"check crashed: {exc}"
        results.append({**{k: c[k] for k in ("category", "dataset", "question")}, "passed": bool(ok), "why": why,
                        "answer": " ".join(resp.get("narrative", []))[:140]})
    return results


def report(results: list[dict]) -> str:
    total = len(results)
    ok = sum(r["passed"] for r in results)
    lines = ["# Chat accuracy report", "",
             f"**{ok} of {total} answers matched an independently computed value** ({ok / total:.0%}).", "",
             "Each question goes through the real chat endpoint with Private mode on (no AI service), and the answer is "
             "compared with a number or name computed separately with pandas from the same file. "
             "'Honest' cases pass only if the app says it cannot answer.", "",
             "| Group | Passed |", "|---|---|"]
    for cat in dict.fromkeys(r["category"] for r in results):
        part = [r for r in results if r["category"] == cat]
        lines.append(f"| {cat} | {sum(r['passed'] for r in part)} / {len(part)} |")
    lines += ["", "| | Dataset | Question | Result |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {'✅' if r['passed'] else '❌'} | {r['dataset']} | {r['question']} | {r['why'] or 'matches'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    res = run()
    md = report(res)
    print(md)
    with open(os.path.join(HERE, "..", "EVAL_REPORT.md"), "w", encoding="utf-8") as f:
        f.write(md)
    sys.exit(0 if all(r["passed"] for r in res) else 1)
