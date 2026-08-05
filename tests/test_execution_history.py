"""Offline tests for engine/execution/execution_history.py (Day 12). All
tests use a monkeypatched HISTORY_PATH — mirrors test_macro_history.py's
(Day 11) established pattern for file-backed history modules."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import execution_history as exh  # noqa: E402


def _report(score="Good", cost_r=0.1, entry_filled=True):
    return {
        "execution_score": score, "intended_entry": 2350.0, "actual_entry": 2350.1,
        "entry_filled": entry_filled, "expected_exit": None, "actual_exit": None,
        "exit_filled": None, "total_execution_cost": 0.1, "cost_r": cost_r,
        "cost_bps": 0.4, "both_legs_filled": entry_filled,
        "entry_detail": {"spread": {"estimated_spread": 0.35}},  # must NOT be persisted
    }


def test_record_writes_normalized_row(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    row = exh.record("XAUUSD", _report(), ref="XAUUSD-20260803120000")
    assert row["symbol"] == "XAUUSD"
    assert row["ref"] == "XAUUSD-20260803120000"
    assert row["execution_score"] == "Good"
    assert f.exists()


def test_record_never_stores_nested_raw_detail(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    row = exh.record("XAUUSD", _report())
    assert "entry_detail" not in row
    assert "exit_detail" not in row


def test_record_defaults_ref_to_empty_string(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    row = exh.record("EURUSD", _report())
    assert row["ref"] == ""


def test_find_by_ref_round_trips(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    exh.record("XAUUSD", _report(score="Excellent"), ref="A")
    exh.record("XAUUSD", _report(score="Poor"), ref="B")
    found = exh.find_by_ref("B")
    assert found["execution_score"] == "Poor"


def test_find_by_ref_returns_none_when_missing(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    assert exh.find_by_ref("nope") is None


def test_find_by_ref_empty_string_returns_none(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    exh.record("XAUUSD", _report(), ref="")
    assert exh.find_by_ref("") is None


def test_last_for_returns_most_recent(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    exh.record("XAUUSD", _report(score="Average"))
    exh.record("WTIUSD", _report(score="Good"))
    exh.record("XAUUSD", _report(score="Excellent"))
    last = exh.last_for("XAUUSD")
    assert last["execution_score"] == "Excellent"


def test_last_for_none_when_symbol_missing(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    exh.record("WTIUSD", _report())
    assert exh.last_for("BTCUSD") is None


def test_tail_respects_n_and_symbol_filter(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    for i in range(5):
        exh.record("XAUUSD", _report(score=f"S{i}"))
    exh.record("WTIUSD", _report(score="Other"))
    out = exh.tail(n=2, symbol="XAUUSD")
    assert len(out) == 2
    assert out[-1]["execution_score"] == "S4"


def test_all_rows_returns_everything(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    exh.record("XAUUSD", _report())
    exh.record("WTIUSD", _report())
    assert len(exh.all_rows()) == 2


def test_record_never_raises_when_path_unwritable(tmp_path, monkeypatch):
    bogus = tmp_path / "no_such_dir" / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", bogus)
    row = exh.record("XAUUSD", _report())
    assert row["symbol"] == "XAUUSD"
    assert not bogus.exists()


def test_normalize_never_raises_on_malformed_report():
    out = exh._normalize("not-a-dict")
    assert out["execution_score"] == "Unknown"
    assert "error" in out


def test_rotate_trims_to_max_lines(tmp_path, monkeypatch):
    f = tmp_path / "execution_history.jsonl"
    monkeypatch.setattr(exh, "HISTORY_PATH", f)
    monkeypatch.setattr(exh, "MAX_LINES", 3)
    for i in range(6):
        exh.record("XAUUSD", _report(score=f"S{i}"))
    rows = exh.all_rows()
    assert len(rows) == 3
    assert rows[-1]["execution_score"] == "S5"


def test_no_update_or_delete_function_exists():
    assert not hasattr(exh, "update")
    assert not hasattr(exh, "delete")
