"""Offline tests for regime_history.py's Day 7 addition: the optional
`ref` parameter on record() and find_by_ref() — completes the unified
trade ID alongside confluence_history.py / confidence_history.py (Day 6).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import regime_history as rh  # noqa: E402


def _result(primary="Strong Bull Trend", confidence=70, quality_score=65):
    return {"primary": primary, "confidence": confidence, "quality_score": quality_score,
           "transition_risk": 0.2, "transition_label": "stable"}


def test_record_ref_defaults_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rec = rh.record("XAUUSD", "strategic", _result())
    assert rec["ref"] == ""


def test_record_accepts_and_persists_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rec = rh.record("XAUUSD", "strategic", _result(), ref="XAUUSD-2026-08-04T10:00:00")
    assert rec["ref"] == "XAUUSD-2026-08-04T10:00:00"


def test_find_by_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))  # routine scan row, no ref
    rh.record("XAUUSD", "strategic", _result(primary="Strong Bull Trend"),
             ref="XAUUSD-2026-08-04T10:00:00")
    found = rh.find_by_ref("XAUUSD-2026-08-04T10:00:00")
    assert found is not None
    assert found["primary"] == "Strong Bull Trend"


def test_find_by_ref_missing_and_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    assert rh.find_by_ref("nope") is None
    assert rh.find_by_ref("") is None


def test_ref_tagged_row_still_participates_in_transition_detection(tmp_path, monkeypatch):
    """Documented trade-off (MARKET_MEMORY_SPECIFICATION.md Sec.2): a
    ref-tagged row is not a separate record type — it's the same schema,
    so last_for()/transitions() still see it."""
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Strong Bull Trend"), ref="some-ref")
    last = rh.last_for("XAUUSD", "strategic")
    assert last["primary"] == "Strong Bull Trend"
    assert last["ref"] == "some-ref"


def test_pre_day7_rows_without_ref_still_readable(tmp_path, monkeypatch):
    """Backward compatibility: rows written before this field existed lack
    the key entirely — tail()/last_for() must not KeyError on them."""
    import json
    path = tmp_path / "regime_history.jsonl"
    monkeypatch.setattr(rh, "HISTORY_PATH", path)
    legacy = {"ts": "2026-07-01T09:00:00", "symbol": "XAUUSD", "timeframe": "strategic",
             "primary": "Range", "confidence": 50, "quality_score": 40}
    path.write_text(__import__("json").dumps(legacy) + "\n", encoding="utf-8")
    rows = rh.tail(5, symbol="XAUUSD")
    assert len(rows) == 1
    assert rows[0].get("ref", "") == ""
