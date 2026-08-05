"""Offline tests for alert_signals.py's Day 11 integration points:
log_macro_context() and build_entry()'s new macro line. Mirrors
test_alert_signals_confidence.py's (Day 6) pattern of testing the
extracted functions directly with monkeypatched collaborators, rather
than driving main() (live fetch, Telegram, journal I/O).
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402


def _rec():
    return {"symbol": "XAUUSD", "direction": "long", "entry": 2000.0, "stop": 1990.0,
           "target": 2030.0, "rr": 3.0, "invalidation": "close below 1985"}


def _fake_assessment(labels=None, macro_confidence="medium", evidence_quality="medium"):
    return {"symbol": "XAUUSD", "direction": "long",
           "regime": {"labels": labels or ["Risk-On"], "macro_confidence": macro_confidence,
                     "evidence_quality": evidence_quality}}


# --- log_macro_context() ----------------------------------------------------------

def test_log_macro_context_records_and_returns(monkeypatch):
    captured = {}
    monkeypatch.setattr(als, "macro", SimpleNamespace(
        assess=lambda sym, direction: _fake_assessment(),
        record_assessment=lambda sym, a, ref="": {"labels": a["regime"]["labels"],
                                                   "macro_confidence": a["regime"]["macro_confidence"],
                                                   "evidence_quality": a["regime"]["evidence_quality"],
                                                   "ref": ref}))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: captured.update(d)))

    out = als.log_macro_context("XAUUSD", "long", ref="XAUUSD-2026-08-03T10:00:00")
    assert out is not None
    assert out["regime"]["labels"] == ["Risk-On"]
    assert captured["event"] == "macro_assessment"
    assert captured["ref"] == "XAUUSD-2026-08-03T10:00:00"
    assert captured["labels"] == ["Risk-On"]


def test_log_macro_context_never_raises_when_assess_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("macro engine blew up")
    monkeypatch.setattr(als, "macro", SimpleNamespace(assess=boom))
    out = als.log_macro_context("XAUUSD", "long")
    assert out is None  # fail-safe: never propagates, never blocks the caller


def test_log_macro_context_never_raises_when_record_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("history write blew up")
    monkeypatch.setattr(als, "macro", SimpleNamespace(
        assess=lambda sym, direction: _fake_assessment(), record_assessment=boom))
    out = als.log_macro_context("XAUUSD", "long")
    assert out is None


def test_log_macro_context_logs_to_ledger_with_expected_shape(monkeypatch):
    logged = []
    monkeypatch.setattr(als, "macro", SimpleNamespace(
        assess=lambda sym, direction: _fake_assessment(labels=["Tightening", "Risk-Off"]),
        record_assessment=lambda sym, a, ref="": {"labels": a["regime"]["labels"],
                                                   "macro_confidence": a["regime"]["macro_confidence"],
                                                   "evidence_quality": a["regime"]["evidence_quality"]}))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))
    als.log_macro_context("XAUUSD", "long")
    assert len(logged) == 1
    assert logged[0]["event"] == "macro_assessment"
    assert logged[0]["labels"] == ["Tightening", "Risk-Off"]


# --- build_entry()'s macro line (advisory-only, never gates) ----------------------

def test_build_entry_shows_macro_line_when_present():
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=None,
                           macro=_fake_assessment(labels=["Risk-On", "Tightening"],
                                                  macro_confidence="high",
                                                  evidence_quality="medium"))
    assert "macro: Risk-On, Tightening" in text
    assert "macro_confidence=high" in text
    assert "evidence_quality=medium" in text


def test_build_entry_omits_macro_line_when_none():
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=None, macro=None)
    assert "macro:" not in text


def test_build_entry_omits_macro_line_when_labels_empty():
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=None,
                           macro={"regime": {"labels": [], "macro_confidence": "low",
                                             "evidence_quality": "low"}})
    assert "macro:" not in text


def test_build_entry_macro_line_coexists_with_confidence_line():
    from engine import confidence_engine as ce
    assessment = ce.ConfidenceAssessment(
        symbol="XAUUSD", direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=78, tier="High Confidence",
        probability_label="internal decision-quality estimate",
        calibrated_probability=None, is_calibrated=False,
        evidence_quality=70, evidence_diversity=60, market_quality=75,
        regime_confidence=65, confluence_quality=70,
        portfolio_status={"allow": True}, risk_status={"guard_action": "allow"},
    )
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=assessment,
                           macro=_fake_assessment())
    assert "confidence: High Confidence" in text
    assert "macro: Risk-On" in text


def test_build_entry_omits_macro_line_when_regime_key_missing():
    # macro.assess()'s own fail-safe branch always returns SOME dict for
    # "regime" (never a bare string) — the realistic degraded shape is a
    # dict missing the "labels" key entirely, not a malformed type.
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=None,
                           macro={"regime": {"macro_confidence": "low"}})
    assert "macro:" not in text
    assert isinstance(text, str)
