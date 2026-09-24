"""
Offline query engine — the chatbot's ability to answer factual questions
about the data directly (counts, filters, aggregates, top-N) without
training a model or calling an LLM. This is what lets "how many customers
from Delhi bought" or "average income of people who didn't buy" get a real
answer instead of being forced through the prediction/drivers/compare shapes
in insights.py, which were never the right tool for a factual lookup.

Strategy: rather than trying to parse full sentence grammar, look for the
specific signals that identify each question type (an aggregate word, a
comparison operator, a literal value from the data itself) and build a
pandas filter/aggregate from those. This has a real ceiling — genuinely
free-form combinations are what the LLM chat path (llm_chat.py) is for —
but it covers a large share of what people actually type.
"""

import re

import numpy as np
import pandas as pd

import insights as _ins
from insights import pretty

AGG_WORDS = {
    "average": "mean", "avg": "mean", "mean": "mean",
    "total": "sum", "sum": "sum",
    "maximum": "max", "max": "max", "highest": "max",
    "minimum": "min", "min": "min", "lowest": "min",
    "median": "median",
}
AGG_DISPLAY = {"mean": "average", "sum": "total", "max": "highest", "min": "lowest", "median": "median"}


def _fmt(v: float) -> str:
    """Comma-separated, never scientific notation — this is for a shop owner, not a log file."""
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"

COMPARISON_PATTERNS = [
    (re.compile(r"(?:above|over|more than|greater than|higher than|at least)\s+(\d+(?:\.\d+)?)"), "gt"),
    (re.compile(r"(?:below|under|less than|fewer than|lower than|at most)\s+(\d+(?:\.\d+)?)"), "lt"),
    (re.compile(r"(?:exactly|equal to)\s+(\d+(?:\.\d+)?)"), "eq"),
]

NEGATION_WORDS = {"not", "didn't", "did not", "n't", "no", "never", "without", "isn't", "aren't"}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def build_filter(df: pd.DataFrame, text: str) -> tuple[pd.Series, list[str]]:
    """
    Best-effort boolean mask from free text, plus a human-readable list of
    the conditions actually applied (so the answer can say what it filtered
    on, rather than silently guessing). An empty description list means no
    filter was found — the mask is all-True.
    """
    text_l = text.lower()
    mask = pd.Series(True, index=df.index)
    applied = []

    # --- categorical: does any actual value in the column appear in the text? ---
    # This is deliberately data-driven rather than keyword-driven — it works
    # for "Delhi", "Mumbai", any product name, any city, without needing to
    # know the domain in advance.
    for col in df.select_dtypes(exclude=[np.number]).columns:
        values = df[col].dropna().astype(str).unique()
        for v in values:
            if len(v) < 2:
                continue
            if re.search(rf"\b{re.escape(v.lower())}\b", text_l):
                mask &= df[col].astype(str) == v
                applied.append(f"{pretty(col)} is \u201c{v}\u201d")
                break  # one value per column is enough signal

    # --- numeric comparisons: "income above 50000", "age under 30" ---
    comparison_matched = False
    for col in df.select_dtypes(include=[np.number]).columns:
        col_words = set(re.findall(r"[a-z]+", col.lower()))
        if not (col_words & _tokenize(text_l)):
            continue
        for pattern, op in COMPARISON_PATTERNS:
            m = pattern.search(text_l)
            if not m:
                continue
            val = float(m.group(1))
            if op == "gt":
                mask &= df[col] > val
                applied.append(f"{pretty(col)} above {val:g}")
            elif op == "lt":
                mask &= df[col] < val
                applied.append(f"{pretty(col)} below {val:g}")
            else:
                mask &= df[col] == val
                applied.append(f"{pretty(col)} equal to {val:g}")
            comparison_matched = True
            break

    # A bare "over 50" / "under 18" with no column named alongside it almost
    # always means age in everyday phrasing — apply that common-sense default
    # rather than silently ignoring the condition, but only when it's
    # plausible (an actual 'age' column exists and the number reads as an age).
    if not comparison_matched and "age" in df.columns and pd.api.types.is_numeric_dtype(df["age"]):
        for pattern, op in COMPARISON_PATTERNS:
            m = pattern.search(text_l)
            if not m:
                continue
            val = float(m.group(1))
            if not (0 < val <= 120):
                continue
            if op == "gt":
                mask &= df["age"] > val
                applied.append(f"Age above {val:g}")
            elif op == "lt":
                mask &= df["age"] < val
                applied.append(f"Age below {val:g}")
            else:
                mask &= df["age"] == val
                applied.append(f"Age equal to {val:g}")
            break

    # --- binary columns: "who didn't buy" / "who purchased" ---
    for col in df.columns:
        vals = df[col].dropna().unique()
        if len(vals) != 2:
            continue
        col_words = set(re.findall(r"[a-z]+", col.lower()))
        # Reuse insights' synonym expansion so "buy" connects to "purchased" here too.
        expanded = set()
        for w in _tokenize(text_l):
            expanded |= _ins._synonyms_of(w)
        if not (col_words & expanded):
            continue
        negated = any(n in text_l for n in NEGATION_WORDS)
        positive_value = sorted(vals, reverse=True)[0]  # 1/True/"Yes"-ish, by convention
        negative_value = sorted(vals, reverse=True)[1]
        target_value = negative_value if negated else positive_value
        mask &= df[col] == target_value
        applied.append(f"{pretty(col)} = {target_value}" + (" (i.e. no)" if negated else " (i.e. yes)"))
        break

    return mask, applied


