"""
Insight engine for Simple Mode.

A shop owner doesn't think in "target columns" — they think in questions.
This module maps a small library of plain-language business questions onto
whatever dataset was uploaded, by scanning column names for keywords, and
turns model output back into sentences instead of metrics.

Matching is intentionally simple (keyword scoring over column names and free
text) rather than a real LLM call — it's honest about being a heuristic, and
swapping in an LLM later (Module 9 on the roadmap) is a drop-in replacement
for `match_question()` and the narrate_* functions, not a redesign.
"""

import numpy as np
import pandas as pd

import automl

BINARY_KEYWORDS = [
    "churn", "repeat", "return", "purchase", "purchased", "buy", "bought",
    "converted", "conversion", "default", "fraud", "left", "stayed", "renew",
    "subscribed", "cancel", "response",
]
NUMERIC_TARGET_KEYWORDS = [
    "revenue", "sales", "income", "price", "amount", "profit", "score",
    "rating", "value", "spend", "spent", "cost", "duration", "total", "salary",
]
CATEGORY_KEYWORDS = [
    "product", "category", "item", "city", "branch", "store", "region",
    "name", "type", "sku", "department",
]
METRIC_KEYWORDS = [
    "sales", "revenue", "quantity", "amount", "units", "qty", "price",
    "total", "count", "profit",
]


def pretty(name: str) -> str:
    """'purchase_amount' -> 'Purchase amount' — for labels a non-technical user reads."""
    words = str(name).replace("_", " ").replace("-", " ").split()
    if not words:
        return str(name)
    return " ".join([words[0].capitalize()] + words[1:])


def _is_binary(series: pd.Series) -> bool:
    vals = series.dropna().unique()
    return len(vals) == 2


def find_binary_target(df: pd.DataFrame) -> str | None:
    """A yes/no-ish outcome column, found by name first, then by shape."""
    by_name = [c for c in df.columns if any(k in c.lower() for k in BINARY_KEYWORDS)]
    for c in by_name:
        if _is_binary(df[c]):
            return c
    # Fall back to any binary numeric column that isn't an identifier.
    for c in df.select_dtypes(include=[np.number]).columns:
        if _is_binary(df[c]) and df[c].nunique() < len(df):
            return c
    return None


def _looks_like_id(series: pd.Series, name: str) -> bool:
    """
    A genuine row identifier, not just a column with lots of distinct values.
    All-unique alone isn't enough to disqualify a column — a continuous target
    like 'price' is normally all-unique too (that's what makes it continuous).
    Real identifiers are either named like one, or are sequential integers.
    """
    lname = name.lower()
    if lname == "id" or lname.endswith("_id") or lname.endswith("id") or lname == "index":
        return True
    if pd.api.types.is_integer_dtype(series):
        s = series.dropna()
        if len(s) > 1 and s.nunique() == len(s):
            ordered = s.sort_values().reset_index(drop=True)
            if (ordered.diff().dropna() == 1).all():
                return True
    return False


def find_numeric_target(df: pd.DataFrame) -> str | None:
    """A quantity worth predicting, found by name, then by highest variance."""
    numeric = df.select_dtypes(include=[np.number])
    not_id = [c for c in numeric.columns if not _looks_like_id(numeric[c], c)]
    by_name = [c for c in not_id if any(k in c.lower() for k in NUMERIC_TARGET_KEYWORDS)]
    for c in by_name:
        if numeric[c].nunique() > 5:  # not a near-constant
            return c
    candidates = [c for c in not_id if numeric[c].nunique() > 5]
    if not candidates:
        return None
    # Highest coefficient of variation reads as "the thing that actually varies".
    cv = {c: numeric[c].std() / (abs(numeric[c].mean()) + 1e-9) for c in candidates}
    return max(cv, key=cv.get)


DEMOGRAPHIC_SKIP = ["age", "id", "year", "zip", "pincode", "postal", "dob"]


def find_performer_pair(df: pd.DataFrame) -> tuple[str, str] | None:
    """(category column, metric column) for a 'what's doing best' ranking."""
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if not _looks_like_id(df[c], c)
    ]

    cat = next((c for c in cat_cols if any(k in c.lower() for k in CATEGORY_KEYWORDS)), None)
    metric = next((c for c in num_cols if any(k in c.lower() for k in METRIC_KEYWORDS)), None)

    if not cat:
        cat = next((c for c in cat_cols if 2 <= df[c].nunique() <= 50), None)
    if not metric:
        # Demographic-looking columns (age, year...) rarely mean anything when
        # summed across a group — prefer a real business number if one exists.
        metric = next(
            (c for c in num_cols if df[c].nunique() > 5 and not any(k in c.lower() for k in DEMOGRAPHIC_SKIP)),
            None,
        )
    if not metric:
        metric = next((c for c in num_cols if df[c].nunique() > 5), None)

    if cat and metric:
        return cat, metric
    return None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "id": "profile",
        "label": "What does my data look like?",
        "hint": "A plain-English overview — always available.",
        "keywords": ["overview", "look like", "summary", "typical", "normal", "describe"],
    },
    {
        "id": "repeat",
        "label": "Will this happen again?",
        "hint": "e.g. will a customer come back, cancel, or repeat.",
        "keywords": ["again", "repeat", "return", "come back", "churn", "cancel", "buy", "renew"],
    },
    {
        "id": "predict_number",
        "label": "What number should I expect?",
        "hint": "e.g. predict a price, sale amount, or score.",
        "keywords": ["how much", "predict", "expect", "price", "revenue", "sales", "amount", "worth"],
    },
    {
        "id": "top_performers",
        "label": "What's doing best?",
        "hint": "Ranks categories, products, or locations by a number.",
        "keywords": ["best", "top", "worst", "rank", "compare", "which product", "which item"],
    },
]


