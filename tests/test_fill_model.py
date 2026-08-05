"""Offline tests for engine/execution/fill_model.py (Day 12) — order-type
behavior and stress scenarios (zero liquidity, missing data, stale
price, partial fills)."""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import fill_model as fm  # noqa: E402

TS = pd.Timestamp("2026-08-03 08:00:00")


def test_side_derivation_long_entry_is_buy():
    assert fm._side("long", "entry") == "buy"


def test_side_derivation_long_exit_is_sell():
    assert fm._side("long", "exit") == "sell"


def test_side_derivation_short_entry_is_sell():
    assert fm._side("short", "entry") == "sell"


def test_side_derivation_short_exit_is_buy():
    assert fm._side("short", "exit") == "buy"


def test_market_order_fills_under_normal_conditions():
    r = random.Random(1)
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                           session="London KZ", rng=r)
    assert out["filled"] is True
    assert out["actual_price"] is not None
    assert out["execution_cost"] >= 0


def test_market_long_adverse_slippage_increases_price(monkeypatch):
    from engine.execution import slippage_model as slm
    monkeypatch.setattr(slm, "draw_slippage", lambda *a, **k: {
        "price_delta": 0.10, "outcome": "adverse", "liquidity_shock": False,
        "partial_fill": False, "fill_fraction": 1.0})
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS, rng=random.Random(1))
    assert out["actual_price"] == 2350.10


def test_market_short_adverse_slippage_decreases_price(monkeypatch):
    from engine.execution import slippage_model as slm
    monkeypatch.setattr(slm, "draw_slippage", lambda *a, **k: {
        "price_delta": 0.10, "outcome": "adverse", "liquidity_shock": False,
        "partial_fill": False, "fill_fraction": 1.0})
    out = fm.simulate_fill("XAUUSD", "short", "market", 2350.0, signal_ts=TS, rng=random.Random(1))
    assert out["actual_price"] == 2349.90


def test_exit_leg_of_long_position_is_a_sell_and_adverse_lowers_price(monkeypatch):
    from engine.execution import slippage_model as slm
    monkeypatch.setattr(slm, "draw_slippage", lambda *a, **k: {
        "price_delta": 0.10, "outcome": "adverse", "liquidity_shock": False,
        "partial_fill": False, "fill_fraction": 1.0})
    out = fm.simulate_fill("XAUUSD", "long", "market", 2380.0, signal_ts=TS,
                           leg="exit", rng=random.Random(1))
    assert out["side"] == "sell"
    assert out["actual_price"] == 2379.90


def test_stop_order_wider_adverse_skew_than_market():
    r_market = random.Random(0)
    r_stop = random.Random(0)
    n = 100
    market_costs = [fm.simulate_fill("WTIUSD", "long", "market", 78.0, signal_ts=TS,
                                     rng=r_market)["execution_cost"] for _ in range(n)]
    stop_costs = [fm.simulate_fill("WTIUSD", "long", "stop", 78.0, signal_ts=TS,
                                   rng=r_stop)["execution_cost"] for _ in range(n)]
    assert sum(stop_costs) > sum(market_costs)


def test_limit_order_fills_when_price_path_reaches_it():
    df = pd.DataFrame({"High": [2352, 2351], "Low": [2349, 2347]})
    out = fm.simulate_fill("XAUUSD", "long", "limit", 2350.0, signal_ts=TS,
                           limit_price=2348.0, price_path=df, rng=random.Random(1))
    assert out["filled"] is True
    assert "reached in supplied price path" in out["reason"]


def test_limit_order_does_not_fill_when_price_path_never_reaches_it():
    df = pd.DataFrame({"High": [2352, 2351], "Low": [2350, 2349]})
    out = fm.simulate_fill("XAUUSD", "long", "limit", 2350.0, signal_ts=TS,
                           limit_price=2340.0, price_path=df, rng=random.Random(1))
    assert out["filled"] is False
    assert out["actual_price"] is None


def test_limit_order_short_uses_high_column():
    df = pd.DataFrame({"High": [2355, 2360], "Low": [2340, 2338]})
    out = fm.simulate_fill("XAUUSD", "short", "limit", 2350.0, signal_ts=TS,
                           limit_price=2358.0, price_path=df, rng=random.Random(1))
    assert out["filled"] is True


