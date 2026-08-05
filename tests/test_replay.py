"""Offline tests for engine/explainability_engine.py's replay() — proves
"historical explanations must remain reproducible" (Day 8 mandate) is a
structural property, not just a documented promise: replaying the same
decision_id twice must return byte-identical output, purely from persisted
evidence (no live re-computation).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_audit_history as dah  # noqa: E402
from engine import explainability_engine as ee     # noqa: E402
from engine import confluence as cf                # noqa: E402


def _cr():
    return cf.ConfluenceRead(symbol="XAUUSD", direction="long", base_tier="confirmed",
                             final_tier="confirmed", score=82, agree=["price action"], disagree=[])


def test_replay_missing_decision_id_never_raises():
    out = ee.replay("does-not-exist")
    assert out["found"] is False
    assert "decision_id" in out


def test_replay_approved_decision_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", cr=_cr(), trade_ref="XAUUSD-2026-08-03T10:00:00")
    row = dah.record(snap)
    r1 = ee.replay(row["decision_id"])
    r2 = ee.replay(row["decision_id"])
    assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)
    assert r1["found"] is True
    assert r1["graph"]["nodes"]
    assert r1["explanation"]["why_approved"]


def test_replay_rejected_decision_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "WTIUSD", "short", "2026-08-03 11:00:00", stage="confluence_assessment",
        final_action="rejected", rejection={"category": ee.WEAK_EVIDENCE, "reason": "score too low"})
    row = dah.record(snap)
    r1 = ee.replay(row["decision_id"])
    r2 = ee.replay(row["decision_id"])
    assert r1 == r2
    assert r1["explanation"]["rejection_category"] == ee.WEAK_EVIDENCE


def test_replay_includes_corrections(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry")
    row = dah.record(snap)
    dah.record_correction(row["decision_id"], "note", {"symbol": "fixed"})
    out = ee.replay(row["decision_id"])
    assert len(out["corrections"]) == 1


def test_replay_two_different_decisions_are_not_confused(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    s1 = ee.build_decision_snapshot("XAUUSD", "long", "2026-08-03 10:00:00",
                                    stage="approval_or_rejection", final_action="approved_entry")
    s2 = ee.build_decision_snapshot("XAUUSD", "short", "2026-08-03 11:00:00",
                                    stage="confluence_assessment", final_action="rejected",
                                    rejection={"category": ee.WEAK_EVIDENCE, "reason": "x"})
    r1 = dah.record(s1)
    r2 = dah.record(s2)
    out1 = ee.replay(r1["decision_id"])
    out2 = ee.replay(r2["decision_id"])
    assert out1["snapshot"]["direction"] == "long"
    assert out2["snapshot"]["direction"] == "short"
    assert out1 != out2
