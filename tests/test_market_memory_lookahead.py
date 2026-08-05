"""Dedicated look-ahead protection tests for engine/market_memory.py
(Day 7). This is its own file, not folded into test_market_memory.py,
because the Day 7 mandate calls out "look-ahead protection" as its own
required test category — historical comparisons must only use information
that would have been available at the time of each decision.
"""
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import market_memory as mm  # noqa: E402


def _rec(trade_id, opened, closed, status="win", result_r=2.0, regime_primary="Strong Bull Trend",
        session="London KZ", direction="long"):
    return mm.MemoryRecord(
        trade_id=trade_id, symbol="XAUUSD", direction=direction, opened=opened, closed=closed,
        status=status, result_r=result_r,
        regime={"primary": regime_primary, "source": "regime_history"},
        strategy="ict_smc_mast",
        confluence_summary={"agree": ["price action"], "disagree": [], "source": "confluence_history"},
        confidence_assessment={}, risk_profile={}, portfolio_context={}, session=session,
        news_context={}, outcome={"status": status, "result_r": result_r, "closed": closed},
        post_trade_review={}, data_completeness={"regime": "matched", "confluence": "matched", "confidence": "missing"},
    )


def test_open_trade_excluded_regardless_of_timestamp():
    """An open trade has no realized outcome — must never be usable as a
    historical comparison, no matter how far in the past it opened."""
    rec = _rec("t1", "2020-01-01 10:00:00", "", status="open")
    assert mm._look_ahead_safe(rec, datetime(2026, 1, 1)) is False


def test_trade_closed_after_as_of_excluded():
    """The core look-ahead guard: a trade that closed AFTER the query's
    as-of time must be excluded even though it's a real, closed trade —
    its outcome was not yet knowable at that point in history."""
    rec = _rec("t1", "2026-08-01 10:00:00", "2026-08-05 10:00:00")  # closes in the "future"
    as_of = datetime(2026, 8, 3, 0, 0, 0)
    assert mm._look_ahead_safe(rec, as_of) is False


def test_trade_closed_before_as_of_included():
    rec = _rec("t1", "2026-08-01 10:00:00", "2026-08-01 12:00:00")
    as_of = datetime(2026, 8, 3, 0, 0, 0)
    assert mm._look_ahead_safe(rec, as_of) is True


def test_trade_closed_exactly_at_as_of_excluded():
    """Strictly-before, not before-or-equal — avoids an edge case where a
    trade closing in the same instant as the query could leak its own
    outcome into its own comparison set."""
    rec = _rec("t1", "2026-08-01 10:00:00", "2026-08-03 00:00:00")
    as_of = datetime(2026, 8, 3, 0, 0, 0)
    assert mm._look_ahead_safe(rec, as_of) is False


def test_find_similar_only_returns_look_ahead_safe_candidates():
    past = _rec("past", "2026-08-01 10:00:00", "2026-08-01 12:00:00")
    future = _rec("future", "2026-08-05 10:00:00", "2026-08-06 10:00:00")  # closes after as_of
    still_open = _rec("open", "2026-08-02 10:00:00", "", status="open")
    query = mm.extract_features(past)
    as_of = datetime(2026, 8, 3, 0, 0, 0)
    matches = mm.find_similar(query, as_of, records=[past, future, still_open])
    ids = [m["record"].trade_id for m in matches]
    assert "past" in ids
    assert "future" not in ids
    assert "open" not in ids


def test_find_similar_with_string_as_of():
    """as_of may be passed as an ISO string (the live pipeline passes a
    pd.Timestamp, str(), or datetime depending on call site) — must not
    require the caller to pre-parse it."""
    past = _rec("past", "2026-08-01 10:00:00", "2026-08-01 12:00:00")
    query = mm.extract_features(past)
    matches = mm.find_similar(query, "2026-08-03T00:00:00", records=[past])
    assert len(matches) == 1


def test_historical_context_never_uses_future_trades():
    """End-to-end guard: historical_context() must produce a comparable
    count that excludes any trade closing after as_of, even when many
    otherwise-identical future trades exist."""
    as_of = datetime(2026, 8, 3, 0, 0, 0)
    past_trades = [_rec(f"past{i}", "2026-08-01 10:00:00", "2026-08-01 12:00:00") for i in range(5)]
    future_trades = [_rec(f"future{i}", "2026-08-10 10:00:00", "2026-08-10 12:00:00") for i in range(50)]
    query = mm.extract_features(past_trades[0])
    ctx = mm.historical_context(query, as_of, records=past_trades + future_trades)
    assert ctx["comparable_count"] == 5   # the 50 future trades must never count


def test_look_ahead_guard_never_raises_on_garbage_timestamps():
    rec = _rec("t1", "not-a-date", "also-not-a-date")
    assert mm._look_ahead_safe(rec, "still not a date") is False
