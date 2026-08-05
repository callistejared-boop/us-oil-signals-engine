"""Offline tests for engine/confidence_history.py (Day 6). All tests point
HISTORY_PATH at a tmp_path file via monkeypatch so nothing touches the real
repo's confidence_history.jsonl — mirrors test_confluence_history.py's (Day
5) exact fixture pattern.
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confidence_history as ch  # noqa: E402
from engine import confidence_engine as ce   # noqa: E402


def _assessment(symbol="XAUUSD", overall_confidence=80, tier="High Confidence"):
    return ce.ConfidenceAssessment(
        symbol=symbol, direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=overall_confidence, tier=tier,
        probability_label="internal decision-quality estimate", calibrated_probability=None,
        is_calibrated=False, evidence_quality=70, evidence_diversity=60,
        market_quality=75, regime_confidence=65, confluence_quality=70,
        portfolio_status={"allow": True}, risk_status={"guard_action": "allow"},
    )


def test_record_writes_and_tail_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    rec = ch.record(_assessment(), ref="XAUUSD-2026-08-03T10:00:00")
    assert rec["symbol"] == "XAUUSD"
    assert rec["overall_confidence"] == 80
    assert rec["ref"] == "XAUUSD-2026-08-03T10:00:00"
    out = ch.tail(5, symbol="XAUUSD")
    assert len(out) == 1
    assert out[0]["tier"] == "High Confidence"


def test_record_dict_input(tmp_path, monkeypatch):
    """record() must work with either a ConfidenceAssessment (has
    .as_dict()) or an equivalent plain dict — matches the flexibility
    confluence_history.record() doesn't need but confidence_history's
    single-object-parameter signature does."""
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    d = {"symbol": "WTIUSD", "overall_confidence": 55, "tier": "Moderate Confidence"}
    rec = ch.record(d)
    assert rec["symbol"] == "WTIUSD" and rec["overall_confidence"] == 55
    assert rec["ref"] == ""   # default when not passed


def test_tail_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    ch.record(_assessment(symbol="XAUUSD"))
    ch.record(_assessment(symbol="WTIUSD"))
    assert len(ch.tail(10, symbol="XAUUSD")) == 1
    assert len(ch.tail(10, symbol="WTIUSD")) == 1
    assert len(ch.tail(10)) == 2


def test_all_rows_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    for i in range(3):
        ch.record(_assessment(overall_confidence=70 + i))
    assert len(ch.all_rows()) == 3


def test_rotation_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    monkeypatch.setattr(ch, "MAX_LINES", 10)
    for i in range(25):
        ch.record(_assessment())
    lines = (tmp_path / "confidence_history.jsonl").read_text().splitlines()
    assert len(lines) <= 10


def test_record_never_raises_on_unwritable_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "no" / "such" / "dir" / "h.jsonl")
    rec = ch.record(_assessment())
    assert rec["symbol"] == "XAUUSD"   # still returns the record


def test_all_rows_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "nope.jsonl")
    assert ch.all_rows() == []


def test_find_by_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    ch.record(_assessment(symbol="XAUUSD", overall_confidence=60), ref="ref-1")
    ch.record(_assessment(symbol="XAUUSD", overall_confidence=90), ref="ref-2")
    found = ch.find_by_ref("ref-2")
    assert found is not None and found["overall_confidence"] == 90


def test_find_by_ref_missing_and_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    assert ch.find_by_ref("nope") is None
    assert ch.find_by_ref("") is None


def test_records_are_never_mutated_in_place(tmp_path, monkeypatch):
    """Design guarantee (mandate: 'without modifying historical records') —
    writing a second assessment must never alter a previously-written row's
    bytes on disk."""
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confidence_history.jsonl")
    ch.record(_assessment(overall_confidence=60), ref="ref-1")
    before = (tmp_path / "confidence_history.jsonl").read_text()
    ch.record(_assessment(overall_confidence=90), ref="ref-2")
    after = (tmp_path / "confidence_history.jsonl").read_text()
    assert after.startswith(before)   # original bytes untouched, only appended to
