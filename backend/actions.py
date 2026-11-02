"""
Action layer: turning a trained model into things a person can do on Monday.

  score_frame   score a whole file of new rows, with a trust rating per row
  rank          "who should I call first": most likely, among those not yet won
  levers        the single changes that would move one case the most
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import trust

MAX_ROWS = 5000
FIXED_WORDS = ("age", "gender", "sex", "city", "area", "region", "state", "country", "birth", "caste", "religion", "tenure", "year")


def _classes(pipeline):
    return [str(c) for c in pipeline.named_steps["model"].classes_]


def score_frame(bundle: dict, df: pd.DataFrame, pos_label: str | None = None) -> pd.DataFrame:
    """Return df with prediction, chance (classifiers) and trust columns appended."""
    if len(df) > MAX_ROWS:
        raise ValueError(f"Too many rows ({len(df):,}). Score up to {MAX_ROWS:,} at a time.")
    pipeline, features, task = bundle["pipeline"], bundle["features"], bundle["task"]
    reference = bundle.get("reference") or {}
    frame = trust._coerce_frame(df.to_dict("records"), features, reference)
    frame.index = df.index
    out = df.copy()
    target = bundle["target"]
    preds = pipeline.predict(frame)
    out[f"predicted_{target}"] = preds
    if task == "classification":
        classes = _classes(pipeline)
        proba = pipeline.predict_proba(frame)
        pos = str(pos_label) if pos_label is not None and str(pos_label) in classes else (trust.positive_class(classes) if len(classes) == 2 else None)
        if pos is not None:
            out["chance"] = proba[:, classes.index(pos)].round(4)
        out["confidence"] = proba.max(axis=1).round(4)
    levels = []
    for i, rec in enumerate(df[[c for c in features if c in df.columns]].to_dict("records")):
        levels.append(trust.check_row(reference, rec)["level"] if reference else None)
    out["trust"] = levels
    return out


def rank(bundle: dict, df: pd.DataFrame, top: int = 10, direction: str = "most", only_not_yet: bool = True) -> dict:
    pipeline, task, target = bundle["pipeline"], bundle["task"], bundle["target"]
    work = df.dropna(subset=[target]) if target in df.columns else df
    scored = score_frame(bundle, work)
    pred_col = f"predicted_{target}"
    note = None
    if task == "classification" and "chance" in scored:
        classes = _classes(pipeline)
        pos = trust.positive_class(classes)
        key = "chance"
        if only_not_yet and target in scored.columns:
            mask = scored[target].astype(str) != str(pos)
            if mask.sum() >= 1:
                scored = scored[mask]
                note = f"Among rows where {trust.pretty(target)} is not “{pos}” yet."
        what = f"most likely to be “{pos}”" if direction == "most" else f"least likely to be “{pos}”"
    else:
        key = pred_col
        what = "highest predicted" if direction == "most" else "lowest predicted"
    scored = scored.sort_values(key, ascending=(direction != "most")).head(top)
    keep = [c for c in scored.columns if c != "confidence"]
    rows = []
    for idx, r in scored[keep].iterrows():
        rows.append({k: _plain(v) for k, v in r.items()})
    return {
        "target": target,
        "task": task,
        "key": key,
        "direction": direction,
        "headline": f"The {len(rows)} rows {what}" + (f". {note}" if note else "."),
        "rows": rows,
    }


def levers(bundle: dict, row: dict, target_class: str | None = None, top: int = 5) -> list[dict]:
    pipeline, features, task = bundle["pipeline"], bundle["features"], bundle["task"]
    reference = bundle.get("reference") or {}
    if task == "classification" and target_class is None:
        frame = trust._coerce_frame([row], features, reference)
        target_class = str(pipeline.predict(frame)[0])
    out = []
    for f in features:
        sw = trust.sweep(pipeline, features, task, row, f, reference, target_class)
        delta = sw["best"]["output"] - sw["current_output"]
        out.append(
            {
                "feature": f,
                "current": sw["current_value"],
                "best_value": sw["best"]["value"],
                "current_output": sw["current_output"],
                "best_output": sw["best"]["output"],
                "delta": float(delta),
                "output_kind": sw["output_kind"],
                "changeable": not any(w in f.lower() for w in FIXED_WORDS),
            }
        )
    out = [o for o in out if o["delta"] > (0.005 if task == "classification" else 1e-9)]
    out.sort(key=lambda o: (not o["changeable"], -o["delta"]))
    return out[:top]


def _plain(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v
