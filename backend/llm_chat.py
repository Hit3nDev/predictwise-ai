"""
LLM-backed chat, with a tool that lets Claude query the dataframe directly.

This is the actual "answer anything" path. query_engine.py and insights.py
cover a wide but fixed set of question shapes (counts, aggregates, top-N,
predictions); this module removes that ceiling by giving Claude a
run_query tool that executes a pandas expression against the real data and
returns the result, so it can compose whatever operation the question
actually needs — including things no fixed shape anticipated, like
multi-condition filters, correlations between two named columns, or a
question that combines a lookup with an explanation.

Sandboxing: the tool runs `eval()` with no builtins and only `df`/`pd`/`np`
in scope, plus a regex blocklist for dangerous substrings before that eval
ever happens. This is defense-in-depth for a local single-user tool, not a
guarantee against a determined attacker — it is not safe to expose this
endpoint on a multi-tenant or public deployment without a real sandboxed
execution environment (a subprocess with resource limits, or a proper
restricted-execution library) in front of it.

NOTE: like llm_resolver.py, the live API round-trip is not exercised by
this project's test suite (no key in the build sandbox). The sandboxing
blocklist, the eval scope restriction, and the fallback-on-any-failure path
are tested directly; the actual conversation with Claude is not.
"""

import os
import re

import numpy as np
import pandas as pd
import httpx

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_SECONDS = 20.0
MAX_TOOL_ROUNDS = 4

BLOCKLIST = re.compile(
    r"__|import|exec|eval|open\s*\(|os\.|sys\.|subprocess|globals|locals|"
    r"getattr|setattr|delattr|compile\s*\(|input\s*\(|file|\.to_csv|\.to_pickle|"
    r"\.write|\.read|breakpoint",
    re.IGNORECASE,
)

RUN_QUERY_TOOL = {
    "name": "run_query",
    "description": (
        "Execute a single read-only pandas expression against the dataframe `df` "
        "(the uploaded dataset) and return the result. Use this for anything that "
        "needs an actual number or lookup from the data — counts, filters, "
        "aggregates, correlations, groupbys. Only `df`, `pd`, and `np` are "
        "available. One expression per call; call it multiple times if you need "
        "several pieces of information. Do not attempt file I/O, imports, or "
        "anything outside a plain data-analysis expression — it will be rejected."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A single Python expression, e.g. \"df[df['city']=='Delhi']['income'].mean()\"",
            }
        },
        "required": ["expression"],
    },
}

SYSTEM_PROMPT = """You are a data analyst answering questions about one uploaded dataset for someone with
no data-analysis background — a small business owner, not an analyst. Use the run_query tool to compute
real numbers from the data; never guess or make up a figure. Keep your final answer to 1-3 short sentences
in plain English, with no jargon (no "R-squared", "standard deviation", "p-value" etc.) and no code shown.
If a question can't be answered from this data, say so plainly rather than guessing."""


SAFE_BUILTINS = {
    "len": len, "str": str, "int": int, "float": float, "round": round,
    "sum": sum, "min": min, "max": max, "abs": abs, "sorted": sorted,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "bool": bool,
    "range": range, "enumerate": enumerate, "zip": zip,
}


def _safe_eval(expression: str, df: pd.DataFrame):
    if BLOCKLIST.search(expression):
        raise ValueError("That operation isn't allowed.")
    if len(expression) > 500:
        raise ValueError("Expression too long.")
    scope = {"df": df, "pd": pd, "np": np, "__builtins__": SAFE_BUILTINS}
    return eval(expression, scope, {})  # noqa: S307 — deliberately restricted, see module docstring


def _describe(columns: list[dict]) -> str:
    return "\n".join(f"- {c['name']} ({c['dtype']})" for c in columns)


def chat(df: pd.DataFrame, columns: list[dict], question: str, history: list[dict] | None = None) -> dict | None:
    """
    Returns {"narrative": [str, ...]} on success, or None if no key is
    configured or the exchange fails for any reason — the caller should fall
    back to the offline paths in that case.
    """
    if not API_KEY or not question or not question.strip():
        return None

    messages = list(history or [])
    messages.append({
        "role": "user",
        "content": f"Dataset columns:\n{_describe(columns)}\n\nQuestion: {question}",
    })

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = httpx.post(
                API_URL,
                headers={
                    "x-api-key": API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 500,
                    "system": SYSTEM_PROMPT,
                    "tools": [RUN_QUERY_TOOL],
                    "messages": messages,
                },
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content", [])
            messages.append({"role": "assistant", "content": blocks})

            tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
            if not tool_calls:
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
                if not text:
                    return None
                return {"narrative": [text], "history": messages}

            tool_results = []
            for call in tool_calls:
                expr = call.get("input", {}).get("expression", "")
                try:
                    result = _safe_eval(expr, df)
                    result_str = str(result)[:2000]
                except Exception as exc:
                    result_str = f"Error: {exc}"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": result_str,
                })
            messages.append({"role": "user", "content": tool_results})

        return None  # ran out of tool-call rounds without a final answer
    except Exception:
        return None