def try_count(df: pd.DataFrame, text: str) -> dict | None:
    text_l = text.lower()
    if not re.search(r"\bhow many\b|\bcount of\b|\bnumber of\b", text_l):
        return None
    mask, applied = build_filter(df, text)
    n = int(mask.sum())
    narrative = [f"{n} out of {len(df)} rows" + (f" match: {', '.join(applied)}." if applied else ".")]
    return {"kind": "count", "narrative": narrative, "value": n}


def try_aggregate(df: pd.DataFrame, text: str) -> dict | None:
    text_l = text.lower()
    agg_fn = next((fn for word, fn in AGG_WORDS.items() if re.search(rf"\b{word}\b", text_l)), None)
    if not agg_fn:
        return None

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    target = None
    for col in numeric_cols:
        col_words = set(re.findall(r"[a-z]+", col.lower()))
        if col_words & _tokenize(text_l):
            target = col
            break
    if not target:
        return None

    mask, applied = build_filter(df, text)
    subset = df.loc[mask, target].dropna()
    if subset.empty:
        return {"kind": "aggregate", "narrative": ["No matching rows to calculate that from."], "value": None}

    value = round(float(getattr(subset, agg_fn)()), 2)
    filter_note = f" for rows where {', '.join(applied)}" if applied else ""
    display_name = AGG_DISPLAY.get(agg_fn, agg_fn)
    narrative = [f"The {display_name} {pretty(target).lower()}{filter_note} is {_fmt(value)}."]
    return {"kind": "aggregate", "narrative": narrative, "value": value, "target": target}


def try_top_n(df: pd.DataFrame, text: str) -> dict | None:
    text_l = text.lower()
    m = re.search(r"\btop\s+(\d+)\b", text_l)
    n = int(m.group(1)) if m else (5 if re.search(r"\btop\b|\bhighest\b|\blowest\b|\bbest\b|\bworst\b", text_l) else None)
    if n is None:
        return None

    ascending = bool(re.search(r"\blowest\b|\bworst\b|\bsmallest\b|\bbottom\b", text_l))
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    sort_col = None
    for col in numeric_cols:
        col_words = set(re.findall(r"[a-z]+", col.lower()))
        if col_words & _tokenize(text_l):
            sort_col = col
            break
    if not sort_col:
        return None

    mask, applied = build_filter(df, text)
    subset = df.loc[mask].sort_values(sort_col, ascending=ascending).head(min(n, 25))
    rows = subset.to_dict(orient="records")
    direction = "lowest" if ascending else "highest"
    filter_note = f" (filtered to {', '.join(applied)})" if applied else ""
    narrative = [f"Showing the {len(rows)} rows with the {direction} {pretty(sort_col).lower()}{filter_note}."]
    return {"kind": "table", "narrative": narrative, "rows": rows, "columns": list(df.columns)}


def try_offline_query(df: pd.DataFrame, text: str) -> dict | None:
    """Try each offline handler in order of specificity; None means 'couldn't parse this'."""
    for fn in (try_count, try_top_n, try_aggregate):
        result = fn(df, text)
        if result:
            return result
    return None
