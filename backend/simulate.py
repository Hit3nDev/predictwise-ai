"""
Rehearse a decision before making it.

The shop's own bills become a model of a typical day: how many bills, which products, how much
of it on credit. The next thirty days are then played out two thousand times by re-drawing days
from the last twelve weeks (a Monday from past Mondays, a Sunday from past Sundays), with a
festival week that falls inside the period taken from last year's same week, scaled to this
year's level. A decision ("close on Tuesdays", "raise prices 5%", "stop udhaar") is applied to
every one of those futures, so what comes back is not one number but the range it would most
likely land in, and the difference the decision makes, paired future by future.

Nothing here is guessed by a language model. The few things a file cannot say (how customers
react to a price change, how many come back after a message) are shown as assumptions the
shopkeeper can change on the screen.

  options        what the screen needs: products, weekdays, defaults, which levers this file supports
  run            baseline and scenario over the next `horizon` days, with ranges and per-lever effects
  from_question  "What if I close on Sundays?" in the chat -> the same answer, or None
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

import analytics
import lookup
import shop
from analytics import WEEKDAYS, money

HORIZON = 30
SIMS = 2000
POOL_DAYS = 84                       # the last twelve weeks are "how the shop runs now"
SENSITIVITY = {"low": 0.5, "medium": 1.0, "high": 1.5}
QUIET_DAYS = lookup.QUIET_DAYS


# ---------------------------------------------------------------------------
# The model of a typical day, read off the file
# ---------------------------------------------------------------------------


@analytics._memo
def _model(df: pd.DataFrame, horizon: int = HORIZON) -> dict | None:
    """Read-only once built: `run` copies the arrays it changes, so the same model serves every lever."""
    r = shop.roles(df)
    rev = shop._revenue(df, r)
    d = shop._dates(df, r)
    if rev is None or d is None:
        return None
    if r["payment"]:
        pay = df[r["payment"]].astype(str)
        credit = pay.str.contains(shop.CREDIT_RE) & ~pay.str.contains("card", case=False)
        repaid = pay.str.contains(shop.REPAID_RE) & ~credit
    else:
        credit = pd.Series(False, index=df.index)
        repaid = pd.Series(False, index=df.index)
    day = d.dt.normalize()
    ok = day.notna() & rev.notna() & ~repaid                 # a repayment is money in, not a sale
    t = pd.DataFrame({"day": day[ok], "rev": rev[ok].astype(float), "credit": credit[ok].to_numpy()})
    t["item"] = df.loc[ok, r["item"]].astype(str) if r["item"] else "all"
    qty = df.loc[ok, r["qty"]].astype(float).fillna(1.0) if r["qty"] else pd.Series(1.0, index=t.index)
    has_cost = bool(r["cost"]) and bool(df.loc[ok, r["cost"]].notna().any())
    t["cost"] = (df.loc[ok, r["cost"]].astype(float) * qty).fillna(0.0) if has_cost else 0.0
    if r["bill"]:
        t["bill"] = df.loc[ok, r["bill"]].astype(str)
    if r["customer"]:
        t["cust"] = df.loc[ok, r["customer"]].astype(str)
    if t.empty or t["day"].nunique() < 28:
        return None

    end = t["day"].max()
    pool_start = end - pd.Timedelta(days=POOL_DAYS - 1)
    pool = t[t["day"] >= pool_start]
    days = pd.date_range(pool_start, end)                    # closed days stay in as zero days
    by_item = pool.groupby("item")["rev"].sum().sort_values(ascending=False)
    products = [str(i) for i in by_item.index if by_item[i] > 0]
    if not products or pool["day"].nunique() < 14:
        return None

    def wide(frame, value, index=days):
        w = frame.pivot_table(index="day", columns="item", values=value, aggfunc="sum", fill_value=0.0)
        return w.reindex(index=index, columns=products, fill_value=0.0).to_numpy(float)

    P, C = wide(pool, "rev"), (wide(pool, "cost") if has_cost else None)
    CR = pool[pool["credit"]].groupby("day")["rev"].sum().reindex(days, fill_value=0.0).to_numpy(float)
    daily_all = t.groupby("day")["rev"].sum()
    level_now = float(daily_all.reindex(days, fill_value=0.0).mean())

    # last year's festival week, scaled to this year's level, for a festival inside the horizon
    festivals = []
    first_day = t["day"].min()
    for name, when in shop.FESTIVALS:
        f = pd.Timestamp(when)
        if not (end < f + pd.Timedelta(days=3) and f - pd.Timedelta(days=6) <= end + pd.Timedelta(days=horizon)):
            continue
        for p in sorted((pd.Timestamp(x) for n, x in shop.FESTIVALS if n == name and f - pd.Timestamp(x) > pd.Timedelta(days=200)), reverse=True):
            w0, w1, b0 = p - pd.Timedelta(days=6), p + pd.Timedelta(days=3), p - pd.Timedelta(days=51)
            if b0 < first_day or w1 > end:
                continue
            base = float(daily_all.reindex(pd.date_range(b0, p - pd.Timedelta(days=7)), fill_value=0.0).mean())
            win = float(daily_all.reindex(pd.date_range(w0, p), fill_value=0.0).mean())
            if base > 0 and win / base >= 1.15:
                window = t[(t["day"] >= w0) & (t["day"] <= w1)]
                fdays = pd.date_range(w0, w1)
                scale = level_now / base
                festivals.append({
                    "name": name, "date": f, "past": p, "uplift": win / base, "scale": scale,
                    "rev": wide(window, "rev", fdays) * scale if len(window) else np.zeros((len(fdays), len(products))),
                    "cost": (wide(window, "cost", fdays) * scale if len(window) else np.zeros((len(fdays), len(products)))) if has_cost else None,
                    "credit": window[window["credit"]].groupby("day")["rev"].sum().reindex(fdays, fill_value=0.0).to_numpy(float) * scale,
                    "offsets": np.array([(x - p).days for x in fdays]),
                })
            break
    festivals.sort(key=lambda x: -x["uplift"])
    kept = []
    for c in festivals:                                        # overlapping festival weeks: keep the stronger
        lo, hi = c["date"] - pd.Timedelta(days=6), c["date"] + pd.Timedelta(days=3)
        if all(hi < k["date"] - pd.Timedelta(days=6) or lo > k["date"] + pd.Timedelta(days=3) for k in kept):
            kept.append(c)

    prod_rev = P.sum(axis=0)
    prod_cost = C.sum(axis=0) if has_cost else None
    margin_j = np.where(prod_rev > 0, (prod_rev - prod_cost) / np.where(prod_rev > 0, prod_rev, 1), 0.0) if has_cost else None
    margin = float((prod_rev - prod_cost).sum() / prod_rev.sum()) if has_cost and prod_rev.sum() > 0 else 0.0

    attach = np.zeros(len(products))                           # other items' sales in the bills a product sits in
    if "bill" in pool.columns:
        bill_total = pool.groupby("bill")["rev"].transform("sum")
        other = (bill_total - pool["rev"]).groupby(pool["item"]).sum()
        own = pool.groupby("item")["rev"].sum()
        for j, name in enumerate(products):
            if own.get(name, 0) > 0:
                attach[j] = min(float(other.get(name, 0.0) / own[name]), 5.0)

    quiet_spend = np.zeros(0)
    if "cust" in t.columns:
        g = t.groupby("cust").agg(first=("day", "min"), last=("day", "max"), spend=("rev", "sum"), n=("day", "size"))
        g = g[(g["n"] >= 3) & ((end - g["last"]).dt.days > QUIET_DAYS)]
        if len(g):
            months = ((g["last"] - g["first"]).dt.days / 30.4).clip(lower=1.0)
            quiet_spend = (g["spend"] / months).to_numpy(float)

    wd_mean = pd.Series(P.sum(axis=1), index=days).groupby(days.dayofweek).mean().reindex(range(7)).fillna(0.0)
    return {
        "products": products, "P": P, "C": C, "CR": CR, "days": days, "end": end, "has_cost": has_cost,
        "has_credit": bool(CR.sum() > 0), "has_bill": "bill" in pool.columns, "margin": margin, "margin_j": margin_j,
        "attach": attach, "quiet_spend": quiet_spend, "festivals": kept, "wd_mean": wd_mean,
        "credit_share": float(CR.sum() / P.sum()) if P.sum() > 0 else 0.0, "level": level_now,
    }


# ---------------------------------------------------------------------------
# Levers: what the shopkeeper can change
# ---------------------------------------------------------------------------


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return float(min(max(v, lo), hi)) if np.isfinite(v) else default


def _product(m: dict, name) -> int | None:
    if name is None or str(name).strip().lower() in ("", "all", "all products"):
        return None
    hit = lookup._match(m["products"], str(name), fuzzy=True)
    return m["products"].index(hit) if hit else None


def _sensitivity(v) -> float:
    if isinstance(v, str) and v.lower() in SENSITIVITY:
        return SENSITIVITY[v.lower()]
    return _clamp(v, 0.0, 3.0, 1.0)


def _normalize(m: dict, levers: dict | None) -> dict:
    """Only the levers this file can support, with every number kept in a sane range."""
    L = levers or {}
    out = {}
    x = L.get("close_day")
    if isinstance(x, dict) and x.get("day") is not None:
        day = int(_clamp(x.get("day"), 0, 6, 6))
        out["close_day"] = {"day": day, "shift": _clamp(x.get("shift"), 0, 1, 0.5)}
    x = L.get("price")
    if isinstance(x, dict) and x.get("pct") is not None:
        j = _product(m, x.get("product"))
        if x.get("product") in (None, "", "all", "all products") or j is not None:
            out["price"] = {"product": None if j is None else m["products"][j], "pct": _clamp(x.get("pct"), -50, 50, 5.0),
                            "sensitivity": _sensitivity(x.get("sensitivity", "medium"))}
    x = L.get("offer")
    if isinstance(x, dict) and _product(m, x.get("product")) is not None:
        pct = _clamp(x.get("pct"), 0, 70, 10.0)
        out["offer"] = {"product": m["products"][_product(m, x.get("product"))], "pct": pct,
                        "uplift": _clamp(x.get("uplift"), 0, 3, round(2 * pct / 100, 2))}
    x = L.get("drop")
    if isinstance(x, dict) and _product(m, x.get("product")) is not None:
        out["drop"] = {"product": m["products"][_product(m, x.get("product"))], "loss": _clamp(x.get("loss"), 0, 1, 0.1)}
    x = L.get("no_udhaar")
    if isinstance(x, dict) and m["has_credit"]:
        out["no_udhaar"] = {"lost": _clamp(x.get("lost"), 0, 1, 0.3)}
    x = L.get("winback")
    if isinstance(x, dict) and len(m["quiet_spend"]):
        out["winback"] = {"rate": _clamp(x.get("rate"), 0, 1, 0.2)}
    return out


# ---------------------------------------------------------------------------
# Playing the next month out
# ---------------------------------------------------------------------------


def _draw(m: dict, horizon: int, n: int, rng: np.random.Generator):
    """One index per simulated day: a past day of the same weekday, or last year's festival day."""
    P, C, CR, days = m["P"], m["C"], m["CR"], m["days"]
    rev_rows, cost_rows, cr_rows = [P], [C if C is not None else np.zeros_like(P)], [CR]
    future = pd.date_range(m["end"] + pd.Timedelta(days=1), periods=horizon)
    cands = []
    for h, day in enumerate(future):
        c = np.where(days.dayofweek == day.dayofweek)[0]
        cands.append(c if len(c) else np.arange(len(days)))
    offset = len(days)
    festival_days = {}
    for f in m["festivals"]:
        rev_rows.append(f["rev"]); cost_rows.append(f["cost"] if f["cost"] is not None else np.zeros_like(f["rev"])); cr_rows.append(f["credit"])
        for h, day in enumerate(future):
            o = (day - f["date"]).days
            if -6 <= o <= 3:
                near = np.where(np.abs(f["offsets"] - o) <= 1)[0]
                if len(near):
                    cands[h] = near + offset
                    festival_days[h] = f["name"]
        offset += len(f["offsets"])
    M_rev, M_cost, M_cr = np.vstack(rev_rows), np.vstack(cost_rows), np.concatenate(cr_rows)
    idx = np.empty((n, horizon), dtype=int)
    for h, c in enumerate(cands):
        idx[:, h] = c[rng.integers(0, len(c), n)]
    return M_rev[idx], M_cost[idx], M_cr[idx], future, festival_days


