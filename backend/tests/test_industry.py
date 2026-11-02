import json
import os

import numpy as np
import pandas as pd
import pytest

import forecast
import llm_chat
import llm_provider
import privacy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sample(name):
    return pd.read_csv(os.path.join(HERE, "samples", f"{name}.csv"))


# ---------------------------------------------------------------- forecasting

def synthetic(weeks=30, seed=1, mean=20):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2026-01-01", periods=weeks * 7)
    rows = []
    for d in days:
        for p, base in (("Milk", mean), ("Tea", mean / 2), ("Soap", mean / 4)):
            rows.append([d, p, int(rng.poisson(base * (1.3 if d.dayofweek >= 5 else 1.0)))])
    return pd.DataFrame(rows, columns=["date", "item", "quantity"])


def test_forecast_is_deterministic_and_complete():
    a, b = forecast.plan(synthetic()), forecast.plan(synthetic())
    assert a["available"] and a["rows"] == b["rows"]
    assert {r["Product"] for r in a["rows"]} == {"Milk", "Tea", "Soap"}
    for r in a["rows"]:
        lo, hi = map(int, r["Likely range"].split(" to "))
        assert lo <= r["Likely next 7 days"] <= hi + 1
        assert r["Order about"] >= r["Likely next 7 days"]


def test_higher_service_level_orders_more():
    low = {r["Product"]: r["Order about"] for r in forecast.plan(synthetic(), 0.80)["rows"]}
    high = {r["Product"]: r["Order about"] for r in forecast.plan(synthetic(), 0.99)["rows"]}
    assert all(high[p] >= low[p] for p in low) and any(high[p] > low[p] for p in low)


def test_service_level_is_honest_on_held_back_weeks():
    """The cushion is sized without the last 6 weeks, so coverage there is a fair test."""
    covers = [forecast.plan(synthetic(weeks=40, seed=s), 0.95)["check"]["in_stock_ours"] for s in range(5)]
    assert np.mean(covers) >= 0.80               # close to the 95% target, allowing small-sample noise


def test_flat_buffer_comparison_is_reported():
    chk = forecast.plan(sample("kirana_sales"))["check"]
    assert chk["weeks"] == 6 and 0 <= chk["in_stock_flat"] <= 1 and chk["extra_ours"] >= 0


def test_picks_the_method_with_lowest_replay_error():
    r = forecast.plan(sample("kirana_sales"))
    chosen = [p for p in r["proof_rows"] if "(chosen)" in p["Method"]][0]
    best = min(float(p["Average miss"].strip("%")) for p in r["proof_rows"])
    assert float(chosen["Average miss"].strip("%")) == best


def test_forecast_refuses_short_history():
    r = forecast.plan(synthetic(weeks=6))
    assert r["available"] is False and "three months" in r["reason"]


