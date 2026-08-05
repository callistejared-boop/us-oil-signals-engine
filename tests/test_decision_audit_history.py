"""Offline tests for engine/decision_audit_history.py (Day 8). All tests
point HISTORY_PATH at a tmp_path file via monkeypatch so nothing touches
the real repo's decision_audit.jsonl — mirrors test_confidence_history.py's
(Day 6) exact fixture pattern.
"""
import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_audit_history as dah  # noqa: E402
from engine import explainability_engine as ee     # noqa: E402
from engine import journal                          # noqa: E402


def _snapshot(symbol="XAUUSD", when="2026-08-03 10:00:00",
             final_action="approved_heads_up", rejection=None):
    return ee.build_decision_snapshot(
        symbol, "long", when, stage="approval_or_rejection",
        final_action=final_action, rejection=rejection)


def _did(symbol, when):
    """Compute the same decision_id build_decision_snapshot() would, for
    test assertions — mirrors journal.make_ref()'s exact format."""
    return journal.make_ref(symbol, when)


def test_record_writes_and_tail_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    rec = dah.record(_snapshot())
    assert rec["symbol"] == "XAUUSD"
    assert rec["decision_id"] == _did("XAUUSD", "2026-08-03 10:00:00")
    assert rec["record_type"] == "decision"
    out = dah.tail(5, symbol="XAUUSD")
    assert len(out) == 1


def test_record_dict_input(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    d = {"decision_id": "WTIUSD-x", "symbol": "WTIUSD", "final_action": "rejected"}
    rec = dah.record(d)
    assert rec["symbol"] == "WTIUSD"


def test_tail_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record(_snapshot(symbol="XAUUSD", when="2026-08-03 10:00:00"))
    dah.record(_snapshot(symbol="WTIUSD", when="2026-08-03 10:01:00"))
    assert len(dah.tail(10, symbol="XAUUSD")) == 1
    assert len(dah.tail(10, symbol="WTIUSD")) == 1
    assert len(dah.tail(10)) == 2


def test_all_rows_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    for i in range(3):
        dah.record(_snapshot(when=f"2026-08-03 10:{i:02d}:00"))
    assert len(dah.all_rows()) == 3


def test_rotation_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    monkeypatch.setattr(dah, "MAX_LINES", 10)
    for i in range(25):
        dah.record(_snapshot(when=f"2026-08-03 10:{i % 60:02d}:00"))
    lines = (tmp_path / "decision_audit.jsonl").read_text().splitlines()
    assert len(lines) <= 10


def test_record_never_raises_on_unwritable_path(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "no" / "such" / "dir" / "h.jsonl")
    rec = dah.record(_snapshot())
    assert rec["symbol"] == "XAUUSD"


def test_all_rows_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "nope.jsonl")
    assert dah.all_rows() == []


def test_find_by_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record(_snapshot(when="2026-08-03 10:00:00"))
    dah.record(_snapshot(when="2026-08-03 10:01:00"))
    expected = _did("XAUUSD", "2026-08-03 10:01:00")
    found = dah.find_by_ref(expected)
    assert found is not None and found["decision_id"] == expected


def test_find_by_ref_missing_and_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    assert dah.find_by_ref("nope") is None
    assert dah.find_by_ref("") is None


def test_find_by_trade_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", trade_ref="XAUUSD-2026-08-03T10:00:00")
    dah.record(snap)
    found = dah.find_by_trade_ref("XAUUSD-2026-08-03T10:00:00")
    assert found is not None
    assert dah.find_by_trade_ref("") is None
    assert dah.find_by_trade_ref("nope") is None


def test_records_are_never_mutated_in_place(tmp_path, monkeypatch):
    """Design guarantee (mandate: 'must never be edited after creation') —
    writing a second row must never alter a previously-written row's bytes
    on disk."""
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record(_snapshot(when="2026-08-03 10:00:00"))
    before = (tmp_path / "decision_audit.jsonl").read_text()
    dah.record(_snapshot(when="2026-08-03 10:01:00"))
    after = (tmp_path / "decision_audit.jsonl").read_text()
    assert after.startswith(before)


def test_no_mutator_besides_record_exists():
    """Structural proof of immutability, not just a documented promise —
    the module must expose no update/delete/overwrite function of any
    kind."""
    names = [n for n, obj in inspect.getmembers(dah) if inspect.isfunction(obj)]
    forbidden = {"update", "delete", "overwrite", "edit", "modify", "remove", "patch"}
    for n in names:
        lname = n.lower()
        assert not any(f in lname for f in forbidden), f"unexpected mutator-like function: {n}"


def test_record_correction_appends_new_row_original_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record(_snapshot(when="2026-08-03 10:00:00"))
    did = _did("XAUUSD", "2026-08-03 10:00:00")
    before = (tmp_path / "decision_audit.jsonl").read_text()
    corr = dah.record_correction(did, "test note", {"symbol": "XAUUSD-typo-fix"})
    after = (tmp_path / "decision_audit.jsonl").read_text()
    assert after.startswith(before)   # original row's bytes untouched
    assert corr["record_type"] == "correction"
    assert corr["corrects_ref"] == did


def test_history_for_ref_returns_original_plus_corrections(tmp_path, monkeypatch):
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record(_snapshot(when="2026-08-03 10:00:00"))
    dah.record(_snapshot(when="2026-08-03 10:01:00"))   # unrelated row, must not appear
    did = _did("XAUUSD", "2026-08-03 10:00:00")
    dah.record_correction(did, "note 1", {})
    dah.record_correction(did, "note 2", {})
    hist = dah.history_for_ref(did)
    assert len(hist) == 3
    assert hist[0]["record_type"] == "decision"
    assert hist[1]["record_type"] == "correction"
    assert hist[2]["record_type"] == "correction"


def test_history_for_ref_empty_for_unknown():
    assert dah.history_for_ref("") == []
    assert dah.history_for_ref("nope-does-not-exist") == []
