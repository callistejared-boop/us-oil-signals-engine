import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine.data_health import freshness as fr  # noqa: E402


def test_log_data_health_returns_report_shape(data_health_paths):
    class FakeSettings:
        pass
    report = als.log_data_health(FakeSettings(), 1.5, 4)
    assert "overall_status" in report
    assert "counts" in report


def test_log_data_health_never_raises_on_bad_settings(data_health_paths, monkeypatch):
    from engine.data_health import feed_monitor as dh_monitor

    def _boom(**kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(dh_monitor, "run_health_check", _boom)
    report = als.log_data_health(None, None, None)
    assert report["overall_status"] == "unavailable"
    assert "log_data_health error" in report["note"]


def test_news_state_observation_recorded_on_evaluate(data_health_paths, monkeypatch):
    # main() calls news_guard.evaluate() then records an observation for
    # the news_calendar feed — simulate that one call in isolation rather
    # than running the full multi-symbol main() loop.
    fake_state = {"ok": True, "blackout": False, "note": ""}
    fr.record_observation("news_calendar", bool(fake_state.get("ok", True)), fake_state.get("note", "") or "")
    row = fr.last_observation("news_calendar")
    assert row["ok"] is True


def test_news_state_observation_records_failure(data_health_paths):
    fake_state = {"ok": False, "blackout": False, "note": "calendar unavailable (timeout)"}
    fr.record_observation("news_calendar", bool(fake_state.get("ok", True)), fake_state.get("note", "") or "")
    row = fr.last_observation("news_calendar")
    assert row["ok"] is False
    assert "timeout" in row["detail"]


def test_data_health_never_imported_by_gating_modules():
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "data_health",
         "engine/risk_guard.py", "engine/confluence.py", "engine/confidence_engine.py",
         "engine/bias_adjust.py", "engine/signals.py", "engine/portfolio_risk.py",
         "engine/regime_engine.py"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert result.returncode == 1  # grep exit code 1 == no matches found
    assert result.stdout == ""
