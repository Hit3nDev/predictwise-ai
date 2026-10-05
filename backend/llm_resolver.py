"""
LLM-backed question resolver -- resolves free text into a structured intent
(same shape as insights.resolve_question()) using real language understanding
instead of keyword/synonym matching.

Works with either provider in llm_provider.py -- Groq (free, the default
recommendation, since Anthropic has no free API tier) or Anthropic if
configured. Without a key, resolve() returns None immediately and the caller
falls back to insights.resolve_question(), so the app behaves identically
either way; this is additive, not a dependency.

NOTE: the live round-trip is not exercised by this project's test suite (no
key in the build sandbox). _validate() and the no-key fallback path are
tested; the actual conversation is not.
"""

import json

import llm_provider

VALID_KINDS = {"predict_number", "repeat", "drivers_number", "drivers_repeat", "compare", "profile"}

SYSTEM_PROMPT = """You turn a plain-language business question about a dataset into a structured intent.
You will be given the dataset's column names and types, and the user's question.
Respond with ONLY a JSON object and nothing else -- no markdown fences, no explanation:

{"kind": "predict_number" | "repeat" | "drivers_number" | "drivers_repeat" | "compare" | "profile",
 "target": "<column name>" or null,
 "cat_col": "<column name>" or null,
 "metric_col": "<column name>" or null}

Rules:
- Use column names EXACTLY as given -- never invent or alter one.
- "repeat" / "drivers_repeat": target must be a column with exactly two distinct values (a yes/no-style outcome).
- "predict_number" / "drivers_number": target must be a numeric column.
- Use the "drivers_*" kinds when the question asks what AFFECTS, DRIVES, or EXPLAINS a column,
  rather than asking to predict a new case directly.
- Use "compare": cat_col is a category-like column, metric_col is a numeric column to average per group.
- Use "profile" (with target/cat_col/metric_col all null) if the question is vague, general,
  or genuinely doesn't map to answering with a specific column.
"""


def resolve(columns: list, question: str) -> dict | None:
    """
    columns: [{"name": str, "dtype": str}, ...] -- from the actual dataframe.
    Returns a dict shaped like insights.resolve_question()'s output, or None
    if no provider is configured, the call fails, or the response doesn't
    hold up under validation.
    """
    if not llm_provider.active_provider() or not question or not question.strip():
        return None

    messages = [{"role": "user", "content": f"Columns: {json.dumps(columns)}\nQuestion: {question}"}]
    result = llm_provider.complete(messages, SYSTEM_PROMPT, tools=None, max_tokens=200)
    if not result or not result.get("text"):
        return None

    text = result["text"].strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()

    try:
        parsed = json.loads(text)
    except Exception:
        return None

    return _validate(parsed, {c["name"] for c in columns})


def _validate(parsed: dict, valid_columns: set) -> dict | None:
    """
    Never trust a column name the model returns without checking it against
    the real dataframe -- an LLM can hallucinate a plausible-looking column
    that doesn't exist, and that would otherwise surface as a confusing
    error several layers downstream instead of a clean 'couldn't parse' skip.
    """
    if not isinstance(parsed, dict):
        return None
    kind = parsed.get("kind")
    if kind not in VALID_KINDS:
        return None

    if kind == "profile":
        return {"kind": "profile", "explicit": False}

    if kind == "compare":
        cat, metric = parsed.get("cat_col"), parsed.get("metric_col")
        if cat in valid_columns and metric in valid_columns and cat != metric:
            return {"kind": "compare", "cat_col": cat, "metric_col": metric, "explicit": True}
        return None

    target = parsed.get("target")
    if target in valid_columns:
        return {"kind": kind, "target": target, "explicit": True}
    return None
