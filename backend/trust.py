"""
Trust layer: everything that answers "should I believe this prediction?"

  check_row      out-of-range / unseen-value guard against the training data
  explain_row    per-prediction explanation (Monte-Carlo Shapley values)
  sweep          what-if curve: how the answer moves as one input changes
  audit          fairness audit of held-out predictions across a group column
  monitor        summary of the prediction log (volume, trust, drift)

No extra dependencies — Shapley values are estimated directly from the fitted
sklearn pipeline, so this works for every model the AutoML engine can pick.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def pretty(name: str) -> str:
    return re.sub(r"[_\s]+", " ", str(name)).strip().lower()


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "blank"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        v = float(v)
        if abs(v) >= 100:
            return f"{v:,.0f}"
        if abs(v) >= 10:
            return f"{v:,.1f}".rstrip("0").rstrip(".")
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "")


def _coerce_frame(rows: list[dict], features: list[str], reference: dict) -> pd.DataFrame:
    """Build a frame with exactly the training columns; numbers become numbers."""
    frame = pd.DataFrame(rows)
    for f in features:
        if f not in frame.columns:
            frame[f] = np.nan
    frame = frame[features].copy()
    for f in features:
        kind = reference.get(f, {}).get("kind") or (
            "numeric" if pd.api.types.is_numeric_dtype(frame[f]) else "categorical"
        )
        if kind == "numeric":
            frame[f] = pd.to_numeric(frame[f], errors="coerce")
        else:
            frame[f] = frame[f].map(lambda v: np.nan if _is_blank(v) else str(v)).astype(object)
    return frame


# ---------------------------------------------------------------------------
# 1. Out-of-range guard
# ---------------------------------------------------------------------------

LEVELS = ["low", "medium", "high"]


def check_row(reference: dict, row: dict, confidence: float | None = None) -> dict:
    """
    Compare one input against what the model was trained on.

    Returns {"level": high|medium|low, "reasons": [plain strings], "flags": [...]}.
    A model is only a summary of its training data; outside it, the number it
    prints is a guess dressed as a result, so we say so.
    """
    flags = []
    for feat, ref in reference.items():
        label = pretty(feat)
        raw = row.get(feat)

        if _is_blank(raw):
            flags.append(
                {
                    "feature": feat,
                    "severity": "warn",
                    "kind": "missing",
                    "message": f"No {label} was given, so a typical value was assumed.",
                }
            )
            continue

        if ref["kind"] == "numeric":
            try:
                val = float(raw)
            except (TypeError, ValueError):
                flags.append(
                    {
                        "feature": feat,
                        "severity": "alert",
                        "kind": "not_a_number",
                        "message": f"{label.capitalize()} should be a number but got “{raw}”.",
                    }
                )
                continue
            lo, hi = ref["min"], ref["max"]
            if val < lo or val > hi:
                flags.append(
                    {
                        "feature": feat,
                        "severity": "alert",
                        "kind": "out_of_range",
                        "message": (
                            f"{label.capitalize()} of {_fmt(val)} is outside anything the model "
                            f"learned from (it saw {_fmt(lo)} to {_fmt(hi)})."
                        ),
                    }
                )
            elif ref["max"] > ref["min"] and (val < ref["p01"] or val > ref["p99"]):
                flags.append(
                    {
                        "feature": feat,
                        "severity": "warn",
                        "kind": "extreme",
                        "message": f"{label.capitalize()} of {_fmt(val)} is at the very edge of the data the model saw.",
                    }
                )
        else:
            seen = ref["values"]
            if str(raw) not in seen:
                lowered = {k.lower(): k for k in seen}
                hint = ""
                if str(raw).strip().lower() in lowered:
                    hint = f" Did you mean “{lowered[str(raw).strip().lower()]}”?"
                flags.append(
                    {
                        "feature": feat,
                        "severity": "alert",
                        "kind": "unseen_category",
                        "message": f"“{raw}” never appeared in {label} when the model was trained.{hint}",
                    }
                )
            elif seen[str(raw)] < 3:
                flags.append(
                    {
                        "feature": feat,
                        "severity": "warn",
                        "kind": "rare_category",
                        "message": f"“{raw}” appeared only {seen[str(raw)]} time(s) in {label}; the model knows little about it.",
                    }
                )

    alerts = sum(1 for f in flags if f["severity"] == "alert")
    warns = sum(1 for f in flags if f["severity"] == "warn")
    level = "high"
    if alerts:
        level = "low"
    elif warns:
        level = "medium"

    reasons = [f["message"] for f in sorted(flags, key=lambda f: f["severity"] != "alert")]

    if confidence is not None and confidence < 0.6:
        reasons.append(f"The model itself is unsure here (only {confidence:.0%} confident).")
        # Uncertainty alone caps trust at "medium"; "low" is reserved for inputs
        # outside the training data, which is what its explanation text promises.
        if level == "high":
            level = "medium"

    return {"level": level, "reasons": reasons, "flags": flags}


TRUST_PHRASE = {
    "high": "Looks like the data the model learned from, so you can lean on this answer.",
    "medium": "Mostly familiar, with a few caveats. Treat this as a good estimate, not a promise.",
    "low": "This is outside what the model has seen. Treat the number as a rough guess.",
}


# ---------------------------------------------------------------------------
# 2. Per-prediction explanation (Monte-Carlo Shapley)
# ---------------------------------------------------------------------------


def _scorer(pipeline, task: str, target_class: str | None):
    """Return f(frame) -> 1-D array: P(target_class) for classifiers, value for regressors."""
    if task == "classification":
        classes = [str(c) for c in pipeline.named_steps["model"].classes_]
        idx = classes.index(str(target_class)) if target_class is not None and str(target_class) in classes else 0

        def f(frame):
            return pipeline.predict_proba(frame)[:, idx]

        return f

    def g(frame):
        return np.asarray(pipeline.predict(frame), dtype=float)

    return g


def explain_row(
    pipeline,
    features: list[str],
    task: str,
    row: dict,
    background: pd.DataFrame,
    reference: dict,
    target_class: str | None = None,
    n_perm: int = 40,
    seed: int = 7,
) -> dict:
    """
    Shapley-value attribution for one row.

    For random feature orderings we start from a random background row and swap
    in this row's values one feature at a time, recording how the output moves.
    Averaged over orderings, each feature's marginal move is its Shapley value,
    and the contributions add up exactly to (output - base).
    """
    rng = np.random.default_rng(seed)
    x = _coerce_frame([row], features, reference).iloc[0]
    bg = _coerce_frame(background[features].to_dict("records"), features, reference)
    f = _scorer(pipeline, task, target_class)

    n = len(features)
    frames = []
    perms = []
    for _ in range(n_perm):
        perm = rng.permutation(n)
        z = bg.iloc[int(rng.integers(len(bg)))]
        perms.append(perm)
        cur = z.copy()
        frames.append(cur.copy())
        for j in perm:
            cur[features[j]] = x[features[j]]
            frames.append(cur.copy())

    batch = pd.DataFrame(frames).reset_index(drop=True)
    for col in features:
        if reference.get(col, {}).get("kind") == "numeric":
            batch[col] = pd.to_numeric(batch[col], errors="coerce")
        else:
            batch[col] = batch[col].astype(object)
    out = f(batch)

    contrib = np.zeros(n)
    base_vals = []
    pos = 0
    for perm in perms:
        base_vals.append(out[pos])
        prev = out[pos]
        for k, j in enumerate(perm):
            cur = out[pos + 1 + k]
            contrib[j] += cur - prev
            prev = cur
        pos += n + 1
    contrib /= n_perm
    base = float(np.mean(base_vals))
    final = float(f(_coerce_frame([row], features, reference))[0])

    rows_out = []
    for i, feat in enumerate(features):
        ref = reference.get(feat, {})
        rows_out.append(
            {
                "feature": feat,
                "value": None if _is_blank(row.get(feat)) else row.get(feat),
                "contribution": float(contrib[i]),
                "context": _context(ref, x[feat]),
            }
        )
    rows_out.sort(key=lambda r: abs(r["contribution"]), reverse=True)

    return {
        "kind": "probability" if task == "classification" else "value",
        "target_class": target_class,
        "base": base,
        "output": final,
        "contributions": rows_out,
    }


def _context(ref: dict, value) -> str | None:
    """How this value compares to normal: 'higher than usual', 'a common choice'..."""
    if not ref or _is_blank(value):
        return None
    if ref["kind"] == "numeric":
        std = ref.get("std") or 0
        if std == 0:
            return None
        z = (float(value) - ref["mean"]) / std
        if z > 1.0:
            return "higher than usual"
        if z < -1.0:
            return "lower than usual"
        return "about average"
    seen = ref.get("values", {})
    total = sum(seen.values()) or 1
    share = seen.get(str(value), 0) / total
    if share >= 0.3:
        return "a very common choice"
    if share <= 0.05:
        return "an uncommon choice"
    return None


def narrate_explanation(exp: dict, target_label: str, task: str, top: int = 3) -> str:
    """Plain-English reading of an explanation: the few inputs that mattered, and which way."""
    unit = "points" if exp["kind"] == "probability" else None
    parts = []
    for c in exp["contributions"][:top]:
        amount = c["contribution"] * 100 if unit else c["contribution"]
        if abs(amount) < (0.5 if unit else 1e-9) or _is_blank(c.get("value")):
            continue
        direction = "raised" if amount > 0 else "lowered"
        ctx = f" ({c['context']})" if c.get("context") else ""
        size = f"{abs(amount):.0f} {'point' if round(abs(amount)) == 1 else unit}" if unit else _fmt(abs(amount))
        parts.append(f"{pretty(c['feature'])} of {_fmt(c['value'])}{ctx} {direction} it by about {size}")
    if not parts:
        return "No single input moved this answer much; it sits close to the typical result."
    return "; ".join(parts).capitalize() + "."


# ---------------------------------------------------------------------------
# 3. What-if sweep
# ---------------------------------------------------------------------------


def sweep(
    pipeline,
    features: list[str],
    task: str,
    row: dict,
    feature: str,
    reference: dict,
    target_class: str | None = None,
    points: int = 14,
) -> dict:
    """Vary one input across its realistic range, holding the rest fixed."""
    if feature not in features:
        raise ValueError(f"'{feature}' is not an input of this model.")
    ref = reference.get(feature, {})
    base_row = {f: row.get(f) for f in features}

    if ref.get("kind") == "numeric":
        lo, hi = ref["p01"], ref["p99"]
        if hi <= lo:
            lo, hi = ref["min"], ref["max"]
        grid = list(np.linspace(lo, hi, points))
        cur = pd.to_numeric(pd.Series([row.get(feature)]), errors="coerce").iloc[0]
        if not math.isnan(cur):
            grid.append(float(cur))
        grid = sorted(set(grid))
        if ref.get("is_integer"):
            grid = sorted({int(round(g)) for g in grid})
        else:
            grid = [round(g, 4) for g in grid]
    else:
        vals = list(ref.get("values", {}).keys())[:12]
        if not _is_blank(row.get(feature)) and str(row.get(feature)) not in vals:
            vals.append(str(row.get(feature)))
        grid = vals

    rows = [{**base_row, feature: g} for g in grid]
    frame = _coerce_frame(rows, features, reference)
    f = _scorer(pipeline, task, target_class)
    out = f(frame)

    cur_frame = _coerce_frame([base_row], features, reference)
    current = float(f(cur_frame)[0])
    pts = [{"value": g, "output": float(o)} for g, o in zip(grid, out)]
    best = max(pts, key=lambda p: p["output"])
    worst = min(pts, key=lambda p: p["output"])
    return {
        "feature": feature,
        "kind": ref.get("kind", "numeric"),
        "output_kind": "probability" if task == "classification" else "value",
        "target_class": target_class,
        "current_value": None if _is_blank(row.get(feature)) else row.get(feature),
        "current_output": current,
        "points": pts,
        "best": best,
        "worst": worst,
    }


# ---------------------------------------------------------------------------
# 4. Fairness audit
# ---------------------------------------------------------------------------

SENSITIVE_HINTS = (
    "gender", "sex", "age", "religion", "caste", "race", "ethnic", "nationality",
    "marital", "disab", "region", "state", "city", "area", "location", "language",
)
MIN_GROUP = 5
FOUR_FIFTHS = 0.8


def positive_class(classes: list[str]) -> str:
    """The 'yes' outcome of a binary target; otherwise the last class alphabetically."""
    lowered = {c.lower(): c for c in classes}
    for key in ("1", "yes", "true", "y", "positive", "churned", "bought", "approved"):
        if key in lowered:
            return lowered[key]
    return classes[-1]


def group_options(df: pd.DataFrame, exclude: list[str]) -> list[dict]:
    """Columns that make sense to audit by, with likely-sensitive ones first."""
    out = []
    for col in df.columns:
        if col in exclude:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        n = s.nunique()
        numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
        if numeric and n > 6 and n >= len(s) * 0.9 and col.lower().endswith("id"):
            continue
        if (not numeric and 2 <= n <= 12) or (numeric and 2 <= n <= 12) or (numeric and n > 12):
            out.append(
                {
                    "column": col,
                    "groups": int(min(n, 4)) if (numeric and n > 12) else int(n),
                    "banded": bool(numeric and n > 12),
                    "sensitive": any(h in col.lower() for h in SENSITIVE_HINTS),
                }
            )
    out.sort(key=lambda o: (not o["sensitive"], o["column"]))
    return out


def _band(series: pd.Series) -> pd.Series:
    """Split a many-valued number into quartile bands, labelled with the real ranges."""
    try:
        cats = pd.qcut(series, 4, duplicates="drop")
    except ValueError:
        return series.astype(str)
    return cats.map(lambda iv: f"{_fmt(iv.left)}–{_fmt(iv.right)}" if pd.notna(iv) else None)


def audit(
    test_frame: pd.DataFrame,
    y_true: pd.Series,
    preds,
    group_col: str,
    task: str,
    pos_label: str | None = None,
) -> dict:
    """
    Compare how the model treats each group on the held-out rows.

    Classification: how often each group gets the 'yes' outcome (selection rate),
    and how often the model is right for them. Flag by the four-fifths rule.
    Regression: average predicted value and typical error per group.
    """
    g = test_frame[group_col]
    numeric = pd.api.types.is_numeric_dtype(g) and not pd.api.types.is_bool_dtype(g)
    banded = bool(numeric and g.nunique() > 12)
    labels = _band(g) if banded else g.astype(object).where(g.notna(), "unknown").astype(str)

    df = pd.DataFrame(
        {"group": labels.values, "y": np.asarray(y_true), "p": np.asarray(preds)},
        index=test_frame.index,
    )
    rows = []
    for name, part in df.groupby("group", sort=True):
        r = {"group": str(name), "n": int(len(part)), "reliable": len(part) >= MIN_GROUP}
        if task == "classification":
            r["accuracy"] = float((part["y"].astype(str) == part["p"].astype(str)).mean())
            if pos_label is not None:
                r["selection_rate"] = float((part["p"].astype(str) == str(pos_label)).mean())
                r["actual_rate"] = float((part["y"].astype(str) == str(pos_label)).mean())
        else:
            yt, pp = part["y"].astype(float), part["p"].astype(float)
            r["mean_actual"] = float(yt.mean())
            r["mean_predicted"] = float(pp.mean())
            r["mae"] = float((yt - pp).abs().mean())
        rows.append(r)

    ok = [r for r in rows if r["reliable"]]
    findings = []
    status = "pass"

    if len(ok) < 2:
        return {
            "group_column": group_col,
            "banded": banded,
            "task": task,
            "positive_class": pos_label,
            "groups": rows,
            "findings": [
                f"Only {len(ok)} group(s) in the held-out data had {MIN_GROUP}+ people, so a fair comparison isn't possible yet. Add more data."
            ],
            "status": "insufficient_data",
            "disparity_ratio": None,
            "n_test": int(len(df)),
        }

    ratio = None
    if task == "classification":
        if pos_label is not None:
            rates = [r["selection_rate"] for r in ok]
            hi = max(rates)
            if hi > 0:
                ratio = min(rates) / hi
                top = max(ok, key=lambda r: r["selection_rate"])
                low = min(ok, key=lambda r: r["selection_rate"])
                if ratio < FOUR_FIFTHS:
                    status = "review"
                    findings.append(
                        f"“{low['group']}” gets the “{pos_label}” result {low['selection_rate']:.0%} of the time "
                        f"versus {top['selection_rate']:.0%} for “{top['group']}” — "
                        f"{ratio:.0%} of the top rate, below the usual 80% guideline."
                    )
                else:
                    findings.append(
                        f"The “{pos_label}” result is given at similar rates across groups "
                        f"(lowest is {ratio:.0%} of the highest)."
                    )
                # A gap that mirrors the real data is different from one the model invented.
                real = [r["actual_rate"] for r in ok]
                if status == "review" and max(real) > 0 and min(real) / max(real) < FOUR_FIFTHS:
                    findings.append(
                        "The same gap exists in the real data, so the model is reflecting history rather than creating it. "
                        "Whether that's acceptable is a judgement call for you."
                    )
        accs = [r["accuracy"] for r in ok]
        gap = max(accs) - min(accs)
        if gap > 0.10:
            status = "review"
            worst = min(ok, key=lambda r: r["accuracy"])
            best = max(ok, key=lambda r: r["accuracy"])
            findings.append(
                f"The model is right {best['accuracy']:.0%} of the time for “{best['group']}” "
                f"but only {worst['accuracy']:.0%} for “{worst['group']}”."
            )
        else:
            findings.append(f"Accuracy is similar across groups (within {gap * 100:.0f} points).")
    else:
        maes = [r["mae"] for r in ok]
        if min(maes) > 0:
            ratio = min(maes) / max(maes)
        elif max(maes) == 0:
            ratio = 1.0
        else:
            ratio = 0.0
        if ratio is not None and ratio < 1 / 1.5:
            status = "review"
            worst = max(ok, key=lambda r: r["mae"])
            best = min(ok, key=lambda r: r["mae"])
            findings.append(
                f"Predictions are off by about {_fmt(worst['mae'])} for “{worst['group']}” "
                f"versus {_fmt(best['mae'])} for “{best['group']}”."
            )
        else:
            findings.append("The size of the model's errors is similar across groups.")

    small = [r["group"] for r in rows if not r["reliable"]]
    if small:
        findings.append(
            f"Left out of the comparison because there were fewer than {MIN_GROUP} people: {', '.join(small)}."
        )
    if min(r["n"] for r in ok) < 30:
        findings.append("Some groups are small, so treat these gaps as a signal to look closer, not a verdict.")

    return {
        "group_column": group_col,
        "banded": banded,
        "task": task,
        "positive_class": pos_label,
        "groups": rows,
        "findings": findings,
        "status": status,
        "disparity_ratio": ratio,
        "n_test": int(len(df)),
    }


# ---------------------------------------------------------------------------
# 5. Monitoring
# ---------------------------------------------------------------------------


def monitor(logged: list[dict]) -> dict:
    """
    Summarise the prediction log. `logged` is oldest→newest dicts with
    trust_level, confidence and created_at.
    """
    total = len(logged)
    levels = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    confs = []
    for p in logged:
        levels[p.get("trust_level") or "unknown"] = levels.get(p.get("trust_level") or "unknown", 0) + 1
        if p.get("confidence") is not None:
            confs.append(p["confidence"])

    status = "idle"
    note = "No predictions yet."
    if total:
        low_share = levels["low"] / total
        recent = logged[-20:]
        recent_low = sum(1 for p in recent if p.get("trust_level") == "low") / len(recent)
        status, note = "healthy", "Inputs look like the training data."
        if total >= 5 and recent_low >= 0.3:
            status = "drifting"
            note = (
                f"{recent_low:.0%} of recent predictions used inputs outside the training data. "
                "The real world may have moved; consider retraining on fresh data."
            )
        elif low_share > 0:
            status = "watch"
            note = f"{levels['low']} of {total} predictions used unfamiliar inputs."

    return {
        "total": total,
        "trust_counts": levels,
        "avg_confidence": float(np.mean(confs)) if confs else None,
        "status": status,
        "note": note,
    }
