"""
Look up one customer or one product by name: the facts a shopkeeper wants at the counter,
worked out from the file. "Tell me about Geeta Chauhan" or "Atta 10kg" in the chat, or the
Look up screen. No AI service is involved and every number can be checked by hand.

  find          a card for the customer or product the name points at
  from_question a card when a chat message is a lookup, else None (other engines continue)
  options       the names worth suggesting on the Look up screen
"""

from __future__ import annotations

import difflib
import re

import numpy as np
import pandas as pd

import advanced
import analytics
import shop
from analytics import money

ASK_RE = re.compile(
    r"^\s*(?:tell me about|about|show me|who is|how is|what about|details?(?: of| for| on)?|look ?up|find|"
    r"info(?:rmation)? (?:on|about)|history of|hisab(?: of| for)?)\s+(.+?)\s*[?.!]*\s*$",
    re.I,
)
QUESTION_WORDS = re.compile(r"\b(how|what|which|who|when|why|show|many|much|average|total|top|best|worst|list|chart)\b", re.I)
QUIET_DAYS = 45


# ---------------------------------------------------------------------------
# Matching a typed name to a value in the file
# ---------------------------------------------------------------------------


def _values(df: pd.DataFrame, col: str | None) -> list[str]:
    return [] if not col else sorted(df[col].dropna().astype(str).unique().tolist())


def _match(values: list[str], q: str, fuzzy: bool = True) -> str | None:
    """The value the shopkeeper meant: exact, then the only prefix or substring hit, then close spelling."""
    if not values or not q:
        return None
    ql = q.strip().lower()
    low = {v.lower(): v for v in values}
    if ql in low:
        return low[ql]
    if not fuzzy:
        return None
    starts = [v for v in values if v.lower().startswith(ql)]
    if len(starts) == 1:
        return starts[0]
    contains = [v for v in values if ql in v.lower()]
    if len(contains) == 1:
        return contains[0]
    if starts or contains:
        return None                                  # ambiguous: let the caller suggest
    close = difflib.get_close_matches(ql, list(low), n=1, cutoff=0.75)
    return low[close[0]] if close else None


def _suggest(values: list[str], q: str, n: int = 6) -> list[str]:
    ql = q.strip().lower()
    hits = [v for v in values if ql in v.lower() or v.lower().startswith(ql)]
    if not hits:
        low = {v.lower(): v for v in values}
        hits = [low[c] for c in difflib.get_close_matches(ql, list(low), n=n, cutoff=0.5)]
    return hits[:n]


def options(df: pd.DataFrame) -> dict:
    """Names worth suggesting: the biggest customers and products by sales (or by rows)."""
    r = shop.roles(df)
    rev = shop._revenue(df, r)
    out = {"customers": [], "products": []}
    for key, col, n in (("customers", r["customer"], 24), ("products", r["item"], 40)):
        if not col:
            continue
        names = df[col].astype(str)
        top = rev.groupby(names).sum().sort_values(ascending=False) if rev is not None else names.value_counts()
        out[key] = [str(i) for i in top.head(n).index if str(i) != "nan"]
    return out


def find(df: pd.DataFrame, q: str, fuzzy: bool = True) -> dict:
    r = shop.roles(df)
    q = (q or "").strip()
    if not q:
        return {"available": False, "reason": "Type a customer or product name."}
    custs, items = _values(df, r["customer"]), _values(df, r["item"])
    if not custs and not items:
        return {"available": False, "reason": "This file has no customer or product column to look up."}
    name = _match(custs, q, fuzzy)
    if name:
        return customer_card(df, r, name)
    name = _match(items, q, fuzzy)
    if name:
        return product_card(df, r, name)
    return {"available": False, "reason": f"I could not find a customer or product called “{q}”.",
            "suggestions": _suggest(custs + items, q)}


def from_question(df: pd.DataFrame, question: str) -> dict | None:
    """A card when the message asks about one name ("tell me about X", or just the name)."""
    q = (question or "").strip()
    m = ASK_RE.match(q)
    if m:
        res = find(df, m.group(1), fuzzy=True)
        return res if res.get("available") else None
    bare = re.sub(r"[?.!]+$", "", q).strip()
    if 2 <= len(bare) <= 40 and not QUESTION_WORDS.search(bare):
        res = find(df, bare, fuzzy=False)
        return res if res.get("available") else None
    return None


# ---------------------------------------------------------------------------
# Pieces shared by both cards
# ---------------------------------------------------------------------------


def _monthly(values: pd.Series, dates: pd.Series, title: str, unit: str) -> dict | None:
    """The last year of this person's or product's figures, month by month, as a chart block."""
    if values is None or dates is None:
        return None
    t = pd.DataFrame({"v": values, "d": dates}).dropna()
    if t.empty:
        return None
    t = t[t["d"] > dates.max() - pd.Timedelta(days=365)]
    m = t.groupby(t["d"].dt.to_period("M"))["v"].sum()
    if len(m) < 2:
        return None
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0.0)
    return {"type": "chart", "chart": "line", "title": title, "unit": unit,
            "points": [{"label": p.strftime("%b %y"), "value": float(v)} for p, v in m.items()], "forecast": []}


