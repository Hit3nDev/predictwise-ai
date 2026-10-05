"""
Provider abstraction so llm_resolver.py and llm_chat.py don't need to know
which LLM is actually configured.

Anthropic has no free API tier, so this defaults to Groq -- free, no credit
card, OpenAI-compatible chat completions with tool/function calling. If the
user later gets Anthropic access, ANTHROPIC_API_KEY still works; Groq takes
priority if both are set, since it's the zero-cost path.

Exposes one function, complete(), that normalizes both providers' very
different request/response shapes (Anthropic's Messages API with top-level
`tools` and `tool_use` content blocks, vs. OpenAI-style chat completions with
`tools`/`tool_calls`) into one shape the callers can use identically:

    {"text": str | None, "tool_calls": [{"id", "name", "input": dict}], ...}

NOTE: as with the rest of the LLM-backed code in this project, the live
network round-trip to either provider is not exercised by the test suite --
no key was available in the sandbox this was built in. Provider selection,
request-shape construction, and response parsing are tested against
hand-built sample payloads matching each provider's documented format; the
actual conversation is not. Test with a real key before relying on this.
"""

import json as _json
import os

import httpx

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

TIMEOUT_SECONDS = 20.0


def active_provider() -> str | None:
    """Groq first -- it's the free path. Anthropic as a fallback if configured."""
    if GROQ_API_KEY:
        return "groq"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return None


def configured() -> bool:
    """True if any provider is set up -- convenience alias for active_provider()."""
    return active_provider() is not None


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def complete(messages: list, system: str, tools=None, max_tokens: int = 500):
    """
    messages: plain [{"role": "user"|"assistant", "content": str}, ...] --
    provider-specific tool-result formatting is handled internally per call,
    since the two APIs disagree on how a tool result gets threaded back in.
    Returns None on any failure (no key, network error, bad response) so
    callers can fall back to the offline paths uniformly.
    """
    provider = active_provider()
    if not provider:
        return None
    try:
        if provider == "groq":
            return _complete_groq(messages, system, tools, max_tokens)
        return _complete_anthropic(messages, system, tools, max_tokens)
    except Exception:
        return None


def _complete_groq(messages, system, tools, max_tokens) -> dict:
    payload_messages = [{"role": "system", "content": system}] + messages
    body = {"model": GROQ_MODEL, "messages": payload_messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = [_to_openai_tool(t) for t in tools]

    resp = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "content-type": "application/json"},
        json=body,
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    choice = resp.json()["choices"][0]["message"]

    tool_calls = []
    for tc in choice.get("tool_calls") or []:
        try:
            args = _json.loads(tc["function"]["arguments"])
        except Exception:
            args = {}
        tool_calls.append({"id": tc["id"], "name": tc["function"]["name"], "input": args})

    return {
        "text": choice.get("content"),
        "tool_calls": tool_calls,
        "_provider": "groq",
        "_raw_assistant_message": choice,
    }


def _complete_anthropic(messages, system, tools, max_tokens) -> dict:
    body = {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system, "messages": messages}
    if tools:
        body["tools"] = tools

    resp = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])

    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip() or None
    tool_calls = [
        {"id": b["id"], "name": b["name"], "input": b.get("input", {})}
        for b in blocks if b.get("type") == "tool_use"
    ]
    return {"text": text, "tool_calls": tool_calls, "_provider": "anthropic", "_raw_blocks": blocks}


def append_assistant_turn(messages: list, result: dict) -> None:
    """Append the assistant's turn to the running history in whichever shape
    that provider needs it to appear in on the next call."""
    if result["_provider"] == "groq":
        messages.append({"role": "assistant", "content": result["_raw_assistant_message"].get("content"),
                          "tool_calls": result["_raw_assistant_message"].get("tool_calls")})
    else:
        messages.append({"role": "assistant", "content": result["_raw_blocks"]})


def append_tool_results(messages: list, result: dict, outputs: list) -> None:
    """outputs: [(tool_call_id, result_string), ...], in the same order as result['tool_calls']."""
    if result["_provider"] == "groq":
        for call_id, output in outputs:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
    else:
        messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": output}
                for call_id, output in outputs
            ],
        })
