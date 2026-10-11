import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_old_sqlite_schema_is_healed(tmp_path):
    """The exact crash from the screenshots: a db file from before cleaned_path existed."""
    import database, models  # noqa

    eng = create_engine(f"sqlite:///{tmp_path/'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE datasets (id INTEGER PRIMARY KEY, owner_id INTEGER, file_name TEXT NOT NULL, storage_path TEXT NOT NULL, row_count INTEGER, column_count INTEGER, columns_json TEXT, uploaded_at DATETIME)"))
        c.execute(text("INSERT INTO datasets (file_name, storage_path) VALUES ('a.csv','x')"))
    added = database.ensure_schema(bind=eng)
    assert "datasets.cleaned_path" in added
    with eng.begin() as c:
        assert c.execute(text("SELECT file_name, cleaned_path FROM datasets")).fetchone() == ("a.csv", None)
    assert database.ensure_schema(bind=eng) == []  # idempotent


@pytest.fixture(scope="module")
def trained():
    import main
    client = TestClient(main.app)
    with open(os.path.join(ROOT, "sample_customers.csv"), "rb") as f:
        up = client.post("/upload", files={"file": ("sample_customers.csv", f, "text/csv")})
    assert up.status_code == 200, up.text
    did = up.json()["id"]
    assert client.post(f"/datasets/{did}/clean", json={}).status_code == 200
    tr = client.post(f"/datasets/{did}/train", json={"target": "purchased"})
    assert tr.status_code == 200, tr.text
    return client, did, tr.json()


ROW = {"age": 40, "income": 70000, "city": "Mumbai", "tenure": 5}


def test_explanation_adds_up(trained):
    client, _, exp = trained
    r = client.post(f"/models/{exp['best_model_id']}/predict", json={"rows": [ROW], "explain": True})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    e = res["explanation"]
    assert e and e["kind"] == "probability"
    total = sum(c["contribution"] for c in e["contributions"])
    assert abs(total - (e["output"] - e["base"])) < 1e-6   # Shapley efficiency
    assert e["narration"]
    assert res["trust"]["flags"] == [] and res["trust"]["level"] in {"high", "medium"}, res["trust"]


def test_guard_flags_unseen_inputs(trained):
    client, _, exp = trained
    bad = {"age": 900, "income": 70000, "city": "Atlantis", "tenure": 5}
    res = client.post(f"/models/{exp['best_model_id']}/predict", json={"rows": [bad]}).json()["results"][0]
    assert res["trust"]["level"] == "low"
    kinds = {f["kind"] for f in res["trust"]["flags"]}
    assert {"out_of_range", "unseen_category"} <= kinds
    blank = {"age": "", "income": 70000, "city": "Mumbai", "tenure": 5}
    res = client.post(f"/models/{exp['best_model_id']}/predict", json={"rows": [blank]}).json()["results"][0]
    assert res["trust"]["level"] == "medium"
    # a typo'd category gets a "did you mean"
    res = client.post(f"/models/{exp['best_model_id']}/predict", json={"rows": [{**ROW, "city": "mumbai"}]}).json()["results"][0]
    assert "Did you mean" in " ".join(res["trust"]["reasons"])


def test_whatif_curve(trained):
    client, _, exp = trained
    r = client.post(f"/models/{exp['best_model_id']}/whatif", json={"row": ROW, "feature": "income"})
    assert r.status_code == 200, r.text
    w = r.json()
    assert len(w["points"]) >= 10 and 0 <= w["current_output"] <= 1
    r = client.post(f"/models/{exp['best_model_id']}/whatif", json={"row": ROW, "feature": "city"})
    assert r.status_code == 200 and r.json()["kind"] == "categorical"
    assert client.post(f"/models/{exp['best_model_id']}/whatif", json={"row": ROW, "feature": "nope"}).status_code == 400


def test_fairness_audit(trained):
    client, _, exp = trained
    mid = exp["best_model_id"]
    opts = client.get(f"/models/{mid}/fairness/options").json()["columns"]
    names = [o["column"] for o in opts]
    assert "city" in names and "age" in names and "purchased" not in names
    assert next(o for o in opts if o["column"] == "age")["banded"] is True
    for col in ("city", "age"):
        a = client.get(f"/models/{mid}/fairness", params={"group": col})
        assert a.status_code == 200, a.text
        body = a.json()
        assert body["status"] in {"pass", "review", "insufficient_data"}
        assert sum(g["n"] for g in body["groups"]) == exp["n_test"]   # same held-out rows as training
    assert client.get(f"/models/{mid}/fairness", params={"group": "zzz"}).status_code == 400


def test_monitoring_and_report(trained):
    client, _, exp = trained
    mid = exp["best_model_id"]
    mon = client.get(f"/models/{mid}/monitoring").json()
    assert mon["total"] >= 3 and mon["trust_counts"]["low"] >= 1
    for audience in ("simple", "technical"):
        r = client.get(f"/models/{mid}/report", params={"audience": audience, "group": "city"})
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "Fairness check by city" in r.text and "How far to trust it" in r.text
    assert "Model card" in client.get(f"/models/{mid}/report", params={"audience": "technical"}).text
    assert "Model card" not in client.get(f"/models/{mid}/report").text


def test_regression_explain_and_audit(trained):
    client, did, _ = trained
    tr = client.post(f"/datasets/{did}/train", json={"target": "income"}).json()
    assert tr["task"] == "regression"
    mid = tr["best_model_id"]
    row = {"age": 40, "city": "Pune", "tenure": 5, "purchased": 1}
    res = client.post(f"/models/{mid}/predict", json={"rows": [row], "explain": True}).json()["results"][0]
    e = res["explanation"]
    assert e["kind"] == "value"
    assert abs(sum(c["contribution"] for c in e["contributions"]) - (e["output"] - e["base"])) < 1e-4
    a = client.get(f"/models/{mid}/fairness", params={"group": "city"}).json()
    assert a["task"] == "regression" and all("mae" in g for g in a["groups"])
