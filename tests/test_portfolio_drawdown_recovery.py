"""Regression tests for V2.2 Priority 2 Item 7 (Task #237): the portfolio
drawdown-protection stand-down (engine/portfolio_risk.py::DRAWDOWN_PROTECTION)
must never be able to permanently self-lock.

Root cause found live 2026-08-10: portfolio_drawdown_r()'s trailing 30-trade
window only ever advances when a NEW trade closes. But once the stand-down
trips (dd >= portfolio_max_drawdown_r), it blocks every new trade from
opening. With zero open positions, the live account was frozen at a 12.0R/
30-trade reading for 18 consecutive days with no possible path back to
compliant.

Fix: portfolio_drawdown_r() gained an optional `max_age_days` (+ `as_of`)
staleness ceiling. Any closed trade older than that many calendar days is
excluded from the window, independent of trade count. This gives the
window a second, time-based way to shrink purely from the passage of time.
Wired through engine/config.py's `portfolio_drawdown_max_age_days` (default
30.0) and engine/portfolio_risk.py::evaluate().

See portfolio_drawdown_r()'s own docstring for the full narrative.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import portfolio_risk as pr  # noqa: E402
from engine import config  # noqa: E402


def _row(result_r, closed_iso, symbol="XAUUSD", status=None):
    if status is None:
        status = "win" if result_r >= 0 else "loss"
    return {"status": status, "result_r": result_r, "closed": closed_iso, "symbol": symbol}


class _Settings:
    portfolio_equity = 10000.0
    portfolio_risk_mode = "block"
    portfolio_max_risk_pct = 6.0
    portfolio_day_stop_r = 2.0
    portfolio_max_drawdown_r = 6.0
    portfolio_drawdown_max_age_days = 30.0
    portfolio_max_directional = 2
    correlation_high_threshold = 0.75
    correlation_window_days = 30


# ---------------------------------------------------------------------------
# 1. Backward compatibility: no max_age_days supplied at all -> identical to
#    pre-fix behavior (pure trade-count window, no time filtering).
# ---------------------------------------------------------------------------

def test_no_max_age_days_matches_pre_fix_pure_count_behavior():
    # 10 wins then 7 losses, all with ancient timestamps -> pre-fix code
    # would still compute the full 7R drawdown since it never looked at age.
    rows = []
    for i in range(10):
        rows.append(_row(1.0, f"2020-01-01T{i % 23:02d}:00:00", symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(7):
        rows.append(_row(-1.0, f"2020-01-02T{i % 23:02d}:00:00", symbol="BTCUSD"))
    dd = pr.portfolio_drawdown_r(rows, window=30)  # max_age_days defaults to None
    assert dd == 7.0


# ---------------------------------------------------------------------------
# 2. Normal operation (recent trades) is unaffected by the new ceiling.
# ---------------------------------------------------------------------------

def test_recent_trades_unaffected_by_staleness_ceiling():
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(10):
        ts = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(7):
        ts = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(-1.0, ts, symbol="BTCUSD"))
    dd_uncapped = pr.portfolio_drawdown_r(rows, window=30)
    dd_capped = pr.portfolio_drawdown_r(rows, window=30, max_age_days=30.0, as_of=now)
    assert dd_uncapped == dd_capped == 7.0


# ---------------------------------------------------------------------------
# 3. Fully stale window -> dd recovers all the way to 0, unblocking entries.
# ---------------------------------------------------------------------------

def test_fully_stale_window_recovers_to_zero():
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(10):
        ts = (now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(7):
        ts = (now - timedelta(days=38)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(-1.0, ts, symbol="BTCUSD"))
    dd = pr.portfolio_drawdown_r(rows, window=30, max_age_days=30.0, as_of=now)
    assert dd == 0.0


# ---------------------------------------------------------------------------
# 4. Partially stale window -> drawdown computed only over the non-stale
#    subset (i.e. the fresh trades), not the full 30-trade set.
# ---------------------------------------------------------------------------

def test_partially_stale_window_computes_over_fresh_subset_only():
    """Stale rows carry their OWN internal drawdown (5 wins then 5 losses,
    35 days old -> +5 peak then back to 0 -> dd=5 mid-sequence). The fresh
    rows that follow (3 wins, 5 days old) are pure gains with zero internal
    drawdown. Uncapped, the run's peak (5) from the stale segment is still
    in effect when the stale losses hit bottom, so the max-drawdown-anywhere
    computation reports 5.0 even though the sequence ends higher. Capped to
    only the fresh subset, the peak resets to 0 and the 3 wins never dip,
    so drawdown is 0.0. This is the actual mechanism by which the staleness
    ceiling can shrink a reported drawdown even when window=30 doesn't
    change (i.e. below the 30-trade cap already) -- it only shows up once
    old, no-longer-representative history ages out."""
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    # Stale segment (35 days old): 5 wins then 5 losses -> internal dd=5.
    for i in range(5):
        ts = (now - timedelta(days=35, hours=10 - i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(5):
        ts = (now - timedelta(days=35, hours=5 - i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(-1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    # Fresh segment (5 days old): 3 pure wins, no dip.
    for i in range(3):
        ts = (now - timedelta(days=5, hours=3 - i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="BTCUSD"))
    dd_uncapped = pr.portfolio_drawdown_r(rows, window=30)
    assert dd_uncapped == 5.0
    dd_capped = pr.portfolio_drawdown_r(rows, window=30, max_age_days=30.0, as_of=now)
    assert dd_capped == 0.0


# ---------------------------------------------------------------------------
# 5. The exact live production scenario: 30 closed trades, all >18 calendar
#    days old, trailing dd = 12.0R (verified independently against the real
#    trades.json during live diagnosis). Confirms the fix actually unlocks
#    it once the trades cross the staleness threshold, and confirms it is
#    STILL blocked while they're within it (no false-positive unlock).
# ---------------------------------------------------------------------------

def test_live_deadlock_scenario_blocked_within_threshold_then_recovers():
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    trade_day = now - timedelta(days=18)
    rows = []
    for i in range(11):
        ts = (trade_day - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(12):
        ts = (trade_day + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(-1.0, ts, symbol="BTCUSD"))
    # Peak-to-trough on 11 wins then 12 losses: peak +11, trough -1 -> dd = 12.0
    dd_uncapped = pr.portfolio_drawdown_r(rows, window=30)
    assert dd_uncapped == 12.0

    # Still within the 30-day ceiling (18 days old < 30) -> correctly still blocked.
    dd_still_blocked = pr.portfolio_drawdown_r(rows, window=30, max_age_days=30.0, as_of=now)
    assert dd_still_blocked == 12.0

    # 13 more days pass (cutoff now = trade_day+1d, past the last (trade_day+11h) row).
    later = now + timedelta(days=13)
    dd_recovered = pr.portfolio_drawdown_r(rows, window=30, max_age_days=30.0, as_of=later)
    assert dd_recovered == 0.0


# ---------------------------------------------------------------------------
# 6. Config wiring: field exists with the documented default and is in the
#    env-override allowlist.
# ---------------------------------------------------------------------------

def test_config_field_default_and_allowlist():
    cfg = config.Settings()
    assert cfg.portfolio_drawdown_max_age_days == 30.0
    assert "portfolio_drawdown_max_age_days" in config._FIELDS


# ---------------------------------------------------------------------------
# 7. evaluate() wiring: the resolved ceiling is surfaced in the detail dict
#    (so it's visible in decision snapshots / dashboards, not just internal).
# ---------------------------------------------------------------------------

def test_evaluate_surfaces_resolved_max_age_days_in_detail():
    v = pr.evaluate("XAUUSD", "long", 2000.0, 1990.0, settings=_Settings(), rows=[])
    assert v["detail"]["portfolio_drawdown_max_age_days"] == 30.0


def test_evaluate_respects_custom_max_age_days_from_settings():
    class _ShortWindowSettings(_Settings):
        portfolio_drawdown_max_age_days = 5.0

    now = datetime.now(timezone.utc)
    trade_day = now - timedelta(days=10)  # older than the custom 5-day ceiling
    rows = []
    for i in range(11):
        ts = (trade_day - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(1.0, ts, symbol="XAUUSD" if i % 2 else "WTIUSD"))
    for i in range(12):
        ts = (trade_day + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(_row(-1.0, ts, symbol="BTCUSD"))
    v = pr.evaluate("XAUUSD", "long", 2000.0, 1990.0, settings=_ShortWindowSettings(), rows=rows)
    assert v["detail"]["portfolio_drawdown_max_age_days"] == 5.0
    assert v["detail"]["portfolio_drawdown_r_30"] == 0.0
    assert v["allow"] is True