def match_question(text: str) -> str:
    """Keyword-score free text against the templates; 'profile' is the safe fallback."""
    text = (text or "").lower()
    if not text.strip():
        return "profile"
    scores = {}
    for t in TEMPLATES:
        scores[t["id"]] = sum(1 for k in t["keywords"] if k in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "profile"


def availability(df: pd.DataFrame) -> dict:
    """Which templates this specific dataset can actually answer, and why not."""
    out = {}
    binary = find_binary_target(df)
    numeric = find_numeric_target(df)
    pair = find_performer_pair(df)

    out["profile"] = {"available": True, "reason": None, "detected": None}
    out["repeat"] = {
        "available": binary is not None,
        "reason": None if binary else "No yes/no outcome column found (like 'purchased' or 'churn').",
        "detected": binary,
    }
    out["predict_number"] = {
        "available": numeric is not None,
        "reason": None if numeric else "No numeric column worth predicting was found.",
        "detected": numeric,
    }
    out["top_performers"] = {
        "available": pair is not None,
        "reason": None if pair else "Needs a category column (like product or city) and a number to rank by.",
        "detected": pair,
    }
    return out


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

def confidence_phrase(score: float, kind: str = "accuracy") -> str:
    if kind == "accuracy":
        if score >= 0.85:
            return "very reliable"
        if score >= 0.65:
            return "fairly reliable"
        return "a rough guide at best"
    if score >= 0.7:
        return "quite reliable"
    if score >= 0.4:
        return "moderately reliable"
    return "weak — treat any prediction as a rough estimate"


def narrate_drivers(feature_importance: list[dict], n: int = 3) -> str:
    top = [f["feature"] for f in feature_importance[:n] if f["importance"] > 0]
    if not top:
        return "no single factor stood out clearly"
    names = [pretty(t) for t in top]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def narrate_profile(eda: dict, df: pd.DataFrame) -> list[str]:
    lines = [
        f"This dataset has {eda['row_count']} rows and {eda['column_count']} columns."
    ]
    if eda["total_missing"] > 0:
        lines.append(
            f"{eda['total_missing']} values were missing — run Clean first if you haven't."
        )
    if eda["duplicate_rows"] > 0:
        lines.append(f"{eda['duplicate_rows']} rows look like duplicates.")

    for col in eda["columns"]:
        if col["is_numeric"] and col.get("mean") is not None:
            lines.append(
                f"{pretty(col['name'])} typically runs around "
                f"{round(col['mean'], 1)} (from {col.get('min')} to {col.get('max')})."
            )
        elif not col["is_numeric"] and col.get("top_value"):
            lines.append(
                f"The most common {pretty(col['name']).lower()} is \u201c{col['top_value']}\u201d."
            )
        if len(lines) >= 7:
            break
    return lines


def top_performers(df: pd.DataFrame, cat_col: str, metric_col: str, n: int = 5) -> dict:
    grouped = (
        df.groupby(cat_col)[metric_col]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )
    total = df[metric_col].sum()
    rows = [
        {
            "name": str(idx),
            "value": round(float(v), 2),
            "share_pct": round(float(v) / total * 100, 1) if total else None,
        }
        for idx, v in grouped.items()
    ]
    lead = rows[0]
    narrative = (
        f"By {pretty(metric_col).lower()}, \u201c{lead['name']}\u201d comes out on top"
        + (f", making up about {lead['share_pct']}% of the total." if lead["share_pct"] else ".")
    )
    return {"narrative": narrative, "rows": rows, "category": cat_col, "metric": metric_col}


def run_repeat_question(df: pd.DataFrame, target: str) -> dict:
    result = automl.run_automl(df, target=target)
    acc = result["best_metrics"].get("accuracy")
    rate = round(float(df[target].mean()) * 100, 1) if _is_binary(df[target]) else None
    drivers = narrate_drivers(result["feature_importance"])

    narrative = []
    if rate is not None:
        narrative.append(
            f"Looking at your past data, about {rate}% of records ended up as \u201cyes\u201d for {pretty(target).lower()}."
        )
    if acc is not None:
        narrative.append(
            f"Using the patterns in your data, this is {confidence_phrase(acc)} "
            f"— correct about {round(acc * 100)} times out of 100."
        )
    narrative.append(f"The biggest factors were: {drivers}.")

    return {"type": "predictable", "target": target, "task": result["task"],
            "narrative": narrative, "result": result}


def run_number_question(df: pd.DataFrame, target: str) -> dict:
    result = automl.run_automl(df, target=target)
    r2 = result["best_metrics"].get("r2")
    drivers = narrate_drivers(result["feature_importance"])
    mean_val = round(float(df[target].mean()), 2)

    narrative = [f"On average, {pretty(target).lower()} is around {mean_val}."]
    if r2 is not None:
        narrative.append(
            f"The pattern behind this is {confidence_phrase(r2, kind='r2')}."
        )
    narrative.append(f"The biggest factors were: {drivers}.")

    return {"type": "predictable", "target": target, "task": result["task"],
            "narrative": narrative, "result": result}
