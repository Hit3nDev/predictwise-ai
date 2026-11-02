import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def c():
    import main
    return TestClient(main.app)


@pytest.fixture(scope="module")
def kirana(c):
    return c.post("/samples/kirana_sales/load").json()["id"]


@pytest.fixture(scope="module")
def customers(c):
    return c.post("/samples/customers/load").json()["id"]


def test_playbook_for_a_shop(c, kirana):
    r = c.get(f"/datasets/{kirana}/playbook").json()
    assert r["available"] and 1 <= len(r["items"]) <= 6
    titles = " ".join(i["title"] for i in r["items"])
    assert "last 30 days" in titles or "Stock up" in titles or "Never run out" in titles
    assert all(i["tone"] in ("do", "watch", "good") and i["detail"] for i in r["items"])
    assert "$" not in titles + " ".join(i["detail"] for i in r["items"])


def test_playbook_without_dates_uses_outcome_groups(c, customers):
    r = c.get(f"/datasets/{customers}/playbook").json()
    assert r["available"]


def test_chat_playbook_intent(c, kirana):
    r = c.post(f"/datasets/{kirana}/chat", json={"message": "what should I do this week?"}).json()
    assert r["kind"] == "playbook" and r["blocks"][0]["type"] == "playbook"


def test_private_mode_never_calls_the_ai(c, kirana, monkeypatch):
    import llm_chat, llm_resolver, lang

    def boom(*a, **k):
        raise AssertionError("AI was called in private mode")
    monkeypatch.setattr(llm_chat, "chat", boom)
    monkeypatch.setattr(llm_resolver, "resolve", boom)
    monkeypatch.setattr(lang, "translate_lines", boom)
    r = c.post(f"/datasets/{kirana}/chat", json={"message": "tell me a joke about onions", "private": True, "lang": "hi"})
    assert r.status_code == 200
    assert "Private mode" in " ".join(r.json()["narrative"])


def test_llm_answer_carries_its_working(c, customers, monkeypatch):
    import llm_chat
    monkeypatch.setattr(llm_chat, "chat", lambda *a, **k: {
        "narrative": ["Average income is ₹59,898."],
        "trace": [{"expr": "df['income'].mean()", "result": "59898.1"}]})
    r = c.post(f"/datasets/{customers}/chat", json={"message": "avg income of customers in the south zone"}).json()
    assert r["source"] == "llm"
    assert r["blocks"][0] == {"type": "work", "steps": [{"expr": "df['income'].mean()", "result": "59898.1"}]}


def test_wrong_language_is_translated(monkeypatch):
    import lang
    monkeypatch.setattr(lang.llm_provider, "configured", lambda: True)
    monkeypatch.setattr(lang.llm_provider, "complete", lambda **k: {"text": '["दिल्ली में औसत आय ₹59,670 है।"]'})
    assert lang.ensure(["In Delhi the average income is ₹59,670."], "hi") == ["दिल्ली में औसत आय ₹59,670 है।"]
    assert lang.ensure(["दिल्ली में औसत आय ₹59,670 है।"], "hi") == ["दिल्ली में औसत आय ₹59,670 है।"]   # already Hindi: untouched
    assert lang.ensure(["In Delhi the average income is ₹59,670."], "en") == ["In Delhi the average income is ₹59,670."]
