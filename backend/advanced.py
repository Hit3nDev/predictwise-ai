"""
Advanced business tools, all computed from the file itself (no AI service needed):

  stock_plan     how much of each product to order for next week
  chart_request  "show sales by weekday as a chart" -> a chart
  rfm            best, loyal, at-risk and lost customers, plus a win-back list
  compare        what changed between an older file and a newer one
  digest         a short end-of-day summary, ready to share
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

import analytics
from analytics import cap, fmt, pretty

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PRODUCT_WORDS = ("product", "item", "sku", "goods", "brand", "category")
QTY_WORDS = ("quantity", "qty", "units", "pieces", "count")
CUSTOMER_WORDS = ("customer", "client", "buyer", "member", "phone", "name")


# ---------------------------------------------------------------------------
# Stock planner
# ---------------------------------------------------------------------------


def _product_col(df: pd.DataFrame, exclude: tuple = ()) -> str | None:
    for c in df.columns:
        s = df[c]
        if c in exclude or pd.api.types.is_numeric_dtype(s) or analytics._looks_like_id(s, c):
            continue
        if any(w in c.lower() for w in PRODUCT_WORDS) and 3 <= s.nunique() <= 200:
            return c
    return None


def stock_plan(df: pd.DataFrame, horizon: int = 7, buffer: float = 0.15) -> dict:
    """
    Expected demand for the next `horizon` days per product:
    the last four weeks' daily average, scaled by how busy each weekday usually is,
    plus a safety buffer. Simple on purpose: a shopkeeper can check it by hand.
    """
    date = analytics.detect_date_col(df)
    prod = _product_col(df, exclude=(date,) if date else ())
    if not date or not prod:
        return {"available": False, "reason": "I need a date column and a product column to plan stock."}

    qty = next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and any(w in c.lower() for w in QTY_WORDS)), None)
    measure = qty or analytics.pick_metric(df, date)
    if not measure:
        return {"available": False, "reason": "I need a quantity or sales column to plan stock."}

    d = analytics.to_dates(df, date)
    data = df.loc[d.notna(), [prod, measure]].assign(_d=d[d.notna()].dt.normalize())
    span = (data["_d"].max() - data["_d"].min()).days + 1
    if span < 28 or data[prod].nunique() < 3:
        return {"available": False, "reason": "I need at least four weeks of sales across a few products to plan stock."}

    end = data["_d"].max()
    last28 = data[data["_d"] > end - pd.Timedelta(days=28)]
    prev14 = last28[last28["_d"] <= end - pd.Timedelta(days=14)]
    last14 = last28[last28["_d"] > end - pd.Timedelta(days=14)]

    daily_all = data.groupby("_d")[measure].sum()
    wd = daily_all.groupby(daily_all.index.dayofweek).mean()
    factor = (wd / daily_all.mean()).reindex(range(7)).fillna(1.0)
    future = pd.date_range(end + pd.Timedelta(days=1), periods=horizon)
    mult = float(sum(factor[x.dayofweek] for x in future)) / horizon      # average busyness of those days

    per_day = last28.groupby(prod)[measure].sum() / 28.0
    week_ago = data[data["_d"] > end - pd.Timedelta(days=7)].groupby(prod)[measure].sum()
    a, b = last14.groupby(prod)[measure].sum(), prev14.groupby(prod)[measure].sum()

    rows = []
    for name, rate in per_day.sort_values(ascending=False).items():
        need = rate * horizon * mult
        trend = "steady"
        if b.get(name, 0) > 0:
            ch = (a.get(name, 0) - b[name]) / b[name]
            trend = "rising" if ch >= 0.15 else "falling" if ch <= -0.15 else "steady"
        rows.append({
            "Product": str(name),
            "Sold last 7 days": int(round(week_ago.get(name, 0))),
            "Likely next 7 days": int(round(need)),
            "Order about": int(np.ceil(need * (1 + buffer))),
            "Trend": trend,
        })

    unit = "units" if qty else pretty(measure)
    top = rows[0]
    rising = [r["Product"] for r in rows if r["Trend"] == "rising"][:2]
    narrative = [
        f"Plan for {future[0]:%d %b} to {future[-1]:%d %b}. For {top['Product']}, the likely demand is about {top['Likely next 7 days']:,} {unit}; "
        f"ordering {top['Order about']:,} leaves a {buffer:.0%} safety cushion."
    ]
    if mult > 1.05:
        narrative.append(f"Those days include your busier days, so the plan is {mult - 1:.0%} above a normal week.")
    if rising:
        narrative.append(f"Selling faster than two weeks ago: {', '.join(rising)}.")
    if not qty:
        narrative.append(f"There is no quantity column, so the figures are in {pretty(measure)}, not units.")
    return {
        "available": True,
        "columns": ["Product", "Sold last 7 days", "Likely next 7 days", "Order about", "Trend"],
        "rows": rows,
        "narrative": narrative,
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# Chart on request
# ---------------------------------------------------------------------------

AGG_WORDS = [("mean", r"\b(average|avg|mean|typical)\b"), ("count", r"\b(count|how many|number of|orders|transactions)\b")]


def chart_request(df: pd.DataFrame, question: str) -> dict:
    q = question.lower()
    date = analytics.detect_date_col(df)
    agg = next((a for a, pat in AGG_WORDS if re.search(pat, q)), "sum")

    num_named = [c for c in analytics.numeric_cols(df, exclude=(date,) if date else ()) if pretty(c).lower() in q or c.lower() in q]
    metric = num_named[0] if num_named else analytics.pick_metric(df, date)

    dim_label, groups = None, None
    if re.search(r"week ?day|day of (the )?week|which day|by day\b", q) and date:
        d = analytics.to_dates(df, date)
        dim_label = "weekday"
        key = d.dt.dayofweek
    elif re.search(r"\bmonth(s|ly)?\b", q) and date:
        d = analytics.to_dates(df, date)
        dim_label = "month"
        key = d.dt.to_period("M")
    else:
        cats = [
            c for c in df.columns
            if not pd.api.types.is_numeric_dtype(df[c]) and c != date and 2 <= df[c].nunique() <= 40
            and (pretty(c).lower() in q or c.lower() in q or pretty(c).lower().rstrip("s") in q)
        ]
        dim = cats[0] if cats else analytics.pick_category(df, exclude=(date,) if date else ())
        if not dim:
            return {"available": False, "reason": "Tell me what to split by, for example “chart sales by city”."}
        dim_label, key = pretty(dim), df[dim].astype(str)

    if agg != "count" and not metric:
        return {"available": False, "reason": "I could not find a number column to chart."}
    frame = pd.DataFrame({"k": key, "v": df[metric] if agg != "count" else 1}).dropna(subset=["k"])
    g = frame.groupby("k")["v"].agg("sum" if agg in ("sum", "count") else "mean")
    if dim_label == "weekday":
        g = g.sort_index()
        labels = [WEEKDAYS[int(i)] for i in g.index]
    elif dim_label == "month":
        g = g.sort_index()
        labels = [str(i) for i in g.index]
    else:
        g = g.sort_values(ascending=False).head(12)
        labels = [str(i) for i in g.index]

    if agg == "count":
        unit, what = "number", "Number of rows"
    else:
        unit = "money" if analytics.is_money(metric) else "number"
        what = f"{'Average ' if agg == 'mean' else 'Total '}{pretty(metric)}"
    points = [{"label": l, "value": float(v)} for l, v in zip(labels, g.values)]
    best = max(points, key=lambda p: p["value"])
    low = min(points, key=lambda p: p["value"])
    value_fmt = (lambda v: fmt(metric, v)) if agg != "count" else (lambda v: f"{v:,.0f}")
    narrative = [f"{what} by {dim_label}. Highest is {best['label']} at {value_fmt(best['value'])}, lowest is {low['label']} at {value_fmt(low['value'])}."]
    return {
        "available": True,
        "narrative": narrative,
        "chart": {"type": "chart", "chart": "bar", "title": f"{what} by {dim_label}", "unit": unit, "points": points},
    }


# ---------------------------------------------------------------------------
# Customer value (RFM)
# ---------------------------------------------------------------------------


def _customer_col(df: pd.DataFrame, exclude: tuple) -> str | None:
    best = None
    for c in df.columns:
        s = df[c]
        if c in exclude or pd.api.types.is_numeric_dtype(s) and not analytics._looks_like_id(s, c):
            continue
        if any(w in c.lower() for w in CUSTOMER_WORDS) and 10 <= s.nunique() < len(s):
            return c
    return best


def rfm(df: pd.DataFrame) -> dict:
    """
    Recency (how long since they last came), frequency (how often) and
    monetary (how much they spend), turned into five plain groups.
    """
    date = analytics.detect_date_col(df)
    cust = _customer_col(df, exclude=(date,) if date else ())
    metric = analytics.pick_metric(df, date)
    if not (date and cust and metric):
        return {"available": False, "reason": "I need a customer column, a date column and an amount column to rank customers."}

    d = analytics.to_dates(df, date)
    data = df.loc[d.notna() & df[cust].notna(), [cust, metric]].assign(_d=d[d.notna() & df[cust].notna()])
    t = data.groupby(cust).agg(last=("_d", "max"), first=("_d", "min"), orders=("_d", "size"), spend=(metric, "sum"))
    if len(t) < 20 or (t["orders"] > 1).sum() < 5:
        return {"available": False, "reason": "I need at least 20 customers, some of them repeat buyers, to group them."}

    today = data["_d"].max()
    t["days_since"] = (today - t["last"]).dt.days
    span = max((today - data["_d"].min()).days, 1)
    typical_gap = (t["first"].rsub(t["last"]).dt.days / (t["orders"] - 1).clip(lower=1))[t["orders"] > 1].median()
    away = max(typical_gap * 2.5, 45)

    median_spend = t["spend"].median()

    def label(r):
        if r["orders"] <= 2 and (today - r["first"]).days <= max(span * 0.15, 30):
            return "New"
        if r["days_since"] > away:
            return "At risk" if r["spend"] >= median_spend and r["orders"] >= 3 else "Lost"
        if r["spend"] >= t["spend"].quantile(0.7) and r["orders"] >= max(t["orders"].quantile(0.7), 3):
            return "Best"
        return "Regular"

    t["group"] = t.apply(label, axis=1)
    order = ["Best", "Regular", "New", "At risk", "Lost"]
    meaning = {
        "Best": "Spend the most and come often. Look after them.",
        "Regular": "Steady customers. Keep them coming.",
        "New": "Recent first-time buyers. A good second visit makes them regulars.",
        "At risk": "Good customers who have gone quiet. Worth a call.",
        "Lost": "Light buyers who have not been back for a long time.",
    }
    total = float(t["spend"].sum())
    groups = []
    for g in order:
        part = t[t["group"] == g]
        if part.empty:
            continue
        groups.append({
            "Group": g,
            "Customers": int(len(part)),
            "Share of customers": f"{len(part) / len(t):.0%}",
            "Share of spend": f"{part['spend'].sum() / total:.0%}",
            "What it means": meaning[g],
        })

    win = t[t["group"] == "At risk"].sort_values("spend", ascending=False).head(10)
    winback = [{
        "Customer": str(i),
        "Last visit": f"{int(r['days_since'])} days ago",
        "Orders": int(r["orders"]),
        "Total spent": fmt(metric, float(r["spend"])),
    } for i, r in win.iterrows()]

    best = t[t["group"] == "Best"]
    narrative = []
    if len(best):
        narrative.append(f"{len(best)} customers ({len(best) / len(t):.0%}) bring {best['spend'].sum() / total:.0%} of all spending.")
    risk = t[t["group"] == "At risk"]
    if len(risk):
        narrative.append(f"{len(risk)} good customers have not been back in over {int(away)} days, together worth {fmt(metric, float(risk['spend'].sum()))}. Call them first.")
    if not narrative:
        narrative.append("Your customers look evenly spread; no small group carries most of the spending.")
    winback_raw = [str(i) for i in t[t["group"] == "At risk"].sort_values("spend", ascending=False).head(12).index]
    return {"available": True, "groups": groups, "winback": winback, "winback_raw": winback_raw,
            "narrative": narrative, "metric": metric}


# ---------------------------------------------------------------------------
# What changed between two files
# ---------------------------------------------------------------------------


def compare(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """Plain list of what moved between an older and a newer version of the same kind of file."""
    shared = [c for c in new.columns if c in old.columns]
    if len(shared) < 2:
        return {"available": False, "reason": "The two files share fewer than two columns, so there is nothing to compare."}

    findings = []
    findings.append(f"The newer file has {len(new):,} rows against {len(old):,} before ({(len(new) - len(old)) / max(len(old), 1):+.0%}).")
    gone = [c for c in old.columns if c not in new.columns]
    added = [c for c in new.columns if c not in old.columns]
    if gone:
        findings.append(f"Columns no longer there: {', '.join(gone[:4])}.")
    if added:
        findings.append(f"New columns: {', '.join(added[:4])}.")

    moves = []
    for c in shared:
        if pd.api.types.is_numeric_dtype(old[c]) and pd.api.types.is_numeric_dtype(new[c]) and not analytics._looks_like_id(new[c], c):
            a, b = old[c].mean(), new[c].mean()
            if a and not np.isnan(a) and not np.isnan(b):
                ch = (b - a) / abs(a)
                if abs(ch) >= 0.10:
                    moves.append((abs(ch), f"Average {pretty(c)} moved from {fmt(c, a)} to {fmt(c, b)} ({ch:+.0%})."))
        elif not pd.api.types.is_numeric_dtype(new[c]) and 2 <= new[c].nunique() <= 40:
            o, n = old[c].astype(str).value_counts(normalize=True), new[c].astype(str).value_counts(normalize=True)
            fresh = [v for v in n.index if v not in o.index and n[v] >= 0.01]
            dropped = [v for v in o.index if v not in n.index and o[v] >= 0.01]
            if fresh:
                moves.append((0.5, f"New {pretty(c)} values: {', '.join(fresh[:3])}."))
            if dropped:
                moves.append((0.5, f"{cap(pretty(c))} values that disappeared: {', '.join(dropped[:3])}."))
            shift = (n.reindex(o.index.union(n.index)).fillna(0) - o.reindex(o.index.union(n.index)).fillna(0))
            if len(shift) and shift.abs().max() >= 0.08:
                v = shift.abs().idxmax()
                moves.append((float(shift.abs().max()), f"{cap(pretty(c))} “{v}” went from {o.get(v, 0):.0%} to {n.get(v, 0):.0%} of rows."))
    moves.sort(key=lambda m: -m[0])
    findings += [m[1] for m in moves[:6]]
    if len(findings) <= 1 + bool(gone) + bool(added):
        findings.append("Nothing else changed by much. The two files look alike.")
    return {"available": True, "findings": findings}


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def digest(df: pd.DataFrame, raw: pd.DataFrame | None = None, name: str = "your shop") -> dict:
    """A short message that can be sent on WhatsApp: headline numbers, what to do, what to order."""
    lines = [f"PredictWise summary for {name}"]
    pb = analytics.playbook(df, raw)
    t = analytics.trend(df)
    if t.get("available") and t.get("narrative"):
        lines.append(t["narrative"][0])
    if pb.get("available"):
        lines.append("What to do:")
        lines += [f"{i}. {it['title']}. {it['detail']}" for i, it in enumerate(pb["items"][:4], 1)]
    sp = stock_plan(df)
    if sp.get("available"):
        top = sp["rows"][:3]
        lines.append("Order for next week: " + "; ".join(f"{r['Product']} {r['Order about']:,}" for r in top))
    if len(lines) == 1:
        lines.append("Add a file with dates and sales to get a daily summary.")
    return {"text": "\n".join(lines)}