def test_chat_proof_and_stock_service_level(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    ds = c.post("/samples/kirana_sales/load").json()["id"]
    r = c.post(f"/datasets/{ds}/chat", json={"message": "How much should I order?", "private": True}).json()
    assert r["kind"] == "table_block" and "Honest check" in " ".join(r["narrative"])
    r = c.post(f"/datasets/{ds}/chat", json={"message": "How much should I order? I want enough for 99% of weeks", "private": True}).json()
    assert "99%" in r["narrative"][0]
    assert c.get(f"/datasets/{ds}/forecast?service=0.9").json()["service"] == 0.9


# ------------------------------------------------------------------- privacy

def test_shield_finds_identifying_columns_only():
    sh = privacy.Shield(sample("provision_store"))
    assert sh.kinds == {"customer": "name", "phone": "phone"}          # items, bill numbers, payment untouched


def test_shield_roundtrip_and_masking():
    df = sample("provision_store")
    sh = privacy.Shield(df)
    safe = sh.frame()
    real = df["customer"].iloc[0]
    assert real not in set(safe["customer"]) and safe["customer"].nunique() == df["customer"].nunique()
    assert not safe["phone"].astype(str).str.contains(r"\d{10}").any()
    assert real not in sh.mask(f"how much does {real.upper()} owe?")
    assert sh.unmask(sh.mask(f"how much does {real} owe?")) == f"how much does {real} owe?"
    # numbers are untouched, so every calculation gives the same answer
    assert safe["amount"].sum() == df["amount"].sum()


def test_nothing_identifying_reaches_the_ai(monkeypatch):
    df = sample("provision_store")
    who = df.groupby("customer")["amount"].sum().idxmax()
    phone = df.loc[df["customer"] == who, "phone"].iloc[0]
    seen = []

    monkeypatch.setattr(llm_provider, "active_provider", lambda: "groq")
    script = iter([
        {"text": "", "tool_calls": [{"id": "1", "input": {"expression": "df.groupby('customer')['amount'].sum().idxmax()"}}]},
        None,
    ])

    def complete(messages, system, tools=None, max_tokens=500):
        seen.append(json.dumps(messages, ensure_ascii=False))
        nxt = next(script)
        if nxt is None:                      # second call: answer using whatever code the tool returned
            code = json.loads(seen[-1])[-1]["content"]
            return {"text": f"{code.strip()[2:-2] if code.startswith('[(') else code} is the top customer.", "tool_calls": []}
        return nxt

    monkeypatch.setattr(llm_provider, "complete", complete)
    monkeypatch.setattr(llm_provider, "append_assistant_turn", lambda m, r: m.append({"role": "assistant", "content": "ok"}))
    monkeypatch.setattr(llm_provider, "append_tool_results", lambda m, r, outs: m.append({"role": "user", "content": outs[0][1]}))

    cols = [{"name": c, "dtype": str(t)} for c, t in df.dtypes.items()]
    out = llm_chat.chat(df, cols, f"How much has {who} spent? Phone {phone}", history=[{"role": "user", "content": f"about {who}"}])
    assert out is not None
    sent = " ".join(seen)
    assert who not in sent and phone not in sent                   # the AI only ever saw codes
    assert who in out["narrative"][0]                              # but the shopkeeper sees the real name
    assert any(t["expr"] == "Privacy shield" for t in out["trace"])


def test_no_shield_when_nothing_identifying():
    assert not privacy.Shield(sample("kirana_sales")).active


def test_metrics_count_routes_by_template_not_by_id():
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    ds = c.post("/samples/customers/load").json()["id"]
    c.get(f"/datasets/{ds}/toolkit"); c.get(f"/datasets/{ds}/toolkit"); c.get("/datasets/999999/toolkit")
    body = c.get("/metrics").text
    assert 'route="/datasets/{dataset_id}/toolkit",status="200"} 2' in body
    assert 'route="/datasets/{dataset_id}/toolkit",status="404"} 1' in body
    assert f"/datasets/{ds}/" not in body


# --------------------------------------------------------------- calibration

def _trained(target):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    ds = c.post("/samples/customers/load").json()["id"]
    c.post(f"/datasets/{ds}/clean", json={})
    tr = c.post(f"/datasets/{ds}/train", json={"target": target}).json()
    return c, tr


def test_regression_prediction_comes_with_a_tested_range():
    c, tr = _trained("income")
    row = {"age": 40, "city": "Mumbai", "tenure": 5, "purchased": 1}
    r = c.post(f"/models/{tr['best_model_id']}/predict", json={"rows": [row]}).json()["results"][0]
    rg = r["range"]
    assert rg["low"] < r["prediction"] < rg["high"] and rg["level"] == 90
    assert 0.6 <= rg["held_out_coverage"] <= 1.0 and rg["n_test"] >= 10     # the range is checked on unseen rows


def test_classification_prediction_reports_track_record():
    c, tr = _trained("purchased")
    out = c.post(f"/models/{tr['best_model_id']}/predict", json={"rows": [{"age": 40, "income": 70000, "city": "Mumbai", "tenure": 5}]}).json()["results"][0]
    assert out["range"] is None
    if out["reliability"]:
        assert 0 <= out["reliability"]["accuracy"] <= 1 and out["reliability"]["n"] >= 5
