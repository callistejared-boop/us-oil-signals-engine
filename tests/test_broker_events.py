"""Offline tests for engine/broker/events.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker import events  # noqa: E402


def test_emit_persists_and_tail_reads_back(broker_paths):
    events.emit(events.EventType.FILL, "acct1", "XAUUSD", {"price": 2000.0}, ref="r1")
    rows = events.tail(n=5, account_id="acct1")
    assert len(rows) == 1
    assert rows[0]["event_type"] == events.EventType.FILL
    assert rows[0]["ref"] == "r1"
    assert rows[0]["payload"]["price"] == 2000.0


def test_emit_unknown_event_type_is_tagged_not_dropped(broker_paths):
    row = events.emit("not_a_real_type", "acct1", "XAUUSD", {}, ref="r1")
    assert row["event_type"].startswith("unknown:")


def test_for_ref_filters_correctly(broker_paths):
    events.emit(events.EventType.ORDER_SUBMITTED, "acct1", "XAUUSD", {}, ref="ref-A")
    events.emit(events.EventType.FILL, "acct1", "XAUUSD", {}, ref="ref-B")
    rows = events.for_ref("ref-A")
    assert len(rows) == 1
    assert rows[0]["ref"] == "ref-A"


def test_for_ref_empty_string_returns_empty(broker_paths):
    assert events.for_ref("") == []


def test_tail_filters_by_event_type(broker_paths):
    events.emit(events.EventType.FILL, "acct1", "XAUUSD", {})
    events.emit(events.EventType.CANCELLATION, "acct1", "XAUUSD", {})
    rows = events.tail(n=10, account_id="acct1", event_type=events.EventType.CANCELLATION)
    assert len(rows) == 1
    assert rows[0]["event_type"] == events.EventType.CANCELLATION


def test_all_event_types_present_in_taxonomy():
    expected = {"order_submitted", "order_accepted", "fill", "partial_fill",
               "cancellation", "rejection", "position_opened", "position_closed"}
    assert set(events.EventType.ALL) == expected


def test_emit_never_raises_on_persist_failure(broker_paths, monkeypatch):
    from engine.broker import broker_history as bh

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(bh, "record_event", _boom)
    row = events.emit(events.EventType.FILL, "acct1", "XAUUSD", {}, ref="r1")
    assert "error" in row
