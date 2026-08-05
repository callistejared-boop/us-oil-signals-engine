"""Offline tests for engine/paper_trading_review.py (Day 9). Reuses the
same tmp_path isolation discipline as test_post_trade_review.py (Day 8).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_audit_history as dah  # noqa: E402
from engine import explainability_engine as ee     # noqa: E402
from engine import paper_trading_review as ptr      # noqa: E402
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


def test_evaluate_not_found():
    out = ptr.evaluate("does-not-exist")
    assert out["found"] is False


def test_evaluate_rejected_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 09:00:00", stage="confluence_assessment",
        final_action="rejected", rejection={"category": ee.WEAK_EVIDENCE, "reason": "score too low"})
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert out["found"] is True
    assert out["proposed_vs_executed"]["matches"] is True
    assert "rejected" in out["proposed_vs_executed"]["proposed"]


def test_evaluate_heads_up_no_direct_link_disclosed(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 09:00:00", stage="approval_or_rejection",
        final_action="approved_heads_up")
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert out["proposed_vs_executed"]["matches"] is None
    assert "note" in out["proposed_vs_executed"]


def test_evaluate_approved_entry_with_trade_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="win", result_r=1.5, closed="2026-08-03 14:00:00")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert out["proposed_vs_executed"]["matches"] is True
    assert out["realized_outcome"]["status"] == "win"
    assert out["deviations"]["heuristic_disclosure"]


def test_evaluate_approved_entry_missing_trade_ref_flagged(tmp_path, monkeypatch):
    """An approved_entry snapshot with no trade_ref is unexpected —
    surfaced as `matches: False`, not silently ignored."""
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry")   # no trade_ref
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert out["proposed_vs_executed"]["matches"] is False


def test_evaluate_lookup_via_trade_ref_also_works(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    _write_trade(tmp_path / "trades.json", status="loss", result_r=-1.0, closed="2026-08-03 14:00:00")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    dah.record(snap)
    out = ptr.evaluate("XAUUSD-2026-08-03T10:00:00")   # lookup by trade_ref, not decision_id
    assert out["found"] is True


def test_operational_issues_empty_when_no_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_heads_up")
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert out["operational_issues"] == []


def test_evaluate_never_raises_on_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(journal, "STORE", tmp_path / "does_not_exist.json")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    out = ptr.evaluate(row["decision_id"])
    assert isinstance(out, dict)
