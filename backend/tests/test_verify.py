import pytest
from fastapi.testclient import TestClient
import verify


def T(*results):
    return [{"expr": "x", "result": r, "raw": r} for r in results]


def test_traced_amounts_in_every_format():
    tr = T("224813.4", "0.1834", "Rakesh Verma 18506")
    out = verify.check(["Total is ₹2,24,813, margin 18%, and Rakesh owes ₹18,506."], tr)
    assert out["status"] == "all" and out["matched"] == 3


def test_lakh_shorthand_is_understood():
    assert verify.numbers("₹2.25 L and 1.2 Cr")[0]["value"] == 225000
    assert verify.numbers("₹2.25 L and 1.2 Cr")[1]["value"] == 12_000_000


def test_invented_number_is_flagged():
    out = verify.check(["You sold ₹47,000 last week."], T("52310.0"))
    assert out["status"] == "none" and out["unmatched"] == ["₹47,000"]


def test_partly_traced():
    out = verify.check(["Sales were 52,310 and profit was 9,999."], T("52310.0"))
    assert out["status"] == "partly" and out["unmatched"] == ["9,999"]


def test_sizes_years_and_small_counts_are_not_claims():
    out = verify.check(["Milk 1L is your top item in 2026, top 3 shown, Atta 5kg too."], T("whatever"))
    assert out["status"] == "nofigures"


def test_no_calculation_means_unchecked():
    out = verify.check(["You have 1,250 customers."], [])
    assert out["status"] == "nocalc"


def test_chat_attaches_verification(monkeypatch):
    import main
    c = TestClient(main.app)
    ds = c.post("/samples/kirana_sales/load").json()["id"]
    monkeypatch.setattr(main.llm_chat, "chat", lambda *a, **k: {
        "narrative": ["Total sales are ₹9,99,999 and there are 4,297 rows."], "history": [],
        "trace": [{"expr": "len(df)", "result": "4297", "raw": "4297"}]})
    r = c.post(f"/datasets/{ds}/chat", json={"message": "Tell me one interesting fact", "private": False}).json()
    v = next(b for b in r["blocks"] if b["type"] == "verified")
    assert v["status"] == "partly" and v["unmatched"] == ["₹9,99,999"] and v["matched"] == 1
