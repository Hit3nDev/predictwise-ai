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


def inr(v: float) -> str:
    """Exact rupees with Indian digit grouping: 3701526 -> ₹37,01,526 (paise only when present)."""
    neg, a = v < 0, abs(v)
    whole, frac = divmod(round(a * 100), 100)
    s = str(int(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{'-' if neg else ''}₹{s}" + (f".{int(frac):02d}" if frac else "")


def _fmt(v: float) -> str:
    """Comma-separated, never scientific notation — this is for a shop owner, not a log file."""
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"

COMPARISON_PATTERNS = [
    (re.compile(r"(?:above|over|more than|greater than|higher than|older than|older|at least)\s+(\d+(?:\.\d+)?)"), "gt"),
    (re.compile(r"(?:below|under|less than|fewer than|lower than|younger than|younger|at most)\s+(\d+(?:\.\d+)?)"), "lt"),
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

    # "orders above 500" / "bills over 1000": no column named, so use the shop's main amount column
    if not comparison_matched and not applied_age(applied) and re.search(r"\b(orders?|bills?|sales?|purchases?|transactions?|invoices?)\b", text_l):
        import analytics
        amount = analytics.pick_metric(df)
        if amount:
            for pattern, op in COMPARISON_PATTERNS:
                m = pattern.search(text_l)
                if not m:
                    continue
                val = float(m.group(1))
                mask &= {"gt": df[amount] > val, "lt": df[amount] < val, "eq": df[amount] == val}[op]
                applied.append(f"{pretty(amount)} {'above' if op == 'gt' else 'below' if op == 'lt' else 'equal to'} {val:g}")
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


def applied_age(applied: list[str]) -> bool:
    return any(a.lower().startswith("age ") for a in applied)


ENTITY_SYNONYMS = {
    "customer": ("customer", "client", "buyer", "member"), "bill": ("bill", "invoice", "receipt"),
    "order": ("order", "bill", "invoice"), "product": ("product", "item", "sku"), "item": ("item", "product", "sku"),
    "supplier": ("supplier", "vendor"), "city": ("city",), "area": ("area",), "shop": ("shop", "store", "branch"),
    "store": ("store", "shop", "branch"),
}


def _entity_column(df: pd.DataFrame, text_l: str):
    """"How many customers" on a bills file means distinct customers, not rows."""
    m = re.search(r"(?:how many|number of|count of)\s+(?:different |distinct |unique |total )?([a-z]+)", text_l)
    if not m:
        return None
    noun = m.group(1)
    noun = noun[:-3] + "y" if noun.endswith("ies") else noun[:-1] if noun.endswith("s") else noun
    words = ENTITY_SYNONYMS.get(noun)
    if not words:
        return None
    for w in words:
        for col in df.columns:
            if w in re.split(r"[^a-z]+", str(col).lower()) and 1 < df[col].nunique() < len(df):
                return col, noun
    return None


def try_count(df: pd.DataFrame, text: str) -> dict | None:
    text_l = text.lower()
    if not re.search(r"\bhow many\b|\bcount of\b|\bnumber of\b", text_l):
        return None
    mask, applied = build_filter(df, text)
    entity = _entity_column(df, text_l)
    if entity:
        col, noun = entity
        n = int(df.loc[mask, col].nunique())
        note = f" match: {', '.join(applied)}" if applied else ""
        return {"kind": "count", "value": n,
                "narrative": [f"{n} different {noun}{'' if n == 1 else 's'}{note.replace(' match:', ', matching:') if note else ''} (counted once each, even if they appear on many rows)."]}
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
    import analytics
    shown = inr(value) if analytics.is_money(target) else _fmt(value)
    narrative = [f"The {display_name} {pretty(target).lower()}{filter_note} is {shown}."]
    return {"kind": "aggregate", "narrative": narrative, "value": value, "target": target}


def _singular(w: str) -> str:
    return w[:-3] + "y" if w.endswith("ies") else w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def _group_column(df: pd.DataFrame, text_l: str, sort_col: str):
    """"Top 3 products by sales" means products ranked by their TOTAL, not the 3 biggest single rows."""
    asked = {_singular(w) for w in re.findall(r"[a-z]+", text_l)}
    for col in df.columns:
        if col == sort_col or pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        n = df[col].nunique()
        if not (2 <= n <= len(df) / 2):
            continue
        if {_singular(t) for t in re.split(r"[^a-z]+", str(col).lower()) if t} & asked:
            return col
    return None


def try_top_n(df: pd.DataFrame, text: str) -> dict | None:
    text_l = text.lower()
    # "what is the highest income?" asks for one number, not a list
    if re.search(r"\bwhat(?:'s| is| was) the (?:highest|lowest)\b", text_l) and not re.search(r"\b(?:top|best|worst|bottom)\b|\b\d+\b", text_l):
        return None
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
    grouped = _group_column(df, text_l, sort_col)
    if grouped:
        import analytics
        how = "mean" if re.search(r"\baverage\b|\bavg\b|\bmean\b", text_l) else "sum"
        agg = getattr(df.loc[mask].groupby(grouped)[sort_col], how)().sort_values(ascending=ascending).head(min(n, 25))
        show = inr if analytics.is_money(sort_col) else _fmt
        label = f"{'average' if how == 'mean' else 'total'} {pretty(sort_col).lower()}"
        direction = "Lowest" if ascending else "Top"
        rows = [{pretty(grouped).capitalize(): str(k), label.capitalize(): round(float(v), 2)} for k, v in agg.items()]
        head = ", ".join(f"{k} {show(float(v))}" for k, v in agg.head(3).items())
        return {"kind": "table", "rows": rows, "columns": list(rows[0].keys()) if rows else [],
                "narrative": [f"{direction} {len(rows)} by {label}: {head}."]}
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
