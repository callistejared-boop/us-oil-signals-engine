"""Day 15: tests for alert_signals.write_scan_status() — the durable,
cache-backed scan-outcome record introduced to fix the 11+ day silent
heartbeat gap (see DAY15_IMPLEMENTATION_REPORT.md)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402


def test_write_scan_status_all_ok_is_not_an_outage(tmp_path, monkeypatch):
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", tmp_path / "heartbeat_status.json")
    status = {
        "XAUUSD": {"fetch_ok": True, "error": None},
        "WTIUSD": {"fetch_ok": True, "error": None},
    }
    record = als.write_scan_status(status, 1.23)
    assert record["total_data_outage"] is False
    assert record["n_symbols"] == 2
    assert record["n_fetch_ok"] == 2


def test_write_scan_status_all_failed_is_an_outage(tmp_path, monkeypatch):
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", tmp_path / "heartbeat_status.json")
    status = {
        "XAUUSD": {"fetch_ok": False, "error": "yfinance empty for GC=F"},
        "WTIUSD": {"fetch_ok": False, "error": "yfinance empty for CL=F"},
        "BTCUSD": {"fetch_ok": False, "error": "yfinance empty for BTC-USD"},
    }
    record = als.write_scan_status(status, 2.5)
    assert record["total_data_outage"] is True
    assert record["n_fetch_ok"] == 0


def test_write_scan_status_partial_failure_is_not_a_total_outage(tmp_path, monkeypatch):
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", tmp_path / "heartbeat_status.json")
    status = {
        "XAUUSD": {"fetch_ok": True, "error": None},
        "WTIUSD": {"fetch_ok": False, "error": "timeout"},
    }
    record = als.write_scan_status(status, 1.0)
    assert record["total_data_outage"] is False


def test_write_scan_status_empty_symbol_list_is_not_an_outage(tmp_path, monkeypatch):
    # No symbols configured at all should never be misreported as an
    # outage — there's nothing to have failed.
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", tmp_path / "heartbeat_status.json")
    record = als.write_scan_status({}, 0.5)
    assert record["total_data_outage"] is False
    assert record["n_symbols"] == 0


def test_write_scan_status_persists_readable_json(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat_status.json"
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", path)
    als.write_scan_status({"XAUUSD": {"fetch_ok": True, "error": None}}, 1.0)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["n_symbols"] == 1
    assert "ts" in on_disk


def test_write_scan_status_never_raises_on_unwritable_path(monkeypatch):
    # Point at a path whose parent can't be created (a file, not a dir) —
    # write_text/mkdir will raise internally; write_scan_status must
    # swallow it and still return a usable record, same fail-safe
    # discipline as the rest of this file.
    bad_parent = pathlib.Path(__file__)  # a real file, not a directory
    monkeypatch.setattr(als, "SCAN_STATUS_PATH", bad_parent / "nested" / "heartbeat_status.json")
    record = als.write_scan_status({"XAUUSD": {"fetch_ok": True, "error": None}}, 1.0)
    assert record["total_data_outage"] is False  # still computed correctly despite the write failure