def _apply(m: dict, levers: dict, R0, C0, CR0, future, U):
    """Return (sales, profit, cash, daily) per simulation after the levers."""
    n, H, J = R0.shape
    R, C, CR = R0.copy(), C0.copy(), CR0.copy()
    adj_rev, adj_cost = np.zeros((n, H)), np.zeros((n, H))
    margin = m["margin"]

    if "price" in levers:
        x = levers["price"]
        p = x["pct"] / 100.0
        units = max(0.0, 1.0 - x["sensitivity"] * p)
        cols = slice(None) if x["product"] is None else [m["products"].index(x["product"])]
        R[:, :, cols] *= (1 + p) * units
        C[:, :, cols] *= units
    if "offer" in levers:
        x = levers["offer"]
        j = m["products"].index(x["product"])
        R[:, :, j] *= (1 - x["pct"] / 100.0) * (1 + x["uplift"])
        C[:, :, j] *= (1 + x["uplift"])
    if "drop" in levers:
        x = levers["drop"]
        j = m["products"].index(x["product"])
        lost = x["loss"] * m["attach"][j] * R[:, :, j]
        adj_rev -= lost
        adj_cost -= lost * (1 - margin)
        R[:, :, j] = 0.0
        C[:, :, j] = 0.0
    base_day = R0.sum(axis=2)
    ratio = np.divide(R.sum(axis=2) + adj_rev, base_day, out=np.ones_like(base_day), where=base_day > 0)
    CR = CR * np.clip(ratio, 0, None)
    if "close_day" in levers:
        x = levers["close_day"]
        closed = np.array([day.dayofweek == x["day"] for day in future])
        for h in np.where(closed)[0]:
            tot = R[:, h, :].sum(axis=1) + adj_rev[:, h]
            cst = C[:, h, :].sum(axis=1) + adj_cost[:, h]
            R[:, h, :] = 0.0; C[:, h, :] = 0.0; adj_rev[:, h] = 0.0; adj_cost[:, h] = 0.0; CR[:, h] = 0.0
            targets = [k for k in (h - 1, h + 1) if 0 <= k < H and not closed[k]]
            for k in targets:
                adj_rev[:, k] += x["shift"] * tot / len(targets)
                adj_cost[:, k] += x["shift"] * cst / len(targets)
    if "no_udhaar" in levers:
        lost = levers["no_udhaar"]["lost"] * CR
        adj_rev -= lost
        adj_cost -= lost * (1 - margin)
        CR = np.zeros_like(CR)
    if "winback" in levers:
        back = (U < levers["winback"]["rate"]).astype(float) @ m["quiet_spend"] * (H / 30.4)
        adj_rev += back[:, None] / H
        adj_cost += back[:, None] / H * (1 - margin)

    daily = R.sum(axis=2) + adj_rev
    sales = daily.sum(axis=1)
    profit = (R - C).sum(axis=(1, 2)) + (adj_rev - adj_cost).sum(axis=1)
    cash = sales - CR.sum(axis=1)
    return sales, profit, cash, daily


