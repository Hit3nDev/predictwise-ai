import io
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client():
    import main
    return TestClient(main.app)


@pytest.fixture(scope="module")
def kirana(client):
    d = client.post("/samples/kirana_sales/load").json()
    client.post(f"/datasets/{d['id']}/clean", json={})
    return d["id"]


@pytest.fixture(scope="module")
def customers(client):
    d = client.post("/samples/customers/load").json()
    client.post(f"/datasets/{d['id']}/clean", json={})
    tr = client.post(f"/datasets/{d['id']}/train", json={"target": "purchased"}).json()
    return d["id"], tr["best_model_id"]


def test_samples_listed_and_loadable(client):
    names = {s["id"] for s in client.get("/samples").json()}
    assert {"kirana_sales", "customers"} <= names
    assert client.post("/samples/nope/load").status_code == 404


def test_briefing_finds_roles_and_charts(client, kirana):
    b = client.get(f"/datasets/{kirana}/briefing").json()
    assert b["roles"] == {"date": "date", "metric": "sales", "category": "product", "outcome": None}
    assert {c["chart"] for c in b["charts"]} == {"line", "bar"}
    assert any("₹" in h for h in b["headline"])
    assert 0 <= b["quality"]["score"] <= 100 and b["suggested_questions"]


def test_trend_forecast_is_sane(client, kirana):
    t = client.get(f"/datasets/{kirana}/trend").json()
    assert t["available"] and t["freq"] == "month" and t["direction"] == "up"
    assert len(t["series"]) == 12 and len(t["forecast"]) == 3
    f = t["forecast"][0]
    assert f["low"] <= f["value"] <= f["high"]
    assert t["backtest_error"] is not None and t["backtest_error"] < 0.3
    assert client.get(f"/datasets/{kirana}/trend", params={"metric": "zzz"}).status_code == 400


def test_trend_unavailable_without_dates(client, customers):
    t = client.get(f"/datasets/{customers[0]}/trend").json()
    assert t["available"] is False and "date" in t["reason"]


def test_segments_and_anomalies(client, customers, kirana):
    sg = client.get(f"/datasets/{customers[0]}/segments").json()
    assert sg["available"] and 2 <= sg["k"] <= 5
    assert abs(sum(s["share"] for s in sg["segments"]) - 1) < 1e-6
    assert len({s["name"] for s in sg["segments"]}) == sg["k"]          # names are unique
    an = client.get(f"/datasets/{kirana}/anomalies").json()
    assert an["available"] and an["count"] >= 1
    assert "×" in an["rows"][0]["reasons"][0]                           # the planted bulk orders


def test_download_cleaned_csv(client, customers):
    r = client.get(f"/datasets/{customers[0]}/download")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    df = pd.read_csv(io.BytesIO(r.content))
    assert df.isna().sum().sum() == 0


def test_chat_rich_intents(client, kirana, customers):
    def ask(did, q, **kw):
        return client.post(f"/datasets/{did}/chat", json={"message": q, **kw}).json()
    r = ask(kirana, "give me a summary of my data")
    assert r["kind"] == "briefing" and any(b["type"] == "chart" for b in r["blocks"])
    r = ask(kirana, "what will my sales be next month?")
    assert r["kind"] == "chart" and r["blocks"][0]["forecast"]
    r = ask(customers[0], "show me my customer groups")
    assert r["kind"] == "segments"
    r = ask(kirana, "any unusual orders?")
    assert r["kind"] == "anomalies"
    r = ask(customers[0], "which customers should I call first?")
    assert r["kind"] == "table" and len(r["table"]) == 10 and r["table"][0]["chance"].endswith("%")
    assert all(row["purchased"] == 0 for row in r["table"])           # only people not yet won
    r = ask(customers[0], "hello", lang="hi")                           # no key: falls back, doesn't crash
    assert r["narrative"]


def test_score_file_json_and_csv(client, customers):
    _, mid = customers
    new = "age,income,city,tenure\n30,50000,Delhi,3\n45,9999999,Atlantis,2\n"
    r = client.post(f"/models/{mid}/score-file", files={"file": ("new.csv", new, "text/csv")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["summary"]["rows"] == 2 and j["summary"]["low_trust"] == 1
    assert {"predicted_purchased", "chance", "trust"} <= set(j["preview"][0])
    c = client.post(f"/models/{mid}/score-file", params={"format": "csv"}, files={"file": ("new.csv", new, "text/csv")})
    assert c.status_code == 200 and "new_scored.csv" in c.headers["content-disposition"]
    bad = client.post(f"/models/{mid}/score-file", files={"file": ("x.csv", "foo,bar\n1,2\n", "text/csv")})
    assert bad.status_code == 400 and "expects" in bad.json()["detail"]
    assert client.post(f"/models/{mid}/score-file", files={"file": ("x.txt", "hi", "text/plain")}).status_code == 400


def test_rank_and_levers(client, customers):
    _, mid = customers
    r = client.get(f"/models/{mid}/rank", params={"top": 5}).json()
    chances = [x["chance"] for x in r["rows"]]
    assert len(chances) == 5 and chances == sorted(chances, reverse=True)
    low = client.get(f"/models/{mid}/rank", params={"top": 5, "direction": "least"}).json()
    assert low["rows"][0]["chance"] <= chances[-1]
    lv = client.post(f"/models/{mid}/levers", json={"row": {"age": 40, "income": 30000, "city": "Pune", "tenure": 1}}).json()["levers"]
    assert all(l["delta"] > 0 for l in lv)
    changeable = [l["changeable"] for l in lv]
    assert changeable == sorted(changeable, reverse=True)               # actionable levers first


def test_existing_chat_paths_not_hijacked(client, customers):
    did = customers[0]
    def ask(q):
        return client.post(f"/datasets/{did}/chat", json={"message": q}).json()
    r = ask("how many customers are from Delhi")
    assert r["source"] == "offline" and r["kind"] in ("count", "text")
    r = ask("what is the average income")
    assert r["source"] == "offline"
    r = ask("top 5 by income")
    assert r["kind"] == "table" and len(r["table"]) == 5
    r = ask("will customers buy again")
    assert r["kind"] == "predictable" and r["model_id"]


def test_anomalies_judge_rows_against_their_own_group():
    """A pricey product is not an unusual row; a bulk order is."""
    import numpy as np, pandas as pd, analytics
    rng = np.random.default_rng(1)
    n = 400
    product = rng.choice(["milk", "rice"], n)
    price = np.where(product == "rice", 520, 60) + rng.normal(0, 2, n)
    qty = rng.integers(1, 6, n).astype(float)
    qty[7] = 80                                   # the genuine outlier
    df = pd.DataFrame({"product": product, "unit price": price, "quantity": qty})
    res = analytics.anomalies(df)
    flagged = {r["row_number"] - 2 for r in res["rows"]}
    assert 7 in flagged
    assert not any("unit price" in reason for r in res["rows"] for reason in r["reasons"])
