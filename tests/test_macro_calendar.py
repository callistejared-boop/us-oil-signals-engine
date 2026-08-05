"""Offline tests for engine/macro_calendar.py (Day 11). Every test passes
an explicit `raw_events=` list (the same override convention this
codebase already uses throughout — engine.risk_sentiment.alignment's `d=`,
engine.edge_decay_monitor's `rows=`) so nothing here ever calls
engine.news_guard.fetch_events() / hits the real network.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_calendar as mcal  # noqa: E402

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _ev(minutes_from_now, title):
    return (NOW + timedelta(minutes=minutes_from_now), title)


def test_classify_central_bank():
    events = [_ev(60, "USD FOMC Interest Rate Decision")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert out[0]["category"] == "central_bank"
    assert out[0]["importance"] == "high"


def test_classify_inflation():
    events = [_ev(60, "USD CPI m/m")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert out[0]["category"] == "inflation"


def test_classify_employment():
    events = [_ev(60, "USD Non-Farm Employment Change")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert out[0]["category"] == "employment"


def test_classify_unknown_falls_back_to_other():
    events = [_ev(60, "USD Some Totally Novel Release")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert out[0]["category"] == "other"
    assert out[0]["importance"] == "medium"


def test_timing_buckets():
    events = [_ev(-10, "USD Past Event"), _ev(30, "USD Imminent Event"),
             _ev(600, "USD Today Event"), _ev(3000, "USD Upcoming Event")]
    out = mcal.get_events(now=NOW, raw_events=events)
    timing = {e["title"]: e["timing"] for e in out}
    assert timing["USD Past Event"] == "past"
    assert timing["USD Imminent Event"] == "imminent"
    assert timing["USD Today Event"] == "today"
    assert timing["USD Upcoming Event"] == "upcoming"


def test_events_sorted_by_time():
    events = [_ev(120, "B"), _ev(10, "A"), _ev(500, "C")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert [e["title"] for e in out] == ["A", "B", "C"]


def test_affected_assets_includes_all_four_symbols():
    events = [_ev(60, "USD CPI m/m")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert set(out[0]["affected_assets"]) == {"XAUUSD", "EURUSD", "WTIUSD", "BTCUSD"}


def test_upcoming_excludes_past_events():
    events = [_ev(-10, "USD Past"), _ev(60, "USD Future")]
    out = mcal.upcoming(now=NOW, raw_events=events)
    assert len(out) == 1 and out[0]["title"] == "USD Future"


def test_upcoming_filters_by_category():
    events = [_ev(60, "USD CPI m/m"), _ev(120, "USD Retail Sales")]
    out = mcal.upcoming(category="inflation", now=NOW, raw_events=events)
    assert len(out) == 1 and out[0]["category"] == "inflation"


def test_upcoming_within_hours_window():
    events = [_ev(30, "USD Near"), _ev(600, "USD Far")]
    out = mcal.upcoming(now=NOW, raw_events=events, within_hours=1)
    assert len(out) == 1 and out[0]["title"] == "USD Near"


def test_next_event_returns_earliest_upcoming():
    events = [_ev(120, "USD B"), _ev(-10, "USD Past"), _ev(10, "USD A")]
    nxt = mcal.next_event(now=NOW, raw_events=events)
    assert nxt["title"] == "USD A"


def test_next_event_none_when_nothing_upcoming():
    events = [_ev(-10, "USD Past Only")]
    assert mcal.next_event(now=NOW, raw_events=events) is None


def test_summary_counts_by_category():
    events = [_ev(10, "USD CPI m/m"), _ev(20, "USD PPI m/m"), _ev(30, "USD Retail Sales")]
    s = mcal.summary(now=NOW, raw_events=events)
    assert s["n_events_this_week"] == 3
    assert s["by_category"]["inflation"] == 2
    assert s["by_category"]["growth"] == 1
    assert s["next_event"]["title"] == "USD CPI m/m"


def test_summary_never_raises_on_empty_events():
    s = mcal.summary(now=NOW, raw_events=[])
    assert s["n_events_this_week"] == 0
    assert s["next_event"] is None


def test_get_events_never_raises_when_fetch_fails(monkeypatch):
    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(mcal, "_fetch_raw", boom)
    assert mcal.get_events(now=NOW) == []


def test_line_no_upcoming_events():
    assert "no upcoming" in mcal.line(now=NOW, raw_events=[]).lower()


def test_line_with_upcoming_event():
    events = [_ev(90, "USD FOMC Interest Rate Decision")]
    out = mcal.line(now=NOW, raw_events=events)
    assert "central_bank" in out and "FOMC" in out


def test_malformed_event_entry_skipped_not_raised():
    events = [_ev(60, "USD CPI m/m"), ("not-a-datetime", "USD Bad Entry")]
    out = mcal.get_events(now=NOW, raw_events=events)
    assert len(out) == 1 and out[0]["title"] == "USD CPI m/m"
