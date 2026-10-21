"""
Checking the stock plan against the shop's own history.

For each of the last few weeks we pretend it is that week, build the plan from
only the data available then, and compare it with what really sold. That gives:

  * an honest error figure, next to the simplest alternative ("repeat last week")
  * how often the plan would have run short
  * a range around each order (an 80% interval), calibrated on the earlier
    weeks and then tested on the latest ones it never saw

Nothing is fitted to the weeks used for the final score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import advanced
import analytics

HORIZON = 7
ORIGINS = 6          # weekly backtest points
TEST_ORIGINS = 2     # the latest of them are held out for the coverage check
LOW_Q, HIGH_Q = 0.10, 0.90


def _measure(df: pd.DataFrame, date: str) -> str | None:
    qty = next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
                and any(w in c.lower() for w in advanced.QTY_WORDS)), None)
    return qty or analytics.pick_metric(df, date)


def _records(df: pd.DataFrame, buffer: float = 0.15) -> pd.DataFrame | None:
    date = analytics.detect_date_col(df)
    prod = advanced._product_col(df, exclude=(date,) if date else ())
    measure = _measure(df, date) if date else None
    if not (date and prod and measure):
        return None
    d = analytics.to_dates(df, date)
    data = df.loc[d.notna()].assign(_d=d[d.notna()].dt.normalize())
    end = data["_d"].max()
    rows = []
    for k in range(ORIGINS, 0, -1):
        cutoff = end - pd.Timedelta(days=HORIZON * k)
        past = data[data["_d"] <= cutoff]
        if (past["_d"].max() - past["_d"].min()).days + 1 < 28:
            continue
        plan = advanced.stock_plan(past.drop(columns="_d"), horizon=HORIZON, buffer=buffer)
        if not plan["available"]:
            continue
        nxt = data[(data["_d"] > cutoff) & (data["_d"] <= cutoff + pd.Timedelta(days=HORIZON))]
        actual = nxt.groupby(prod)[measure].sum()
        for r in plan["rows"]:
            rows.append({
                "origin": ORIGINS - k, "product": r["Product"],
                "likely": r["Likely next 7 days"], "order": r["Order about"],
                "naive": r["Sold last 7 days"], "actual": float(actual.get(r["Product"], 0.0)),
            })
    return pd.DataFrame(rows) if rows else None


def backtest(df: pd.DataFrame, buffer: float = 0.15) -> dict:
    rec = _records(df, buffer)
    if rec is None or rec["origin"].nunique() < 3:
        return {"available": False, "reason": "I need at least about two months of daily sales with a product column to test the plan against your own history."}

    total = float(rec["actual"].sum())
    if total <= 0:
        return {"available": False, "reason": "There are no sales in the weeks I would test."}

    wape = float((rec["actual"] - rec["likely"]).abs().sum() / total)
    naive_wape = float((rec["actual"] - rec["naive"]).abs().sum() / total)
    short = float((rec["actual"] > rec["order"]).mean())
    naive_order = np.ceil(rec["naive"] * (1 + buffer))
    naive_short = float((rec["actual"] > naive_order).mean())
    extra = float(np.maximum(rec["order"] - rec["actual"], 0).sum() / max(rec["order"].sum(), 1))

    out = {
        "available": True, "weeks": int(rec["origin"].nunique()), "records": int(len(rec)),
        "wape": wape, "naive_wape": naive_wape, "run_short": short, "naive_run_short": naive_short,
        "left_over": extra, "interval": None,
    }

    cal = rec[(rec["origin"] < rec["origin"].max() - TEST_ORIGINS + 1) & (rec["likely"] >= 3)]
    test = rec[(rec["origin"] >= rec["origin"].max() - TEST_ORIGINS + 1) & (rec["likely"] >= 3)]
    if len(cal) >= 30 and len(test) >= 10:
        ratio = cal["actual"] / cal["likely"]
        lo, hi = float(ratio.quantile(LOW_Q)), float(ratio.quantile(HIGH_Q))
        inside = ((test["actual"] >= np.floor(test["likely"] * lo)) & (test["actual"] <= np.ceil(test["likely"] * hi)))
        out["interval"] = {"low": lo, "high": hi, "coverage": float(inside.mean()), "tested": int(len(test))}

    out["narrative"] = _narrative(out, buffer)
    out["columns"] = ["Measure", "This plan", "Repeat last week"]
    out["rows"] = [
        {"Measure": "Average miss (lower is better)", "This plan": f"{wape:.0%}", "Repeat last week": f"{naive_wape:.0%}"},
        {"Measure": f"Product-weeks that ran short, with a {buffer:.0%} cushion", "This plan": f"{short:.0%}", "Repeat last week": f"{naive_short:.0%}"},
    ]
    if out["interval"]:
        out["rows"].append({"Measure": "Real sales inside the 80% range (weeks not used to set it)",
                            "This plan": f"{out['interval']['coverage']:.0%}", "Repeat last week": "no range"})
    return out


def _narrative(o: dict, buffer: float) -> list[str]:
    lines = [
        f"I tested the stock plan on your own history. For each of the last {o['weeks']} weeks I pretended it was that week, "
        f"made the plan from only the earlier data, and compared it with what really sold ({o['records']:,} product-weeks)."
    ]
    if o["wape"] < o["naive_wape"]:
        lines.append(f"The plan missed by {o['wape']:.0%} on average, against {o['naive_wape']:.0%} if you simply repeat last week's sales. "
                     f"That is {(o['naive_wape'] - o['wape']) / o['naive_wape']:.0%} less error.")
    else:
        lines.append(f"The plan missed by {o['wape']:.0%} on average, which is not better than repeating last week ({o['naive_wape']:.0%}). "
                     "Your sales may be too irregular for a forecast to help much, so keep a larger cushion.")
    lines.append(f"With the {buffer:.0%} cushion it would have run short on {o['run_short']:.0%} of product-weeks and left about {o['left_over']:.0%} of the ordered stock unsold.")
    if o["interval"]:
        i = o["interval"]
        lines.append(f"Real sales landed between {i['low']:.0%} and {i['high']:.0%} of the plan in 4 of 5 weeks; "
                     f"on weeks the range was not fitted on, {i['coverage']:.0%} of products stayed inside it.")
    return lines


def stock_plan_with_ranges(df: pd.DataFrame, horizon: int = 7, buffer: float = 0.15) -> dict:
    """The normal plan plus a 'Likely range' for each product, when there is enough history to set one."""
    plan = advanced.stock_plan(df, horizon=horizon, buffer=buffer)
    if not plan["available"] or horizon != HORIZON:
        return plan
    bt = backtest(df, buffer)
    if not (bt["available"] and bt["interval"]):
        return plan
    lo, hi = bt["interval"]["low"], bt["interval"]["high"]
    for r in plan["rows"]:
        likely = r["Likely next 7 days"]
        r["Likely range"] = f"{int(np.floor(likely * lo))} to {int(np.ceil(likely * hi))}"
    plan["columns"] = plan["columns"][:3] + ["Likely range"] + plan["columns"][3:]
    plan["narrative"].append(
        f"The range shows where demand landed in 4 of 5 past weeks. On weeks it was not fitted on, real sales stayed inside it for {bt['interval']['coverage']:.0%} of products."
    )
    plan["backtest"] = {"wape": bt["wape"], "naive_wape": bt["naive_wape"]}
    return plan
