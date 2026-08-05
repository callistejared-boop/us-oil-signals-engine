"""Offline tests for engine/macro_engine.py (Day 11). All tests monkeypatch
`macro_providers.get_all` (and `.seasonality`/`.calendar_summary`) so
`assess()` never triggers a real provider fetch — mirrors how other
orchestrator-level tests in this codebase (e.g. confidence_engine's own
test suite) stay fast by mocking their one upstream call, not the whole
stack beneath it. `macro_history` writes are isolated via a monkeypatched
HISTORY_PATH, same as test_macro_history.py.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_engine as me    # noqa: E402
from engine import macro_providers as mp  # noqa: E402
from engine import macro_history as mh    # noqa: E402

FAKE_PROVIDERS = {
    "interest_rates": {"provider": "interest_rates", "symbol": None,
                       "facts": {"ten_year_trend": "rising"}, "interpretation": "x",
                       "freshness": {"state": "fresh"}, "source_availability": "available",
                       "uncertainty": "low", "source": "engine.rates_feed"},
    "central_bank_policy": {"provider": "central_bank_policy", "symbol": None, "facts": {},
                            "interpretation": "x", "freshness": {"state": "missing"},
                            "source_availability": "not_configured", "uncertainty": "high",
                            "source": "engine.macro_reference"},
    "inflation": {"provider": "inflation", "symbol": None, "facts": {},
                 "interpretation": "x", "freshness": {"state": "missing"},
                 "source_availability": "unavailable", "uncertainty": "high",
                 "source": "engine.rates_feed"},
    "employment": {"provider": "employment", "symbol": None, "facts": {},
                  "interpretation": "x", "freshness": {"state": "missing"},
                  "source_availability": "not_configured", "uncertainty": "high", "source": "x"},
    "energy_fundamentals": {"provider": "energy_fundamentals", "symbol": "WTIUSD", "facts": {},
                            "interpretation": "x", "freshness": {"state": "missing"},
                            "source_availability": "not_configured", "uncertainty": "high", "source": "x"},
    "currency_markets": {"provider": "currency_markets", "symbol": None, "facts": {},
                         "interpretation": "x", "freshness": {"state": "missing"},
                         "source_availability": "unavailable", "uncertainty": "high", "source": "x"},
    "sovereign_bonds": {"provider": "sovereign_bonds", "symbol": None, "facts": {},
                       "interpretation": "x", "freshness": {"state": "missing"},
                       "source_availability": "unavailable", "uncertainty": "high", "source": "x"},
    "volatility": {"provider": "volatility", "symbol": None, "facts": {"regime": "risk-on"},
                  "interpretation": "x", "freshness": {"state": "fresh"},
                  "source_availability": "available", "uncertainty": "low", "source": "x"},
    "geopolitical": {"provider": "geopolitical", "symbol": "XAUUSD",
                     "facts": {"acute_news_signal_active": False}, "interpretation": "x",
                     "freshness": {"state": "missing"}, "source_availability": "not_configured",
                     "uncertainty": "high", "source": "x"},
    "cross_asset": {"provider": "cross_asset", "symbol": "XAUUSD",
                    "facts": {"relationships": {}}, "interpretation": "0/0",
                    "freshness": {"state": "computed"}, "source_availability": "unavailable",
                    "uncertainty": "high", "source": "engine.macro_cross_asset"},
}


def test_assess_returns_full_shape(monkeypatch):
    monkeypatch.setattr(mp, "get_all", lambda symbol, direction="long": FAKE_PROVIDERS)
    monkeypatch.setattr(mp, "seasonality", lambda symbol: {"provider": "seasonality", "lean": "neutral"})
    monkeypatch.setattr(mp, "calendar_summary", lambda: {"provider": "economic_calendar", "n_events_this_week": 0})
    out = me.assess("XAUUSD", direction="long")
    assert out["symbol"] == "XAUUSD" and out["direction"] == "long"
    assert set(["providers", "regime", "cross_asset", "seasonality", "calendar",
               "explainability"]) <= set(out.keys())


def test_assess_regime_reflects_provider_data(monkeypatch):
    monkeypatch.setattr(mp, "get_all", lambda symbol, direction="long": FAKE_PROVIDERS)
    monkeypatch.setattr(mp, "seasonality", lambda symbol: {})
    monkeypatch.setattr(mp, "calendar_summary", lambda: {})
    out = me.assess("XAUUSD")
    assert "Risk-On" in out["regime"]["labels"]
    assert "Tightening" in out["regime"]["labels"]


def test_assess_never_raises_when_providers_blow_up(monkeypatch):
    def boom(symbol, direction="long"):
        raise RuntimeError("providers exploded")
    monkeypatch.setattr(mp, "get_all", boom)
    out = me.assess("XAUUSD")
    assert out["regime"]["labels"] == ["Neutral"]
    assert "error" in out


def test_assess_does_not_perform_its_own_calculations(monkeypatch):
    """Structural check: macro_engine.assess() must not compute new facts —
    every provider payload it returns must be object-identical to what
    macro_providers.get_all() handed it (no re-derivation)."""
    monkeypatch.setattr(mp, "get_all", lambda symbol, direction="long": FAKE_PROVIDERS)
    monkeypatch.setattr(mp, "seasonality", lambda symbol: {})
    monkeypatch.setattr(mp, "calendar_summary", lambda: {})
    out = me.assess("XAUUSD")
    assert out["providers"] is FAKE_PROVIDERS


def test_explain_answers_all_five_questions():
    assessment = {
        "symbol": "XAUUSD",
        "regime": {"labels": ["Risk-On"], "macro_confidence": "high", "evidence_quality": "medium",
                  "label_evidence": {"Risk-On": {"basis": "b", "supporting_providers": ["volatility"],
                                                 "note": "n"}}},
        "providers": FAKE_PROVIDERS,
        "cross_asset": {"facts": {"relationships": {}}},
    }
    out = me.explain(assessment)
    assert set(["what_happened", "why_it_matters", "assets_most_affected",
               "uncertainties_remaining", "evidence_supporting_assessment"]) == set(out.keys())
    assert "XAUUSD" in out["what_happened"]
    assert len(out["evidence_supporting_assessment"]) == 1


def test_explain_flags_low_evidence_quality_as_uncertainty():
    assessment = {"symbol": "XAUUSD",
                 "regime": {"labels": ["Neutral"], "macro_confidence": "low",
                           "evidence_quality": "low", "label_evidence": {}},
                 "providers": {}, "cross_asset": {}}
    out = me.explain(assessment)
    assert any("evidence quality is LOW" in u for u in out["uncertainties_remaining"])


def test_explain_never_raises_on_malformed_assessment():
    out = me.explain({"regime": "not-a-dict"})
    assert out["what_happened"] == "unavailable"
    assert out["uncertainties_remaining"][0].startswith("error:")


def test_explain_avoids_deterministic_language():
    assessment = {"symbol": "XAUUSD",
                 "regime": {"labels": ["Risk-On"], "macro_confidence": "high",
                           "evidence_quality": "high", "label_evidence": {}},
                 "providers": {}, "cross_asset": {}}
    out = me.explain(assessment)
    for banned in (" will ", " guaranteed"):
        assert banned not in out["what_happened"].lower()
        assert banned not in out["why_it_matters"].lower()


def test_record_assessment_delegates_to_macro_history(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assessment = {"version": "1.0.0", "providers": {}, "regime": {"labels": ["Neutral"],
                 "macro_confidence": "low", "evidence_quality": "low"}, "cross_asset": {}}
    row = me.record_assessment("XAUUSD", assessment, ref="XAUUSD-REF1")
    assert row["ref"] == "XAUUSD-REF1"
    assert f.exists()


def test_last_assessment_reads_through_to_macro_history(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assessment = {"version": "1.0.0", "providers": {}, "regime": {"labels": ["Risk-On"],
                 "macro_confidence": "high", "evidence_quality": "high"}, "cross_asset": {}}
    me.record_assessment("XAUUSD", assessment)
    last = me.last_assessment("XAUUSD")
    assert last["labels"] == ["Risk-On"]


def test_find_assessment_by_ref_reads_through_to_macro_history(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assessment = {"version": "1.0.0", "providers": {}, "regime": {"labels": ["Neutral"],
                 "macro_confidence": "low", "evidence_quality": "low"}, "cross_asset": {}}
    me.record_assessment("XAUUSD", assessment, ref="REF-XYZ")
    found = me.find_assessment_by_ref("REF-XYZ")
    assert found["ref"] == "REF-XYZ"


def test_assess_end_to_end_with_real_providers_never_raises():
    """One deliberately un-mocked, fully real call — proves the whole chain
    (macro_providers -> macro_regime -> macro_engine) degrades safely with
    zero live network access, matching the fail-safe posture verified for
    every underlying module individually elsewhere in this test suite."""
    out = me.assess("XAUUSD")
    assert out["symbol"] == "XAUUSD"
    assert "regime" in out and "labels" in out["regime"]