def _days_ago(n: int) -> str:
    return "today" if n == 0 else "yesterday" if n == 1 else f"{n} days ago"


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


def customer_card(df: pd.DataFrame, r: dict, name: str) -> dict:
    cust = r["customer"]
    mask = df[cust].astype(str) == name
    rows = df[mask]
    rev = shop._revenue(df, r)
    d = shop._dates(df, r)
    facts, lines = [], []

    bills = int(rows[r["bill"]].nunique()) if r["bill"] else int(len(rows))
    spend = float(rev.loc[rows.index].sum()) if rev is not None else None
    rank = total_customers = None
    if spend is not None:
        per = rev.groupby(df[cust].astype(str)).sum().sort_values(ascending=False)
        rank, total_customers = int(per.index.get_loc(name)) + 1, int(len(per))
        facts.append({"label": "Total spent", "value": money(spend)})
        facts.append({"label": "Average bill" if r["bill"] else "Average row", "value": money(spend / max(bills, 1))})
        facts.append({"label": "Rank by spend", "value": f"#{rank} of {total_customers:,}"})
    facts.append({"label": "Bills" if r["bill"] else "Rows", "value": f"{bills:,}"})

    status, days_since, first = "Regular", None, None
    if d is not None:
        dd = d.loc[rows.index].dropna()
        if len(dd):
            first, last, end = dd.min(), dd.max(), d.max()
            days_since = int((end - last).days)
            facts.append({"label": "Last visit", "value": _days_ago(days_since)})
            facts.append({"label": "Customer since", "value": f"{first:%b %Y}"})
            if (end - first).days <= 30:
                status = "New"
            elif days_since > QUIET_DAYS:
                status = "Gone quiet"

    favourites = []
    if r["item"]:
        measure = rows[r["qty"]].astype(float) if r["qty"] else (rev.loc[rows.index] if rev is not None else pd.Series(1.0, index=rows.index))
        g = measure.groupby(rows[r["item"]].astype(str)).sum().sort_values(ascending=False).head(3)
        favourites = [{"name": str(k), "value": f"{v:,.0f} units" if r["qty"] else money(float(v))} for k, v in g.items()]

    owed = None
    if r["payment"] and rev is not None:
        pay = rows[r["payment"]].astype(str)
        credit = pay.str.contains(shop.CREDIT_RE) & ~pay.str.contains("card", case=False)
        repaid = pay.str.contains(shop.REPAID_RE) & ~credit
        amt = rev.loc[rows.index]
        owed = float(max(amt[credit].sum() - amt[repaid].sum(), 0.0))
        if owed > 0:
            facts.append({"label": "Udhaar owed", "value": money(owed)})

    phone = ""
    if r["phone"]:
        p = rows[r["phone"]].dropna().astype(str)
        phone = shop._phone(p.iloc[0]) if len(p) else ""

    if spend is not None:
        lines.append(f"{name} has spent {money(spend)} across {bills:,} {'bills' if r['bill'] else 'rows'}, "
                     f"rank #{rank} of your {total_customers:,} customers.")
    else:
        lines.append(f"{name} appears on {bills:,} rows.")
    if status == "New":
        lines.append(f"A new customer: first seen {first:%d %b %Y}. A good second visit makes them a regular.")
    elif status == "Gone quiet":
        lines.append(f"Last visit {_days_ago(days_since)}: they have gone quiet, so a quick message is worth it.")
    elif days_since is not None:
        lines.append(f"Last visit {_days_ago(days_since)}.")
    if favourites:
        lines.append("Buys mostly " + ", ".join(f["name"] for f in favourites) + ".")
    if owed:
        lines.append(f"Owes {money(owed)} on udhaar.")

    first_name = name.split()[0]
    if owed:
        action, text = "Send udhaar reminder", shop.TEXT["en"]["udhaar"].format(name=first_name, shop="our shop", amt=money(owed))
    elif status == "Gone quiet":
        action, text = "Send a come-back message", shop.TEXT["en"]["winback"].format(name=first_name, shop="our shop")
    else:
        action, text = "Say thanks on WhatsApp", f"Namaste {first_name} ji, thank you for shopping with us! Do tell us if there is anything you would like us to stock."
    chart = _monthly(rev.loc[rows.index] if rev is not None else None, d, "Spend by month", "money")

    return {
        "available": True, "kind": "customer", "name": name, "status": status, "facts": facts,
        "favourites": favourites, "owed": owed, "phone": phone,
        "message": {"action": action, "text": text, "link": shop._link(phone, text)},
        "chart": chart, "narrative": lines,
    }


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


