"""Offline tests for engine/execution/spread_model.py (Day 12). Pure
functions, no network dependency — every test is a direct call."""
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import spread_model as sm  # noqa: E402


def test_session_for_london_kz():
    ts = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
    assert sm.session_for(ts) == "London KZ"


def test_session_for_new_york_kz():
    ts = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
    assert sm.session_for(ts) == "New York KZ"


def test_session_for_asian():
    ts = datetime(2026, 8, 3, 3, 0, tzinfo=timezone.utc)
    assert sm.session_for(ts) == "Asian"


def test_session_for_off_session():
    ts = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)
    assert sm.session_for(ts) == "off-session"


def test_session_for_none_defaults_safely():
    # Uses real "now" — just assert it returns one of the valid labels,
    # never raises.
    assert sm.session_for(None) in sm.SESSIONS


def test_estimate_known_symbol_normal_conditions():
    out = sm.estimate("XAUUSD", session="London KZ")
    assert out["estimated_spread"] == sm.BASE_SPREAD["XAUUSD"]
    assert out["session_multiplier"] == 1.0
    assert out["volatility_multiplier"] == 1.0
    assert out["news_multiplier"] == 1.0
    assert out["is_estimate"] is True


def test_estimate_asian_session_widens_spread():
    out = sm.estimate("XAUUSD", session="Asian")
    assert out["estimated_spread"] > sm.BASE_SPREAD["XAUUSD"]


def test_estimate_news_blackout_widens_spread_more():
    normal = sm.estimate("XAUUSD", session="London KZ", news_blackout=False)
    blackout = sm.estimate("XAUUSD", session="London KZ", news_blackout=True)
    assert blackout["estimated_spread"] > normal["estimated_spread"]
    assert blackout["news_multiplier"] == sm.NEWS_MULTIPLIER


def test_estimate_high_volatility_widens_spread():
    calm = sm.estimate("XAUUSD", session="London KZ", atr_pct=0.1)
    volatile = sm.estimate("XAUUSD", session="London KZ", atr_pct=0.95)
    assert volatile["estimated_spread"] > calm["estimated_spread"]


def test_estimate_unknown_symbol_degrades_safely():
    out = sm.estimate("NOTASYMBOL")
    assert out["estimated_spread"] is None
    assert out["base_spread"] is None
    assert "no base-spread assumption" in out["assumption"]


def test_estimate_overrides_substitute_base_spread():
    out = sm.estimate("XAUUSD", session="London KZ", overrides={"XAUUSD": 1.0})
    assert out["base_spread"] == 1.0
    assert out["estimated_spread"] == 1.0


def test_estimate_negative_atr_pct_treated_as_neutral():
    out = sm.estimate("XAUUSD", session="London KZ", atr_pct=-5)
    assert out["volatility_multiplier"] == 1.0


def test_estimate_never_raises_on_malformed_atr_pct():
    out = sm.estimate("XAUUSD", session="London KZ", atr_pct="not-a-number")
    assert out["volatility_multiplier"] == 1.0


def test_all_base_symbols_have_positive_spread():
    for sym, val in sm.BASE_SPREAD.items():
        assert val > 0


def test_estimate_all_four_symbols_return_a_value():
    for sym in sm.BASE_SPREAD:
        out = sm.estimate(sym, session="London KZ")
        assert out["estimated_spread"] is not None


def test_estimate_carries_disclosed_assumption_note():
    out = sm.estimate("XAUUSD", session="London KZ")
    assert "not a live broker feed" in out["assumption"]
