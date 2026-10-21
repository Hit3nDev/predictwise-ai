"""
Demand forecasting that checks itself.

For each product the planner tries several simple methods, replays the past
("what would each have predicted every week, and how wrong was it?"), keeps the
one that would have been closest, and then sizes the order from how much its
forecasts missed in the past, not from a flat guess. The same replay is shown
to the shopkeeper as proof, including a held-back check on the most recent
weeks that were not used to choose the method or size the cushion.

  backtest / plan      walk-forward evaluation + service-level ordering
  The numbers are computed in plain numpy so each step can be audited.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import advanced
import analytics
import shop

H = 7                      # forecast horizon, days
MIN_HISTORY = 28           # days of history before the first forecast
VERIFY_WEEKS = 6           # most recent weeks held back for the honest check
MAX_WEEKS = 26
FLAT_BUFFER = 0.15         # what the simple planner adds

METHODS = {
    "last_week": "Repeat last week",
    "avg4": "Last 4 weeks' average",
    "weekday": "Weekday-adjusted average",
    "smooth": "Smoothed weekly trend",
}


def _matrix(df: pd.DataFrame):
    r = shop.roles(df)
    item = r["item"]
    date = r["date"]
    measure = r["qty"] or r["amount"] or analytics.pick_metric(df, date)
    if not (date and item and measure):
        return None
    d = analytics.to_dates(df, date)
    t = pd.DataFrame({"d": d.dt.normalize(), "item": df[item], "m": df[measure].astype(float)}).dropna()
    if t.empty:
        return None
    wide = t.pivot_table(index="d", columns="item", values="m", aggfunc="sum", fill_value=0.0)
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max()), fill_value=0.0)
    keep = wide.sum().sort_values(ascending=False).head(40).index
    wide = wide[keep]
    return wide, ("units" if r["qty"] else analytics.pretty(measure))


def _forecasts(D: np.ndarray, dow: np.ndarray, t: int, fut: np.ndarray) -> dict:
    rate = D[t - 28:t].mean(axis=0)
    hist = D[max(0, t - 84):t]
    tot, wd = hist.sum(axis=1), dow[max(0, t - 84):t]
    overall = tot.mean() or 1.0
    factor = np.array([tot[wd == k].mean() / overall if (wd == k).any() else 1.0 for k in range(7)])
    mult = float(np.mean(factor[fut]))
    weeks = np.array([D[t - 7 * (k + 1):t - 7 * k].sum(axis=0) for k in range(min(8, t // 7) - 1, -1, -1)])
    level = weeks[0].copy()
    for w in weeks[1:]:
        level = 0.4 * w + 0.6 * level
    return {
        "last_week": D[t - 7:t].sum(axis=0),
        "avg4": rate * H,
        "weekday": rate * H * mult,
        "smooth": level,
    }


def _wape(F: np.ndarray, A: np.ndarray) -> float:
    return float(np.abs(F - A).sum() / max(A.sum(), 1e-9))


def backtest(df: pd.DataFrame) -> dict:
    m = _matrix(df)
    if m is None:
        return {"available": False, "reason": "I need a date column, a product column and a quantity or amount column to forecast."}
    wide, unit = m
    D, dates = wide.to_numpy(float), wide.index
    dow = dates.dayofweek.to_numpy()
    T = len(D)
    origins = list(range(T - H, MIN_HISTORY - 1, -H))[:MAX_WEEKS][::-1]
    if len(origins) < 10:
        return {"available": False, "reason": "I need at least about three months of daily sales to check my forecasts against the past."}

    F = {k: [] for k in METHODS}
    A = []
    for t in origins:
        fut = dow[t:t + H]
        f = _forecasts(D, dow, t, fut)
        for k in METHODS:
            F[k].append(f[k])
        A.append(D[t:t + H].sum(axis=0))
    F = {k: np.array(v) for k, v in F.items()}
    A = np.array(A)
    return {"available": True, "wide": wide, "unit": unit, "D": D, "dow": dow, "origins": origins, "F": F, "A": A}


def _quantile_cushion(E: np.ndarray, Fm: np.ndarray, Am: np.ndarray, q: float):
    """Per-product additive cushion; products with little history borrow a pooled ratio."""
    n, k = E.shape
    add = np.zeros(k)
    ratio = None
    ok = (Fm > 0)
    if ok.any():
        ratio = float(np.quantile((Am[ok] / Fm[ok]), q))
    per_product_ok = n >= 12
    for j in range(k):
        if per_product_ok:
            add[j] = float(np.quantile(E[:, j], q))
        else:
            add[j] = np.nan
    return add, (ratio if ratio is not None else 1.0 + FLAT_BUFFER)


def _order(F: np.ndarray, add: np.ndarray, ratio: float) -> np.ndarray:
    fixed = np.where(np.isnan(add), F * ratio, F + add)
    return np.ceil(np.maximum(fixed, 0.0))


def plan(df: pd.DataFrame, service: float = 0.95) -> dict:
    bt = backtest(df)
    if not bt["available"]:
        return bt
    wide, unit, D, dow, F, A = bt["wide"], bt["unit"], bt["D"], bt["dow"], bt["F"], bt["A"]
    n = A.shape[0]
    n_ver = VERIFY_WEEKS if n >= VERIFY_WEEKS + 10 else 0
    cal = slice(0, n - n_ver)
    ver = slice(n - n_ver, n)

    scores = {k: _wape(F[k][cal], A[cal]) for k in METHODS}
    best = min(scores, key=scores.get)
    Fb = F[best]
    E = A - Fb

    # honest check: size the cushion on the calibration weeks, test it on the held-back weeks
    check = None
    if n_ver:
        add, ratio = _quantile_cushion(E[cal], Fb[cal], A[cal], service)
        order_v = np.array([_order(Fb[i], add, ratio) for i in range(n - n_ver, n)])
        flat_v = np.ceil(Fb[ver] * (1 + FLAT_BUFFER))
        Av = A[ver]
        active = Av.sum(axis=0) > 0
        short_ours = float((order_v[:, active] < Av[:, active]).mean())
        short_flat = float((flat_v[:, active] < Av[:, active]).mean())
        check = {
            "weeks": n_ver,
            "in_stock_ours": 1 - short_ours, "in_stock_flat": 1 - short_flat,
            "extra_ours": float(np.maximum(order_v - Av, 0).sum() / max(Av.sum(), 1e-9)),
            "extra_flat": float(np.maximum(flat_v - Av, 0).sum() / max(Av.sum(), 1e-9)),
            "wape_verify": {k: _wape(F[k][ver], A[ver]) for k in METHODS},
        }

    # final cushion uses every week, then the real forecast for next week
    add, ratio = _quantile_cushion(E, Fb, A, service)
    lo_add, _ = _quantile_cushion(E, Fb, A, 0.10)
    hi_add, _ = _quantile_cushion(E, Fb, A, 0.90)
    T = len(D)
    last = wide.index[-1]
    fut_dows = np.array([(last + pd.Timedelta(days=i + 1)).dayofweek for i in range(H)])
    f_now = _forecasts(D, dow, T, fut_dows)[best]
    order_now = _order(f_now, add, ratio)
    lo = np.ceil(np.maximum(np.where(np.isnan(lo_add), f_now * 0.8, f_now + lo_add), 0))
    hi = np.ceil(np.maximum(np.where(np.isnan(hi_add), f_now * 1.2, f_now + hi_add), 0))

    wk_last = D[T - 7:T].sum(axis=0)
    a14, b14 = D[T - 14:T].sum(axis=0), D[T - 28:T - 14].sum(axis=0)
    rows = []
    for j, name in enumerate(wide.columns):
        if D[T - 28:T, j].sum() <= 0:
            continue
        ch = (a14[j] - b14[j]) / b14[j] if b14[j] > 0 else 0
        rows.append({
            "Product": str(name),
            "Sold last 7 days": int(round(wk_last[j])),
            "Likely next 7 days": int(round(f_now[j])),
            "Likely range": f"{int(lo[j])} to {int(hi[j])}",
            "Order about": int(max(order_now[j], np.ceil(f_now[j]))),
            "Trend": "rising" if ch >= 0.15 else "falling" if ch <= -0.15 else "steady",
        })
    rows.sort(key=lambda r: -r["Likely next 7 days"])

    proof_rows = [{
        "Method": METHODS[k] + ("  (chosen)" if k == best else ""),
        "Average miss": f"{scores[k]:.0%}",
        "Average miss on the latest weeks": f"{check['wape_verify'][k]:.0%}" if check else "n/a",
    } for k in sorted(METHODS, key=scores.get)]

    narrative = [
        f"To have enough stock in about {service:.0%} of weeks, order the figures in the last column. "
        f"I picked '{METHODS[best].lower()}' because, replayed over the last {len(A)} weeks, it missed by {scores[best]:.0%} on average "
        f"against {scores['last_week']:.0%} for simply repeating last week."
    ]
    if check:
        narrative.append(
            f"Honest check on the latest {check['weeks']} weeks, which were kept out of the sizing: you would have had enough stock "
            f"{check['in_stock_ours']:.0%} of the time, against {check['in_stock_flat']:.0%} with a flat 15% cushion. "
            f"Extra stock left over: {check['extra_ours']:.0%} of sales against {check['extra_flat']:.0%}."
        )
    return {
        "available": True, "unit": unit, "service": service, "method": METHODS[best],
        "columns": ["Product", "Sold last 7 days", "Likely next 7 days", "Likely range", "Order about", "Trend"],
        "rows": rows, "proof_rows": proof_rows, "check": check, "weeks_tested": int(len(A)),
        "narrative": narrative,
    }