def _q(v):
    p10, p50, p90 = np.quantile(v, [0.1, 0.5, 0.9])
    return {"p10": float(round(p10)), "p50": float(round(p50)), "p90": float(round(p90))}


def _fan(daily):
    cum = np.cumsum(daily, axis=1)
    q = np.quantile(cum, [0.1, 0.5, 0.9], axis=0)
    return {k: [0.0] + [float(round(x)) for x in q[i]] for i, k in enumerate(("p10", "p50", "p90"))}


LEVER_LABELS = {
    "close_day": "Close on {day}s", "price": "{verb} {what} by {pct}%", "offer": "{pct}% off {product}",
    "drop": "Stop stocking {product}", "no_udhaar": "Stop giving udhaar", "winback": "Message quiet customers",
}


def _label(k: str, x: dict) -> str:
    if k == "close_day":
        return LEVER_LABELS[k].format(day=WEEKDAYS[x["day"]])
    if k == "price":
        return LEVER_LABELS[k].format(verb="Raise" if x["pct"] >= 0 else "Cut", what="all prices" if x["product"] is None else x["product"],
                                      pct=f"{abs(x['pct']):g}")
    if k == "offer":
        return LEVER_LABELS[k].format(pct=f"{x['pct']:g}", product=x["product"])
    if k == "drop":
        return LEVER_LABELS[k].format(product=x["product"])
    return LEVER_LABELS[k]


