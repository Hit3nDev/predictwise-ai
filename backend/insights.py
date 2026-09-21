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

import re

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


# ---------------------------------------------------------------------------
# Custom questions: honor a column the user actually named, instead of only
# ever picking from the 4 generic templates. This is what makes a free-text
# question like "what affects my income the most" or "compare sales between
# cities" actually get answered on its own terms rather than forced into
# whichever fixed bucket scores highest.
# ---------------------------------------------------------------------------

DRIVER_PHRASES = [
    "what affects", "what drives", "what influences", "what impacts",
    "what determines", "why do", "why does", "why are", "why is",
    "what makes", "what causes",
]
COMPARE_PHRASES = [
    "compare", "difference between", "differ by", " vs ", " versus ",
    "which is better", "by city", "by region", "by category", "across",
]


def find_mentioned_columns(df: pd.DataFrame, text: str) -> list[str]:
    """
    Columns the question names directly, matched as whole words so a short
    name like 'age' doesn't false-match inside 'average'. This is the piece
    that lets a custom question be answered on its own terms.
    """
    text_l = (text or "").lower()
    mentioned = []
    for col in df.columns:
        variants = {col.lower(), col.lower().replace("_", " "), col.lower().replace("-", " ")}
        if any(v and re.search(rf"\b{re.escape(v)}\b", text_l) for v in variants):
            mentioned.append(col)
    return mentioned


def resolve_question(df: pd.DataFrame, text: str) -> dict:
    """
    The real entry point for free text. Tries, in order: an explicit
    compare/segment question, an explicit "what affects X" question, an
    explicitly named yes/no or numeric column, and only then falls back to
    the old coarse 4-template keyword scoring.
    """
    text_l = (text or "").lower()
    mentioned = find_mentioned_columns(df, text)
    # An explicit mention is trusted as-is — the identifier heuristic exists to
    # keep *auto-detection* from picking a row ID, not to second-guess a column
    # the user named on purpose (which occasionally looks sequential by chance).
    numeric_mentioned = [c for c in mentioned if pd.api.types.is_numeric_dtype(df[c])]
    binary_mentioned = [c for c in mentioned if _is_binary(df[c])]
    categorical_mentioned = [c for c in mentioned if not pd.api.types.is_numeric_dtype(df[c])]

    is_compare_q = any(p in text_l for p in COMPARE_PHRASES)
    is_driver_q = any(p in text_l for p in DRIVER_PHRASES)

    # 1. "compare X between cities" / "does city affect income" — a category
    #    and a number to look at per group, no modelling needed.
    if is_compare_q and categorical_mentioned:
        cat = categorical_mentioned[0]
        metric = numeric_mentioned[0] if numeric_mentioned else None
        if not metric:
            pair = find_performer_pair(df)
            metric = pair[1] if pair else None
        if metric:
            return {"kind": "compare", "cat_col": cat, "metric_col": metric, "explicit": True}

    # 2. "what affects/drives/influences X" — train on the named column (or
    #    fall back to auto-detection) and lead with the driver list, not a
    #    rate/average sentence.
    if is_driver_q:
        target = binary_mentioned[0] if binary_mentioned else (numeric_mentioned[0] if numeric_mentioned else None)
        explicit = target is not None
        if not target:
            target = find_binary_target(df) or find_numeric_target(df)
        if target:
            kind = "drivers_repeat" if _is_binary(df[target]) else "drivers_number"
            return {"kind": kind, "target": target, "explicit": explicit}

    # 3. A yes/no column was named directly — answer about THAT column, not
    #    whichever one the generic heuristic would have picked.
    if binary_mentioned:
        return {"kind": "repeat", "target": binary_mentioned[0], "explicit": True}

    # 4. A numeric column was named directly.
    if numeric_mentioned:
        return {"kind": "predict_number", "target": numeric_mentioned[0], "explicit": True}

    # 5. Nothing specific enough was named — fall back to the coarse template match.
    return {"kind": match_question(text), "explicit": False}


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


def run_repeat_question(df: pd.DataFrame, target: str, lead_with_drivers: bool = False) -> dict:
    result = automl.run_automl(df, target=target)
    acc = result["best_metrics"].get("accuracy")
    rate = round(float(df[target].mean()) * 100, 1) if _is_binary(df[target]) else None
    drivers = narrate_drivers(result["feature_importance"], n=5 if lead_with_drivers else 3)

    narrative = []
    if lead_with_drivers:
        narrative.append(f"What most affects {pretty(target).lower()}: {drivers}.")
        if acc is not None:
            narrative.append(
                f"That pattern is {confidence_phrase(acc)} — correct about {round(acc * 100)} times out of 100."
            )
    else:
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


def run_number_question(df: pd.DataFrame, target: str, lead_with_drivers: bool = False) -> dict:
    result = automl.run_automl(df, target=target)
    r2 = result["best_metrics"].get("r2")
    drivers = narrate_drivers(result["feature_importance"], n=5 if lead_with_drivers else 3)
    mean_val = round(float(df[target].mean()), 2)

    if lead_with_drivers:
        narrative = [f"What most affects {pretty(target).lower()}: {drivers}."]
        if r2 is not None:
            narrative.append(f"That pattern is {confidence_phrase(r2, kind='r2')}.")
    else:
        narrative = [f"On average, {pretty(target).lower()} is around {mean_val}."]
        if r2 is not None:
            narrative.append(f"The pattern behind this is {confidence_phrase(r2, kind='r2')}.")
        narrative.append(f"The biggest factors were: {drivers}.")

    return {"type": "predictable", "target": target, "task": result["task"],
            "narrative": narrative, "result": result}


def run_compare(df: pd.DataFrame, cat_col: str, metric_col: str, n: int = 8) -> dict:
    """'compare X between cities' — group means, no modelling needed."""
    grouped = df.groupby(cat_col)[metric_col].mean().sort_values(ascending=False)
    if len(grouped) < 2:
        raise automl.TrainingError(f"'{pretty(cat_col)}' doesn't have enough distinct groups to compare.")

    top_name, top_val = str(grouped.index[0]), float(grouped.iloc[0])
    bottom_name, bottom_val = str(grouped.index[-1]), float(grouped.iloc[-1])

    narrative = [
        f"On average, {pretty(metric_col).lower()} is highest for \u201c{top_name}\u201d "
        f"({round(top_val, 2)}) and lowest for \u201c{bottom_name}\u201d ({round(bottom_val, 2)})."
    ]
    if bottom_val:
        diff_pct = round((top_val - bottom_val) / abs(bottom_val) * 100)
        narrative.append(f"That's a difference of about {diff_pct}%.")

    rows = [{"name": str(idx), "value": round(float(v), 2)} for idx, v in grouped.head(n).items()]
    return {"narrative": narrative, "rows": rows}
