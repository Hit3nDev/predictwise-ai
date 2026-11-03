"""The What-if simulator: the next month replayed from the shop's own weeks, checked for direction and sanity."""
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import simulate

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")


def sample(name):
    return pd.read_csv(os.path.join(SAMPLES, f"{name}.csv"))


@pytest.fixture(scope="module")
def store():
    return sample("sharma_store")


def test_baseline_is_in_the_range_of_recent_months(store):
    r = simulate.run(store)
    b = r["baseline"]["sales"]
    assert r["available"] and b["p10"] < b["p50"] < b["p90"]
    d = pd.to_datetime(store["date"])
    recent = store.loc[d > d.max() - pd.Timedelta(days=30), "amount"].sum()
    assert 0.8 * recent < b["p50"] < 1.6 * recent                 # Diwali week sits inside the horizon
    assert r["festivals"] and r["festivals"][0]["name"] == "Diwali" and r["fan"]["festival_days"]
    assert len(r["fan"]["base"]["p50"]) == r["horizon"] + 1 and r["fan"]["base"]["p50"][-1] == b["p50"]
    assert r["scenario"] == r["baseline"] and r["effects"] == []


def test_closing_the_busiest_day_costs_sales_unless_everyone_comes_another_day(store):
    opts = simulate.options(store)
    busiest = max(opts["weekdays"], key=lambda w: w["avg"])["index"]
    half = simulate.run(store, {"close_day": {"day": busiest, "shift": 0.5}})
    full = simulate.run(store, {"close_day": {"day": busiest, "shift": 1.0}})
    assert half["delta"]["sales"]["p50"] < -0.04 * half["baseline"]["sales"]["p50"]
    assert abs(full["delta"]["sales"]["p50"]) < 0.01 * full["baseline"]["sales"]["p50"]
    assert half["effects"][0]["label"] == f"Close on {simulate.WEEKDAYS[busiest]}s"
    assert any("come another day" in line for line in half["narrative"])


def test_price_rise_trades_a_little_sales_for_a_lot_of_profit(store):
    mild = simulate.run(store, {"price": {"pct": 5, "sensitivity": "low"}})
    strong = simulate.run(store, {"price": {"pct": 5, "sensitivity": "high"}})
    assert mild["delta"]["profit"]["p50"] > 0 and mild["delta"]["sales"]["p50"] > strong["delta"]["sales"]["p50"]
    assert strong["delta"]["sales"]["p50"] < 0
    # paired futures: the change is far tighter than the futures themselves
    b, d = mild["baseline"]["sales"], mild["delta"]["sales"]
    assert (d["p90"] - d["p10"]) < 0.2 * (b["p90"] - b["p10"])


def test_stopping_udhaar_loses_some_sales_but_raises_cash(store):
    r = simulate.run(store, {"no_udhaar": {"lost": 0.3}})
    assert r["delta"]["sales"]["p50"] < 0 < r["delta"]["cash"]["p50"]
    assert r["scenario"]["cash"]["p50"] == r["scenario"]["sales"]["p50"]


def test_winback_scales_with_the_share_who_return(store):
    none = simulate.run(store, {"winback": {"rate": 0.0}})
    some = simulate.run(store, {"winback": {"rate": 0.5}})
    assert none["delta"]["sales"]["p50"] == 0 and some["delta"]["sales"]["p50"] > 0


def test_offer_sells_more_but_earns_less_at_a_thin_margin(store):
    r = simulate.run(store, {"offer": {"product": "cold drink", "pct": 10}})      # partial name is fine
    assert r["levers"]["offer"]["product"] == "Cold Drink 2L"
    assert r["delta"]["sales"]["p50"] > 0 > r["delta"]["profit"]["p50"]


def test_levers_are_validated_not_trusted(store):
    r = simulate.run(store, {"price": {"pct": 900, "sensitivity": "wild"}, "drop": {"product": "unicorn milk"}, "close_day": {"day": 42}})
    assert r["levers"]["price"]["pct"] == 50 and r["levers"]["price"]["sensitivity"] == 1.0
    assert "drop" not in r["levers"] and r["levers"]["close_day"]["day"] == 6


def test_questions_become_levers(store):
    f = simulate.from_question
    assert f(store, "What if I close on Sundays?")["levers"] == {"close_day": {"day": 6, "shift": 0.5}}
    assert f(store, "what if i raise all prices by 7%")["levers"]["price"] == {"product": None, "pct": 7.0, "sensitivity": 1.0}
    assert f(store, "what if i cut the price of milk 1l by 3%")["levers"]["price"] == {"product": "Milk 1L", "pct": -3.0, "sensitivity": 1.0}
    assert f(store, "What if I stop giving udhaar?")["levers"] == {"no_udhaar": {"lost": 0.3}}
    assert f(store, "What if I give 10% off on Cold Drink 2L?")["levers"]["offer"]["product"] == "Cold Drink 2L"
    assert f(store, "what if I stop selling Biscuits")["levers"]["drop"]["product"] == "Biscuits"
    assert f(store, "Should I message my old customers?")["levers"] == {"winback": {"rate": 0.2}}
    assert f(store, "agar main tuesday ko band rakhu to?")["levers"]["close_day"]["day"] == 1
    assert f(store, "What is the total sales?") is None                    # not a what-if: other engines continue
    assert f(store, "what if I fly to the moon")["available"] is False      # a what-if it cannot rehearse, said plainly


def test_a_file_without_dates_cannot_be_rehearsed():
    assert not simulate.run(sample("customers"))["available"]
    assert not simulate.options(sample("customers"))["available"]


def test_api_and_chat():
    import main
    c = TestClient(main.app)
    ds = c.post("/samples/sharma_store/load").json()["id"]
    r = c.post(f"/datasets/{ds}/chat", json={"message": "What if I close on Sundays?", "lang": "en", "private": True}).json()
    assert r["kind"] == "simulation" and r["blocks"][0]["type"] == "simulation"
    assert "Closing on Sundays" in " ".join(r["narrative"])
    o = c.get(f"/datasets/{ds}/simulate").json()
    assert o["available"] and o["levers"]["no_udhaar"] and o["quiet"] > 0 and o["defaults"]["close_day"] == 1
    s = c.post(f"/datasets/{ds}/simulate", json={"levers": {"close_day": {"day": o["defaults"]["close_day"], "shift": 0.5}}}).json()
    assert s["available"] and s["delta"]["sales"]["p50"] < 0
    assert c.get(f"/datasets/{ds}/toolkit").json()["simulate"]["available"]