def _signed(v: float) -> str:
    return ("+" if v >= 0 else "−") + money(abs(v))


def run(df: pd.DataFrame, levers: dict | None = None, horizon: int = HORIZON, sims: int = SIMS, seed: int = 11) -> dict:
    m = _model(df, horizon)
    if m is None:
        return {"available": False, "reason": "To rehearse decisions I need a date column, an amount (or price and quantity) column and at least four weeks of sales."}
    levers = _normalize(m, levers)
    rng = np.random.default_rng(seed)
    R, C, CR, future, festival_days = _draw(m, horizon, sims, rng)
    U = rng.random((sims, len(m["quiet_spend"])))

    b_sales, b_profit, b_cash, b_daily = _apply(m, {}, R, C, CR, future, U)
    s_sales, s_profit, s_cash, s_daily = _apply(m, levers, R, C, CR, future, U)

    def block(sales, profit, cash):
        return {"sales": _q(sales), "profit": _q(profit) if m["has_cost"] else None, "cash": _q(cash) if m["has_credit"] else None}

    def delta(a, b, base):
        d = _q(b - a)
        d["pct"] = float((d["p50"] / base) if base else 0.0)
        return d

    out = {
        "available": True, "horizon": horizon, "sims": sims, "pool_days": POOL_DAYS,
        "start": future[0].strftime("%Y-%m-%d"), "end": future[-1].strftime("%Y-%m-%d"),
        "levers": levers, "has_cost": m["has_cost"], "has_credit": m["has_credit"],
        "baseline": block(b_sales, b_profit, b_cash), "scenario": block(s_sales, s_profit, s_cash),
        "delta": {"sales": delta(b_sales, s_sales, float(np.median(b_sales))),
                  "profit": delta(b_profit, s_profit, float(np.median(b_profit))) if m["has_cost"] else None,
                  "cash": delta(b_cash, s_cash, float(np.median(b_cash))) if m["has_credit"] else None},
        "fan": {"labels": [x.strftime("%Y-%m-%d") for x in future], "base": _fan(b_daily), "scenario": _fan(s_daily),
                "festival_days": [{"day": int(h), "name": nm} for h, nm in festival_days.items()]},
        "festivals": [{"name": f["name"], "date": f["date"].strftime("%Y-%m-%d"), "uplift": round(float(f["uplift"]), 2)} for f in m["festivals"]],
    }

    # each change on its own, so the shopkeeper can see which one matters
    effects = []
    for k, x in levers.items():
        e_sales, e_profit, e_cash, _ = _apply(m, {k: x}, R, C, CR, future, U)
        effects.append({"lever": k, "label": _label(k, x), "sales": float(round(np.median(e_sales - b_sales))),
                        "profit": float(round(np.median(e_profit - b_profit))) if m["has_cost"] else None,
                        "cash": float(round(np.median(e_cash - b_cash))) if m["has_credit"] else None})
    out["effects"] = effects
    out["assumptions"] = _assumptions(m, levers)
    out["narrative"] = _narrative(m, levers, out, effects)
    return out


