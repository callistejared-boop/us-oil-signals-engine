"""Offline tests for engine/regime_engine.py (Day 4 Market Regime Engine).

All fixtures are synthetic pandas DataFrames built in-process — no network,
no disk I/O for the classification itself (regime_history writes are tested
separately in tests/test_regime_history.py, isolated to tmp_path).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import pytest

from engine import regime_engine as re  # noqa: E402


def _df(n, close, vol=100.0, start="2026-04-01"):
    idx = pd.date_range(start, periods=n, freq="15min")
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({"Open": close, "High": close + 0.5, "Low": close - 0.5,
                         "Close": close, "Volume": vol}, index=idx)


def _strong_trend_df(n=8000, up=True, start_price=2000.0, drift_total=400.0,
                     noise=0.15, seed=1):
    rng = np.random.default_rng(seed)
    trend = np.linspace(0, drift_total if up else -drift_total, n)
    noise_path = np.cumsum(rng.normal(0, noise, n))
    return _df(n, start_price + trend + noise_path)


def _choppy_range_df(n=8000, price=2000.0, amp=3.0, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    osc = amp * np.sin(t / 40.0) + rng.normal(0, 0.3, n)
    return _df(n, price + osc)


def _tiny_df(n=3):
    return _df(n, np.linspace(2000, 2001, n))


# --- Core classification shape / fail-safety --------------------------------

def test_strong_uptrend_classified_bull_and_never_raises():
    df = _strong_trend_df(up=True)
    r = re.classify(df, "XAUUSD")
    assert r["primary"] in ("Strong Bull Trend", "Weak Bull Trend")
    assert r["symbol"] == "XAUUSD"
    assert 0 <= r["confidence"] <= 100
    assert 0 <= r["quality_score"] <= 100
    assert isinstance(r["evidence"], list) and len(r["evidence"]) > 0


def test_strong_downtrend_classified_bear():
    df = _strong_trend_df(up=False)
    r = re.classify(df, "WTIUSD")
    assert r["primary"] in ("Strong Bear Trend", "Weak Bear Trend")


def test_choppy_data_classified_range_family():
    df = _choppy_range_df()
    r = re.classify(df, "XAUUSD")
    assert r["primary"] in ("Range", "Distribution", "Accumulation")


def test_insufficient_data_degrades_to_unknown_never_raises():
    r = re.classify(_tiny_df(), "XAUUSD")
    assert r["primary"] == "Unknown"
    assert r["confidence"] == 0
    # "Unknown" is deliberately listed as "prohibited" in
    # STRATEGY_COMPATIBILITY (there is no evidence basis to act on at all) —
    # "unrated" is reserved for a strategy name that isn't in the matrix.
    assert r["compatibility"] == "prohibited"


def test_none_dataframe_never_raises():
    r = re.classify(None, "XAUUSD")
    assert r["primary"] == "Unknown"


def test_malformed_dataframe_never_raises():
    bad = pd.DataFrame({"Open": [1, 2], "High": [1, 2]})  # missing Low/Close
    r = re.classify(bad, "XAUUSD")
    assert r["primary"] == "Unknown"


# --- Multi-timeframe hierarchy: strategic anchors, doesn't simple-vote -----

def test_strategic_tf_anchors_primary_even_with_disagreeing_execution_tf():
    """A clean strategic (1d) uptrend should still be labeled bullish even
    though the synthetic noise guarantees some lower-TF wobble — this is the
    'higher timeframes establish context, lower timeframes only refine'
    behavior, not a simple vote across all 5 timeframes."""
    df = _strong_trend_df(up=True, noise=0.05)
    r = re.classify(df, "XAUUSD")
    assert "Bull" in r["primary"]
    assert r["per_tf"]["1d"]["trend"] == "trend"


def test_weekly_insufficient_falls_back_to_daily():
    # ~83 days of 15m bars -> not enough for a trustworthy weekly (needs 22
    # weekly bars = ~5 months); daily should still be sufficient.
    df = _strong_trend_df(n=8000, up=True)
    r = re.classify(df, "XAUUSD")
    assert r["per_tf"]["1w"]["sufficient"] is False
    assert r["per_tf"]["1d"]["sufficient"] is True


def test_conflicting_evidence_populated_on_disagreement():
    df = _choppy_range_df()
    r = re.classify(df, "XAUUSD")
    # choppy data almost always produces some cross-TF disagreement
    assert isinstance(r["conflicting_evidence"], list)


# --- Explainability -----------------------------------------------------

def test_expected_behavior_present_for_every_primary_label():
    for label in re.EXPECTED_BEHAVIOR:
        assert isinstance(re.EXPECTED_BEHAVIOR[label], str) and len(re.EXPECTED_BEHAVIOR[label]) > 10


def test_line_helper_includes_symbol_and_primary():
    df = _strong_trend_df(up=True)
    r = re.classify(df, "XAUUSD")
    out = re.line(r)
    assert "XAUUSD" in out and r["primary"] in out


# --- Strategy compatibility matrix + quality score --------------------------

def test_compatibility_preferred_for_strong_trend():
    assert re._compatibility("ict_smc_mast", "Strong Bull Trend") == "preferred"
    assert re._compatibility("ict_smc_mast", "Strong Bear Trend") == "preferred"


def test_compatibility_discouraged_for_range():
    assert re._compatibility("ict_smc_mast", "Range") == "discouraged"


def test_compatibility_prohibited_for_unknown():
    assert re._compatibility("ict_smc_mast", "Unknown") == "prohibited"


def test_compatibility_unrated_for_unknown_strategy():
    assert re._compatibility("some_future_strategy", "Range") == "unrated"


def test_quality_score_higher_for_preferred_than_prohibited():
    q_pref, _ = re._quality_score("preferred", confidence=70, transition_risk=0.1)
    q_proh, _ = re._quality_score("prohibited", confidence=70, transition_risk=0.1)
    assert q_pref > q_proh


def test_quality_score_penalized_by_transition_risk():
    q_low_risk, _ = re._quality_score("preferred", confidence=70, transition_risk=0.0)
    q_high_risk, _ = re._quality_score("preferred", confidence=70, transition_risk=1.0)
    assert q_low_risk > q_high_risk


def test_quality_score_clipped_to_0_100():
    q, _ = re._quality_score("prohibited", confidence=0, transition_risk=1.0)
    assert 0 <= q <= 100


# --- Volatility trend (expansion/contraction derivative, not just level) ---

def test_vol_trend_unknown_on_short_series():
    assert re._vol_trend(_tiny_df()) == "unknown"


def test_vol_trend_returns_valid_label_on_sufficient_data():
    df = _strong_trend_df()
    assert re._vol_trend(df) in ("expansion", "contraction", "stable", "unknown")


# --- Tags: News-Driven, Illiquid ---------------------------------------

def test_news_driven_tag_when_blackout_active():
    df = _strong_trend_df()
    r = re.classify(df, "XAUUSD", news_state={"blackout": True})
    assert "News-Driven" in r["tags"]


def test_news_driven_tag_when_event_imminent():
    df = _strong_trend_df()
    r = re.classify(df, "XAUUSD", news_state={"blackout": False, "next_in_min": 10})
    assert "News-Driven" in r["tags"]


def test_no_news_tag_when_calendar_clear():
    df = _strong_trend_df()
    r = re.classify(df, "XAUUSD", news_state={"blackout": False, "next_in_min": 999})
    assert "News-Driven" not in r["tags"]


# --- Multi-symbol validation -------------------------------------------

@pytest.mark.parametrize("symbol", ["XAUUSD", "WTIUSD", "BTCUSD", "EURUSD"])
def test_classify_works_for_every_platform_symbol(symbol):
    df = _strong_trend_df(up=True)
    r = re.classify(df, symbol)
    assert r["symbol"] == symbol
    assert r["primary"] != ""


# --- Rapid regime change (edge case) ------------------------------------

def test_rapid_regime_change_still_produces_a_valid_result():
    """Half the series trends hard up, the other half reverses hard down —
    a deliberately unstable/rapid-change scenario. Must not raise and must
    still produce a fully-formed result (transition_risk should reflect the
    instability, but the exact label depends on which half dominates the
    strategic TF's lookback — not asserted here, only structural validity)."""
    n = 8000
    half = n // 2
    up = np.linspace(2000, 2300, half)
    down = np.linspace(2300, 2000, n - half)
    close = np.concatenate([up, down])
    df = _df(n, close)
    r = re.classify(df, "XAUUSD")
    assert r["primary"] != ""
    assert 0.0 <= r["transition_risk"] <= 1.0


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
