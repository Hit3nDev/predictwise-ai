"""The look-up cards: one customer or product, checked against plain pandas on the same file."""
import os

import pandas as pd
import pytest

import lookup
import shop

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")


def sample(name):
    return pd.read_csv(os.path.join(SAMPLES, f"{name}.csv"))


def facts(card):
    return {f["label"]: f["value"] for f in card["facts"]}


def test_customer_card_matches_hand_calculation():
    df = sample("provision_store")
    name = df["customer"].value_counts().index[0]
    card = lookup.find(df, name.lower())                      # case does not matter
    assert card["available"] and card["kind"] == "customer" and card["name"] == name
    mine = df[df["customer"] == name]
    assert facts(card)["Total spent"] == lookup.money(mine["amount"].sum())
    assert facts(card)["Bills"] == f"{mine['bill_no'].nunique():,}"
    pay = mine["payment"].astype(str)
    credit = pay.str.contains(shop.CREDIT_RE) & ~pay.str.contains("card", case=False)
    repaid = pay.str.contains(shop.REPAID_RE) & ~credit
    assert card["owed"] == pytest.approx(max(mine["amount"][credit].sum() - mine["amount"][repaid].sum(), 0))
    assert card["message"]["link"].startswith("https://wa.me/91") and card["chart"]["points"]


def test_product_card_counts_units_and_finds_companions():
    df = sample("provision_store")
    card = lookup.find(df, "bread")
    assert card["kind"] == "product" and card["name"] == "Bread"
    assert facts(card)["Units sold"] == f"{df[df['item'] == 'Bread']['quantity'].sum():,.0f}"
    assert "Butter 100g" in [b["name"] for b in card["bought_with"]]
    assert "Margin" in facts(card) and card["order"] and card["order"]["order"] >= card["order"]["likely"]


def test_ambiguous_name_gives_suggestions_not_a_guess():
    df = sample("provision_store")
    res = lookup.find(df, "Mohan")                            # several Mohans
    assert not res["available"] and len(res["suggestions"]) >= 2
    assert all("Mohan" in s for s in res["suggestions"])


def test_question_routing():
    df = sample("kirana_sales")
    assert lookup.from_question(df, "Tell me about atta 10kg")["kind"] == "product"
    assert lookup.from_question(df, "Atta 10kg")["name"] == "Atta 10kg"        # the bare name works too
    assert lookup.from_question(df, "tell me about unicorn milk") is None       # unknown: other engines continue
    assert lookup.from_question(df, "how many rows have product = Milk 1L") is None
    assert lookup.from_question(df, "What should I do this week?") is None
    assert lookup.find(df, "")["available"] is False
    opts = lookup.options(df)
    assert "Atta 10kg" in opts["products"] and opts["customers"] == []
    assert lookup.find(sample("customers"), "Mumbai")["available"] is False     # no names to look up


def test_chat_returns_a_card():
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    d = c.post("/samples/provision_store/load").json()
    r = c.post(f"/datasets/{d['id']}/chat", json={"message": "Tell me about Geeta Chauhan", "history": [], "private": True}).json()
    assert r["kind"] == "card" and r["blocks"][0]["type"] == "card" and r["blocks"][0]["name"] == "Geeta Chauhan"
    assert "Geeta Chauhan" in r["narrative"][0]
    o = c.get(f"/datasets/{d['id']}/lookup").json()
    assert o["customers"] and o["products"]
