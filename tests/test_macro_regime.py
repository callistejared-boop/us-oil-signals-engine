"""Offline tests for engine/macro_regime.py (Day 11). All tests pass
synthetic `providers=` dicts directly (macro_regime.classify() never
fetches on its own — the caller, macro_engine.py, owns fetching) so
nothing here ever touches macro_providers.py or the network.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_regime as mr  # noqa: E402


def _provider(facts=None, source_availability="available", freshness_state="fresh",
              uncertainty="low"):
    return {"facts": facts or {}, "source_availability": source_availability,
            "freshness": {"state": freshness_state}, "uncertainty": uncertainty}


def test_classify_empty_providers_defaults_to_neutral():
    out = mr.classify({}, symbol="XAUUSD")
    assert out["labels"] == ["Neutral"]
    assert out["macro_confidence"] == "low"
    assert out["evidence_quality"] == "low"


def test_classify_risk_on_from_volatility_provider():
    providers = {"volatility": _provider({"regime": "risk-on"})}
    out = mr.classify(providers, symbol="BTCUSD")
    assert "Risk-On" in out["labels"]


def test_classify_risk_off_from_volatility_provider():
    providers = {"volatility": _provider({"regime": "risk-off"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Risk-Off" in out["labels"]


def test_classify_volatility_mixed_regime_produces_mixed_label():
    providers = {"volatility": _provider({"regime": "mixed"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Mixed" in out["labels"]


def test_classify_volatility_not_available_yields_no_risk_label():
    providers = {"volatility": _provider({"regime": "risk-on"}, source_availability="unavailable")}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Risk-On" not in out["labels"]
    assert out["labels"] == ["Neutral"]


def test_classify_tightening_from_rising_yields():
    providers = {"interest_rates": _provider({"ten_year_trend": "rising"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Tightening" in out["labels"]


def test_classify_easing_from_falling_yields():
    providers = {"interest_rates": _provider({"ten_year_trend": "falling"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Easing" in out["labels"]


def test_classify_easing_from_rising_bond_prices():
    providers = {"sovereign_bonds": _provider({"trend": "rising"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Easing" in out["labels"]


def test_classify_tightening_from_falling_bond_prices():
    providers = {"sovereign_bonds": _provider({"trend": "falling"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Tightening" in out["labels"]


def test_classify_central_bank_hawkish_direction_supports_tightening():
    providers = {"central_bank_policy": _provider(
        {"Federal Reserve": {"expected_direction": "hike"}})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Tightening" in out["labels"]


def test_classify_central_bank_dovish_direction_supports_easing():
    providers = {"central_bank_policy": _provider(
        {"Federal Reserve": {"expected_direction": "cut"}})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Easing" in out["labels"]


def test_classify_conflicting_rate_signals_yield_mixed():
    providers = {
        "interest_rates": _provider({"ten_year_trend": "rising"}),
        "sovereign_bonds": _provider({"trend": "rising"}),  # rising bonds -> easing signal
    }
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Mixed" in out["labels"]
    assert out["macro_confidence"] == "low"


def test_classify_inflationary_from_rising_proxy():
    providers = {"inflation": _provider(
        {"market_implied_proxy": {"trend": "rising", "interpretation": "x"}})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Inflationary" in out["labels"]


def test_classify_disinflationary_from_falling_proxy():
    providers = {"inflation": _provider(
        {"market_implied_proxy": {"trend": "falling", "interpretation": "x"}})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert "Disinflationary" in out["labels"]


def test_classify_multiple_labels_can_coexist():
    providers = {
        "volatility": _provider({"regime": "risk-off"}),
        "interest_rates": _provider({"ten_year_trend": "rising"}),
        "inflation": _provider({"market_implied_proxy": {"trend": "rising", "interpretation": "x"}}),
    }
    out = mr.classify(providers, symbol="XAUUSD")
    assert set(out["labels"]) == {"Risk-Off", "Tightening", "Inflationary"}


def test_classify_high_confidence_when_all_hints_high():
    providers = {"volatility": _provider({"regime": "risk-on"})}
    out = mr.classify(providers, symbol="XAUUSD")
    assert out["macro_confidence"] == "high"


def test_classify_medium_confidence_on_mixed_hint_levels():
    providers = {
        "volatility": _provider({"regime": "risk-on"}),  # high hint
        "inflation": _provider({"market_implied_proxy": {"trend": "rising", "interpretation": "x"}}),  # medium
    }
    out = mr.classify(providers, symbol="XAUUSD")
    assert out["macro_confidence"] == "medium"


def test_evidence_quality_high_when_all_fresh():
    providers = {
        "volatility": _provider({"regime": "risk-on"}, freshness_state="fresh"),
        "interest_rates": _provider({"ten_year_trend": "rising"}, freshness_state="fresh"),
    }
    out = mr.classify(providers, symbol="XAUUSD")
    assert out["evidence_quality"] == "high"


def test_evidence_quality_low_when_all_missing():
    providers = {
        "volatility": _provider({}, source_availability="unavailable", freshness_state="missing"),
        "interest_rates": _provider({}, source_availability="unavailable", freshness_state="missing"),
    }
    out = mr.classify(providers, symbol="XAUUSD")
    assert out["evidence_quality"] == "low"


def test_labels_are_never_mutually_exclusive_by_construction():
    assert len(mr.LABELS) == 8
    assert "Neutral" in mr.LABELS and "Mixed" in mr.LABELS


def test_classify_never_raises_on_malformed_providers():
    out = mr.classify({"volatility": "not-a-dict"}, symbol="XAUUSD")
    assert out["labels"] == ["Neutral"]
    assert "error" in out or out["macro_confidence"] == "low"


def test_classify_note_discloses_descriptive_only_intent():
    out = mr.classify({}, symbol="XAUUSD")
    assert "not a weighted score" in out["note"]
    assert "confluence" in out["note"] or "confidence_engine" in out["note"]


def test_classify_includes_version_symbol_and_timestamp():
    out = mr.classify({}, symbol="EURUSD")
    assert out["version"] == mr.VERSION
    assert out["symbol"] == "EURUSD"
    assert "generated" in out
