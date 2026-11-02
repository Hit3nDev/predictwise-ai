import datetime as dt
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import shop


@pytest.fixture(scope="module")
def c():
    import main
    return TestClient(main.app)


def load(c, name):
    return c.post(f"/samples/{name}/load").json()["id"]


@pytest.fixture(scope="module")
def prov(c): return load(c, "provision_store")
@pytest.fixture(scope="module")
def kirana(c): return load(c, "kirana_sales")
@pytest.fixture(scope="module")
def customers(c): return load(c, "customers")


def ask(c, ds, q, lang="en", shop_name=""):
    return c.post(f"/datasets/{ds}/chat", json={"message": q, "lang": lang, "private": True, "shop": shop_name}).json()


def test_profit_arithmetic_matches_the_bills():
    df = pd.read_csv("samples/provision_store.csv") if False else pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(shop.__file__), "samples/provision_store.csv"))
    res = shop.profit(df)
    assert res["available"]
    total = (df["amount"] - df["cost_price"] * df["quantity"]).sum()
    assert f"{shop.money(float(total))} profit" in res["narrative"][0]
    # Milk is the planted "busy but thin" item
    assert any(r["Product"] == "Milk 1L" and "earns little" in r["Verdict"] for r in res["rows"])


def test_profit_flags_cost_creep():
    d = pd.date_range("2026-01-01", periods=240)
    cost = [10.0] * 150 + [12.0] * 90
    df = pd.DataFrame({"date": d, "item": "Oil", "quantity": 1, "selling_price": 14.0, "cost_price": cost, "amount": 14.0})
    others = [df.assign(item=n, cost_price=5.0, selling_price=8.0, amount=8.0) for n in ("Salt", "Tea")]
    watch = shop.profit(pd.concat([df] + others))["watch"]
    assert [w["Product"] for w in watch] == ["Oil"] and float(watch[0]["Rise"].strip("+%")) >= 10


def test_udhaar_totals_and_chase_flag(c, prov):
    r = c.get(f"/datasets/{prov}/shop/udhaar").json()
    assert r["available"] and len(r["rows"]) == 14
    df = pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(shop.__file__), "samples/provision_store.csv"))
    owed = df[df["payment"] == "Udhaar"]["amount"].sum()
    assert abs(r["total"] - owed) < 1
    assert "record repayments" in " ".join(r["narrative"])


def test_udhaar_repayment_reduces_balance():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=60),
        "customer": (["Asha Devi", "Ravi Kumar"] + [f"Cust {i}" for i in range(10)]) * 5,
        "amount": 100.0, "payment": (["Udhaar", "Cash"] + ["Cash"] * 10) * 5})
    df.loc[df.index[-12], "payment"] = "Repaid"
    r = shop.udhaar(df)
    assert r["available"] and r["raw"][0]["customer"] == "Asha Devi"
    assert r["raw"][0]["amount"] == 100.0 * 4 - 100.0


def test_slow_movers_finds_stopped_products(c, prov):
    r = c.get(f"/datasets/{prov}/shop/slow").json()
    names = [x["Product"] for x in r["rows"]]
    assert "Pickle Jar" in names and "Milk 1L" not in names


def test_festival_uses_last_years_data(c, prov):
    df = pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(shop.__file__), "samples/provision_store.csv"))
    r = shop.festivals(df, today=dt.date(2026, 10, 12))
    text = " ".join(r["narrative"])
    assert "Dussehra is in 8 days" in text and "Dhanteras" in text
    dhan = next(b for b in r["blocks"] if "Dhanteras" in b["caption"])
    assert any(row["Product"].startswith("Diyas") for row in dhan["rows"])      # the planted festival item


def test_festival_without_history_says_so():
    df = pd.DataFrame({"date": pd.date_range("2026-08-01", periods=70), "item": ["a", "b"] * 35, "amount": 100.0})
    r = shop.festivals(df, today=dt.date(2026, 10, 12))
    assert "does not cover" in " ".join(r["narrative"])


def test_bundles_find_planted_pairs(c, prov):
    r = c.get(f"/datasets/{prov}/shop/bundles").json()
    pairs = {(x["If they buy"], x["They also buy"]) for x in r["rows"]}
    assert ("Bread", "Butter 100g") in pairs and ("Soap", "Detergent 1kg") in pairs


def test_peak_day(c, prov):
    r = c.get(f"/datasets/{prov}/shop/peak").json()
    assert "Saturday is your busiest day" in r["narrative"][0]


def test_messages_have_working_whatsapp_links():
    df = pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(shop.__file__), "samples/provision_store.csv"))
    for lang in ("en", "hi"):
        m = shop.messages(df, "udhaar", lang, "Sharma Store")
        first = m["messages"][0]
        assert first["link"].startswith("https://wa.me/91") and "Sharma%20Store" in first["link"]
        assert first["phone"].isdigit() and len(first["phone"]) == 12
    hi = shop.messages(df, "udhaar", "hi", "Sharma Store")["messages"][0]["text"]
    assert "बकाया" in hi
    sup = shop.messages(df, "supplier", "en", "Sharma Store")["messages"][0]
    assert "Milk 1L" in sup["text"] and sup["link"].startswith("https://wa.me/?text=")


def test_phone_normalising():
    assert shop._phone("+91 98001 04432") == "919800104432"
    assert shop._phone("098001 04432") == "919800104432"
    assert shop._phone("n/a") == ""


@pytest.mark.parametrize("q,kind", [
    ("who owes me money?", "table_block"),
    ("which products give me the most profit?", "table_block"),
    ("what is not selling?", "table_block"),
    ("what should I stock for Diwali?", "table_block"),
    ("what do customers buy together?", "table_block"),
    ("which day is busiest?", "table_block"),
    ("write a whatsapp reminder for udhaar", "messages"),
])
def test_chat_routes_to_shop_tools(c, prov, q, kind):
    r = ask(c, prov, q)
    assert r["source"] == "analytics" and r["kind"] == kind, r


def test_chat_message_uses_shop_name_and_language(c, prov):
    r = ask(c, prov, "write a message to my udhaar customers", lang="hi", shop_name="Gupta Kirana")
    msg = r["blocks"][0]["messages"][0]["text"]
    assert "Gupta Kirana" in msg and "नमस्ते" in msg


def test_tools_say_why_when_data_is_missing(c, kirana, customers):
    assert "cost price" in c.get(f"/datasets/{kirana}/shop/profit").json()["reason"]
    assert c.get(f"/datasets/{customers}/shop/udhaar").json()["available"] is False
    t = c.get(f"/datasets/{kirana}/toolkit").json()
    assert t["stock"]["available"] and not t["udhaar"]["available"]


def test_existing_questions_still_route_the_old_way(c, kirana):
    for q, kind in [("What should I do this week?", "playbook"), ("How much should I order?", "table_block")]:
        assert ask(c, kirana, q)["kind"] == kind
