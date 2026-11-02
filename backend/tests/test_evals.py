import pandas as pd
import pytest

import evals
import validation


def test_every_eval_case_passes():
    results = evals.run(chdir=False)
    failed = [f"{r['question']} ({r['dataset']}): {r['why']}" for r in results if not r["passed"]]
    assert not failed, failed
    assert len(results) >= 25


def test_backtest_beats_or_matches_naive_and_is_honest_about_ranges():
    df = evals.sample("provision_store")
    bt = validation.backtest(df)
    assert bt["available"] and bt["weeks"] >= 5
    assert bt["wape"] <= bt["naive_wape"] + 0.02            # never meaningfully worse than "repeat last week"
    i = bt["interval"]
    assert 0 < i["low"] < 1 < i["high"] and 0.6 <= i["coverage"] <= 1.0


def test_backtest_uses_only_past_data():
    # sales jump in the final week; a plan made before it must not see the jump
    d = pd.date_range("2026-01-01", periods=84)
    df = pd.DataFrame({"date": d.repeat(3), "product": ["a", "b", "c"] * 84, "quantity": 5})
    df.loc[df["date"] > d[-8], "quantity"] = 500
    rec = validation._records(df)
    last = rec[rec["origin"] == rec["origin"].max()]
    assert (last["likely"] < 100).all() and (last["actual"] > 1000).all()


def test_ranges_added_only_with_enough_history():
    short = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=35).repeat(3),
                          "product": ["a", "b", "c"] * 35, "quantity": 5})
    plan = validation.stock_plan_with_ranges(short)
    assert plan["available"] and "Likely range" not in plan["columns"]
    full = validation.stock_plan_with_ranges(evals.sample("kirana_sales"))
    assert "Likely range" in full["columns"] and all("to" in r["Likely range"] for r in full["rows"])
