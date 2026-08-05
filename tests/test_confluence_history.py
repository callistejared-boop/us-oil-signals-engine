"""Offline tests for engine/confluence_history.py (Day 5). All tests point
HISTORY_PATH at a tmp_path file via monkeypatch so nothing touches the real
repo's confluence_history.jsonl.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confluence_history as ch  # noqa: E402


def test_record_writes_and_tail_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    rec = ch.record("XAUUSD", "long", 82, "confirmed",
                    ["price action", "COT positioning"], ["mean reversion (overextended)"],
                    {"score": 70}, [{"pattern": "x"}])
    assert rec["symbol"] == "XAUUSD"
    assert rec["score"] == 82
    assert rec["quality_score"] == 70
    assert rec["n_conflicts"] == 1
    out = ch.tail(5, symbol="XAUUSD")
    assert len(out) == 1
    assert out[0]["agree"] == ["price action", "COT positioning"]


def test_tail_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    ch.record("XAUUSD", "long", 80, "confirmed", [], [], {}, [])
    ch.record("WTIUSD", "short", 60, "watch", [], [], {}, [])
    assert len(ch.tail(10, symbol="XAUUSD")) == 1
    assert len(ch.tail(10, symbol="WTIUSD")) == 1
    assert len(ch.tail(10)) == 2


def test_all_rows_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    for i in range(3):
        ch.record("XAUUSD", "long", 70 + i, "confirmed", [], [], {}, [])
    assert len(ch.all_rows()) == 3


def test_rotation_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    monkeypatch.setattr(ch, "MAX_LINES", 10)
    for i in range(25):
        ch.record("XAUUSD", "long", 70, "confirmed", [], [], {}, [])
    lines = (tmp_path / "confluence_history.jsonl").read_text().splitlines()
    assert len(lines) <= 10


def test_record_never_raises_on_unwritable_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "no" / "such" / "dir" / "h.jsonl")
    rec = ch.record("XAUUSD", "long", 80, "confirmed", [], [], {}, [])
    assert rec["symbol"] == "XAUUSD"   # still returns the record


def test_all_rows_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "HISTORY_PATH", tmp_path / "nope.jsonl")
    assert ch.all_rows() == []


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