def _assumptions(m: dict, levers: dict) -> list[str]:
    lines = [f"Each of the {SIMS:,} futures re-draws every day from your last {POOL_DAYS // 7} weeks, a Monday from past Mondays and so on, so weekday patterns and ordinary ups and downs are kept."]
    for f in m["festivals"]:
        lines.append(f"{f['name']} ({f['date']:%d %b}) falls in this period: its ten days are taken from last year's {f['name']} ({f['past']:%d %b %Y}, {f['uplift']:.1f}x a normal day), scaled to this year's level.")
    for k, x in levers.items():
        if k == "close_day":
            lines.append(f"{x['shift']:.0%} of a closed {WEEKDAYS[x['day']]}'s sales move to the day before or after; the rest is lost.")
        elif k == "price":
            lines.append(f"Customers react {'mildly' if x['sensitivity'] <= 0.6 else 'strongly' if x['sensitivity'] >= 1.4 else 'moderately'}: a {abs(x['pct']):g}% price {'rise' if x['pct'] >= 0 else 'cut'} {'loses' if x['pct'] >= 0 else 'adds'} about {abs(x['sensitivity'] * x['pct']):.0f}% of units. Cost prices stay the same.")
        elif k == "offer":
            lines.append(f"{x['pct']:g}% off {x['product']} sells {x['uplift']:.0%} more units of it; the cost price stays the same.")
        elif k == "drop":
            lines.append(f"Without {x['product']}, {x['loss']:.0%} of the other items in the bills it sat in are lost too (customers who go elsewhere).")
        elif k == "no_udhaar":
            lines.append(f"Without udhaar, {x['lost']:.0%} of credit sales are lost; the rest is paid in cash or UPI.")
        elif k == "winback":
            lines.append(f"{x['rate']:.0%} of the {len(m['quiet_spend'])} customers who have not visited for over {QUIET_DAYS} days come back and spend what they used to each month.")
    lines.append("Rehearsals, not promises: the ranges show where nine in ten replays landed.")
    return lines


