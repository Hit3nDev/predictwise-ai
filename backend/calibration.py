"""
Honest uncertainty for predictions.

Regression: a range around each predicted number (split-conformal style). The
width comes from how wrong the model was on rows it did NOT train on (the
out-of-fold residuals from cross-validation). The range is then tested on the
separate held-out rows, so the app reports how often the range really held:
"80% range, and it held for 81% of unseen rows".

Classification: a reliability check. When the model says it is 90% sure, how
often is it right on unseen rows? Reported per confidence band, with the gap
summarised as the expected calibration error.

Neither needs any AI service. Both can be wrong when the future differs from
the past, and the wording says so.
"""

from __future__ import annotations

import math

import numpy as np
from sklearn.base import clone
from sklearn.model_selection import cross_val_predict

LEVELS = (0.8, 0.9)
BANDS = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.0001)]


def _conformal_q(res: np.ndarray, level: float) -> float:
    n = len(res)
    k = min(n, math.ceil((n + 1) * level))
    return float(np.sort(res)[k - 1])


def regression_intervals(pipeline, X_train, y_train, X_test, y_test, folds: int) -> dict | None:
    if len(X_train) < 30 or len(X_test) < 5:
        return None
    try:
        oof = cross_val_predict(clone(pipeline), X_train, y_train, cv=max(2, min(folds, 5)))
    except Exception:
        return None
    res = np.abs(np.asarray(y_train, float) - oof)
    test_res = np.abs(np.asarray(y_test, float) - pipeline.predict(X_test))
    levels = {}
    for lv in LEVELS:
        q = _conformal_q(res, lv)
        levels[str(int(lv * 100))] = {"half_width": q, "held_out_coverage": float((test_res <= q).mean())}
    return {"kind": "interval", "levels": levels, "n_calibration": int(len(res)), "n_test": int(len(test_res))}


def classification_reliability(pipeline, X_test, y_test) -> dict | None:
    if not hasattr(pipeline, "predict_proba") or len(X_test) < 20:
        return None
    try:
        proba = pipeline.predict_proba(X_test)
    except Exception:
        return None
    conf = proba.max(axis=1)
    pred = pipeline.classes_[proba.argmax(axis=1)] if hasattr(pipeline, "classes_") else pipeline.predict(X_test)
    right = np.asarray(pred).astype(str) == np.asarray(y_test).astype(str)
    bins, gap, total = [], 0.0, len(conf)
    for lo, hi in BANDS:
        m = (conf >= lo) & (conf < hi)
        if not m.any():
            continue
        c, a = float(conf[m].mean()), float(right[m].mean())
        gap += m.sum() / total * abs(c - a)
        bins.append({"low": lo, "high": min(hi, 1.0), "n": int(m.sum()), "confidence": c, "accuracy": a})
    return {"kind": "reliability", "ece": float(gap), "bins": bins, "n_test": int(total)}


def calibrate(task: str, pipeline, X_train, y_train, X_test, y_test, folds: int) -> dict | None:
    try:
        if task == "regression":
            return regression_intervals(pipeline, X_train, y_train, X_test, y_test, folds)
        return classification_reliability(pipeline, X_test, y_test)
    except Exception:
        return None


def range_for(cal: dict | None, prediction: float, level: int = 90) -> dict | None:
    """The range to show next to one predicted number."""
    if not cal or cal.get("kind") != "interval":
        return None
    lv = cal["levels"].get(str(level))
    if not lv:
        return None
    return {
        "low": prediction - lv["half_width"], "high": prediction + lv["half_width"], "level": level,
        "held_out_coverage": lv["held_out_coverage"], "n_test": cal["n_test"],
    }


def reliability_for(cal: dict | None, confidence: float | None) -> dict | None:
    """What the model's track record says about a confidence this high."""
    if not cal or cal.get("kind") != "reliability" or confidence is None:
        return None
    for b in cal["bins"]:
        if b["low"] <= confidence < b["high"] or (b["high"] >= 1.0 and confidence >= b["low"]):
            if b["n"] < 5:
                return None
            return {"confidence": confidence, "accuracy": b["accuracy"], "n": b["n"]}
    return None
