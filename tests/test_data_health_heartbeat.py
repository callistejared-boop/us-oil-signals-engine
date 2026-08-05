import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import heartbeat as hb  # noqa: E402
from engine.data_health import freshness as fr  # noqa: E402


def test_scheduler_status_unknown_when_no_heartbeat_file(data_health_paths, monkeypatch):
    import heartbeat_watchdog as hbw
    monkeypatch.setattr(hbw, "ROOT", data_health_paths["tmp_path"])
    block = hb.scheduler_status()
    assert block["state"] == fr.UNKNOWN


def test_scheduler_status_fresh_when_recent(data_health_paths, monkeypatch):
    import heartbeat_watchdog as hbw
    tmp = data_health_paths["tmp_path"]
    monkeypatch.setattr(hbw, "ROOT", tmp)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (tmp / "alert_heartbeat.txt").write_text(f"{ts}\nsome log line\n", encoding="utf-8")
    block = hb.scheduler_status()
    assert block["state"] == fr.FRESH


def test_scheduler_status_expired_when_old(data_health_paths, monkeypatch):
    import heartbeat_watchdog as hbw
    tmp = data_health_paths["tmp_path"]
    monkeypatch.setattr(hbw, "ROOT", tmp)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M UTC")
    (tmp / "alert_heartbeat.txt").write_text(f"{old_ts}\nsome log line\n", encoding="utf-8")
    block = hb.scheduler_status()
    assert block["state"] == fr.EXPIRED


def test_dashboard_publish_status_unknown_when_missing(data_health_paths):
    block = hb.dashboard_publish_status()
    assert block["state"] == fr.UNKNOWN


def test_dashboard_publish_status_fresh_when_recent(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hb.DASHBOARD_PUBLISH_HEARTBEAT.write_text(json.dumps({"published_at": ts}), encoding="utf-8")
    block = hb.dashboard_publish_status()
    assert block["state"] == fr.FRESH


def test_journal_persistence_status_unknown_when_missing(data_health_paths):
    block = hb.journal_persistence_status()
    assert block["state"] == fr.UNKNOWN


def test_journal_persistence_status_fresh_when_recent(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    (tmp / "trades.json").write_text("[]", encoding="utf-8")
    block = hb.journal_persistence_status()
    assert block["state"] == fr.FRESH


def test_current_status_never_writes_to_history(data_health_paths):
    row = hb.current_status(processing_latency_seconds=1.0)
    assert "scheduler" in row
    assert not hb.HEARTBEAT_HISTORY.exists()


def test_record_beat_persists_and_returns_row(data_health_paths):
    row = hb.record_beat(processing_latency_seconds=1.23, queue_depth=4,
                          provider_fresh_count=10, provider_total_count=15, note="test run")
    assert row["processing_latency_seconds"] == 1.23
    assert row["queue_depth"] == 4
    assert row["provider_fresh_count"] == 10
    assert row["note"] == "test run"
    assert "scheduler" in row and "dashboard_publish" in row and "journal_persistence" in row


def test_tail_returns_recent_records(data_health_paths):
    hb.record_beat(note="first")
    hb.record_beat(note="second")
    tail = hb.tail(5)
    assert len(tail) == 2
    assert tail[-1]["note"] == "second"


def test_tail_empty_when_no_history(data_health_paths):
    assert hb.tail(5) == []


def test_record_beat_never_raises(data_health_paths, monkeypatch):
    monkeypatch.setattr(hb, "HEARTBEAT_HISTORY", pathlib.Path("/nonexistent_dir_xyz/hb.jsonl"))
    row = hb.record_beat()
    assert "ts" in row  # either a normal row or an error row, never an exception


def test_rotate_caps_history_length(data_health_paths):
    monkeypatch_max = 10
    import engine.data_health.heartbeat as hb_mod
    original_max = hb_mod.MAX_LINES
    hb_mod.MAX_LINES = monkeypatch_max
    try:
        for i in range(monkeypatch_max + 5):
            hb.record_beat(note=f"beat-{i}")
        lines = hb.HEARTBEAT_HISTORY.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= monkeypatch_max
    finally:
        hb_mod.MAX_LINES = original_max
