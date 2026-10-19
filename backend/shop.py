"""
The shop toolkit: practical answers for a neighbourhood shopkeeper, worked out
from the shop's own bills. Nothing here needs an AI service, and every number
can be checked by hand.

  profit         which products really earn money, and which only look busy
  udhaar         who owes how much on credit, and how old each balance is
  slow_movers    products that stopped selling or are fading (money stuck on the shelf)
  festivals      what is coming up, and what sold last time
  bundles        what customers buy together
  peak           busiest and quietest days
  messages       ready-to-send WhatsApp texts in English or Hindi
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date as _date
from itertools import combinations
from urllib.parse import quote

import numpy as np
import pandas as pd

import advanced
import analytics
from analytics import money, pretty

QTY_WORDS = ("quantity", "qty", "units", "pieces")
AMOUNT_WORDS = ("amount", "total", "sales", "revenue", "value")
COST_WORDS = ("cost", "purchase", "buying", "wholesale")
PRICE_WORDS = ("selling", "price", "rate", "mrp")
PHONE_WORDS = ("phone", "mobile", "contact", "whatsapp")
PAY_WORDS = ("payment", "pay_mode", "paid", "mode", "tender")
BILL_WORDS = ("bill", "invoice", "receipt", "order", "txn", "transaction")

CREDIT_RE = re.compile(r"udhaar|udhar|credit|\bdue\b|pending|baki|unpaid|khata|later", re.I)
REPAID_RE = re.compile(r"repaid|settled|received|recovered|paid back|clear", re.I)


# ---------------------------------------------------------------------------
# Finding the columns
# ---------------------------------------------------------------------------


def _num(df, words, exclude=()):
    for c in df.columns:
        if c in exclude or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if any(w in c.lower() for w in words):
            return c
    return None


def _txt(df, words, exclude=()):
    for c in df.columns:
        if c in exclude or pd.api.types.is_numeric_dtype(df[c]) and "phone" not in c.lower() and "mobile" not in c.lower():
            continue
        if any(w in c.lower() for w in words):
            return c
    return None


def roles(df: pd.DataFrame) -> dict:
    date = analytics.detect_date_col(df)
    ex = (date,) if date else ()
    item = advanced._product_col(df, exclude=ex)
    cost = _num(df, COST_WORDS, ex)
    qty = _num(df, QTY_WORDS, ex)
    price = _num(df, PRICE_WORDS, ex + ((cost,) if cost else ()))
    amount = _num(df, AMOUNT_WORDS, ex + tuple(x for x in (cost, price) if x))
    cust = advanced._customer_col(df, exclude=ex)
    phone = _txt(df, PHONE_WORDS)
    if cust and phone == cust:
        cust = None
    pay = _txt(df, PAY_WORDS, ex)
    bill = _txt(df, BILL_WORDS, ex + tuple(x for x in (item, cust) if x))
    return dict(date=date, item=item, cost=cost, qty=qty, price=price, amount=amount,
                customer=cust, phone=phone, payment=pay, bill=bill)


def _revenue(df, r) -> pd.Series | None:
    if r["amount"]:
        return df[r["amount"]].astype(float)
    if r["price"]:
        q = df[r["qty"]].astype(float) if r["qty"] else 1.0
        return df[r["price"]].astype(float) * q
    return None


def _dates(df, r) -> pd.Series | None:
    return analytics.to_dates(df, r["date"]) if r["date"] else None


# ---------------------------------------------------------------------------
# Profit and margin
# ---------------------------------------------------------------------------


def profit(df: pd.DataFrame) -> dict:
    r = roles(df)
    if not (r["cost"] and r["item"]) or _revenue(df, r) is None:
        return {"available": False, "reason": "To work out profit I need a product column, what each item sells for, and what it cost you (a cost price column)."}

    rev = _revenue(df, r)
    qty = df[r["qty"]].astype(float) if r["qty"] else pd.Series(1.0, index=df.index)
    cost = df[r["cost"]].astype(float) * qty
    t = pd.DataFrame({"item": df[r["item"]], "rev": rev, "cost": cost, "qty": qty}).dropna()
    if len(t) < 20:
        return {"available": False, "reason": "I need a few more rows to work out profit."}
    t["profit"] = t["rev"] - t["cost"]
    g = t.groupby("item").agg(rev=("rev", "sum"), profit=("profit", "sum"), qty=("qty", "sum"))
    g = g[g["rev"] > 0]
    g["margin"] = g["profit"] / g["rev"]
    total_rev, total_profit = float(g["rev"].sum()), float(g["profit"].sum())
    overall = total_profit / total_rev if total_rev else 0.0

    top_cut = g["profit"].quantile(0.75)
    vol_cut = g["rev"].quantile(0.6)

    def verdict(row):
        if row["margin"] < 0:
            return "Losing money on every sale"
        if row["margin"] < 0.05:
            return "Barely earns anything"
        if row["rev"] >= vol_cut and row["margin"] < overall - 0.05:
            return "Sells a lot but earns little"
        if row["profit"] >= top_cut:
            return "Your money maker"
        return ""

    g["verdict"] = g.apply(verdict, axis=1)
    g = g.sort_values("profit", ascending=False)
    rows = [{
        "Product": str(i),
        "Sales": money(row["rev"]),
        "Profit": money(row["profit"]),
        "Margin": f"{row['margin']:.0%}",
        "Verdict": row["verdict"],
    } for i, row in g.head(20).iterrows()]

    best = g.index[0]
    narrative = [
        f"Overall you keep about {overall:.0%} of every rupee you sell, {money(total_profit)} profit on {money(total_rev)} sales.",
        f"{best} earns you the most: {money(g.loc[best, 'profit'])} ({g.loc[best, 'profit'] / total_profit:.0%} of all profit).",
    ]
    busy_low = g[g["verdict"] == "Sells a lot but earns little"]
    if len(busy_low):
        n = busy_low["rev"].idxmax()
        gain = float(busy_low.loc[n, "rev"]) * 0.02
        narrative.append(
            f"{n} is a big seller ({money(busy_low.loc[n, 'rev'])}) but keeps only {busy_low.loc[n, 'margin']:.0%}. "
            f"A 2% price rise would add about {money(gain)} over the period this file covers."
        )
    losing = g[g["margin"] < 0.02]
    if len(losing):
        narrative.append(f"Check the price of: {', '.join(map(str, losing.index[:4]))}. They earn almost nothing.")

    out = {"available": True, "columns": ["Product", "Sales", "Profit", "Margin", "Verdict"], "rows": rows,
           "narrative": narrative, "watch": price_watch(df, r)}
    return out


def price_watch(df: pd.DataFrame, r: dict | None = None) -> list[dict]:
    """Products whose cost price crept up recently, squeezing the margin."""
    r = r or roles(df)
    if not (r["date"] and r["cost"] and r["item"] and r["price"]):
        return []
    d = _dates(df, r)
    data = pd.DataFrame({"item": df[r["item"]], "cost": df[r["cost"]].astype(float),
                         "price": df[r["price"]].astype(float), "d": d}).dropna()
    if data.empty:
        return []
    end = data["d"].max()
    recent = data[data["d"] > end - pd.Timedelta(days=60)]
    earlier = data[(data["d"] <= end - pd.Timedelta(days=60)) & (data["d"] > end - pd.Timedelta(days=180))]
    out = []
    for name, rc in recent.groupby("item"):
        ec = earlier[earlier["item"] == name]
        if len(rc) < 5 or len(ec) < 5:
            continue
        c_new, c_old = float(rc["cost"].mean()), float(ec["cost"].mean())
        p_new = float(rc["price"].mean())
        if c_old > 0 and (c_new - c_old) / c_old >= 0.04 and p_new > 0:
            m_old = (float(ec["price"].mean()) - c_old) / float(ec["price"].mean())
            m_new = (p_new - c_new) / p_new
            out.append({
                "Product": str(name),
                "Cost before": f"₹{c_old:.1f}",
                "Cost now": f"₹{c_new:.1f}",
                "Rise": f"+{(c_new - c_old) / c_old:.0%}",
                "Margin before": f"{m_old:.0%}",
                "Margin now": f"{m_new:.0%}",
            })
    return sorted(out, key=lambda x: -float(x["Rise"].strip("+%")))[:8]


# ---------------------------------------------------------------------------
# Udhaar (credit)
# ---------------------------------------------------------------------------


def udhaar(df: pd.DataFrame) -> dict:
    r = roles(df)
    if not (r["payment"] and r["customer"]) or _revenue(df, r) is None:
        return {"available": False, "reason": "To track udhaar I need a customer column, a payment column (with a value like Udhaar or Credit) and an amount column."}

    pay = df[r["payment"]].astype(str)
    is_credit = pay.str.contains(CREDIT_RE) & ~pay.str.contains("card", case=False)
    is_repaid = pay.str.contains(REPAID_RE) & ~is_credit
    if not is_credit.any():
        return {"available": False, "reason": "I could not find any credit (udhaar) sales in the payment column."}

    rev = _revenue(df, r)
    d = _dates(df, r)
    t = pd.DataFrame({"c": df[r["customer"]], "amt": rev, "credit": is_credit, "repaid": is_repaid, "d": d})
    if r["phone"]:
        col = df[r["phone"]]
        t["phone"] = col.where(col.notna(), "").astype(str).replace("nan", "")
    t = t.dropna(subset=["c", "amt"])
    ref = t["d"].max() if t["d"].notna().any() else None

    # a bill can have many lines, so work per customer on totals
    given = t[t["credit"]].groupby("c")["amt"].sum()
    paid = t[t["repaid"]].groupby("c")["amt"].sum()
    owed = (given - paid.reindex(given.index).fillna(0)).clip(lower=0)
    owed = owed[owed > 0].sort_values(ascending=False)
    if owed.empty:
        return {"available": True, "columns": [], "rows": [], "total": 0.0, "narrative": ["Nobody owes you anything: every credit sale has been repaid."]}

    first_credit = t[t["credit"]].groupby("c")["d"].min()
    last_visit = t.groupby("c")["d"].max()
    phones = t[t["phone"] != ""].groupby("c")["phone"].first() if "phone" in t else pd.Series(dtype=str)

    rows, raw = [], []
    for name, amt in owed.items():
        age = int((ref - first_credit[name]).days) if ref is not None and pd.notna(first_credit.get(name)) else None
        away = int((ref - last_visit[name]).days) if ref is not None and pd.notna(last_visit.get(name)) else None
        if away is not None and away > 60:
            action = "Chase: has stopped visiting"
        elif age is not None and age > 30:
            action = "Remind this week"
        else:
            action = "Recent, fine for now"
        row = {"Customer": str(name), "Owes": money(float(amt)),
               "Oldest credit": f"{age} days ago" if age is not None else "–",
               "Last visit": f"{away} days ago" if away is not None else "–",
               "Action": action}
        if len(phones):
            row["Phone"] = phones.get(name, "")
        rows.append(row)
        raw.append({"customer": str(name), "amount": float(amt), "age": age, "away": away, "phone": phones.get(name, "") if len(phones) else ""})

    total = float(owed.sum())
    total_sales = float(t["amt"].sum())
    narrative = [f"{len(owed)} customers owe you {money(total)} in total. About {given.sum() / total_sales:.0%} of what you sold went on credit."]
    big = owed.head(3)
    narrative.append("Biggest balances: " + ", ".join(f"{n} {money(float(a))}" for n, a in big.items()) + ".")
    stopped = [x for x in raw if x["away"] is not None and x["away"] > 60]
    if stopped:
        narrative.append(f"{len(stopped)} of them have not visited for over 60 days and owe {money(sum(x['amount'] for x in stopped))}. These are the ones most likely to be forgotten, so ask them first.")
    if not is_repaid.any():
        narrative.append("This file does not record repayments, so treat these amounts as the most they could owe. Add a row with payment 'Repaid' whenever someone pays back.")
    cols = list(rows[0].keys())
    return {"available": True, "columns": cols, "rows": rows[:25], "total": total, "raw": raw, "narrative": narrative}


# ---------------------------------------------------------------------------
# Slow and stopped products
# ---------------------------------------------------------------------------


def slow_movers(df: pd.DataFrame) -> dict:
    r = roles(df)
    measure = r["qty"] or r["amount"]
    if not (r["date"] and r["item"] and measure):
        return {"available": False, "reason": "I need a date column, a product column and a quantity or amount column to spot slow products."}
    d = _dates(df, r)
    data = pd.DataFrame({"item": df[r["item"]], "m": df[measure].astype(float), "d": d.dt.normalize()}).dropna()
    if data.empty or (data["d"].max() - data["d"].min()).days < 60:
        return {"available": False, "reason": "I need at least two months of sales to tell what has slowed down."}
    end = data["d"].max()
    rows, stopped, fading = [], [], []
    for name, g in data.groupby("item"):
        days_sold = g["d"].nunique()
        last = int((end - g["d"].max()).days)
        l30 = float(g[g["d"] > end - pd.Timedelta(days=30)]["m"].sum())
        p30 = float(g[(g["d"] <= end - pd.Timedelta(days=30)) & (g["d"] > end - pd.Timedelta(days=60))]["m"].sum())
        if days_sold >= 8 and last >= 14:
            v = "Stopped selling. Do not reorder; sell off what is left."
            stopped.append(str(name))
        elif p30 >= 6 and l30 <= p30 * 0.5:
            v = "Fading. Halve your next order."
            fading.append(str(name))
        else:
            continue
        rows.append({"Product": str(name), "Last sold": f"{last} days ago" if last else "today",
                     "Last 30 days": f"{l30:,.0f}", "Month before": f"{p30:,.0f}", "What to do": v})
    if not rows:
        return {"available": True, "columns": [], "rows": [], "narrative": ["Nothing has stopped selling and nothing is fading fast. Your range looks healthy."]}
    narrative = []
    if stopped:
        narrative.append(f"Stopped selling: {', '.join(stopped[:5])}. Money tied up in these should not be topped up.")
    if fading:
        narrative.append(f"Fading fast: {', '.join(fading[:5])}. Order about half as much next time, or put them in a small offer.")
    return {"available": True, "columns": ["Product", "Last sold", "Last 30 days", "Month before", "What to do"],
            "rows": rows, "narrative": narrative}


# ---------------------------------------------------------------------------
# Festivals
# ---------------------------------------------------------------------------

# Approximate dates; festival dates move each year with the calendar, so the
# answer always tells the shopkeeper to confirm locally.
FESTIVALS = [
    ("Makar Sankranti", "2025-01-14"), ("Holi", "2025-03-14"), ("Eid al-Fitr", "2025-03-31"),
    ("Raksha Bandhan", "2025-08-09"), ("Janmashtami", "2025-08-16"), ("Ganesh Chaturthi", "2025-08-27"),
    ("Navratri", "2025-09-22"), ("Dussehra", "2025-10-02"), ("Karva Chauth", "2025-10-10"),
    ("Dhanteras", "2025-10-18"), ("Diwali", "2025-10-20"), ("Bhai Dooj", "2025-10-23"), ("Christmas", "2025-12-25"),
    ("Lohri", "2026-01-13"), ("Makar Sankranti", "2026-01-14"), ("Holi", "2026-03-04"), ("Eid al-Fitr", "2026-03-21"),
    ("Raksha Bandhan", "2026-08-28"), ("Janmashtami", "2026-09-04"), ("Ganesh Chaturthi", "2026-09-14"),
    ("Navratri", "2026-10-11"), ("Dussehra", "2026-10-20"), ("Karva Chauth", "2026-10-29"),
    ("Dhanteras", "2026-11-06"), ("Diwali", "2026-11-08"), ("Bhai Dooj", "2026-11-11"), ("Christmas", "2026-12-25"),
    ("Lohri", "2027-01-13"), ("Makar Sankranti", "2027-01-15"), ("Eid al-Fitr", "2027-03-10"), ("Holi", "2027-03-22"),
    ("Raksha Bandhan", "2027-08-17"), ("Janmashtami", "2027-08-25"), ("Ganesh Chaturthi", "2027-09-04"),
    ("Navratri", "2027-09-30"), ("Dussehra", "2027-10-09"), ("Karva Chauth", "2027-10-18"),
    ("Diwali", "2027-10-29"), ("Bhai Dooj", "2027-10-31"), ("Christmas", "2027-12-25"),
]


def _reference_today(data_end: pd.Timestamp, today: _date | None) -> pd.Timestamp:
    real = pd.Timestamp(today or _date.today())
    return real if (real - data_end).days <= 60 else data_end


def festivals(df: pd.DataFrame, today: _date | None = None, horizon_days: int = 75) -> dict:
    r = roles(df)
    measure = r["amount"] or r["qty"] or (r["price"] if r["price"] else None)
    if not r["date"] or not measure:
        return {"available": False, "reason": "I need a date column and an amount column to look at festival seasons."}
    d = _dates(df, r)
    rev = _revenue(df, r)
    series = rev if rev is not None else df[measure].astype(float)
    data = pd.DataFrame({"d": d.dt.normalize(), "rev": series, "item": df[r["item"]] if r["item"] else "all",
                         "qty": df[r["qty"]].astype(float) if r["qty"] else 1.0}).dropna(subset=["d", "rev"])
    if data.empty:
        return {"available": False, "reason": "I could not read the dates in this file."}
    start, end = data["d"].min(), data["d"].max()
    now = _reference_today(end, today)
    daily = data.groupby("d")["rev"].sum()

    upcoming = [(n, pd.Timestamp(x)) for n, x in FESTIVALS if 0 <= (pd.Timestamp(x) - now).days <= horizon_days]
    if not upcoming:
        return {"available": True, "now": now, "upcoming": [], "blocks": [],
                "narrative": [f"No major festival in the next {horizon_days} days. I will show the next ones when they are close."]}

    narrative, tables, picks = [], [], []
    for name, when in upcoming[:3]:
        days = (when - now).days
        line = f"{name} is in {days} day{'s' if days != 1 else ''} ({when:%d %b})."
        past = [pd.Timestamp(x) for n, x in FESTIVALS if n == name and pd.Timestamp(x) < when - pd.Timedelta(days=200)]
        used = None
        for p in sorted(past, reverse=True):
            w0, w1 = p - pd.Timedelta(days=6), p
            b0 = w0 - pd.Timedelta(days=45)
            if b0 >= start and w1 <= end and (daily.index >= b0).any():
                used = (p, w0, w1, b0)
                break
        if not used:
            narrative.append(line + " Your file does not cover this festival from last time, so I cannot say what sold. Stock up about a week before.")
            continue
        p, w0, w1, b0 = used
        win = data[(data["d"] >= w0) & (data["d"] <= w1)]
        base = data[(data["d"] >= b0) & (data["d"] < w0)]
        win_daily = float(win.groupby("d")["rev"].sum().mean())
        base_daily = float(base.groupby("d")["rev"].sum().mean()) if len(base) else 0.0
        if base_daily <= 0:
            narrative.append(line)
            continue
        up = win_daily / base_daily
        if up >= 1.15:
            line += f" Last time ({p:%b %Y}), sales in the week before were {up:.1f}x a normal day."
        else:
            line += f" Last time ({p:%b %Y}), total sales did not rise much, but some products did."
        narrative.append(line)
        if r["item"]:
            wk = win.groupby("item")["qty"].sum()
            bk = base.groupby("item")["qty"].sum() / max((w0 - b0).days, 1) * 7
            rows = []
            for it, units in wk.sort_values(ascending=False).items():
                normal = float(bk.get(it, 0))
                if units < 3:
                    continue
                ratio = units / normal if normal > 0 else np.inf
                if ratio >= 1.5 or normal == 0:
                    rows.append((it, normal, float(units), ratio))
            rows.sort(key=lambda x: -(x[2] - x[1]))
            if rows:
                shown = rows[:8]
                tables.append({
                    "type": "table", "caption": f"Stock for {name}",
                    "columns": ["Product", "Normal week", f"Week before {name} last time", "Stock about"],
                    "rows": [{"Product": str(it), "Normal week": f"{n:,.0f}", f"Week before {name} last time": f"{u:,.0f}",
                              "Stock about": f"{np.ceil(u * 1.1):,.0f}"} for it, n, u, _ in shown],
                    "csv": f"{name.lower().replace(' ', '_')}_stock.csv",
                })
                picks.append((name, [str(x[0]) for x in shown[:4]]))
                narrative.append("Sold far more then: " + ", ".join(f"{x[0]} ({x[3]:.0f}x)" if np.isfinite(x[3]) else f"{x[0]} (new)" for x in shown[:4]) + ".")
    narrative.append("Festival dates are approximate and shift each year, so check the date locally.")
    return {"available": True, "now": now, "upcoming": [(n, w.strftime("%Y-%m-%d")) for n, w in upcoming],
            "blocks": tables, "narrative": narrative, "picks": picks}


# ---------------------------------------------------------------------------
# Bought together
# ---------------------------------------------------------------------------


def bundles(df: pd.DataFrame) -> dict:
    r = roles(df)
    if not (r["bill"] and r["item"]):
        return {"available": False, "reason": "I need a bill or order number column and a product column to see what is bought together."}
    t = df[[r["bill"], r["item"]]].dropna()
    baskets = t.groupby(r["bill"])[r["item"]].agg(lambda s: sorted(set(s)))
    baskets = baskets[baskets.map(len) >= 2]
    n_bills = int(t[r["bill"]].nunique())
    if len(baskets) < 50:
        return {"available": False, "reason": "I need at least 50 bills with two or more products to find pairs."}
    single, pair = Counter(), Counter()
    for items in t.groupby(r["bill"])[r["item"]].agg(lambda s: sorted(set(s))):
        single.update(items)
    for items in baskets:
        pair.update(combinations(items[:12], 2))
    min_together = max(10, int(n_bills * 0.01))
    found = {}
    for (a, b), n in pair.items():
        if n < min_together:
            continue
        lift = (n / n_bills) / ((single[a] / n_bills) * (single[b] / n_bills))
        if lift < 1.5:
            continue
        ca, cb = n / single[a], n / single[b]
        first, second, conf = (a, b, ca) if ca >= cb else (b, a, cb)
        found[(first, second)] = (conf, n, lift)
    if not found:
        return {"available": True, "columns": [], "rows": [], "narrative": ["No products are bought together much more than chance. Customers pick items fairly independently."]}
    ranked = sorted(found.items(), key=lambda kv: -(kv[1][1] * kv[1][2]))[:10]
    rows = [{"If they buy": a, "They also buy": b, "How often": f"{c:.0%}", "Bills together": f"{n:,}"}
            for (a, b), (c, n, _) in ranked]
    (a, b), (c, n, _) = ranked[0]
    narrative = [f"{c:.0%} of the bills with {a} also have {b}.",
                 "Keep these side by side on the shelf, or sell them as a small combo. Remind the customer at the counter: \"Sugar bhi chahiye?\""]
    if len(ranked) > 1:
        (a2, b2), (c2, _, _) = ranked[1]
        narrative.insert(1, f"{c2:.0%} of the bills with {a2} also have {b2}.")
    return {"available": True, "columns": ["If they buy", "They also buy", "How often", "Bills together"], "rows": rows, "narrative": narrative}


# ---------------------------------------------------------------------------
# Busiest days
# ---------------------------------------------------------------------------


def peak(df: pd.DataFrame) -> dict:
    r = roles(df)
    rev = _revenue(df, r)
    if not r["date"] or rev is None:
        return {"available": False, "reason": "I need a date column and an amount column to find your busy days."}
    d = _dates(df, r)
    data = pd.DataFrame({"d": d, "rev": rev}).dropna()
    daily = data.assign(day=data["d"].dt.normalize()).groupby("day")["rev"].sum()
    if len(daily) < 21:
        return {"available": False, "reason": "I need at least three weeks of sales to see a weekly pattern."}
    wd = daily.groupby(daily.index.dayofweek).mean().reindex(range(7))
    avg = float(daily.mean())
    rows = [{"Day": analytics.WEEKDAYS[i], "Average sales": money(float(v)), "Compared with an average day": f"{(v - avg) / avg:+.0%}"}
            for i, v in wd.items() if pd.notna(v)]
    busy, quiet = int(wd.idxmax()), int(wd.idxmin())
    narrative = [
        f"{analytics.WEEKDAYS[busy]} is your busiest day ({(wd[busy] - avg) / avg:+.0%} against an average day) and {analytics.WEEKDAYS[quiet]} is the quietest ({(wd[quiet] - avg) / avg:+.0%}).",
        f"Stock up the day before {analytics.WEEKDAYS[busy]}, and have an extra person on that day. Use {analytics.WEEKDAYS[quiet]} for a small offer to pull customers in.",
    ]
    hours = d.dt.hour
    blocks = [{"type": "table", "columns": list(rows[0].keys()), "rows": rows}]
    if hours.nunique() > 3:
        h = data.assign(h=hours.loc[data.index]).groupby("h")["rev"].sum()
        top = h.sort_values(ascending=False).head(2).index.tolist()
        narrative.append(f"Most money comes in around {top[0]}:00 and {top[1]}:00. Keep the counter free then.")
    return {"available": True, "narrative": narrative, "blocks": blocks}


# ---------------------------------------------------------------------------
# WhatsApp messages
# ---------------------------------------------------------------------------

TEXT = {
    "en": {
        "udhaar": "Namaste {name} ji, a gentle reminder from {shop}. Your pending balance is {amt}. Please clear it when convenient. Thank you!",
        "winback": "Namaste {name} ji, we have not seen you at {shop} for a while and we miss you! Please drop by this week, we have something for you.",
        "festival": "Namaste! {fest} is coming. {shop} will have {items} in stock. Message us to reserve yours or ask for home delivery.",
        "supplier": "Namaste, please send the following for {shop} next week:\n{lines}\nPlease confirm the delivery day. Thank you.",
    },
    "hi": {
        "udhaar": "नमस्ते {name} जी, {shop} की ओर से एक छोटा सा याद दिलाना: आपका {amt} बकाया है। कृपया सुविधा अनुसार चुका दें। धन्यवाद!",
        "winback": "नमस्ते {name} जी, {shop} पर आपको काफ़ी समय से नहीं देखा, हमें आपकी याद आती है! इस हफ़्ते ज़रूर आइए, आपके लिए कुछ खास है।",
        "festival": "नमस्ते! {fest} आने वाला है। {shop} पर {items} उपलब्ध रहेगा। अपना सामान आरक्षित करने या होम डिलीवरी के लिए संदेश करें।",
        "supplier": "नमस्ते, कृपया {shop} के लिए अगले हफ़्ते यह सामान भेजें:\n{lines}\nकृपया डिलीवरी का दिन बताएँ। धन्यवाद।",
    },
}


HI_FEST = {"Diwali": "दिवाली", "Dussehra": "दशहरा", "Holi": "होली", "Dhanteras": "धनतेरस", "Karva Chauth": "करवा चौथ",
           "Raksha Bandhan": "रक्षाबंधन", "Bhai Dooj": "भाई दूज", "Navratri": "नवरात्रि", "Eid al-Fitr": "ईद",
           "Christmas": "क्रिसमस", "Lohri": "लोहड़ी", "Makar Sankranti": "मकर संक्रांति", "Janmashtami": "जन्माष्टमी",
           "Ganesh Chaturthi": "गणेश चतुर्थी"}


def _phone(raw) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    return digits if len(digits) >= 11 else ""


def _link(phone: str, text: str) -> str:
    base = f"https://wa.me/{phone}" if phone else "https://wa.me/"
    return f"{base}?text={quote(text)}"


def _msg(to, phone, text):
    p = _phone(phone)
    return {"to": to, "phone": p, "text": text, "link": _link(p, text)}


def messages(df: pd.DataFrame, kind: str = "winback", lang: str = "en", shop: str = "our shop",
             today: _date | None = None) -> dict:
    """Ready-to-send texts. Hindi uses fixed, hand-written wording, so it needs no AI service."""
    tx = TEXT.get(lang, TEXT["en"])
    r = roles(df)
    out = []
    if kind == "udhaar":
        u = udhaar(df)
        if not u["available"] or not u.get("raw"):
            return {"available": False, "reason": u.get("reason", "Nobody owes you anything right now.")}
        for x in u["raw"][:12]:
            out.append(_msg(x["customer"], x["phone"], tx["udhaar"].format(name=x["customer"].split()[0], shop=shop, amt=money(x["amount"]))))
        lead = f"{len(out)} reminders are ready. Tap Send to open WhatsApp with the message filled in."
    elif kind == "supplier":
        sp = advanced.stock_plan(df)
        if not sp["available"]:
            return {"available": False, "reason": sp["reason"]}
        lines = "\n".join(f"- {x['Product']}: {x['Order about']:,}" for x in sp["rows"][:15])
        out.append(_msg("Your supplier", "", tx["supplier"].format(shop=shop, lines=lines)))
        lead = "Your order for next week is written out. Choose your supplier in WhatsApp and send."
    elif kind == "festival":
        f = festivals(df, today)
        if not f["available"] or not f.get("upcoming"):
            return {"available": False, "reason": f.get("reason", "There is no festival coming up soon.")}
        name = f["upcoming"][0][0]
        items = next((p[1] for p in f.get("picks", []) if p[0] == name), None)
        if items is None:
            items = [x["Product"] for x in advanced.stock_plan(df).get("rows", [])[:4]] or ["everything you need"]
        out.append(_msg("All regular customers", "", tx["festival"].format(fest=HI_FEST.get(name, name) if lang == "hi" else name, shop=shop, items=", ".join(items))))
        lead = f"A {name} message is ready. Send it to your customer list or WhatsApp status."
    else:
        rf = advanced.rfm(df)
        if not rf["available"] or not rf.get("winback_raw"):
            return {"available": False, "reason": rf.get("reason", "No customers have gone quiet.")}
        phones = {}
        if r["phone"] and r["customer"]:
            phones = df.dropna(subset=[r["phone"], r["customer"]]).groupby(r["customer"])[r["phone"]].first().to_dict()
        for name in rf["winback_raw"][:12]:
            out.append(_msg(name, phones.get(name, ""), tx["winback"].format(name=str(name).split()[0], shop=shop)))
        lead = f"{len(out)} messages are ready for customers who have gone quiet."
    return {"available": True, "kind": kind, "messages": out, "narrative": [lead]}
