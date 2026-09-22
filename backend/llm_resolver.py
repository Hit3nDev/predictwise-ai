"""
Optional LLM-backed question resolver.

insights.resolve_question() is a heuristic — literal column-name matching
plus a hand-written synonym list. It has a hard ceiling: it can't understand
genuinely open-ended phrasing that doesn't share vocabulary with any column
name or synonym group ("who's worth chasing for a second sale" has no lexical
overlap with a column called 'purchased' at all).

This module is the real fix for that ceiling. If ANTHROPIC_API_KEY is set,
free text is sent to Claude to resolve into the same structured intent shape
insights.resolve_question() produces — genuine language understanding instead
of word lists. Without a key, or if the call fails for any reason, resolve()
returns None and the caller falls back to the heuristic resolver, so the app
behaves identically either way; this only makes free text smarter when
configured.

NOTE: the live API call is not exercised by this project's test suite (no
key is available in the dev sandbox this was built in) — _validate() and the
no-key fallback path are covered, but test with a real key before relying on
this in a demo.
"""

import json
import os

import httpx

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_SECONDS = 10.0

VALID_KINDS = {"predict_number", "repeat", "drivers_number", "drivers_repeat", "compare", "profile"}

SYSTEM_PROMPT = """You turn a plain-language business question about a dataset into a structured intent.
You will be given the dataset's column names and types, and the user's question.
Respond with ONLY a JSON object and nothing else — no markdown fences, no explanation:

{"kind": "predict_number" | "repeat" | "drivers_number" | "drivers_repeat" | "compare" | "profile",
 "target": "<column name>" or null,
 "cat_col": "<column name>" or null,
 "metric_col": "<column name>" or null}

Rules:
- Use column names EXACTLY as given — never invent or alter one.
- "repeat" / "drivers_repeat": target must be a column with exactly two distinct values (a yes/no-style outcome).
- "predict_number" / "drivers_number": target must be a numeric column.
- Use the "drivers_*" kinds when the question asks what AFFECTS, DRIVES, or EXPLAINS a column,
  rather than asking to predict a new case directly.
- Use "compare": cat_col is a category-like column, metric_col is a numeric column to average per group.
- Use "profile" (with target/cat_col/metric_col all null) if the question is vague, general,
  or genuinely doesn't map to answering with a specific column.
"""


def resolve(columns: list[dict], question: str) -> dict | None:
    """
    columns: [{"name": str, "dtype": str}, ...] — from the actual dataframe.
    Returns a dict shaped like insights.resolve_question()'s output, or None
    if no key is configured, the call fails, or the response doesn't hold up.
    """
    if not API_KEY or not question or not question.strip():
        return None

    try:
        response = httpx.post(
            API_URL,
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 200,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": f"Columns: {json.dumps(columns)}\nQuestion: {question}"}
                ],
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"].strip()
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        parsed = json.loads(text)
    except Exception:
        # Network error, bad key, rate limit, malformed JSON — any of these
        # just means "no LLM answer this time", not a request failure.
        return None

    return _validate(parsed, {c["name"] for c in columns})


def _validate(parsed: dict, valid_columns: set[str]) -> dict | None:
    """
    Never trust a column name the model returns without checking it against
    the real dataframe — an LLM can hallucinate a plausible-looking column
    that doesn't exist, and that would otherwise surface as a confusing
    500 several layers downstream instead of a clean 'couldn't parse' skip.
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
