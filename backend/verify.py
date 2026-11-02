"""
Grounding check for AI answers.

A language model can sound sure and still invent a number. After the model
answers, every figure in its sentence is looked up in the calculations it
actually ran on the shop's data. Figures that appear there are "traced";
figures that do not are listed so the shopkeeper knows what to double check.

This does not judge whether the model reasoned well. It answers one narrow,
checkable question: did this number come out of the data?
"""

from __future__ import annotations

import re

_NUM = re.compile(
    r"(?P<cur>₹|rs\.?|inr)?\s*(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>cr(?:ore)?s?\b|crs?\b|lakhs?\b|lacs?\b|l\b|k\b|%)?",
    re.I,
)
_SCALE = {"cr": 1e7, "crore": 1e7, "crores": 1e7, "crs": 1e7, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "k": 1e3}


def numbers(text: str) -> list[dict]:
    """Every figure in the text, as {"text", "value", "percent"}."""
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group("num")
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        unit = (m.group("unit") or "").lower()
        if unit in ("l", "k") and not (m.group("cur") or "." in raw):
            unit = ""                                  # "Milk 1L", "5k": a size or label, not lakh
        percent = unit == "%"
        if unit in _SCALE:
            value *= _SCALE[unit]
        out.append({"text": m.group(0).strip(), "value": value, "percent": percent,
                    "plain": not (m.group("cur") or unit or "." in raw or "," in raw)})
    return out


def _is_noise(n: dict) -> bool:
    """Years, small counts like 'top 3', and list numbers are not claims about the data."""
    v = n["value"]
    if n["plain"] and (v <= 10 or 1900 <= v <= 2100):
        return True
    return False


def _close(claim: float, source: float) -> bool:
    if claim == source:
        return True
    tol = max(0.5, abs(source) * 0.006)          # rounding: 47,213 -> "47,200" still counts
    if abs(claim - source) <= tol:
        return True
    return False


def check(answer_lines: list[str], trace: list[dict]) -> dict:
    """
    Compare the figures in the answer with the figures the calculations returned.
    status: all (every figure traced), partly, none (nothing traced), nocalc (no calculation ran).
    """
    claims = [n for n in numbers(" ".join(answer_lines)) if not _is_noise(n)]
    if not claims:
        return {"status": "nofigures", "checked": 0, "matched": 0, "unmatched": []}
    if not trace:
        return {"status": "nocalc", "checked": len(claims), "matched": 0, "unmatched": [c["text"] for c in claims][:6]}

    pool = []
    for step in trace:
        for field in ("raw", "result", "expr"):
            for n in numbers(str(step.get(field, ""))):
                pool.append(n["value"])
                if abs(n["value"]) <= 1.5:
                    pool.append(n["value"] * 100)        # 0.18 shown as "18%"
    matched, unmatched = 0, []
    for c in claims:
        if any(_close(c["value"], s) for s in pool):
            matched += 1
        else:
            unmatched.append(c["text"])
    status = "all" if not unmatched else "partly" if matched else "none"
    return {"status": status, "checked": len(claims), "matched": matched, "unmatched": unmatched[:6]}
