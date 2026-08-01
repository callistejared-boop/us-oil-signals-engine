"""Offline tests for heartbeat_watchdog.py (added 2026-07-28)."""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import heartbeat_watchdog as hb  # noqa: E402


def test_missing_file_is_none_not_stale(tmp_path):
    assert hb.heartbeat_age_minutes(tmp_path / "nope.txt") is None


def test_fresh_heartbeat_is_low_age(tmp_path):
    f = tmp_path / "hb.txt"
    f.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "\n")
    age = hb.heartbeat_age_minutes(f)
    assert age is not None and age < 2


def test_stale_heartbeat_detected(tmp_path):
    f = tmp_path / "hb.txt"
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    f.write_text(old.strftime("%Y-%m-%d %H:%M UTC") + "\n")
    age = hb.heartbeat_age_minutes(f)
    assert age is not None and age > hb.STALE_MINUTES


def test_news_blackout_suffix_still_parses(tmp_path):
    f = tmp_path / "hb.txt"
    now = datetime.now(timezone.utc)
    f.write_text(now.strftime("%Y-%m-%d %H:%M UTC") + " [NEWS BLACKOUT]\n")
    age = hb.heartbeat_age_minutes(f)
    assert age is not None and age < 2


def test_garbage_file_fails_safe_to_none(tmp_path):
    f = tmp_path / "hb.txt"
    f.write_text("not a timestamp at all\n")
    assert hb.heartbeat_age_minutes(f) is None


def test_main_does_not_alert_when_no_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hb, "ROOT", tmp_path)
    sent = {"called": False}
    monkeypatch.setattr(hb, "_send_dm", lambda text: sent.update(called=True) or True)
    hb.main()
    assert sent["called"] is False


def test_main_alerts_when_stale(tmp_path, monkeypatch):
    f = tmp_path / "alert_heartbeat.txt"
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    f.write_text(old.strftime("%Y-%m-%d %H:%M UTC") + "\n")
    monkeypatch.setattr(hb, "ROOT", tmp_path)
    captured = {}
    monkeypatch.setattr(hb, "_send_dm", lambda text: captured.setdefault("text", text) or True)
    hb.main()
    assert "text" in captured and "stale" in captured["text"].lower()


def test_main_does_not_alert_when_fresh(tmp_path, monkeypatch):
    f = tmp_path / "alert_heartbeat.txt"
    f.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "\n")
    monkeypatch.setattr(hb, "ROOT", tmp_path)
    sent = {"called": False}
    monkeypatch.setattr(hb, "_send_dm", lambda text: sent.update(called=True) or True)
    hb.main()
    assert sent["called"] is False


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
