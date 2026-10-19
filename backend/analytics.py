"""
Analytics engine: the things a business owner wants to know before they ask.

  briefing    one-screen health check of the data (what it is, what stands out)
  trend       metric over time, direction, and an honest forecast with a backtest
  segments    groups of similar customers, named in plain words
  anomalies   rows that don't look like the rest, with the reason
  rank        who/what to act on first (scores a dataset with a trained model)

Everything is computed directly from the data with pandas / scikit-learn, so it
works offline and every number can be traced.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

MONEY_WORDS = ("price", "amount", "revenue", "sales", "income", "cost", "profit", "salary", "spend", "spent", "fee", "total", "value")
ADDITIVE_WORDS = ("sales", "revenue", "amount", "quantity", "qty", "units", "profit", "orders", "count", "total", "spend", "spent")
DEMOGRAPHIC_WORDS = ("age", "year", "zip", "pin", "phone", "rating", "score", "tenure", "latitude", "longitude")


def pretty(name: str) -> str:
    return re.sub(r"[_\s]+", " ", str(name)).strip().lower()


def is_money(col: str) -> bool:
    c = col.lower()
    return any(w in c for w in MONEY_WORDS) and "count" not in c and "quantity" not in c


def money(v: float) -> str:
    """₹ with Indian grouping and Lakh/Crore shorthand."""
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    s = f"{round(a):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{sign}₹{s}"


def number(v: float) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    a = abs(v)
    if a >= 1e7:
        return f"{v / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{v / 1e5:.2f} L"
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fmt(col: str, v: float) -> str:
    return money(v) if is_money(col) else number(v)


# ---------------------------------------------------------------------------
# Column roles
# ---------------------------------------------------------------------------


def _looks_like_id(series: pd.Series, name: str) -> bool:
    lname = name.lower()
    if lname in ("id", "index") or lname.endswith("_id") or lname.endswith("id"):
        return True
    if pd.api.types.is_integer_dtype(series):
        s = series.dropna()
        if len(s) > 1 and s.nunique() == len(s):
            ordered = s.sort_values().reset_index(drop=True)
            if (ordered.diff().dropna() == 1).all():
                return True
    return False


def detect_date_col(df: pd.DataFrame) -> str | None:
    """A column that is (or parses cleanly as) dates. Plain numbers never count."""
    best = None
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return col
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
            continue
        sample = s.dropna().astype(str).head(200)
        if sample.empty or sample.str.len().max() > 40:
            continue
        try:
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        except Exception:
            continue
        ok = parsed.notna().mean()
        hinted = any(w in col.lower() for w in ("date", "day", "time", "month", "when"))
        if ok >= 0.9 and (hinted or sample.str.contains(r"[-/]").mean() > 0.8):
            if best is None or hinted:
                best = col
    return best


def to_dates(df: pd.DataFrame, col: str) -> pd.Series:
    s = df[col]
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(s.astype(str), errors="coerce", format="mixed")


def numeric_cols(df: pd.DataFrame, exclude: tuple = ()) -> list[str]:
    out = []
    for c in df.columns:
        if c in exclude:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and not _looks_like_id(s, c):
            if s.nunique() > 1:
                out.append(c)
    return out


def pick_metric(df: pd.DataFrame, date_col: str | None = None) -> str | None:
    """The number a business cares about: sales/revenue/amount before anything else."""
    cands = numeric_cols(df, exclude=(date_col,) if date_col else ())
    if not cands:
        return None
    for words in (("sales", "revenue", "amount", "total"), ("profit", "spend", "spent", "income"), ("quantity", "qty", "units", "price")):
        for c in cands:
            if any(w in c.lower() for w in words):
                return c
    non_demo = [c for c in cands if not any(w in c.lower() for w in DEMOGRAPHIC_WORDS)]
    return (non_demo or cands)[0]


def pick_category(df: pd.DataFrame, exclude: tuple = ()) -> str | None:
    best, best_score = None, -1
    for c in df.columns:
        s = df[c]
        if c in exclude or pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        n = s.nunique()
        if not (2 <= n <= 60) or n > len(s) * 0.5 or _looks_like_id(s, c):
            continue
        score = 1
        if any(w in c.lower() for w in ("product", "item", "category", "city", "branch", "store", "region", "area", "type")):
            score += 3
        if 3 <= n <= 20:
            score += 1
        if score > best_score:
            best, best_score = c, score
    return best


def pick_outcome(df: pd.DataFrame) -> str | None:
    """A yes/no column such as purchased or churned, if the data has one."""
    for c in df.columns:
        s = df[c].dropna()
        if s.nunique() == 2 and any(w in c.lower() for w in ("purchase", "churn", "buy", "bought", "repeat", "convert", "default", "renew", "return")):
            return c
    return None


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


def quality(df: pd.DataFrame) -> dict:
    n = max(len(df), 1)
    issues = []
    score = 100.0

    miss = df.isna().mean()
    heavy = miss[miss > 0.0].sort_values(ascending=False)
    total_missing = float(df.isna().sum().sum() / (n * max(df.shape[1], 1)))
    if total_missing > 0:
        score -= min(35, total_missing * 120)
        worst = heavy.index[0]
        issues.append(f"{total_missing:.1%} of cells are blank; {pretty(worst)} has the most ({heavy.iloc[0]:.0%} of its rows).")

    dups = int(df.duplicated().sum())
    if dups:
        score -= min(20, dups / n * 100)
        issues.append(f"{dups} rows are exact repeats of another row.")

    constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    if constant:
        score -= 5 * len(constant)
        issues.append(f"{', '.join(pretty(c) for c in constant[:3])} never changes, so it tells you nothing.")

    padded = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and df[c].dropna().astype(str).map(lambda v: v != v.strip()).any()]
    if padded:
        score -= 3 * len(padded)
        issues.append(f"Extra spaces around values in {', '.join(pretty(c) for c in padded[:3])}.")

    if n < 50:
        score -= 15
        issues.append(f"Only {n} rows. Patterns found in so little data are weak.")

    score = int(max(0, min(100, round(score))))
    label = "Excellent" if score >= 90 else "Good" if score >= 75 else "Needs attention" if score >= 55 else "Poor"
    return {"score": score, "label": label, "issues": issues}


# ---------------------------------------------------------------------------
# Trends and forecast
# ---------------------------------------------------------------------------


def _freq_for(span_days: int) -> str:
    if span_days > 180:
        return "M"
    if span_days > 45:
        return "W"
    return "D"


def _label(period: pd.Period, freq: str) -> str:
    if freq == "M":
        return period.strftime("%b %Y")
    if freq == "W":
        return period.start_time.strftime("%d %b")
    return period.strftime("%d %b")


def trend(df: pd.DataFrame, date_col: str | None = None, metric: str | None = None, horizon: int | None = None) -> dict:
    date_col = date_col or detect_date_col(df)
    if not date_col:
        return {"available": False, "reason": "There is no date column, so there is nothing to show over time."}
    metric = metric or pick_metric(df, date_col)
    if not metric:
        return {"available": False, "reason": "There is no numeric column to track over time."}

    dates = to_dates(df, date_col)
    frame = pd.DataFrame({"d": dates, "v": pd.to_numeric(df[metric], errors="coerce")}).dropna()
    if len(frame) < 6:
        return {"available": False, "reason": "Too few dated rows to see a trend."}

    span = (frame["d"].max() - frame["d"].min()).days + 1
    freq = _freq_for(span)
    additive = any(w in metric.lower() for w in ADDITIVE_WORDS)
    agg = "sum" if additive else "mean"

    frame["p"] = frame["d"].dt.to_period(freq)
    series = frame.groupby("p")["v"].agg(agg)
    full = pd.period_range(series.index.min(), series.index.max(), freq=freq)
    series = series.reindex(full, fill_value=0.0 if additive else np.nan).interpolate()

    note = None
    last_p = series.index[-1]
    if freq in ("M", "W"):
        last_date = frame["d"].max()
        covered = (last_date - last_p.start_time).days + 1
        full_days = (last_p.end_time - last_p.start_time).days + 1
        if covered / full_days < 0.7 and len(series) > 6:
            note = f"{_label(last_p, freq)} is only partly over, so it was left out of the trend."
            series = series.iloc[:-1]

    n = len(series)
    if n < 4:
        return {"available": False, "reason": "Too few periods to see a trend."}

    vals = series.values.astype(float)
    k = max(1, n // 3)
    recent, before = vals[-k:].mean(), vals[-2 * k:-k].mean() if n >= 2 * k else vals[:k].mean()
    change = (recent - before) / abs(before) if before else 0.0
    direction = "up" if change > 0.05 else "down" if change < -0.05 else "steady"

    per = {"M": "month", "W": "week", "D": "day"}[freq]
    h = horizon or {"M": 3, "W": 4, "D": 7}[freq]

    fc = _forecast(series, freq, h)
    best_i, worst_i = int(np.argmax(vals)), int(np.argmin(vals))

    narrative = []
    word = {"up": "rising", "down": "falling", "steady": "holding steady"}[direction]
    narrative.append(
        f"{cap(pretty(metric))} is {word}: the latest {k} {per}{'s' if k > 1 else ''} averaged "
        f"{fmt(metric, recent)} per {per}, {'up' if change >= 0 else 'down'} {abs(change):.0%} on the {k} before."
        if direction != "steady"
        else f"{cap(pretty(metric))} is holding steady at about {fmt(metric, recent)} per {per}."
    )
    narrative.append(
        f"Best {per}: {_label(series.index[best_i], freq)} ({fmt(metric, vals[best_i])}). "
        f"Weakest: {_label(series.index[worst_i], freq)} ({fmt(metric, vals[worst_i])})."
    )
    if fc:
        nxt = fc["points"]
        narrative.append(
            f"If things carry on, the next {len(nxt)} {per}s should bring about "
            f"{fmt(metric, sum(p['value'] for p in nxt) if additive else float(np.mean([p['value'] for p in nxt])))}"
            f"{' in total' if additive else ' on average'}. "
            + (f"On past data this kind of forecast was typically off by about {fc['backtest_error']:.0%}." if fc.get("backtest_error") is not None else "")
        )
    if note:
        narrative.append(note)

    return {
        "available": True,
        "date_col": date_col,
        "metric": metric,
        "aggregate": agg,
        "freq": per,
        "direction": direction,
        "change_pct": float(change),
        "unit": "money" if is_money(metric) else "number",
        "series": [{"label": _label(p, freq), "value": float(v)} for p, v in zip(series.index, vals)],
        "forecast": fc["points"] if fc else [],
        "backtest_error": fc.get("backtest_error") if fc else None,
        "narrative": narrative,
    }


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _fit_forecast(vals: np.ndarray, h: int, freq: str):
    n = len(vals)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, vals, 1)
    trend_line = intercept + slope * x
    resid = vals - trend_line
    season = None
    if freq == "D" and n >= 28:
        idx = np.arange(n) % 7
        season = np.array([resid[idx == i].mean() for i in range(7)])
        resid = resid - season[idx]
    elif freq == "M" and n >= 24:
        idx = np.arange(n) % 12
        season = np.array([resid[idx == i].mean() for i in range(12)])
        resid = resid - season[idx]
    sd = float(resid.std(ddof=1)) if n > 2 else 0.0
    fx = np.arange(n, n + h)
    pred = intercept + slope * fx
    if season is not None:
        m = len(season)
        pred = pred + season[fx % m]
    return pred, sd


def _forecast(series: pd.Series, freq: str, h: int):
    vals = series.values.astype(float)
    n = len(vals)
    if n < 6:
        return None
    pred, sd = _fit_forecast(vals, h, freq)
    floor = 0.0 if vals.min() >= 0 else -np.inf
    points = []
    last = series.index[-1]
    for i in range(h):
        p = last + (i + 1)
        v = max(float(pred[i]), floor)
        spread = 1.96 * sd * math.sqrt(1 + (i + 1) / n)
        points.append({"label": _label(p, freq), "value": v, "low": max(v - spread, floor), "high": v + spread})

    backtest = None
    if n >= h + 8:
        p2, _ = _fit_forecast(vals[:-h], h, freq)
        actual = vals[-h:]
        denom = np.abs(actual).sum()
        if denom > 0:
            backtest = float(np.abs(actual - p2).sum() / denom)
    return {"points": points, "backtest_error": backtest}


# ---------------------------------------------------------------------------
# Concentration (Pareto)
# ---------------------------------------------------------------------------


def concentration(df: pd.DataFrame, cat: str, metric: str) -> dict | None:
    g = df.groupby(cat)[metric].sum(numeric_only=True).sort_values(ascending=False)
    g = g[g > 0]
    if len(g) < 4:
        return None
    total = g.sum()
    cum = g.cumsum() / total
    n80 = int((cum < 0.8).sum() + 1)
    top_share = float(g.iloc[: max(1, round(len(g) * 0.2))].sum() / total)
    return {
        "category": cat,
        "metric": metric,
        "n_groups": int(len(g)),
        "n_for_80": n80,
        "top20_share": top_share,
        "leader": str(g.index[0]),
        "leader_share": float(g.iloc[0] / total),
        "laggard": str(g.index[-1]),
        "ranking": [{"name": str(k), "value": float(v)} for k, v in g.head(8).items()],
    }


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

DESCRIPTORS = {
    "age": ("older", "younger"),
    "tenure": ("longer-standing", "newer"),
    "income": ("higher income", "lower income"),
    "score": ("higher scoring", "lower scoring"),
}


def _describe(col: str, high: bool) -> str:
    key = next((k for k in DESCRIPTORS if k in col.lower()), None)
    if key:
        return DESCRIPTORS[key][0 if high else 1]
    return f"{'higher' if high else 'lower'} {pretty(col)}"


def segments(df: pd.DataFrame, max_k: int = 5) -> dict:
    nums = numeric_cols(df)[:6]
    outcome = pick_outcome(df)
    if outcome in nums:
        nums.remove(outcome)
    cats = []
    for c in df.columns:
        s = df[c]
        if c in nums or c == outcome or pd.api.types.is_numeric_dtype(s) or _looks_like_id(s, c):
            continue
        if 2 <= s.nunique() <= 8:
            cats.append(c)
    cats = cats[:2]
    if len(nums) < 2 or len(df) < 30:
        return {"available": False, "reason": "Need at least 30 rows and two number columns to find groups."}

    X = df[nums].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median())
    parts = [pd.DataFrame(StandardScaler().fit_transform(X), columns=nums, index=df.index)]
    if cats:
        parts.append(pd.get_dummies(df[cats].astype(str), dtype=float) * 0.6)
    M = pd.concat(parts, axis=1).values

    best, best_s = None, -1.0
    for k in range(2, min(max_k, len(df) // 10) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(M)
        s = silhouette_score(M, km.labels_)
        if s > best_s:
            best, best_s = km, s
    if best is None:
        return {"available": False, "reason": "Couldn't find clear groups."}

    labels = best.labels_
    overall_mean, overall_std = X.mean(), X.std().replace(0, 1)
    out, used = [], set()
    for lab in sorted(set(labels), key=lambda l: -(labels == l).sum()):
        mask = labels == lab
        z = ((X[mask].mean() - overall_mean) / overall_std)
        top = z.abs().sort_values(ascending=False)
        traits = [_describe(c, z[c] > 0) for c in top.index[:2] if abs(z[c]) >= 0.5]
        for c in cats:
            share = df.loc[mask, c].astype(str).value_counts(normalize=True)
            base = df[c].astype(str).value_counts(normalize=True)
            v = share.index[0]
            if share.iloc[0] >= 0.5 and share.iloc[0] - base.get(v, 0) >= 0.2:
                traits.append(f"mostly {v}")
        name = cap(", ".join(traits[:3])) if traits else "The typical group"
        base_name, i = name, 2
        while name in used:
            name, i = f"{base_name} ({i})", i + 1
        used.add(name)
        seg = {
            "name": name,
            "size": int(mask.sum()),
            "share": float(mask.mean()),
            "averages": [{"column": c, "value": float(X.loc[mask, c].mean()), "display": fmt(c, float(X.loc[mask, c].mean()))} for c in nums[:4]],
        }
        if outcome:
            pos = df.loc[mask, outcome]
            top_val = sorted(df[outcome].dropna().unique(), key=str)[-1]
            seg["outcome"] = {"column": outcome, "rate": float((pos == top_val).mean()), "positive": str(top_val)}
        out.append(seg)

    narrative = [f"Your data falls into {len(out)} natural groups. The biggest is “{out[0]['name']}” ({out[0]['share']:.0%} of rows)."]
    if outcome:
        ranked = sorted(out, key=lambda s: -s["outcome"]["rate"])
        a, b = ranked[0], ranked[-1]
        if a["outcome"]["rate"] - b["outcome"]["rate"] >= 0.1:
            narrative.append(
                f"“{a['name']}” has the highest {pretty(outcome)} rate ({a['outcome']['rate']:.0%}); "
                f"“{b['name']}” the lowest ({b['outcome']['rate']:.0%})."
            )
    return {"available": True, "k": len(out), "silhouette": float(best_s), "features": nums, "segments": out, "narrative": narrative}


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------


def _baselines(df: pd.DataFrame, X: pd.DataFrame):
    """
    What is 'normal' for each row, per number column.

    A 5kg bag of basmati costing more than a litre of milk is not unusual; it is
    just basmati. So when a text column (product, city...) explains most of a
    number column's variation, 'normal' means normal *for that group*; otherwise
    it is the overall median. Returns (baseline frame, {column: group column}).
    """
    cats = [
        c for c in df.columns
        if c not in X.columns and not pd.api.types.is_numeric_dtype(df[c])
        and 2 <= df[c].nunique() <= 30 and not _looks_like_id(df[c], c)
    ]
    base = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)
    used = {}
    for c in X.columns:
        total = X[c].var()
        best, best_eta = None, 0.5          # only trust a strong explanation
        if total and total > 0:
            for g in cats:
                grp = df[g].fillna("unknown")
                means = X[c].groupby(grp).transform("mean")
                eta = float(((means - X[c].mean()) ** 2).sum() / ((X[c] - X[c].mean()) ** 2).sum())
                if eta > best_eta:
                    best, best_eta = g, eta
        if best:
            base[c] = X[c].groupby(df[best].fillna("unknown")).transform("median")
            used[c] = best
        else:
            base[c] = X[c].median()
    return base, used


def anomalies(df: pd.DataFrame, top: int = 8) -> dict:
    nums = numeric_cols(df)
    if len(nums) < 1 or len(df) < 30:
        return {"available": False, "reason": "Need at least 30 rows and a number column to spot unusual ones."}

    X = df[nums].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median())
    base, used = _baselines(df, X)

    resid = X - base
    mad = resid.abs().median().replace(0, np.nan)
    scale = (mad * 1.4826).fillna(resid.std().replace(0, 1)).fillna(1)
    Z = resid / scale

    iso = IsolationForest(n_estimators=200, contamination=min(0.05, max(0.01, 5 / len(df))), random_state=42).fit(Z)
    score = -iso.score_samples(Z)
    flagged = np.argsort(-score)[:top]
    flagged = [i for i in flagged if iso.predict(Z.iloc[[i]])[0] == -1]

    shown_cols = [c for c in df.columns if not _looks_like_id(df[c], c)][:7]
    id_cols = [c for c in df.columns if _looks_like_id(df[c], c)][:1]
    rows = []
    for i in flagged:
        z = Z.iloc[i]
        reasons = []
        for c in z.abs().sort_values(ascending=False).index[:2]:
            if abs(z[c]) < 2.5:
                continue
            val, norm = X.iloc[i][c], base.iloc[i][c]
            # A statistically big gap that is tiny in real terms (Rs 533 vs Rs 521)
            # is noise in a very steady column, not something worth a person's time.
            if norm and abs(val - norm) / abs(norm) < 0.15:
                continue
            where = f"typical for {df.iloc[i][used[c]]}" if c in used else "typical"
            ratio = val / norm if norm else None
            if ratio and ratio > 2:
                reasons.append(f"{pretty(c)} of {fmt(c, val)} is {ratio:.1f}× the {where} {fmt(c, norm)}")
            else:
                reasons.append(f"{pretty(c)} of {fmt(c, val)} is far from the {where} {fmt(c, norm)}")
        if not reasons:
            reasons.append("An unusual combination of values, though none is extreme alone")
        row = {c: _plain(df.iloc[i][c]) for c in id_cols + shown_cols}
        rows.append({"row_number": int(i) + 2, "values": row, "reasons": reasons, "score": float(score[i])})

    narrative = (
        [f"{len(rows)} of {len(df):,} rows look unusual. Check whether they are mistakes or genuinely special cases. The most unusual is row {rows[0]['row_number']}: {rows[0]['reasons'][0]}."]
        if rows else ["Nothing stands out. No rows look unusual compared with the rest."]
    )
    return {"available": True, "count": len(rows), "rows": rows, "narrative": narrative}


def _plain(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else round(float(v), 2)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if pd.isna(v):
        return None
    return v


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------


def briefing(df: pd.DataFrame, raw: pd.DataFrame | None = None) -> dict:
    """The first thing someone sees: what this data is and what stands out."""
    q = quality(raw if raw is not None else df)
    date_col = detect_date_col(df)
    metric = pick_metric(df, date_col)
    cat = pick_category(df, exclude=(date_col,) if date_col else ())
    outcome = pick_outcome(df)

    headline, stats, charts, ask = [], [], [], []
    stats.append({"label": "rows", "value": f"{len(df):,}"})
    stats.append({"label": "columns", "value": f"{df.shape[1]}"})

    scope = f"This file has {len(df):,} rows"
    t = None
    if date_col:
        d = to_dates(df, date_col).dropna()
        if len(d):
            scope += f" from {d.min():%d %b %Y} to {d.max():%d %b %Y}"
            stats.append({"label": "period", "value": f"{(d.max() - d.min()).days + 1} days"})
    headline.append(scope + ".")

    if metric:
        col = pd.to_numeric(df[metric], errors="coerce")
        if any(w in metric.lower() for w in ADDITIVE_WORDS):
            stats.append({"label": f"total {pretty(metric)}", "value": fmt(metric, float(col.sum()))})
        stats.append({"label": f"typical {pretty(metric)}", "value": fmt(metric, float(col.median()))})

    if date_col and metric:
        t = trend(df, date_col, metric)
        if t["available"]:
            headline.append(t["narrative"][0])
            charts.append({"chart": "line", "title": f"{cap(pretty(metric))} by {t['freq']}", "unit": t["unit"], "points": t["series"], "forecast": t["forecast"]})
            ask.append(f"What will {pretty(metric)} look like next {t['freq']}?")

    if cat and metric:
        c = concentration(df, cat, metric)
        if c:
            if c["n_for_80"] <= 0.75 * c["n_groups"]:
                headline.append(
                    f"{c['n_for_80']} of your {c['n_groups']} {pretty(cat)} values bring in 80% of {pretty(metric)}. "
                    f"{c['leader']} leads with {c['leader_share']:.0%}."
                )
            else:
                headline.append(
                    f"{cap(pretty(metric))} is spread fairly evenly across {pretty(cat)}; "
                    f"{c['leader']} leads with {c['leader_share']:.0%}."
                )
            charts.append({"chart": "bar", "title": f"{cap(pretty(metric))} by {pretty(cat)}", "unit": "money" if is_money(metric) else "number",
                           "points": [{"label": r["name"], "value": r["value"]} for r in c["ranking"]], "forecast": []})
            ask.append(f"Which {pretty(cat)} gives the most {pretty(metric)}?")

    if outcome:
        pos = sorted(df[outcome].dropna().unique(), key=str)[-1]
        rate = float((df[outcome] == pos).mean())
        headline.append(f"{rate:.0%} of rows have {pretty(outcome)} = {pos}.")
        stats.append({"label": pretty(outcome), "value": f"{rate:.0%}"})
        ask.append(f"What affects {pretty(outcome)}?")

    sg = segments(df)
    if sg["available"]:
        headline.append(sg["narrative"][0])
        ask.append("Show me my customer groups")
    an = anomalies(df)
    if an["available"] and an["count"]:
        headline.append(f"{an['count']} rows look unusual and may deserve a second look.")
        ask.append("Which rows look unusual?")

    headline.append(f"Data health: {q['score']}/100 ({q['label'].lower()}).")
    try:
        import advanced
        if advanced.stock_plan(df)["available"]:
            ask.insert(1, "How much should I order for next week?")
        if advanced.rfm(df)["available"]:
            ask.insert(1, "Which customers should I call first?")
    except Exception:
        pass
    ask += [f"How many rows have {pretty(cat)} = {df[cat].mode().iloc[0]}?"] if cat else []
    ask = list(dict.fromkeys(ask))[:7]

    return {
        "headline": headline,
        "stats": stats,
        "quality": q,
        "charts": charts,
        "roles": {"date": date_col, "metric": metric, "category": cat, "outcome": outcome},
        "suggested_questions": ask,
    }


# ---------------------------------------------------------------------------
# Intent detection for chat
# ---------------------------------------------------------------------------

INTENTS = [
    ("messages", r"\b(whatsapp|sms|draft|write (a |the )?(message|text)|(message|text|msg)s?\b.{0,30}\b(customers?|supplier|wholesaler|reminder)|reminder (message|text)s?|send (a )?(message|reminder))\b"),
    ("chart", r"\b(chart|graph|plot|visuali[sz]e|bar ?chart|breakdown of|split (of )?)\b"),
    ("udhaar", r"\b(udhaar|udhar|khata|credit (sales?|customers?|given|balance)|owe[sd]?|dues?|pending (payment|amount|balance)s?|unpaid|baki|outstanding|recover(y)? (of )?(my )?money|who (has not|hasn'?t) paid)\b"),
    ("festival", r"\b(festivals?|diwali|deepavali|dhanteras|holi|eid|rakhi|raksha ?bandhan|dussehra|navratri|karva ?chauth|christmas|lohri|upcoming (rush|season)|wedding season)\b"),
    ("profit", r"\b(profit\w*|margins?|markup|loss.?making|cost price|which (product|item)s? (earn|make)s?|where (do|am) i (make|lose)|how much (do )?i (earn|make)|earn(ing)?s?)\b"),
    ("slow", r"\b(dead stock|slow.?moving?|slow movers?|not selling|stopped selling|unsold|stuck stock|clearance|fading|stop (buying|ordering)|what (should|can) i (stop|clear))\b"),
    ("bundles", r"\b(bought together|buy together|combos?|bundles?|pairs?|goes? with|cross.?sell|also buy|sold together)\b"),
    ("peak", r"\b(busiest|slowest|quietest|peak|rush hours?|which (day|days|weekday)|best day|worst day|staff\w*|extra (help|person))\b"),
    ("stock", r"\b(stock plan|re-?stock|re-?order|how much (.{0,25})(order|buy|stock)|what (should|to) (i )?(order|buy|stock)|inventory|order list|shopping list|purchase plan)\b"),
    ("rfm", r"\b(best|top|loyal|valuable|lost|inactive|at.?risk|win.?back|lapsed|dormant)\b.{0,25}\bcustomers?\b|\bcustomers?\b.{0,30}(haven'?t|have not|stopped|not (come|back|return|visit)|gone quiet|at.?risk|lost|inactive|call first)|\b(rfm|win.?back)\b"),
    ("chart", r"\b(chart|graph|plot|visuali[sz]e|bar ?chart|breakdown of|split (of )?)\b"),
    ("playbook", r"\b(what (should|can|do) i do|what to do|playbook|to-?do|action (plan|items?)|advice|suggest\w*|recommend\w*|tips?|how (can|do) i (grow|improve|increase)|grow my|increase (my )?sales|improve (my )?(sales|business)|today)\b"),
    ("briefing", r"\b(summary|summari[sz]e|overview|briefing|health check|tell me about (this|my) (data|file)|what('s| is) (in )?(this|my) (data|file)|insights?)\b"),
    ("forecast", r"\b(forecast|predict(ion)? (for )?(next|future)|next (month|week|day|year|quarter)|will .* (be|look like) next|future)\b"),
    ("trend", r"\b(trend|over time|growing|growth|declin\w*|per (month|week|day)|monthly|weekly|daily|seasonal\w*|by month|by week|going (up|down))\b"),
    ("segments", r"\b(segments?|groups? of|types of (customers|people)|customer (groups|types)|cluster\w*|categori[sz]e (my )?customers|my customer groups)\b"),
    ("anomalies", r"\b(unusual|anomal\w*|outliers?|weird|strange|suspicious|odd|mistakes?|errors?)\b"),
    ("quality", r"\b(data (quality|health)|clean(ing)? (needed|issues)|is (my|the) data (ok|good|clean)|missing (values|data))\b"),
]


def detect_intent(question: str) -> str | None:
    q = question.lower()
    for name, pat in INTENTS:
        if re.search(pat, q):
            return name
    return None


# ---------------------------------------------------------------------------
# Playbook: plain things to do, in priority order
# ---------------------------------------------------------------------------

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def playbook(df: pd.DataFrame, raw: pd.DataFrame | None = None) -> dict:
    """
    What a shopkeeper could do this week, worked out from the file alone.
    Each item: {"tone": do|watch|good, "title", "detail"}. Nothing here is
    guessed by a language model; every sentence is built from a computed number.
    """
    import trust

    items = []
    date = detect_date_col(df)
    metric = pick_metric(df, date)
    cat = pick_category(df, exclude=(date,) if date else ())
    outcome = pick_outcome(df)

    if date and metric:
        d = to_dates(df, date)
        data = df.loc[d.notna()].assign(_d=d[d.notna()])
        if len(data) >= 30:
            end = data["_d"].max()
            recent = data[data["_d"] > end - pd.Timedelta(days=30)]
            prior = data[(data["_d"] <= end - pd.Timedelta(days=30)) & (data["_d"] > end - pd.Timedelta(days=60))]
            if len(recent) >= 10 and len(prior) >= 10 and prior[metric].sum() > 0:
                r, pr = float(recent[metric].sum()), float(prior[metric].sum())
                chg = (r - pr) / pr
                items.append({
                    "tone": "good" if chg >= 0 else "watch",
                    "title": f"{cap(pretty(metric))} in the last 30 days: {fmt(metric, r)}",
                    "detail": f"That is {abs(chg):.0%} {'more' if chg >= 0 else 'less'} than the 30 days before ({fmt(metric, pr)}).",
                })
                if cat:
                    gr = recent.groupby(cat)[metric].sum()
                    gp = prior.groupby(cat)[metric].sum()
                    both = pd.concat([gr.rename("r"), gp.rename("p")], axis=1).fillna(0)
                    both = both[both["p"] >= 0.03 * pr]
                    both["chg"] = (both["r"] - both["p"]) / both["p"]
                    if len(both):
                        low = both["chg"].idxmin()
                        if both.loc[low, "chg"] <= -0.15:
                            items.append({
                                "tone": "do",
                                "title": f"{low} is selling {abs(both.loc[low, 'chg']):.0%} less than last month",
                                "detail": "Check its price, freshness, shelf position or whether a competitor changed something. A quick fix here is worth the most.",
                            })
                        high = both["chg"].idxmax()
                        if both.loc[high, "chg"] >= 0.15:
                            items.append({
                                "tone": "good",
                                "title": f"{high} is selling {both.loc[high, 'chg']:.0%} more than last month",
                                "detail": "Keep extra stock so you do not run out while it is popular.",
                            })
            daily = data.groupby(data["_d"].dt.normalize())[metric].sum()
            if len(daily) >= 21:
                wd = daily.groupby(daily.index.dayofweek).mean()
                avg = float(daily.mean())
                best, worst = int(wd.idxmax()), int(wd.idxmin())
                if avg > 0 and wd.iloc[best] >= avg * 1.15:
                    items.append({
                        "tone": "do",
                        "title": f"Stock up before {WEEKDAYS[best]}",
                        "detail": f"{WEEKDAYS[best]} is your busiest day: about {fmt(metric, float(wd.iloc[best]))}, {wd.iloc[best] / avg - 1:.0%} above a normal day.",
                    })
                if avg > 0 and wd.iloc[worst] <= avg * 0.85:
                    items.append({
                        "tone": "do",
                        "title": f"{WEEKDAYS[worst]} is your quietest day",
                        "detail": f"About {fmt(metric, float(wd.iloc[worst]))}, {1 - wd.iloc[worst] / avg:.0%} below a normal day. A small offer or restocking day fits here.",
                    })

    if cat and metric:
        c = concentration(df, cat, metric)
        if c and len(c["ranking"]) >= 3:
            top3 = sum(r["value"] for r in c["ranking"][:3])
            total = float(df.groupby(cat)[metric].sum(numeric_only=True).clip(lower=0).sum())
            if total > 0 and top3 / total >= 0.5:
                names = ", ".join(r["name"] for r in c["ranking"][:3])
                sells = any(w in cat.lower() for w in ("product", "item", "sku", "category", "goods", "brand"))
                if sells:
                    items.append({
                        "tone": "do",
                        "title": f"Never run out of {names}",
                        "detail": f"These three bring {top3 / total:.0%} of your total {pretty(metric)}.",
                    })
                else:
                    items.append({
                        "tone": "watch",
                        "title": f"Most of your {pretty(metric)} comes from {names}",
                        "detail": f"These three {pretty(cat)} values make up {top3 / total:.0%} of the total, so a problem there would hurt a lot.",
                    })

    if outcome and cat:
        s = df[outcome].dropna().astype(str)
        pos = trust.positive_class(sorted(s.unique()))
        g = df.assign(_y=(df[outcome].astype(str) == pos)).groupby(cat)["_y"].agg(["mean", "size"])
        g = g[g["size"] >= 10]
        if len(g) >= 2:
            lo, hi = g["mean"].idxmin(), g["mean"].idxmax()
            if g.loc[hi, "mean"] - g.loc[lo, "mean"] >= 0.10:
                items.append({
                    "tone": "do",
                    "title": f"Focus on {lo}",
                    "detail": f"Only {g.loc[lo, 'mean']:.0%} of customers there have {pretty(outcome)} = {pos}, against {g.loc[hi, 'mean']:.0%} in {hi}.",
                })

    an = anomalies(df, top=5)
    if an.get("available") and an["count"]:
        items.append({
            "tone": "watch",
            "title": f"Check {an['count']} unusual entries",
            "detail": "They may be billing mistakes or genuine bulk orders. Ask me to show unusual rows.",
        })

    q = quality(raw if raw is not None else df)
    if q["score"] < 80 and q["issues"]:
        items.append({"tone": "watch", "title": f"Tidy your data ({q['score']}/100)", "detail": q["issues"][0]})

    order = {"do": 0, "watch": 1, "good": 2}
    items.sort(key=lambda i: order[i["tone"]])
    items = items[:6]
    if not items:
        return {"available": False, "reason": "I need dates and a sales or amount column, or a yes/no column such as purchased, to suggest actions."}
    return {
        "available": True,
        "items": items,
        "headline": f"{len(items)} things worth your attention, most useful first.",
    }