def _narrative(m: dict, levers: dict, out: dict, effects: list[dict]) -> list[str]:
    b, s, d = out["baseline"], out["scenario"], out["delta"]
    start, end = pd.Timestamp(out["start"]), pd.Timestamp(out["end"])
    lines = [f"Over the next {out['horizon']} days ({start:%d %b} to {end:%d %b}), as things are, you would most likely sell "
             f"{money(b['sales']['p50'])}, and nine times in ten between {money(b['sales']['p10'])} and {money(b['sales']['p90'])}."]
    if m["has_cost"]:
        lines[0] += f" That is about {money(b['profit']['p50'])} profit."
    for f in m["festivals"]:
        lines.append(f"{f['name']} ({f['date']:%d %b}) falls in this period, so its week is taken from last year's, when sales ran {f['uplift']:.1f}x a normal day.")
    if not levers:
        lines.append("Switch on a change to see what it would do: close a day, move prices, run an offer, stop a product, stop udhaar or call back quiet customers.")
        return lines
    sales_line = f"With your changes: {money(s['sales']['p50'])} in sales, {_signed(d['sales']['p50'])} ({d['sales']['pct']:+.0%})"
    if m["has_cost"]:
        sales_line += f", and {_signed(d['profit']['p50'])} profit ({d['profit']['pct']:+.0%})"
    if m["has_credit"] and "no_udhaar" in levers:
        sales_line += f", with {_signed(d['cash']['p50'])} cash in hand"
    lines.append(sales_line + ".")
    for e in effects:
        k, x = e["lever"], levers[e["lever"]]
        profit_bit = f" and {_signed(e['profit'])} profit" if m["has_cost"] else ""
        if k == "close_day":
            lines.append(f"Closing on {WEEKDAYS[x['day']]}s: {_signed(e['sales'])} sales{profit_bit}, assuming {x['shift']:.0%} of those customers come another day.")
        elif k == "price":
            what = "all prices" if x["product"] is None else f"the price of {x['product']}"
            lines.append(f"{'Raising' if x['pct'] >= 0 else 'Cutting'} {what} by {abs(x['pct']):g}%: {_signed(e['sales'])} sales{profit_bit}, if customers react "
                         f"{'mildly' if x['sensitivity'] <= 0.6 else 'strongly' if x['sensitivity'] >= 1.4 else 'moderately'}.")
        elif k == "offer":
            lines.append(f"{x['pct']:g}% off {x['product']}: {_signed(e['sales'])} sales{profit_bit}, if it sells {x['uplift']:.0%} more units.")
        elif k == "drop":
            lines.append(f"Stopping {x['product']}: {_signed(e['sales'])} sales{profit_bit}, counting the other items its buyers would take elsewhere.")
        elif k == "no_udhaar":
            lines.append(f"Stopping udhaar: {_signed(e['sales'])} sales{profit_bit}, but {_signed(e['cash'])} cash in hand, if {x['lost']:.0%} of credit customers stop buying.")
        elif k == "winback":
            lines.append(f"Messaging the {len(m['quiet_spend'])} customers who went quiet: {_signed(e['sales'])} sales{profit_bit}, if {x['rate']:.0%} of them come back.")
    lines.append(f"Rehearsals, not promises: {SIMS:,} replays of your own last {POOL_DAYS // 7} weeks, and the assumptions are yours to change.")
    return lines


