"""Tests for hardened journal storage: salvage, atomic save, backup."""
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import journal as J  # noqa: E402

FULL = [{"id": f"T{i}", "opened": "2026-07-13 00:00:00", "direction": "long",
         "entry": 1.0, "stop": 0.9, "target": 1.3, "rr": 3.0, "confidence": 80,
         "symbol": "XAUUSD", "status": "win", "closed": "", "result_r": 2.0}
        for i in range(5)]


def test_salvage_recovers_truncated():
    good = json.dumps(FULL, indent=2)
    truncated = good[: int(len(good) * 0.8)]  # cut mid-file
    rows = J._salvage(truncated)
    assert 1 <= len(rows) < len(FULL)  # recovered most, dropped the partial tail
    assert all("id" in r for r in rows)


def test_salvage_empty_on_garbage():
    assert J._salvage("not json at all {[") == []


def test_read_prefers_valid(tmp_path, monkeypatch):
    p = tmp_path / "trades.json"
    p.write_text(json.dumps(FULL))
    assert len(J._read(p)) == 5


def test_read_salvages_corrupt(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(FULL)[:-40])  # truncate tail
    assert len(J._read(p)) >= 4


def test_save_is_atomic_and_backs_up(tmp_path, monkeypatch):
    store = tmp_path / "trades.json"
    monkeypatch.setattr(J, "STORE", store)
    monkeypatch.setattr(J, "BAK", store.with_suffix(".json.bak"))
    monkeypatch.setattr(J, "TMP", store.with_suffix(".json.tmp"))
    J._save(FULL)
    assert len(json.loads(store.read_text())) == 5
    J._save(FULL + [dict(FULL[0], id="T5")])
    assert len(json.loads(store.read_text())) == 6
    assert J.BAK.exists() and len(json.loads(J.BAK.read_text())) == 5  # prior state backed up
    assert not J.TMP.exists()  # temp cleaned by replace
