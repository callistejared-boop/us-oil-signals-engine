"""Offline tests for alert_signals.py's Day 12 integration points:
log_execution_context() and build_entry()'s new execution line. Mirrors
test_alert_signals_macro.py's (Day 11) pattern of testing the extracted
functions directly with monkeypatched collaborators."""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402


def _rec():
    return {"symbol": "XAUUSD", "direction": "long", "entry": 2000.0, "stop": 1990.0,
           "target": 2030.0, "rr": 3.0, "invalidation": "close below 1985"}


def _fake_report(score="Good", cost_r=0.08, spread=0.35, entry_filled=True):
    return {"execution_score": score, "cost_r": cost_r, "entry_filled": entry_filled,
           "entry_detail": {"spread": {"estimated_spread": spread}}}


# --- log_execution_context() -------------------------------------------------

def test_log_execution_context_records_and_returns(monkeypatch):
    captured = {}
    monkeypatch.setattr(als, "exrep", SimpleNamespace(
        build_trade_execution_report=lambda *a, **k: _fake_report()))
    monkeypatch.setattr(als, "exhist", SimpleNamespace(
        record=lambda sym, report, ref="": {**report, "ref": ref}))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: captured.update(d)))

    out = als.log_execution_context("XAUUSD", "long", 2000.0, 1990.0, 2030.0,
                                    ref="XAUUSD-2026-08-03T10:00:00")
    assert out is not None
    assert out["execution_score"] == "Good"
    assert captured["event"] == "execution_report"
    assert captured["ref"] == "XAUUSD-2026-08-03T10:00:00"
    assert captured["execution_score"] == "Good"


def test_log_execution_context_never_raises_when_report_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("execution report blew up")
    monkeypatch.setattr(als, "exrep", SimpleNamespace(build_trade_execution_report=boom))
    out = als.log_execution_context("XAUUSD", "long", 2000.0, 1990.0, 2030.0)
    assert out is None


def test_log_execution_context_never_raises_when_record_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("history write blew up")
    monkeypatch.setattr(als, "exrep", SimpleNamespace(
        build_trade_execution_report=lambda *a, **k: _fake_report()))
    monkeypatch.setattr(als, "exhist", SimpleNamespace(record=boom))
    out = als.log_execution_context("XAUUSD", "long", 2000.0, 1990.0, 2030.0)
    assert out is None


def test_log_execution_context_logs_to_ledger_with_expected_shape(monkeypatch):
    logged = []
    monkeypatch.setattr(als, "exrep", SimpleNamespace(
        build_trade_execution_report=lambda *a, **k: _fake_report(score="Excellent", cost_r=0.02)))
    monkeypatch.setattr(als, "exhist", SimpleNamespace(
        record=lambda sym, report, ref="": {"execution_score": report["execution_score"],
                                            "cost_r": report["cost_r"]}))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))
    als.log_execution_context("XAUUSD", "long", 2000.0, 1990.0, 2030.0)
    assert len(logged) == 1
    assert logged[0]["event"] == "execution_report"
    assert logged[0]["execution_score"] == "Excellent"


# --- build_entry()'s execution line (advisory-only, never gates) ------------

def test_build_entry_shows_execution_line_when_present():
    text = als.build_entry(_rec(), lt=None, execution=_fake_report(score="Excellent",
                                                                    cost_r=0.03, spread=0.35))
    assert "est. execution: Excellent" in text
    assert "spread~0.35" in text
    assert "cost~0.03R" in text


def test_build_entry_omits_execution_line_when_none():
    text = als.build_entry(_rec(), lt=None, execution=None)
    assert "est. execution:" not in text


def test_build_entry_omits_execution_line_when_not_filled():
    text = als.build_entry(_rec(), lt=None, execution=_fake_report(entry_filled=False))
    assert "est. execution:" not in text


def test_build_entry_execution_line_coexists_with_macro_and_confidence():
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
    macro = {"regime": {"labels": ["Risk-On"], "macro_confidence": "medium",
                        "evidence_quality": "medium"}}
    text = als.build_entry(_rec(), lt=None, confidence=assessment, macro=macro,
                           execution=_fake_report())
    assert "confidence: High Confidence" in text
    assert "macro: Risk-On" in text
    assert "est. execution: Good" in text


def test_build_entry_never_raises_on_missing_entry_detail():
    text = als.build_entry(_rec(), lt=None,
                           execution={"execution_score": "Good", "cost_r": 0.1,
                                     "entry_filled": False})
    assert isinstance(text, str)