# ---------------------------------------------------------------------------
# What the screen needs before the first run
# ---------------------------------------------------------------------------


def options(df: pd.DataFrame) -> dict:
    m = _model(df)
    if m is None:
        return {"available": False, "reason": "To rehearse decisions I need a date column, an amount (or price and quantity) column and at least four weeks of sales."}
    monthly = m["P"].sum(axis=0) / POOL_DAYS * 30.4
    products = []
    for j, name in enumerate(m["products"]):
        row = {"name": name, "monthly": float(round(monthly[j]))}
        if m["has_cost"]:
            row["margin"] = float(round(m["margin_j"][j], 3))
        products.append(row)
    wd = m["wd_mean"]
    avg = float(wd.mean()) or 1.0
    weekdays = [{"index": i, "name": WEEKDAYS[i], "avg": float(round(wd[i])), "vs_avg": float((wd[i] - avg) / avg)} for i in range(7)]
    slow = shop.slow_movers(df)
    fading = next((r["Product"] for r in slow.get("rows", []) if r["Product"] in m["products"]), None) if slow.get("available") else None
    lowest_profit = None
    if m["has_cost"]:
        prof = (m["P"] - m["C"]).sum(axis=0)
        lowest_profit = m["products"][int(np.argmin(prof))]
    future = pd.date_range(m["end"] + pd.Timedelta(days=1), periods=HORIZON)
    return {
        "available": True, "horizon": HORIZON, "sims": SIMS, "pool_days": POOL_DAYS,
        "start": future[0].strftime("%Y-%m-%d"), "end": future[-1].strftime("%Y-%m-%d"),
        "products": products, "weekdays": weekdays,
        "quiet": int(len(m["quiet_spend"])), "credit_share": round(m["credit_share"], 4),
        "has_cost": m["has_cost"], "has_credit": m["has_credit"], "has_bill": m["has_bill"],
        "levers": {"close_day": True, "price": True, "offer": True, "drop": True, "no_udhaar": m["has_credit"], "winback": len(m["quiet_spend"]) > 0},
        "defaults": {"close_day": int(wd.idxmin()), "offer_product": fading or m["products"][-1],
                     "drop_product": lowest_profit or m["products"][-1], "price_product": None},
        "festivals": [{"name": f["name"], "date": f["date"].strftime("%Y-%m-%d"), "uplift": round(float(f["uplift"]), 2)} for f in m["festivals"]],
    }


# ---------------------------------------------------------------------------
# "What if I close on Sundays?" in the chat
# ---------------------------------------------------------------------------

WHATIF_RE = re.compile(r"^\s*(what (would happen |happens |will happen |happen )?if|if i\b|should i\b|suppose|agar (main|mai|mein|hum)\b|kya hoga agar)", re.I)
DAYS_RE = re.compile(r"\b(mon|tue|tues|wed|wednes|thu|thur|thurs|fri|sat|satur|sun)(day)?s?\b|\b(somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar|itvar)\b", re.I)
DAY_INDEX = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "wednes": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "satur": 5, "sun": 6,
             "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3, "shukravar": 4, "shanivar": 5, "ravivar": 6, "itvar": 6}
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent|per cent|pc(?!\w))", re.I)


