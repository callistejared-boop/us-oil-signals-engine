"""Offline tests for alert_signals.py's Day 6 integration points:
log_confidence_assessment(), build_entry()/build_prealert()'s confidence
line, and log_confluence_explainability()'s new `ref` passthrough. Mirrors
test_alert_signals_regime_gate.py's (Day 4) pattern: test the extracted
pure/near-pure functions directly rather than driving main() (live fetch,
Telegram, journal I/O).
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine import confidence_engine as ce  # noqa: E402


def _assessment(overall_confidence=78, tier="High Confidence", is_calibrated=False,
                calibrated_probability=None):
    return ce.ConfidenceAssessment(
        symbol="XAUUSD", direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=overall_confidence, tier=tier,
        probability_label="internal decision-quality estimate",
        calibrated_probability=calibrated_probability, is_calibrated=is_calibrated,
        evidence_quality=70, evidence_diversity=60, market_quality=75,
        regime_confidence=65, confluence_quality=70,
        portfolio_status={"allow": True}, risk_status={"guard_action": "allow"},
    )


# --- log_confidence_assessment() -------------------------------------------------

def test_log_confidence_assessment_records_and_returns(monkeypatch):
    captured = {}
    monkeypatch.setattr(als, "confeng", SimpleNamespace(assess=lambda *a, **k: _assessment()))
    monkeypatch.setattr(als, "cfdh", SimpleNamespace(
        record=lambda a, ref="": captured.update(assessment=a, ref=ref)))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: None))

    out = als.log_confidence_assessment("XAUUSD", "long", ref="XAUUSD-2026-08-03T10:00:00")
    assert out is not None
    assert out.overall_confidence == 78
    assert captured["ref"] == "XAUUSD-2026-08-03T10:00:00"


def test_log_confidence_assessment_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("assess() blew up")
    monkeypatch.setattr(als, "confeng", SimpleNamespace(assess=_boom))
    out = als.log_confidence_assessment("XAUUSD", "long")
    assert out is None   # fail-safe: never propagates, never blocks the caller


def test_log_confidence_assessment_logs_to_ledger(monkeypatch):
    logged = []
    monkeypatch.setattr(als, "confeng", SimpleNamespace(assess=lambda *a, **k: _assessment()))
    monkeypatch.setattr(als, "cfdh", SimpleNamespace(record=lambda a, ref="": None))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))
    als.log_confidence_assessment("XAUUSD", "long")
    assert len(logged) == 1
    assert logged[0]["event"] == "confidence_assessment"
    assert logged[0]["overall_confidence"] == 78


# --- log_confluence_explainability()'s ref passthrough (Day 6) -------------------

def test_log_confluence_explainability_forwards_ref(monkeypatch):
    captured = {}
    fake_cr = SimpleNamespace(direction="long", score=80, final_tier="confirmed",
                              agree=["price action"], disagree=[])
    monkeypatch.setattr(als.cfa, "quality_score", lambda cr: {"score": 70, "independent_agreement": 0.8})
    monkeypatch.setattr(als.cfa, "conflict_resolution", lambda cr: [])
    monkeypatch.setattr(als, "cfh", SimpleNamespace(
        record=lambda *a, **k: captured.update(kwargs=k, args=a)))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: None))

    als.log_confluence_explainability("XAUUSD", fake_cr, ref="XAUUSD-2026-08-03T10:00:00")
    assert captured["kwargs"]["ref"] == "XAUUSD-2026-08-03T10:00:00"


def test_log_confluence_explainability_none_cr_is_noop(monkeypatch):
    called = []
    monkeypatch.setattr(als, "cfh", SimpleNamespace(record=lambda *a, **k: called.append(1)))
    als.log_confluence_explainability("XAUUSD", None, ref="whatever")
    assert called == []


# --- build_entry() / build_prealert() confidence line -----------------------------

def _rec():
    return {"symbol": "XAUUSD", "direction": "long", "entry": 2000.0, "stop": 1990.0,
           "target": 2030.0, "rr": 3.0, "invalidation": "close below 1985"}


def test_build_entry_shows_uncalibrated_confidence_line():
    text = als.build_entry(_rec(), lt=None, confluence=None,
                           confidence=_assessment(is_calibrated=False))
    assert "confidence: High Confidence (78/100" in text
    assert "uncalibrated" in text


def test_build_entry_shows_calibrated_confidence_line():
    text = als.build_entry(_rec(), lt=None, confluence=None,
                           confidence=_assessment(is_calibrated=True, calibrated_probability=0.65))
    assert "65% calibrated" in text


def test_build_entry_omits_confidence_line_when_none():
    text = als.build_entry(_rec(), lt=None, confluence=None, confidence=None)
    assert "confidence:" not in text


def test_build_prealert_shows_confidence_line():
    sig = SimpleNamespace(symbol="XAUUSD", direction="long", entry=2000.0, stop=1990.0,
                          target=2030.0, rr=3.0, confidence=80, reasons=["swept liquidity"])
    r = {"session": "London KZ", "biases": {"1d": "up", "4h": "up", "1h": "up"}}
    text = als.build_prealert(sig, r, guard=None, confluence=None,
                              confidence=_assessment(is_calibrated=False))
    assert "confidence: High Confidence (78/100" in text


def test_build_prealert_omits_confidence_line_when_none():
    sig = SimpleNamespace(symbol="XAUUSD", direction="long", entry=2000.0, stop=1990.0,
                          target=2030.0, rr=3.0, confidence=80, reasons=[])
    r = {"session": "London KZ", "biases": {"1d": "up", "4h": "up", "1h": "up"}}
    text = als.build_prealert(sig, r, guard=None, confluence=None, confidence=None)
    assert "confidence:" not in text


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
