"""Offline tests for engine/execution/slippage_model.py (Day 12). Every
random draw uses an explicitly seeded random.Random for reproducibility
— the same pattern edge_investigation.py's variance_permutation_test()
(Day 10) established for this codebase's own seeded randomness."""
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import slippage_model as slm  # noqa: E402


def test_shock_probability_base_case():
    p = slm.shock_probability()
    assert p == slm.SHOCK_BASE_PROB


def test_shock_probability_news_blackout_raises_it():
    p = slm.shock_probability(news_blackout=True)
    assert p > slm.SHOCK_BASE_PROB


def test_shock_probability_off_session_raises_it():
    p = slm.shock_probability(session="Asian")
    assert p > slm.SHOCK_BASE_PROB


def test_shock_probability_high_vol_raises_it():
    p = slm.shock_probability(atr_pct=0.95)
    assert p > slm.SHOCK_BASE_PROB


def test_shock_probability_capped_at_max():
    p = slm.shock_probability(atr_pct=0.99, news_blackout=True, session="Asian")
    assert p == slm.SHOCK_MAX_PROB


def test_shock_probability_never_raises_on_bad_input():
    p = slm.shock_probability(atr_pct="bad")
    assert p == slm.SHOCK_BASE_PROB


def test_draw_slippage_reproducible_with_same_seed():
    r1 = random.Random(99)
    r2 = random.Random(99)
    out1 = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r1)
    out2 = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r2)
    assert out1 == out2


def test_draw_slippage_different_seeds_can_differ():
    r1 = random.Random(1)
    r2 = random.Random(2)
    out1 = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r1)
    out2 = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r2)
    assert out1["price_delta"] != out2["price_delta"]


def test_draw_slippage_outcome_matches_sign():
    r = random.Random(3)
    for _ in range(20):
        out = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r)
        if out["outcome"] == "adverse":
            assert out["price_delta"] >= 0
        elif out["outcome"] == "favorable":
            assert out["price_delta"] <= 0


def test_draw_slippage_zero_spread_gives_zero_magnitude():
    r = random.Random(5)
    out = slm.draw_slippage("XAUUSD", "long", "market", 0.0, rng=r)
    assert out["price_delta"] == 0.0


def test_draw_slippage_unknown_order_type_falls_back_to_market():
    r = random.Random(6)
    out = slm.draw_slippage("XAUUSD", "long", "bogus_type", 0.35, rng=r)
    assert out["order_type"] == "market"


def test_draw_slippage_force_shock_always_shocks():
    r = random.Random(7)
    for _ in range(10):
        out = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r, force_shock=True)
        assert out["liquidity_shock"] is True
        assert out["outcome"] == "adverse"


def test_draw_slippage_force_shock_can_produce_partial_fill():
    r = random.Random(11)
    saw_partial = False
    for _ in range(50):
        out = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r, force_shock=True)
        if out["partial_fill"]:
            saw_partial = True
            assert 0 < out["fill_fraction"] < 1
    assert saw_partial


def test_draw_slippage_shock_magnitude_larger_than_normal():
    r_normal = random.Random(42)
    r_shock = random.Random(42)
    normal = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r_normal)
    shock = slm.draw_slippage("XAUUSD", "long", "market", 0.35, rng=r_shock, force_shock=True)
    assert abs(shock["price_delta"]) >= abs(normal["price_delta"])


def test_draw_slippage_stop_orders_skew_more_adverse_than_market():
    r_market = random.Random(0)
    r_stop = random.Random(0)
    n = 200
    market_adverse = sum(1 for _ in range(n)
                         if slm.draw_slippage("XAUUSD", "long", "market", 0.35,
                                              rng=r_market)["outcome"] == "adverse")
    stop_adverse = sum(1 for _ in range(n)
                       if slm.draw_slippage("XAUUSD", "long", "stop", 0.35,
                                            rng=r_stop)["outcome"] == "adverse")
    assert stop_adverse > market_adverse


def test_draw_slippage_never_raises_on_bad_spread():
    r = random.Random(8)
    out = slm.draw_slippage("XAUUSD", "long", "market", "not-a-number", rng=r)
    assert out["price_delta"] == 0.0
    assert "error" in out


def test_draw_slippage_always_returns_required_keys():
    r = random.Random(9)
    out = slm.draw_slippage("XAUUSD", "short", "limit", 0.02, rng=r)
    required = {"symbol", "direction", "order_type", "outcome", "price_delta",
               "liquidity_shock", "shock_probability_used", "partial_fill",
               "fill_fraction", "is_estimate", "source"}
    assert required <= set(out.keys())
