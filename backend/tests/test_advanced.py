import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def c():
    import main
    return TestClient(main.app)


def load(c, name):
    return c.post(f"/samples/{name}/load").json()["id"]


@pytest.fixture(scope="module")
def kirana(c): return load(c, "kirana_sales")
@pytest.fixture(scope="module")
def sweet(c): return load(c, "sweet_shop")
@pytest.fixture(scope="module")
def customers(c): return load(c, "customers")


def test_stock_plan_is_sane(c, kirana):
    r = c.get(f"/datasets/{kirana}/stock-plan").json()
    assert r["available"] and r["unit"] == "units"
    rows = r["rows"]
    assert len(rows) == 12
    for x in rows:
        assert x["Order about"] >= x["Likely next 7 days"] >= 0          # safety cushion never negative
        assert x["Trend"] in {"rising", "falling", "steady"}
    # the planner follows what sells: milk and biscuits outsell soap
    names = [x["Product"] for x in rows]
    assert names.index("Milk 1L") < names.index("Soap (4 pack)")


def test_stock_plan_needs_dates_and_products(c, customers):
    assert c.get(f"/datasets/{customers}/stock-plan").json()["available"] is False


def test_chart_on_request(c, kirana):
    for q, dim in [("chart sales by weekday", "weekday"), ("plot total sales by month", "month"),
                   ("graph average sales by category", "category"), ("chart number of orders by payment mode", "payment mode")]:
        r = c.post(f"/datasets/{kirana}/chat", json={"message": q}).json()
        assert r["kind"] == "chart", q
        ch = r["blocks"][0]
        assert ch["type"] == "chart" and ch["title"].endswith(dim) and len(ch["points"]) >= 3
    wk = c.post(f"/datasets/{kirana}/chat", json={"message": "chart sales by weekday"}).json()["blocks"][0]
    assert [p["label"] for p in wk["points"]] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def test_customer_groups_value(c, sweet):
    r = c.get(f"/datasets/{sweet}/customers").json()
    assert r["available"]
    assert sum(g["Customers"] for g in r["groups"]) == 140
    assert {g["Group"] for g in r["groups"]} >= {"Best", "At risk", "Lost"}
    assert 1 <= len(r["winback"]) <= 10
    # win-back list is the *valuable* lapsed customers, biggest first
    spends = [float(w["Total spent"].replace("₹", "").replace(",", "").split()[0]) for w in r["winback"] if " " not in w["Total spent"]]
    assert spends == sorted(spends, reverse=True)


def test_chat_routes_new_intents_without_hijacking_old_ones(c, kirana, sweet, customers):
    ask = lambda d, q: c.post(f"/datasets/{d}/chat", json={"message": q}).json()
    assert ask(kirana, "how much should I order for next week?")["blocks"][0]["csv"] == "stock_plan.csv"
    assert ask(sweet, "which customers should I call first?")["blocks"][-1]["caption"] == "Call these first"
    assert ask(sweet, "who are my best customers")["kind"] == "table_block"
    # existing behaviour stays put
    assert ask(customers, "show me my customer groups")["kind"] == "segments"
    assert ask(kirana, "what will sales look like next month")["kind"] == "chart"
    assert ask(kirana, "what should I do this week?")["kind"] == "playbook"


def test_compare_two_files(c, kirana):
    import pandas as pd, main, os
    # a newer file where one product vanished and prices jumped
    old = pd.read_csv(os.path.join(main.SAMPLES_DIR, "kirana_sales.csv"))
    new = old[old["product"] != "Milk 1L"].copy()
    new["sales"] = new["sales"] * 1.3
    path = os.path.join(main.UPLOAD_DIR, "newer.csv"); new.to_csv(path, index=False)
    with open(path, "rb") as f:
        n = c.post("/upload", files={"file": ("newer.csv", f, "text/csv")}).json()["id"]
    r = c.get(f"/datasets/{n}/compare/{kirana}").json()
    text = " ".join(r["findings"])
    assert r["available"] and "Milk 1L" in text and "sales" in text.lower()


def test_digest_is_shareable_text(c, kirana):
    t = c.get(f"/datasets/{kirana}/digest").json()["text"]
    assert t.startswith("PredictWise summary") and "What to do:" in t and "Order for next week:" in t
    assert "$" not in t


def test_suggested_questions_offer_new_tools(c, sweet, kirana):
    assert "Which customers should I call first?" in c.get(f"/datasets/{sweet}/briefing").json()["suggested_questions"]
    assert "How much should I order for next week?" in c.get(f"/datasets/{kirana}/briefing").json()["suggested_questions"]
