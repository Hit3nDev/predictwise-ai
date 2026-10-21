"""
Privacy shield for anything that leaves this computer.

Customer names, phone numbers and emails are swapped for neutral codes
("Customer 007") before a question, a conversation or a query result is sent to
an AI service, and swapped back in the answer the shopkeeper sees. The AI can
still count, group and rank per customer; it just never learns who they are.

Scope: this protects the chat path (llm_chat, llm_resolver). It is
pseudonymisation, not encryption: a name typed in a way the shield cannot
recognise (a misspelling, a nickname) is sent as typed. Private mode sends nothing.
"""

from __future__ import annotations

import re

import pandas as pd

NAME_HINTS = ("customer", "client", "buyer", "member", "person", "guest", "patient", "party", "name")
NAME_VETO = ("product", "item", "shop", "store", "brand", "city", "category", "file", "area", "sku", "company", "dealer")
PHONE_HINTS = ("phone", "mobile", "contact", "whatsapp", "cell")
EMAIL_HINTS = ("email", "e-mail", "mail")


def _kind(name: str, s: pd.Series) -> str | None:
    c = name.lower()
    if s.dtype.kind in "iuf" and not any(h in c for h in PHONE_HINTS):
        return None
    sample = s.dropna().astype(str).head(200)
    if sample.empty:
        return None
    if any(h in c for h in EMAIL_HINTS) or sample.str.contains(r"^[^@\s]+@[^@\s]+\.\w+$").mean() > 0.8:
        return "email"
    digits = sample.str.replace(r"\D", "", regex=True).str.len()
    if (any(h in c for h in PHONE_HINTS) and (digits >= 8).mean() > 0.6) or (digits.between(10, 13).mean() > 0.9 and sample.str.contains(r"^[+\d\s\-()]+$").mean() > 0.9):
        return "phone"
    if any(h in c for h in NAME_HINTS) and not any(v in c for v in NAME_VETO):
        n = s.nunique()
        if 2 <= n <= max(len(s) * 0.95, 2) and not pd.api.types.is_numeric_dtype(s):
            return "name"
    return None


class Shield:
    def __init__(self, df: pd.DataFrame):
        self.kinds: dict[str, str] = {}
        self.forward: dict[str, str] = {}      # real value -> code
        self.back: dict[str, str] = {}         # code -> real value
        for col in df.columns:
            kind = _kind(str(col), df[col])
            if kind:
                self.kinds[str(col)] = kind
        self._df = df

    @property
    def active(self) -> bool:
        return bool(self.kinds)

    def _code(self, kind: str, n: int) -> str:
        return {"name": f"Customer {n:03d}", "phone": f"PHONE-{n:03d}", "email": f"EMAIL-{n:03d}"}[kind]

    def frame(self) -> pd.DataFrame:
        """A copy of the data with identifying values replaced by codes."""
        out = self._df.copy()
        counters = {"name": 0, "phone": 0, "email": 0}
        for col, kind in self.kinds.items():
            mapping = {}
            for v in out[col].dropna().astype(str).unique():
                if v in self.forward:
                    mapping[v] = self.forward[v]
                    continue
                counters[kind] += 1
                code = self._code(kind, counters[kind])
                self.forward[v], self.back[code] = code, v
                mapping[v] = code
            out[col] = out[col].astype(object).where(out[col].isna(), out[col].astype(str).map(mapping))
        return out

    def mask(self, text: str) -> str:
        if not text or not self.forward:
            return text
        for real in sorted(self.forward, key=len, reverse=True):
            if len(real) >= 3 and real.lower() in text.lower():
                text = re.sub(re.escape(real), self.forward[real], text, flags=re.I)
        return text

    def unmask(self, text: str) -> str:
        if not text or not self.back:
            return text
        for code in sorted(self.back, key=len, reverse=True):
            text = text.replace(code, self.back[code])
        return text

    def summary(self) -> str:
        cols = ", ".join(self.kinds)
        return f"Replaced the values in {cols} with codes before anything was sent to the AI service, and put the real ones back in the answer."