def product_card(df: pd.DataFrame, r: dict, name: str) -> dict:
    item = r["item"]
    mask = df[item].astype(str) == name
    rows = df[mask]
    rev = shop._revenue(df, r)
    d = shop._dates(df, r)
    facts, lines = [], []

    units = float(rows[r["qty"]].astype(float).sum()) if r["qty"] else None
    revenue = share = rank = None
    if units is not None:
        facts.append({"label": "Units sold", "value": f"{units:,.0f}"})
    if rev is not None:
        revenue = float(rev.loc[rows.index].sum())
        total = float(rev.sum())
        share = revenue / total if total else 0.0
        per = rev.groupby(df[item].astype(str)).sum().sort_values(ascending=False)
        rank = int(per.index.get_loc(name)) + 1
        facts.append({"label": "Sales", "value": money(revenue)})
        facts.append({"label": "Share of sales", "value": f"{share:.1%}"})
        facts.append({"label": "Rank", "value": f"#{rank} of {len(per)}"})

    margin = profit = None
    if r["cost"] and r["price"]:
        cost, price = rows[r["cost"]].astype(float), rows[r["price"]].astype(float)
        m = ((price - cost) / price.replace(0, np.nan)).mean()
        if pd.notna(m):
            margin = float(m)
            facts.append({"label": "Margin", "value": f"{margin:.0%}"})
        qty = rows[r["qty"]].astype(float) if r["qty"] else 1.0
        profit = float((price * qty - cost * qty).sum())
        facts.append({"label": "Profit", "value": money(profit)})

    status, days_since, best_day = "Steady", None, None
    measure = rows[r["qty"]].astype(float) if r["qty"] else (rev.loc[rows.index] if rev is not None else pd.Series(1.0, index=rows.index))
    if d is not None:
        dd = d.loc[rows.index].dropna()
        if len(dd):
            end, last = d.max(), dd.max()
            days_since = int((end - last).days)
            facts.append({"label": "Last sold", "value": _days_ago(days_since)})
            if rev is not None and len(dd) >= 14:
                by_day = rev.loc[dd.index].groupby(dd.dt.dayofweek).sum()
                best_day = analytics.WEEKDAYS[int(by_day.idxmax())]
                facts.append({"label": "Best day", "value": best_day})
            m = measure.loc[dd.index]
            a = float(m[dd > end - pd.Timedelta(days=14)].sum())
            b = float(m[(dd <= end - pd.Timedelta(days=14)) & (dd > end - pd.Timedelta(days=28))].sum())
            if b > 0:
                ch = (a - b) / b
                status = "Rising" if ch >= 0.15 else "Falling" if ch <= -0.15 else "Steady"
            if dd.dt.normalize().nunique() >= 8 and days_since >= 14:
                status = "Stopped selling"

    bought_with = []
    if r["bill"]:
        bills_with = set(rows[r["bill"]].dropna())
        if len(bills_with) >= 10:
            others = df[df[r["bill"]].isin(bills_with) & ~mask]
            if len(others):
                per_bill = others.groupby(r["bill"])[item].agg(lambda s: set(s.astype(str)))
                counts = pd.Series([x for s in per_bill for x in s]).value_counts().head(3)
                bought_with = [{"name": str(k), "share": f"{v / len(bills_with):.0%}"} for k, v in counts.items()]

    top_customers = []
    if r["customer"]:
        g = measure.groupby(rows[r["customer"]].astype(str)).sum().sort_values(ascending=False).head(3)
        top_customers = [{"name": str(k), "value": f"{v:,.0f} units" if r["qty"] else money(float(v))} for k, v in g.items()]

    order = None
    try:
        sp = advanced.stock_plan(df)
        if sp.get("available"):
            row = next((x for x in sp["rows"] if x["Product"] == name), None)
            if row:
                order = {"likely": int(row["Likely next 7 days"]), "order": int(row["Order about"]), "trend": row["Trend"]}
                facts.append({"label": "Order for next week", "value": f"{order['order']:,}"})
    except Exception:
        order = None

    if revenue is not None:
        lines.append(f"{name} brought in {money(revenue)}, {share:.1%} of all sales, rank #{rank} of your {len(per)} products"
                     + (f", from {units:,.0f} units." if units is not None else "."))
    elif units is not None:
        lines.append(f"{name}: {units:,.0f} units sold.")
    else:
        lines.append(f"{name} appears on {len(rows):,} rows.")
    if margin is not None:
        lines.append(f"You keep about {margin:.0%} of every rupee it sells, {money(profit)} profit in total.")
    if status == "Stopped selling":
        lines.append(f"It last sold {_days_ago(days_since)} and looks to have stopped. Sell off what is left before reordering.")
    elif status in ("Rising", "Falling"):
        lines.append(f"Sales are {status.lower()} compared with the two weeks before" + (f"; best day is {best_day}." if best_day else "."))
    elif best_day:
        lines.append(f"Sells most on {best_day}s.")
    if bought_with:
        lines.append("Usually bought with " + ", ".join(f"{b['name']} ({b['share']} of its bills)" for b in bought_with[:2]) + ".")
    if order:
        lines.append(f"For next week, order about {order['order']:,} (likely demand {order['likely']:,}).")

    unit = "money" if rev is not None else "number"
    chart = _monthly(rev.loc[rows.index] if rev is not None else measure, d, "Sales by month" if rev is not None else "Units by month", unit)

    return {
        "available": True, "kind": "product", "name": name, "status": status, "facts": facts,
        "bought_with": bought_with, "top_customers": top_customers, "order": order, "margin": margin,
        "chart": chart, "narrative": lines,
    }
