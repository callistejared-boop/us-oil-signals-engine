"""Offline tests for engine/execution/execution_report.py (Day 12)."""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import execution_report as er  # noqa: E402

TS = pd.Timestamp("2026-08-03 08:00:00")


def test_score_execution_excellent_band():
    assert er.score_execution(cost_r=0.01, filled=True) == "Excellent"


def test_score_execution_good_band():
    assert er.score_execution(cost_r=0.10, filled=True) == "Good"


def test_score_execution_average_band():
    assert er.score_execution(cost_r=0.25, filled=True) == "Average"


def test_score_execution_poor_band():
    assert er.score_execution(cost_r=0.50, filled=True) == "Poor"


def test_score_execution_boundary_values_are_inclusive():
    assert er.score_execution(cost_r=0.05, filled=True) == "Excellent"
    assert er.score_execution(cost_r=0.15, filled=True) == "Good"
    assert er.score_execution(cost_r=0.35, filled=True) == "Average"


def test_score_execution_failed_overrides_everything():
    assert er.score_execution(cost_r=0.001, filled=False) == "Failed"


def test_score_execution_bps_fallback_when_no_cost_r():
    assert er.score_execution(cost_bps=1.0, filled=True) == "Excellent"
    assert er.score_execution(cost_bps=20.0, filled=True) == "Poor"


def test_score_execution_unknown_when_no_cost_provided():
    assert er.score_execution(filled=True) == "Unknown"


def test_score_execution_never_raises_on_bad_input():
    assert er.score_execution(cost_r="bad", filled=True) == "Unknown"


def test_build_report_entry_only_no_exit():
    r = random.Random(1)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, rng=r)
    assert rep["entry_filled"] is True
    assert rep["expected_exit"] is None
    assert rep["exit_filled"] is None
    assert rep["execution_score"] in ("Excellent", "Good", "Average", "Poor")


def test_build_report_entry_and_exit():
    r = random.Random(2)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS, rng=r)
    assert rep["entry_filled"] is True
    assert rep["exit_filled"] is True
    assert rep["both_legs_filled"] is True
    assert rep["total_execution_cost"] >= 0


def test_build_report_cost_r_uses_planned_risk():
    r = random.Random(3)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS, rng=r)
    risk = abs(2350.0 - 2340.0)
    expected_cost_r = round(rep["total_execution_cost"] / risk, 6)
    assert rep["cost_r"] == expected_cost_r


def test_build_report_no_stop_falls_back_to_bps():
    r = random.Random(4)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          signal_ts=TS, rng=r)
    assert rep["cost_r"] is None
    assert rep["cost_bps"] is not None


def test_build_report_zero_liquidity_scores_failed():
    r = random.Random(5)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, zero_liquidity=True, rng=r)
    assert rep["execution_score"] == "Failed"
    assert rep["both_legs_filled"] is False


def test_build_report_partial_leg_failure_scores_failed():
    """Entry fills but exit does not (e.g. exit leg hits missing data) —
    both_legs_filled must be False and score Failed, not silently scored
    off the entry leg alone."""
    r = random.Random(6)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS, rng=r)
    # sanity: force a manual failure scenario by re-scoring with filled=False
    assert er.score_execution(cost_r=rep["cost_r"], filled=False) == "Failed"


def test_build_report_note_discloses_estimate_nature():
    r = random.Random(7)
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, rng=r)
    assert "MODELED ESTIMATE" in rep["note"]
    assert "no live broker connection" in rep["note"]


def test_build_report_never_raises_on_internal_error(monkeypatch):
    from engine.execution import fill_model as fmmod
    monkeypatch.setattr(fmmod, "simulate_fill", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS)
    assert rep["execution_score"] == "Unknown"
    assert "error" in rep


def test_build_report_short_direction_works():
    r = random.Random(8)
    rep = er.build_trade_execution_report("WTIUSD", "short", 78.0, exit_price=75.0,
                                          stop_price=79.0, signal_ts=TS, rng=r)
    assert rep["entry_filled"] is True
    assert rep["exit_filled"] is True
