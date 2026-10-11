"""
Reply-in-your-language support.

Questions in any language reach the LLM path as-is; we just tell it which
language to answer in. Answers produced by the offline engines are written in
English, so when another language is chosen and an LLM key is configured we
translate those lines (numbers and names untouched). Without a key they stay
in English and the interface says so rather than pretending.
"""

import json

import llm_provider

LANGUAGES = {
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "hinglish": "Hinglish (Hindi in Roman script, the way people text)",
    "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "mr": "Marathi", "gu": "Gujarati",
}


def instruction(lang: str | None) -> str:
    if not lang or lang == "en" or lang not in LANGUAGES:
        return ""
    return f"\nReply in {LANGUAGES[lang]}. Keep numbers, currency symbols and column values exactly as they are."


def translate_lines(lines: list[str], lang: str | None) -> list[str]:
    """Translate narrative lines; on any failure return them unchanged."""
    if not lang or lang == "en" or lang not in LANGUAGES or not llm_provider.configured() or not lines:
        return lines
    result = llm_provider.complete(
        messages=[{"role": "user", "content": json.dumps(lines, ensure_ascii=False)}],
        system=(
            f"Translate each string in the JSON array into {LANGUAGES[lang]}. Keep every number, ₹ amount, "
            "date, product name and column value exactly as written. Return ONLY a JSON array of the same "
            "length, nothing else."
        ),
        max_tokens=900,
    )
    text = (result or {}).get("text") or ""
    try:
        start, end = text.index("["), text.rindex("]") + 1
        out = json.loads(text[start:end])
        if isinstance(out, list) and len(out) == len(lines) and all(isinstance(x, str) for x in out):
            return out
    except Exception:
        pass
    return lines