def test_limit_order_probabilistic_fallback_when_no_price_path():
    r = random.Random(42)
    out = fm.simulate_fill("XAUUSD", "long", "limit", 2350.0, signal_ts=TS,
                           limit_price=2348.0, rng=r)
    assert out["limit_fill_probability_used"] == fm.DEFAULT_LIMIT_FILL_PROBABILITY
    assert "probabilistic assumption" in out["reason"]


def test_limit_order_probabilistic_fill_rate_matches_assumption_over_many_draws():
    r = random.Random(7)
    n = 2000
    fills = sum(1 for _ in range(n)
               if fm.simulate_fill("XAUUSD", "long", "limit", 2350.0, signal_ts=TS,
                                   limit_price=2348.0, rng=r)["filled"])
    rate = fills / n
    assert abs(rate - fm.DEFAULT_LIMIT_FILL_PROBABILITY) < 0.05


# --- Stress scenarios (mandate's explicit list) ------------------------------

def test_stress_zero_liquidity_never_fills():
    r = random.Random(1)
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                           zero_liquidity=True, rng=r)
    assert out["filled"] is False
    assert out["actual_price"] is None
    assert "zero liquidity" in out["reason"]


def test_stress_zero_liquidity_applies_to_limit_and_stop_too():
    for ot in ("limit", "stop"):
        out = fm.simulate_fill("XAUUSD", "long", ot, 2350.0, signal_ts=TS,
                               zero_liquidity=True, rng=random.Random(1))
        assert out["filled"] is False


def test_stress_missing_data_never_fills_and_no_price_computed():
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                           missing_data=True, rng=random.Random(1))
    assert out["filled"] is False
    assert out["actual_price"] is None
    assert "missing market data" in out["reason"]
    assert "spread" not in out  # short-circuits before any spread/latency computed


def test_stress_high_volatility_increases_execution_cost():
    r_calm = random.Random(1)
    r_volatile = random.Random(1)
    calm = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                            atr_pct=0.1, rng=r_calm)
    volatile = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                                atr_pct=0.95, rng=r_volatile)
    assert volatile["spread"]["estimated_spread"] > calm["spread"]["estimated_spread"]


def test_stress_stale_price_widens_cost_and_flags_caveat():
    fresh = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                             rng=random.Random(5))
    stale = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                             stale_price=True, rng=random.Random(5))
    assert stale["stale_price_caveat"] is True
    assert fresh["stale_price_caveat"] is False
    assert stale["execution_cost"] >= fresh["execution_cost"]


def test_stress_delayed_fills_latency_recorded_and_timestamp_shifted():
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS, rng=random.Random(1))
    assert out["latency"]["total_latency_ms"] > 0
    assert out["estimated_execution_timestamp"] > out["signal_timestamp"]


def test_stress_partial_fill_surfaces_through_simulate_fill(monkeypatch):
    """fill_model.py must surface slippage_model's partial_fill/fill_fraction
    verbatim on the assembled report. Uses a deterministic monkeypatched
    slippage draw (a liquidity-shock partial fill) rather than relying on
    a low-probability random path — see test_slippage_model.py's own
    test_draw_slippage_force_shock_can_produce_partial_fill for the
    underlying probabilistic behavior."""
    from engine.execution import slippage_model as slm
    monkeypatch.setattr(slm, "draw_slippage", lambda *a, **k: {
        "price_delta": 1.2, "outcome": "adverse", "liquidity_shock": True,
        "partial_fill": True, "fill_fraction": 0.4})
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS, rng=random.Random(1))
    assert out["filled"] is True
    assert out["partial_fill"] is True
    assert out["fill_fraction"] == 0.4


def test_missing_market_data_takes_priority_over_zero_liquidity():
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                           missing_data=True, zero_liquidity=True, rng=random.Random(1))
    assert out["reason"] == "missing market data — cannot simulate execution"


def test_simulate_fill_never_raises_on_internal_error(monkeypatch):
    from engine.execution import spread_model as spr

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(spr, "estimate", boom)
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS, rng=random.Random(1))
    assert out["filled"] is False
    assert "error" in out["reason"]


def test_spread_overrides_pass_through_to_spread_model():
    out = fm.simulate_fill("XAUUSD", "long", "market", 2350.0, signal_ts=TS,
                           spread_overrides={"XAUUSD": 5.0}, rng=random.Random(1))
    assert out["spread"]["base_spread"] == 5.0
