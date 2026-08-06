"""Tests for engine/scan_latency.py (V2.2 Priority 1 Item 2). ScanTimer
accumulates cumulative ms per stage across a scan - most stages fire once
per symbol or conditionally on a fill, never a single start/end pair - so
these tests exercise repeated/absent stage calls, not just one-shot timing.
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.scan_latency import ScanTimer  # noqa: E402


def test_single_stage_call_records_positive_elapsed():
    t = ScanTimer()
    with t.stage("regime"):
        time.sleep(0.005)
    snap = t.snapshot()
    assert snap["regime"] > 0
    assert t.call_counts()["regime"] == 1


def test_repeated_stage_calls_accumulate_cumulatively():
    t = ScanTimer()
    with t.stage("market_fetch"):
        time.sleep(0.005)
    with t.stage("market_fetch"):
        time.sleep(0.005)
    with t.stage("market_fetch"):
        time.sleep(0.005)
    snap = t.snapshot()
    counts = t.call_counts()
    assert counts["market_fetch"] == 3
    # cumulative across 3 calls should be roughly >= sum of the three sleeps,
    # not just the last call's elapsed time.
    assert snap["market_fetch"] >= 13.0


def test_stage_never_called_is_absent_not_zero():
    t = ScanTimer()
    with t.stage("regime"):
        pass
    snap = t.snapshot()
    assert "execution_simulation" not in snap
    assert "paper_broker" not in snap


def test_multiple_distinct_stages_tracked_independently():
    t = ScanTimer()
    with t.stage("confluence"):
        time.sleep(0.002)
    with t.stage("confidence"):
        time.sleep(0.004)
    snap = t.snapshot()
    assert snap["confluence"] > 0
    assert snap["confidence"] > 0
    assert snap["confluence"] != snap["confidence"]


def test_exception_inside_stage_still_propagates_and_records_elapsed():
    t = ScanTimer()
    try:
        with t.stage("origination"):
            raise ValueError("boom")
    except ValueError:
        pass
    else:
        raise AssertionError("exception should have propagated")
    # the timer's own bookkeeping (finally block) must still have run
    assert t.call_counts()["origination"] == 1
    assert t.snapshot()["origination"] >= 0


def test_total_ms_grows_across_scan():
    t = ScanTimer()
    first = t.total_ms()
    time.sleep(0.005)
    second = t.total_ms()
    assert second > first


def test_snapshot_is_a_copy_not_live_reference():
    t = ScanTimer()
    with t.stage("memory"):
        pass
    snap = t.snapshot()
    snap["memory"] = 999999.0
    assert t.snapshot()["memory"] != 999999.0