def _parse(df: pd.DataFrame, q: str) -> dict | None:
    ql = q.lower().rstrip(" ?!.")
    levers = {}
    day = DAYS_RE.search(ql)
    if day and re.search(r"\b(close|closed|closing|shut|off|band|bandh|chhutti|chutti|holiday|rest)\b", ql):
        key = (day.group(1) or day.group(3)).lower()
        levers["close_day"] = {"day": DAY_INDEX[key], "shift": 0.5}
    pct = PCT_RE.search(ql)
    if re.search(r"\b(udhaar|udhar|credit|khata)\b", ql) and re.search(r"\b(stop|no|ban|band|bandh|nahi|nahin|end|close)\b", ql):
        levers["no_udhaar"] = {"lost": 0.3}
    if re.search(r"\b(win ?back|bring (them |customers |the customers )?back|come back)\b", ql) or (
            re.search(r"\b(message|whatsapp|text|call|remind|contact|bula)\w*", ql) and re.search(r"\b(quiet|lost|old|inactive|lapsed|gone|purane|puraane|missing)\b", ql)):
        levers["winback"] = {"rate": 0.2}
    m_drop = re.search(r"\b(?:stop|quit)\s+(?:selling|stocking|keeping|buying|ordering)\s+(.+)$", ql) or re.search(r"\b(?:remove|drop)\s+(.+?)\s+from\b", ql)
    if m_drop and not re.search(r"\b(udhaar|udhar|credit|khata)\b", m_drop.group(1)):
        levers["drop"] = {"product": m_drop.group(1).strip(), "loss": 0.1}
    m_offer = re.search(r"(\d+(?:\.\d+)?)\s?%\s?(?:off|discount|offer|chhoot|chut|sale)(?:\s+(?:on|for|of)\s+(.+))?", ql) or \
        re.search(r"\b(?:discount|offer|off|sale)\b(?:\s+of\s+(\d+(?:\.\d+)?)\s?%)?\s+(?:on|for)\s+(.+)", ql)
    if m_offer:
        prod = (m_offer.group(2) or "").strip()
        if prod:
            levers["offer"] = {"product": prod, "pct": float(m_offer.group(1) or 10)}
    if "offer" not in levers and re.search(r"\b(price|prices|rate|rates|daam|dam|mrp)\b", ql) and \
            re.search(r"\b(raise|raised|increase|increased|hike|up|badha\w*|more|cut|reduce|reduced|lower|drop|kam|ghata\w*|less|change)\b", ql):
        down = bool(re.search(r"\b(cut|reduce|reduced|lower|drop|kam|ghata\w*|less|decrease)\b", ql))
        val = float(pct.group(1)) if pct else 5.0
        m_prod = re.search(r"\b(?:price|prices|rate|rates|daam|dam)\s+(?:of|for|on)\s+(.+?)(?:\s+by\b|\s+\d|$)", ql)
        levers["price"] = {"product": m_prod.group(1).strip() if m_prod else None, "pct": -val if down else val, "sensitivity": "medium"}
    return levers or None


def from_question(df: pd.DataFrame, question: str) -> dict | None:
    q = (question or "").strip()
    if not WHATIF_RE.search(q):
        return None
    levers = _parse(df, q)
    if not levers:
        return {"available": False, "reason": "I can rehearse a few kinds of change: closing on a weekday, raising or cutting prices, an offer on a product, "
                                              "stopping a product, stopping udhaar, or messaging quiet customers. Try “What if I close on Tuesdays?” "
                                              "or “What if I raise all prices by 5%?”, or open the What if screen."}
    res = run(df, levers)
    if res["available"] and not res["levers"]:
        return {"available": False, "reason": "I understood the question but could not match it to this file: check the product name, or open the What if screen to pick from the list."}
    return res
