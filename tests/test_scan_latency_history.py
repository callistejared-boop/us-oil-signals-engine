"""Tests for engine/scan_latency_history.py (V2.2 Priority 1 Item 2). All
tests point HISTORY_PATH at a tmp_path file via monkeypatch, mirroring
tests/test_regime_history.py, so nothing touches the real repo's
scan_latency_history.jsonl.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import scan_latency_history as slh  # noqa: E402


def test_record_writes_and_tail_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    rec = slh.record({"market_fetch": 12.5, "regime": 3.1}, total_ms=45.0,
                      symbol_count=2, call_counts={"market_fetch": 2, "regime": 2})
    assert rec["stages"]["market_fetch"] == 12.5
    assert rec["total_ms"] == 45.0
    assert rec["symbol_count"] == 2
    rows = slh.tail(5)
    assert len(rows) == 1
    assert rows[0]["stages"]["regime"] == 3.1


def test_stage_stats_computes_max_avg_p95_p99(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    # 100 scans, market_fetch elapsed = 1..100 ms
    for i in range(1, 101):
        slh.record({"market_fetch": float(i)}, total_ms=float(i) * 2)
    stats = slh.stage_stats("market_fetch", n=200)
    assert stats["n"] == 100
    assert stats["max_ms"] == 100.0
    assert stats["avg_ms"] == 50.5
    # nearest-rank P95/P99 over 1..100
    assert stats["p95_ms"] == 95.0
    assert stats["p99_ms"] == 99.0


def test_stage_stats_missing_stage_returns_none_fields_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    slh.record({"market_fetch": 5.0}, total_ms=10.0)
    stats = slh.stage_stats("macro")   # never recorded - conditional stage
    assert stats["n"] == 0
    assert stats["max_ms"] is None
    assert stats["avg_ms"] is None


def test_longest_scan_picks_max_total_ms(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    slh.record({}, total_ms=100.0)
    slh.record({}, total_ms=500.0)
    slh.record({}, total_ms=250.0)
    longest = slh.longest_scan()
    assert longest["total_ms"] == 500.0


def test_longest_today_excludes_older_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    path = tmp_path / "scan_latency_history.jsonl"
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    old_row = {"ts": yesterday, "total_ms": 9999.0, "symbol_count": 0,
               "stages": {}, "call_counts": {}}
    import json
    path.write_text(json.dumps(old_row) + "\n", encoding="utf-8")
    slh.record({}, total_ms=50.0)   # today, much smaller
    longest = slh.longest_today()
    assert longest["total_ms"] == 50.0   # the huge row from yesterday is excluded


def test_longest_this_week_includes_today(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    slh.record({}, total_ms=77.0)
    longest = slh.longest_this_week()
    assert longest["total_ms"] == 77.0


def test_all_stage_stats_covers_every_stage_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(slh, "HISTORY_PATH", tmp_path / "scan_latency_history.jsonl")
    slh.record({"market_fetch": 10.0, "regime": 2.0}, total_ms=20.0)
    slh.record({"market_fetch": 12.0}, total_ms=15.0)
    all_stats = slh.all_stage_stats()
    assert set(all_stats.keys()) == {"market_fetch", "regime"}
    assert all_stats["market_fetch"]["n"] == 2
    assert all_stats["regime"]["n"] == 1


def test_record_never_raises_on_bad_input():
    # stage_ms with a non-numeric value should be swallowed, not raise -
    # same fail-safe posture as regime_history.py/ledger.py.
    rec = slh.record({"market_fetch": "not-a-number"}, total_ms=10.0)
    assert rec is not None


def test_rotate_caps_history_length(tmp_path, monkeypatch):
    path = tmp_path / "scan_latency_history.jsonl"
    monkeypatch.setattr(slh, "HISTORY_PATH", path)
    monkeypatch.setattr(slh, "MAX_LINES", 10)
    for i in range(25):
        slh.record({"market_fetch": float(i)}, total_ms=float(i))
    rows = slh.tail(1000)
    assert len(rows) == 10
    # rotation keeps the most recent rows
    assert rows[-1]["total_ms"] == 24.0
