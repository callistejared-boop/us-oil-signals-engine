import json
import os
import pathlib
import sys
import time as time_mod

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import feed_monitor as fm  # noqa: E402
from engine.data_health import provider_status as ps  # noqa: E402
from engine.data_health.registry import FeedSpec  # noqa: E402


def _age_file(path: pathlib.Path, minutes_old: float):
    path.write_text("{}", encoding="utf-8")
    old = time_mod.time() - minutes_old * 60
    os.utime(path, (old, old))


def test_run_health_check_never_raises_with_empty_registry(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    report = fm.run_health_check()
    assert report["total_feeds"] == 0
    assert report["overall_status"] == "unavailable"


def test_run_health_check_missing_feed_reports_unavailable_or_degraded_never_crashes(
        data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(
        feed_id="missing_feed", provider="p", purpose="x", category="macro",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="does_not_exist.json"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "missing_feed")
    assert entry["status"] in (ps.DEGRADED, ps.UNAVAILABLE)  # UNKNOWN freshness -> degraded floor


def test_run_health_check_delayed_feed_reports_worse_than_fresh(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    _age_file(tmp / "delayed.json", minutes_old=120)  # way past expected
    registry_sandbox.register(FeedSpec(
        feed_id="delayed_feed", provider="p", purpose="x", category="macro",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="delayed.json"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "delayed_feed")
    assert entry["status"] == ps.UNAVAILABLE  # 6x expected -> EXPIRED -> UNAVAILABLE


def test_run_health_check_fresh_feed_reports_operational(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    (tmp / "fresh.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    registry_sandbox.register(FeedSpec(
        feed_id="fresh_feed", provider="p", purpose="x", category="infrastructure",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="fresh.json"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "fresh_feed")
    assert entry["status"] == ps.OPERATIONAL


def test_run_health_check_malformed_market_cache_reports_critical(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    (tmp / "BADSYM.pkl").write_text("not a real pickle file", encoding="utf-8")
    registry_sandbox.register(FeedSpec(
        feed_id="market_data:BADSYM", provider="p", purpose="x", category="market_data",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="BADSYM.pkl"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "market_data:BADSYM")
    # unreadable pickle -> _load_market_dataframe returns None -> completeness CRITICAL
    assert entry["status"] == ps.UNAVAILABLE


def test_run_health_check_frozen_price_detected(data_health_paths, registry_sandbox):
    import pandas as pd
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    df = pd.DataFrame({
        "open": [2000.0] * 20, "high": [2001.0] * 20, "low": [1999.0] * 20,
        "close": [2000.0] * 20,  # frozen — identical every bar
    })
    df.to_pickle(tmp / "FROZEN.pkl")
    registry_sandbox.register(FeedSpec(
        feed_id="market_data:FROZEN", provider="p", purpose="x", category="market_data",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="FROZEN.pkl"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "market_data:FROZEN")
    assert entry["status"] != ps.OPERATIONAL
    assert any("anomaly" in r for r in entry["reasons"])


def test_run_health_check_duplicate_timestamps_detected(data_health_paths, registry_sandbox):
    import pandas as pd
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    idx = list(pd.date_range("2026-01-01", periods=19, freq="15min")) + [pd.Timestamp("2026-01-01")]
    base = [2000 + x for x in range(20)]
    df = pd.DataFrame({
        "open": base, "high": [x + 1 for x in base],
        "low": [x - 1 for x in base], "close": base,
    }, index=idx)
    df.to_pickle(tmp / "DUPE.pkl")
    registry_sandbox.register(FeedSpec(
        feed_id="market_data:DUPE", provider="p", purpose="x", category="market_data",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="DUPE.pkl"))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "market_data:DUPE")
    assert any("consistency" in r for r in entry["reasons"])


def test_run_health_check_dependency_failure_cascades(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    _age_file(tmp / "upstream.json", minutes_old=500)  # far expired
    (tmp / "downstream.json").write_text(json.dumps({"a": 1}), encoding="utf-8")  # itself fresh
    registry_sandbox.register(FeedSpec(
        feed_id="cascade_upstream", provider="p", purpose="x", category="macro",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="upstream.json"))
    registry_sandbox.register(FeedSpec(
        feed_id="cascade_downstream", provider="p", purpose="x", category="macro",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="downstream.json",
        dependency_ids=("cascade_upstream",)))
    report = fm.run_health_check()
    entry = next(p for p in report["providers"] if p["feed_id"] == "cascade_downstream")
    assert entry["status"] == ps.UNAVAILABLE
    upstream_entry = next(p for p in report["providers"] if p["feed_id"] == "cascade_upstream")
    assert "cascade_downstream" in upstream_entry["affected_subsystems"]


def test_run_health_check_persists_run_summary(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(
        feed_id="simple", provider="p", purpose="x", category="computed", freshness_kind="computed",
        probe_kind="computed"))
    fm.run_health_check()
    history = fm.history_tail(10)
    assert any(row.get("kind") == "run_summary" for row in history)


def test_run_health_check_recovery_detected_across_two_runs(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    tmp = data_health_paths["tmp_path"]
    _age_file(tmp / "recover.json", minutes_old=500)
    registry_sandbox.register(FeedSpec(
        feed_id="recovering_feed", provider="p", purpose="x", category="macro",
        expected_freshness_minutes=20, probe_kind="file_mtime", probe_target="recover.json"))
    report1 = fm.run_health_check()
    entry1 = next(p for p in report1["providers"] if p["feed_id"] == "recovering_feed")
    assert entry1["status"] == ps.UNAVAILABLE

    # "recover" the feed — fresh write
    (tmp / "recover.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    fm.run_health_check()
    history = fm.history_tail(20)
    assert any(row.get("kind") == "recovery" and row.get("feed_id") == "recovering_feed" for row in history)


def test_run_health_check_registry_validation_surfaced(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(
        feed_id="broken_dep_feed", provider="p", purpose="x", category="macro",
        dependency_ids=("nonexistent_dep",)))
    report = fm.run_health_check()
    assert report["registry_validation"]["ok"] is False


def test_run_health_check_with_default_registry_never_raises(data_health_paths):
    # Uses the platform's REAL default registry (18 feeds), all pointed at
    # an empty tmp_path via data_health_paths — every feed should report
    # UNKNOWN/missing gracefully, never an exception.
    report = fm.run_health_check()
    assert report["total_feeds"] >= 15
    assert isinstance(report["providers"], list)


def test_dashboard_snapshot_matches_run_health_check_shape(data_health_paths):
    snap = fm.dashboard_snapshot()
    assert "overall_status" in snap and "providers" in snap


def test_dashboard_snapshot_never_writes_history_or_heartbeat(data_health_paths):
    # A dashboard page load (dashboard_snapshot -> persist=False) must
    # never itself count as a scan-level heartbeat or research event —
    # only alert_signals.py's actual scan (persist=True, the default)
    # should write to either file.
    fm.dashboard_snapshot()
    fm.dashboard_snapshot()
    fm.dashboard_snapshot()
    assert not fm.DATA_HEALTH_HISTORY.exists()
    assert not data_health_paths["heartbeat"].HEARTBEAT_HISTORY.exists()


def test_run_health_check_persist_true_writes_history_and_heartbeat(data_health_paths):
    fm.run_health_check(persist=True)
    assert fm.DATA_HEALTH_HISTORY.exists()
    assert data_health_paths["heartbeat"].HEARTBEAT_HISTORY.exists()


def test_run_health_check_persist_false_report_shape_matches_persist_true(data_health_paths, registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(
        feed_id="simple2", provider="p", purpose="x", category="computed",
        freshness_kind="computed", probe_kind="computed"))
    report_no_persist = fm.run_health_check(persist=False)
    assert not fm.DATA_HEALTH_HISTORY.exists()
    report_persist = fm.run_health_check(persist=True)
    assert fm.DATA_HEALTH_HISTORY.exists()
    assert report_no_persist["overall_status"] == report_persist["overall_status"]
    assert set(report_no_persist.keys()) == set(report_persist.keys())
