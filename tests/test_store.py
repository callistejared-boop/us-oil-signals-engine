"""Tests for the resilient shared JSON-array loader."""
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import store  # noqa: E402

FULL = [{"id": f"T{i}", "status": "win", "result_r": 2.0} for i in range(6)]


def test_load_valid(tmp_path):
    p = tmp_path / "t.json"; p.write_text(json.dumps(FULL))
    assert len(store.load_array(p)) == 6


def test_load_missing_returns_empty(tmp_path):
    assert store.load_array(tmp_path / "nope.json") == []


def test_load_salvages_truncation(tmp_path):
    p = tmp_path / "t.json"; p.write_text(json.dumps(FULL)[:-30])  # cut the tail
    rows = store.load_array(p)
    assert 4 <= len(rows) < 6 and all("id" in r for r in rows)


def test_salvage_garbage_is_empty():
    assert store.salvage("total nonsense {[") == []
