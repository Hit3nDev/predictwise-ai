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

def _clean_key(v):
    # Keys pasted into PowerShell often carry stray quotes or spaces.
    return v.strip().strip("\"'").strip() if v else None


GROQ_API_KEY = _clean_key(os.environ.get("GROQ_API_KEY"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
# Groq retires models from time to time. If the first one is refused, try the
# next so the chat keeps working instead of silently falling back.
GROQ_MODELS = [GROQ_MODEL] + [
    m for m in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b", "openai/gpt-oss-120b")
    if m != GROQ_MODEL
]
LAST_ERROR = {"message": None}
_working = {"model": None}
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ANTHROPIC_API_KEY = _clean_key(os.environ.get("ANTHROPIC_API_KEY"))
ANTHROPIC_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

TIMEOUT_SECONDS = 20.0


_PLACEHOLDER_MARKERS = ("your_key_here", "your-key-here", "xxx", "gsk_...", "sk-ant-...")


def _looks_like_placeholder(key: str) -> bool:
    return any(m in key.lower() for m in _PLACEHOLDER_MARKERS)


def active_provider() -> str | None:
    """Groq first -- it's the free path. Anthropic as a fallback if configured."""
    if GROQ_API_KEY:
        return "groq"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return None


if GROQ_API_KEY and _looks_like_placeholder(GROQ_API_KEY):
    print("[llm_provider] WARNING: GROQ_API_KEY looks like the placeholder text from an example, "
          "not a real key copied from console.groq.com/keys — every call will fail.", flush=True)
if ANTHROPIC_API_KEY and _looks_like_placeholder(ANTHROPIC_API_KEY):
    print("[llm_provider] WARNING: ANTHROPIC_API_KEY looks like placeholder text, not a real key.", flush=True)


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
    except httpx.HTTPStatusError as exc:
        # The single most useful line in this whole file: a bad/placeholder
        # key, an expired key, or a rate limit all land here, and previously
        # got silently swallowed into the same generic "couldn't answer"
        # message as a model genuinely having no answer — completely
        # indistinguishable from the person's point of view. This prints to
        # the same terminal uvicorn is already running in.
        body = exc.response.text[:300] if exc.response is not None else ""
        LAST_ERROR["message"] = _explain(exc.response.status_code if exc.response is not None else None, body)
        print(f"[llm_provider] {provider} call failed: HTTP {exc.response.status_code if exc.response is not None else '?'} — {body}", flush=True)
        return None
    except Exception as exc:
        print(f"[llm_provider] {provider} call failed: {type(exc).__name__}: {exc}", flush=True)
        LAST_ERROR["message"] = (
            "couldn't reach the AI service from this computer (check your internet or firewall)"
            if "connect" in type(exc).__name__.lower() or "timeout" in type(exc).__name__.lower()
            else f"{type(exc).__name__}: {exc}"
        )
        return None


def _explain(status, body: str) -> str:
    """Turn an API failure into a sentence a person can act on."""
    low = (body or "").lower()
    if status in (401, 403) or "invalid api key" in low:
        return "Groq rejected the API key (it may be wrong, expired or revoked). Make a new one at console.groq.com/keys"
    if status == 429:
        return "Groq's free limit was hit for now. Wait a minute and try again"
    if status in (400, 404) and "model" in low:
        return "the AI model is no longer available on Groq"
    return f"HTTP {status}: {(body or '')[:160]}"


_NOT_CHAT = ("whisper", "guard", "tts", "playai", "embed", "distil-whisper", "orpheus", "safeguard", "compound")
_PREFER = ("llama-3.3", "llama-3.1-70b", "gpt-oss-120b", "qwen", "llama-4", "gpt-oss-20b", "llama-3.1-8b", "llama")
_discovered: list = []


def _discover_groq_models() -> list:
    """Ask Groq which chat models this key can actually use, best-looking first."""
    if _discovered:
        return _discovered
    resp = httpx.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    ids = [m["id"] for m in resp.json().get("data", []) if m.get("active", True)]
    ids = [i for i in ids if not any(x in i.lower() for x in _NOT_CHAT)]
    ids.sort(key=lambda i: next((n for n, p in enumerate(_PREFER) if p in i.lower()), len(_PREFER)))
    print(f"[llm_provider] models available to this key: {ids}", flush=True)
    _discovered.extend(ids)
    return _discovered


def _is_model_error(resp) -> bool:
    low = resp.text.lower()
    return resp.status_code in (400, 404) and ("model" in low) and ("tool" not in low or "not_found" in low)


def _complete_groq(messages, system, tools, max_tokens) -> dict:
    payload_messages = [{"role": "system", "content": system}] + messages
    tried = []
    resp = None

    def attempt(model):
        body = {"model": model, "messages": payload_messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = [_to_openai_tool(t) for t in tools]
        return httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "content-type": "application/json"},
            json=body,
            timeout=TIMEOUT_SECONDS,
        )

    # Remembered from an earlier success so we don't re-probe on every message.
    queue = ([_working["model"]] if _working["model"] else []) + list(GROQ_MODELS)
    discovered = False
    while queue:
        model = queue.pop(0)
        if model in tried:
            continue
        tried.append(model)
        resp = attempt(model)
        if resp.status_code < 400:
            _working["model"] = model
            break
        if _is_model_error(resp):
            print(f"[llm_provider] groq model {model} unavailable, trying another", flush=True)
            if not queue and not discovered:
                discovered = True
                queue.extend(_discover_groq_models())
            continue
        break
    resp.raise_for_status()
    LAST_ERROR["message"] = None
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
