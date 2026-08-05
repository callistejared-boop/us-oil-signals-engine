"""Day 12 — dedicated stress-test suite, per the mandate's explicit
Testing section: "Stress test: zero liquidity, high volatility, stale
prices, delayed fills, partial fills, missing market data." Each of the
six named scenarios gets its own end-to-end test here (through
execution_report.py and replay.py, not just fill_model.py's own unit
tests) so this requirement is satisfied visibly and explicitly, not just
incidentally covered by other test files.
"""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import execution_report as er   # noqa: E402
from engine.execution import replay as rp              # noqa: E402

TS = pd.Timestamp("2026-08-03 08:00:00")


# 1. Zero liquidity ------------------------------------------------------------

def test_stress_zero_liquidity_end_to_end_report():
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS,
                                          zero_liquidity=True, rng=random.Random(1))
    assert rep["execution_score"] == "Failed"
    assert rep["both_legs_filled"] is False
    assert rep["actual_entry"] is None
    assert rep["actual_exit"] is None


def test_stress_zero_liquidity_replay_profile_fails_every_trade():
    rows = [{"id": "X-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
            "stop": 2340.0, "status": "win", "result_r": 3.0, "opened": "2026-07-20 08:00:00"}]
    out = rp.run_replay(rows=rows, profile="zero_liquidity", seed=1)
    assert out["score_distribution"]["Failed"] == 1


# 2. High volatility -------------------------------------------------------------

def test_stress_high_volatility_widens_execution_cost_vs_calm():
    calm = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                           stop_price=2340.0, signal_ts=TS, atr_pct=0.1,
                                           rng=random.Random(3))
    volatile = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                               stop_price=2340.0, signal_ts=TS, atr_pct=0.97,
                                               rng=random.Random(3))
    assert volatile["entry_detail"]["spread"]["estimated_spread"] > \
        calm["entry_detail"]["spread"]["estimated_spread"]


def test_stress_high_volatility_replay_profile_runs_without_error():
    rows = [{"id": "X-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
            "stop": 2340.0, "status": "win", "result_r": 2.0, "opened": "2026-07-20 08:00:00"}]
    out = rp.run_replay(rows=rows, profile="wide", seed=1)
    assert out["n_trades_replayed"] == 1
    assert out["reports"][0]["execution_score"] in ("Excellent", "Good", "Average", "Poor")


# 3. Stale prices ------------------------------------------------------------------

def test_stress_stale_price_flagged_and_widens_cost():
    fresh = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                            stop_price=2340.0, signal_ts=TS, rng=random.Random(9))
    stale = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                            stop_price=2340.0, signal_ts=TS, stale_price=True,
                                            rng=random.Random(9))
    assert stale["entry_detail"]["stale_price_caveat"] is True
    assert stale["total_execution_cost"] >= fresh["total_execution_cost"]


def test_stress_stale_price_replay_profile_runs_without_error():
    rows = [{"id": "X-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
            "stop": 2340.0, "status": "loss", "result_r": -1.0, "opened": "2026-07-20 08:00:00"}]
    out = rp.run_replay(rows=rows, profile="stale_price", seed=1)
    assert out["n_trades_replayed"] == 1


# 4. Delayed fills (latency) --------------------------------------------------------

def test_stress_delayed_fills_latency_visible_in_report():
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS, rng=random.Random(4))
    entry_latency = rep["entry_detail"]["latency"]["total_latency_ms"]
    entry_ts = rep["entry_detail"]["estimated_execution_timestamp"]
    assert entry_latency > 0
    assert entry_ts > TS


def test_stress_market_order_latency_dominated_by_human_reaction():
    rep = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS,
        entry_order_type="market", rng=random.Random(4))
    stages = rep["entry_detail"]["latency"]["stages_ms"]
    assert stages["human_reaction"] == max(stages.values())


# 5. Partial fills ------------------------------------------------------------------

def test_stress_partial_fill_surfaces_in_report(monkeypatch):
    from engine.execution import slippage_model as slm
    monkeypatch.setattr(slm, "draw_slippage", lambda *a, **k: {
        "price_delta": 0.9, "outcome": "adverse", "liquidity_shock": True,
        "partial_fill": True, "fill_fraction": 0.35})
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, rng=random.Random(1))
    assert rep["entry_detail"]["partial_fill"] is True
    assert rep["entry_detail"]["fill_fraction"] == 0.35


def test_stress_partial_fill_probability_reachable_via_forced_shock():
    """Confirms the underlying probabilistic path (not just a monkeypatch)
    can produce a partial fill — force_shock=True guarantees a shock,
    and SHOCK_PARTIAL_FILL_PROB (0.35) means roughly a third of forced
    shocks over many draws should show partial_fill=True."""
    from engine.execution import slippage_model as slm
    r = random.Random(123)
    partials = sum(1 for _ in range(300)
                   if slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r,
                                        force_shock=True)["partial_fill"])
    rate = partials / 300
    assert abs(rate - slm.SHOCK_PARTIAL_FILL_PROB) < 0.10


# 6. Missing market data ------------------------------------------------------------

def test_stress_missing_market_data_end_to_end_report():
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, exit_price=2380.0,
                                          stop_price=2340.0, signal_ts=TS,
                                          missing_data=True, rng=random.Random(1))
    assert rep["execution_score"] == "Failed"
    assert rep["actual_entry"] is None
    assert rep["actual_exit"] is None
    assert rep["total_execution_cost"] == 0.0


def test_stress_missing_market_data_replay_profile_fails_every_trade():
    rows = [{"id": "X-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
            "stop": 2340.0, "status": "win", "result_r": 1.0, "opened": "2026-07-20 08:00:00"}]
    out = rp.run_replay(rows=rows, profile="missing_data", seed=1)
    assert out["score_distribution"]["Failed"] == 1


# --- Combined stress: everything at once, must still never raise -----------------

def test_all_stresses_combined_never_raises():
    rep = er.build_trade_execution_report(
        "BTCUSD", "short", 60000.0, exit_price=58000.0, stop_price=61000.0, signal_ts=TS,
        atr_pct=0.99, news_blackout=True, session="Asian",
        stale_price=True, rng=random.Random(1))
    assert rep["execution_score"] in ("Excellent", "Good", "Average", "Poor", "Failed", "Unknown")


def test_zero_liquidity_and_missing_data_combined_prioritizes_missing_data():
    rep = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS,
        zero_liquidity=True, missing_data=True, rng=random.Random(1))
    assert rep["entry_fill_reason"] == "missing market data — cannot simulate execution"
