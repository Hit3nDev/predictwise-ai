import httpx, pytest
import llm_provider as lp


class FakeResp:
    def __init__(self, status, text, js=None):
        self.status_code, self.text, self._js = status, text, js
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=self)


def _use(monkeypatch, responses):
    monkeypatch.setattr(lp, "GROQ_API_KEY", "gsk_test")
    calls = []
    def post(url, headers=None, json=None, timeout=None):
        calls.append(json["model"]); return responses.pop(0)
    monkeypatch.setattr(lp.httpx, "post", post)
    return calls


OK = FakeResp(200, "", {"choices": [{"message": {"content": "ok", "tool_calls": None}}]})


def test_retired_model_falls_through_to_next(monkeypatch):
    calls = _use(monkeypatch, [FakeResp(400, '{"error":"The model `x` has been decommissioned"}'), OK])
    out = lp.complete([{"role": "user", "content": "hi"}], "sys")
    assert out["text"] == "ok" and len(calls) == 2 and calls[0] != calls[1]


def test_discovers_models_when_every_default_is_gone(monkeypatch):
    lp._working["model"] = None; lp._discovered.clear()
    gone = '{"error":{"message":"The model `m` does not exist or you do not have access to it.","code":"model_not_found"}}'
    n = len(lp.GROQ_MODELS)
    calls = _use(monkeypatch, [FakeResp(404, gone) for _ in range(n)] + [OK])
    listing = FakeResp(200, "", {"data": [{"id": "whisper-large-v3"}, {"id": "new-chat-model-9"}, {"id": "llama-guard-4"}]})
    monkeypatch.setattr(lp.httpx, "get", lambda *a, **k: listing)
    out = lp.complete([{"role": "user", "content": "hi"}], "sys")
    assert out["text"] == "ok" and calls[-1] == "new-chat-model-9"
    assert lp._working["model"] == "new-chat-model-9"
    lp._working["model"] = None; lp._discovered.clear()


def test_bad_key_gives_actionable_reason(monkeypatch):
    _use(monkeypatch, [FakeResp(401, '{"error":{"message":"Invalid API Key"}}')])
    assert lp.complete([{"role": "user", "content": "hi"}], "sys") is None
    assert "rejected the API key" in lp.LAST_ERROR["message"]


def test_rate_limit_reason_when_every_model_is_busy(monkeypatch):
    lp._working["model"] = None
    _use(monkeypatch, [FakeResp(429, "rate limit") for _ in range(len(lp.GROQ_MODELS) + 1)])
    lp.complete([{"role": "user", "content": "hi"}], "sys")
    assert "limit" in lp.LAST_ERROR["message"]


def test_busy_model_falls_through_to_another_models_quota(monkeypatch):
    """Each Groq model has its own free quota: a 429 on one is answered by the next, and the
    stand-in is not remembered as the usual model."""
    lp._working["model"] = None
    calls = _use(monkeypatch, [FakeResp(429, "rate limit"), OK])
    out = lp.complete([{"role": "user", "content": "hi"}], "sys")
    assert out["text"] == "ok" and len(calls) == 2 and calls[0] != calls[1]
    assert lp._working["model"] is None


def test_bad_key_stops_the_search_immediately(monkeypatch):
    lp._working["model"] = None
    calls = _use(monkeypatch, [FakeResp(401, '{"error":{"message":"Invalid API Key"}}'), OK])
    assert lp.complete([{"role": "user", "content": "hi"}], "sys") is None and len(calls) == 1


def test_frame_description_lists_real_values_and_date_span():
    import llm_chat, pandas as pd
    df = pd.DataFrame({"date": ["2025-10-01", "2025-10-02", "2025-10-03"], "product": ["Tea 500g", "Atta 10kg", "Tea 500g"],
                       "sales": [100.0, 250.5, 90.0]})
    text = llm_chat.describe_frame(df)
    assert "'Tea 500g'" in text and "'Atta 10kg'" in text
    assert "from 2025-10-01 to 2025-10-03" in text and "pd.to_datetime(df['date'])" in text
    assert "sales (number, from 90 to 250.50)" in text


def test_key_with_stray_quotes_is_cleaned():
    assert lp._clean_key('  "gsk_abc" ') == "gsk_abc"


def test_llm_answers_are_rupees_without_markdown():
    import llm_chat
    assert llm_chat.clean_answer("The average order value is about **$788.11**.") == "The average order value is about ₹788."
    assert llm_chat.clean_answer("Total is $3,386,700 overall") == "Total is ₹33.87 L overall"
    assert "*" not in llm_chat.clean_answer("- **Atta** leads\n- Rice next")
    # a model that repeats its final sentence is trimmed to one copy
    assert llm_chat.clean_answer("Tea sells ₹1,292 on Sundays.Tea sells ₹1,292 on Sundays.") == "Tea sells ₹1,292 on Sundays."
    assert llm_chat.clean_answer("Atta leads. Rice is next. Atta leads.") == "Atta leads. Rice is next."


def test_starter_question_skips_llm_and_predicts(monkeypatch):
    """'What number should I expect?' must produce a prediction form, not a clarifying question."""
    import os
    from fastapi.testclient import TestClient
    import main, llm_chat
    monkeypatch.setattr(llm_chat, "chat", lambda *a, **k: {"narrative": ["Which figure do you mean?"]})
    c = TestClient(main.app)
    d = c.post("/samples/kirana_sales/load").json()
    r = c.post(f"/datasets/{d['id']}/chat", json={"message": "What number should I expect?", "history": []}).json()
    assert r["kind"] == "predictable" and "Which figure" not in " ".join(r["narrative"])
