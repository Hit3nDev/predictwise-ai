"""The two demonstration files: every tool lights up on the bills, and the ledger trains cleanly."""
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import analytics

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")


@pytest.fixture(scope="module")
def c():
    import main
    return TestClient(main.app)


def test_sharma_store_powers_every_tool(c):
    ds = c.post("/samples/sharma_store/load").json()["id"]
    c.post(f"/datasets/{ds}/clean", json={"drop_duplicates": True, "numeric_strategy": "median",
                                           "categorical_strategy": "mode", "outlier_method": "none"})
    tk = c.get(f"/datasets/{ds}/toolkit").json()
    assert all(tk[k]["available"] for k in ("profit", "udhaar", "slow", "festival", "bundles", "peak", "stock", "rfm", "simulate")), tk
    b = c.get(f"/datasets/{ds}/briefing").json()
    assert b["roles"]["category"] == "item" and b["roles"]["metric"] == "amount"
    assert any("unusual" in h for h in b["headline"])
    slow = c.get(f"/datasets/{ds}/shop/slow").json()
    assert {r["Product"] for r in slow["rows"]} == {"Candles", "Cold Drink 2L"}
    peak = c.get(f"/datasets/{ds}/shop/peak").json()
    assert "Sunday is your busiest day" in peak["narrative"][0] and "19:00" in peak["narrative"][2]
    profit = c.get(f"/datasets/{ds}/shop/profit").json()
    assert any(r["Product"] == "Milk 1L" and r["Verdict"] == "Sells a lot but earns little" for r in profit["rows"])
    assert profit["watch"][0]["Product"] == "Cooking Oil 1L"
    card = c.get(f"/datasets/{ds}/lookup", params={"q": "dinesh sharma"}).json()
    assert card["kind"] == "customer" and card["owed"] > 0 and card["message"]["link"].startswith("https://wa.me/91")
    bundles = c.get(f"/datasets/{ds}/shop/bundles").json()
    assert bundles["rows"][0]["If they buy"] in ("Bread", "Tea 500g")
    an = c.get(f"/datasets/{ds}/anomalies").json()
    assert an["count"] and "Basmati Rice 5kg" in an["narrative"][0]        # the wedding order, not a price change
    # the real numbers survive the automatic clean: no amount was clipped
    raw = pd.read_csv(os.path.join(SAMPLES, "sharma_store.csv"))
    assert b["stats"][3]["value"] == analytics.fmt("amount", float(raw.drop_duplicates()["amount"].sum()))


def test_udhaar_khata_trains_and_drops_the_id(c):
    df = pd.read_csv(os.path.join(SAMPLES, "udhaar_khata.csv"))
    assert analytics.pick_outcome(df) == "repaid_on_time"
    d = c.post("/samples/udhaar_khata/load").json()
    c.post(f"/datasets/{d['id']}/clean", json={})
    tr = c.post(f"/datasets/{d['id']}/train", json={"target": "repaid_on_time"}).json()
    assert tr["task"] == "classification" and tr["dropped_columns"] == ["customer_id"]
    assert tr["best_model_id"]
    groups = {g["column"] for g in c.get(f"/models/{tr['best_model_id']}/fairness/options").json()["columns"]}
    assert {"area", "gender", "age"} <= groups
