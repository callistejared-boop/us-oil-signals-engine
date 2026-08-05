"""Offline tests for engine/explainability_engine.py's post_trade_review().
Uses a monkeypatched engine.journal.STORE pointed at a tmp_path file so
nothing touches the real trades.json — same isolation discipline as
test_journal_confidence.py.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_audit_history as dah  # noqa: E402
from engine import explainability_engine as ee     # noqa: E402
from engine import journal                          # noqa: E402


def _write_trade(path, **overrides):
    row = {
        "id": "XAUUSD-2026-08-03T10:00:00", "opened": "2026-08-03 10:00:00",
        "direction": "long", "entry": 2400.0, "stop": 2390.0, "target": 2430.0,
        "rr": 3.0, "confidence": 75, "symbol": "XAUUSD", "status": "open",
        "closed": "", "result_r": 0.0,
    }
    row.update(overrides)
    path.write_text(json.dumps([row]))
    return row


def test_post_trade_review_no_snapshot_found():
    out = ee.post_trade_review("does-not-exist")
    assert out["found"] is False


def test_post_trade_review_heads_up_never_became_a_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 09:00:00", stage="approval_or_rejection",
        final_action="approved_heads_up")
    row = dah.record(snap)
    out = ee.post_trade_review(row["decision_id"])
    assert out["found"] is True
    assert out["closed"] is False


def test_post_trade_review_still_open_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="open")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    out = ee.post_trade_review(row["decision_id"])
    assert out["found"] is True
    assert out["closed"] is False


def test_post_trade_review_closed_win(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="win", result_r=1.5, closed="2026-08-03 14:00:00")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    out = ee.post_trade_review(row["decision_id"])
    assert out["found"] is True and out["closed"] is True
    assert out["actual_outcome"]["status"] == "win"
    assert out["actual_outcome"]["result_r"] == 1.5
    assert "recommendations_for_future_research" in out
    assert "heuristic_disclosure" in out


def test_post_trade_review_closed_loss_lists_uncertainty_as_may_have_failed(tmp_path, monkeypatch):
    from engine import confidence_engine as ce
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="loss", result_r=-1.0, closed="2026-08-03 14:00:00")
    assessment = ce.ConfidenceAssessment(
        symbol="XAUUSD", direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=60, tier="Moderate Confidence",
        probability_label="internal decision-quality estimate", calibrated_probability=None,
        is_calibrated=False, evidence_quality=50, evidence_diversity=40, market_quality=60,
        regime_confidence=50, confluence_quality=55, portfolio_status={}, risk_status={},
        uncertainty_indicators=["incomplete market data (evidence coverage below 60%)"],
        conflicting_rationale=["confluence: momentum divergence"])
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00",
        confidence_assessment=assessment)
    row = dah.record(snap)
    out = ee.post_trade_review(row["decision_id"])
    assert out["assumptions_that_may_have_failed"]
    assert out["conflicting_evidence_at_decision_time"]
    assert out["recommendations_for_future_research"]


def test_post_trade_review_never_raises_on_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "does_not_exist.json")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    out = ee.post_trade_review(row["decision_id"])
    assert isinstance(out, dict)


def test_post_trade_review_does_not_modify_production_data(tmp_path, monkeypatch):
    """Mandate: 'Do not automatically modify production logic.' Structural
    proof: trades.json's bytes are untouched by a review call."""
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="win", result_r=1.0, closed="2026-08-03 14:00:00")
    before = (tmp_path / "trades.json").read_text()
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    ee.post_trade_review(row["decision_id"])
    after = (tmp_path / "trades.json").read_text()
    assert before == after
