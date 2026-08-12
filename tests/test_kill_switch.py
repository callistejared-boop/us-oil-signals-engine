"""Offline tests for engine/kill_switch.py (V2.2 Priority 2, rescoped:
stateless stand-down status reporter, not a stateful kill-switch object).

Every test monkeypatches the same underlying functions the live pipeline
already calls (news_guard.evaluate, risk_guard.evaluate,
risk_guard.today_realized_r, portfolio_risk.portfolio_drawdown_r) so these
tests prove kill_switch.py's reporting matches what those functions
actually return, not just that kill_switch.py is internally consistent.
No new threshold logic is being tested here because none exists in
kill_switch.py -- it is pure passthrough/aggregation."""
import pathlib
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import kill_switch as ks  # noqa: E402
from engine import portfolio_risk as pr  # noqa: E402


def _settings(**overrides):
    d = dict(portfolio_day_stop_r=2.0, portfolio_max_drawdown_r=6.0,
            portfolio_drawdown_max_age_days=30.0)
    d.update(overrides)
    return SimpleNamespace(**d)


# --------------------------------------------------------------------------
# StandDownStatus dataclass
# --------------------------------------------------------------------------

def test_stand_down_status_basic_construction():
    s = ks.StandDownStatus(name="x", engaged=True, scope="platform", reason="r")
    assert s.engaged is True
    assert s.category is None
    assert s.detail == {}


# --------------------------------------------------------------------------
# news_blackout_status
# --------------------------------------------------------------------------

def test_news_blackout_status_engaged(monkeypatch):
    monkeypatch.setattr(ks.news_guard, "evaluate",
                        lambda now=None: {"ok": True, "blackout": True,
                                          "active": ("FOMC Rate Decision", 12),
                                          "next": None, "next_in_min": None, "note": ""})
    s = ks.news_blackout_status()
    assert s.engaged is True
    assert s.scope == "platform"
    assert s.category == "news_blackout"
    assert "FOMC Rate Decision" in s.reason


def test_news_blackout_status_clear(monkeypatch):
    monkeypatch.setattr(ks.news_guard, "evaluate",
                        lambda now=None: {"ok": True, "blackout": False, "active": None,
                                          "next": "CPI", "next_in_min": 240, "note": ""})
    s = ks.news_blackout_status()
    assert s.engaged is False
    assert s.category is None


def test_news_blackout_status_fail_open_surfaces_note(monkeypatch):
    """news_guard.evaluate() fails open (ok=False, blackout=False) on a
    fetch error -- kill_switch must not upgrade that into an engaged
    stand-down; it should just surface the note for visibility."""
    monkeypatch.setattr(ks.news_guard, "evaluate",
                        lambda now=None: {"ok": False, "blackout": False, "active": None,
                                          "next": None, "next_in_min": None,
                                          "note": "calendar fetch failed"})
    s = ks.news_blackout_status()
    assert s.engaged is False
    assert s.reason == "calendar fetch failed"


# --------------------------------------------------------------------------
# risk_guard_status
# --------------------------------------------------------------------------

def test_risk_guard_status_locked(monkeypatch):
    monkeypatch.setattr(ks.risk_guard, "evaluate",
                        lambda sym: {"locked": True, "reason": "DAILY LOSS LIMIT (-2.0R)"})
    s = ks.risk_guard_status("WTIUSD")
    assert s.engaged is True
    assert s.scope == "symbol"
    assert s.category == "risk_lock"
    assert "DAILY LOSS" in s.reason


def test_risk_guard_status_clear(monkeypatch):
    monkeypatch.setattr(ks.risk_guard, "evaluate", lambda sym: {"locked": False, "reason": ""})
    s = ks.risk_guard_status("WTIUSD")
    assert s.engaged is False
    assert s.category is None


# --------------------------------------------------------------------------
# drawdown_status -- mirrors portfolio_risk.evaluate() checks #4 and #5
# --------------------------------------------------------------------------

def test_drawdown_status_clear_when_both_checks_pass(monkeypatch):
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: -0.5)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 1.2)
    s = ks.drawdown_status(settings=_settings(), rows=[])
    assert s.engaged is False
    assert s.category is None
    assert s.detail["portfolio_day_r"] == -0.5
    assert s.detail["portfolio_drawdown_r_30"] == 1.2


def test_drawdown_status_engaged_via_day_stop(monkeypatch):
    """Check #4: portfolio-wide daily loss stop -- today_realized_r() at or
    beyond -day_stop_r engages, independent of the trailing drawdown
    reading."""
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: -2.5)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 0.0)
    s = ks.drawdown_status(settings=_settings(portfolio_day_stop_r=2.0), rows=[])
    assert s.engaged is True
    assert s.category == pr.DRAWDOWN_PROTECTION
    assert "PORTFOLIO DAY STOP" in s.reason
    assert s.source == "engine.risk_guard.today_realized_r"


def test_drawdown_status_engaged_via_trailing_drawdown(monkeypatch):
    """Check #5: trailing 30-trade drawdown cap -- engages independent of
    today's realized R, once the day-stop check has already passed."""
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 7.5)
    s = ks.drawdown_status(settings=_settings(portfolio_max_drawdown_r=6.0), rows=[])
    assert s.engaged is True
    assert s.category == pr.DRAWDOWN_PROTECTION
    assert "drawdown" in s.reason.lower()
    assert s.source == "engine.portfolio_risk.portfolio_drawdown_r"


def test_drawdown_status_day_stop_checked_before_trailing_drawdown(monkeypatch):
    """When BOTH conditions would engage, the day-stop check must win (it's
    check #4, checked first in portfolio_risk.evaluate() -- kill_switch.py
    mirrors that ordering so the reported reason matches what the live
    gate would have reported)."""
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: -3.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 9.0)
    s = ks.drawdown_status(settings=_settings(), rows=[])
    assert "PORTFOLIO DAY STOP" in s.reason


def test_drawdown_status_passes_configured_thresholds_through(monkeypatch):
    """Confirms settings attributes are actually read, not hardcoded --
    same attribute names portfolio_risk.evaluate() reads
    (portfolio_day_stop_r, portfolio_max_drawdown_r,
    portfolio_drawdown_max_age_days)."""
    captured = {}

    def _fake_dd(closed_rows, window=30, max_age_days=None):
        captured["max_age_days"] = max_age_days
        return 0.0
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r", _fake_dd)
    ks.drawdown_status(settings=_settings(portfolio_drawdown_max_age_days=45.0), rows=[])
    assert captured["max_age_days"] == 45.0


def test_drawdown_status_defaults_settings_via_config_load(monkeypatch):
    """settings=None must fall back to config.load(), exactly like
    portfolio_risk.evaluate() does -- not some separate default set."""
    from engine import config
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 0.0)
    real_settings = config.load()
    s = ks.drawdown_status(settings=None, rows=[])
    assert s.detail["day_stop_r"] == real_settings.portfolio_day_stop_r


def test_drawdown_status_filters_rows_to_closed_only(monkeypatch):
    """Only win/loss/scratch rows should reach portfolio_drawdown_r() --
    exactly the same filter portfolio_risk.evaluate() applies before
    calling it (open/pending rows excluded)."""
    captured = {}

    def _fake_dd(closed_rows, window=30, max_age_days=None):
        captured["rows"] = closed_rows
        return 0.0
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r", _fake_dd)
    rows = [{"status": "open"}, {"status": "win"}, {"status": "pending"},
           {"status": "loss"}, {"status": "scratch"}]
    ks.drawdown_status(settings=_settings(), rows=rows)
    statuses = {r["status"] for r in captured["rows"]}
    assert statuses == {"win", "loss", "scratch"}


def test_drawdown_status_defaults_rows_via_shared_rows_reader(monkeypatch):
    """rows=None must fall back to portfolio_risk._rows() -- the same
    salvage-on-corruption reader risk_guard.py and portfolio_risk.py both
    already use, not a separate/new loader."""
    sentinel = [{"status": "win", "result_r": 1.0, "closed": "2026-01-01T00:00:00"}]
    monkeypatch.setattr(ks.pr, "_rows", lambda: sentinel)
    monkeypatch.setattr(ks.risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(ks.pr, "portfolio_drawdown_r",
                        lambda closed_rows, window=30, max_age_days=None: 0.0)
    ks.drawdown_status(settings=_settings(), rows=None)  # should not raise


# --------------------------------------------------------------------------
# current_stand_downs / any_engaged
# --------------------------------------------------------------------------

def test_current_stand_downs_without_symbol_omits_risk_guard(monkeypatch):
    monkeypatch.setattr(ks, "news_blackout_status",
                        lambda now=None: ks.StandDownStatus("news_blackout", False, "platform"))
    monkeypatch.setattr(ks, "drawdown_status",
                        lambda settings=None, rows=None: ks.StandDownStatus(
                            "drawdown_protection", False, "portfolio"))
    out = ks.current_stand_downs(symbol=None)
    names = {s.name for s in out}
    assert names == {"news_blackout", "drawdown_protection"}


def test_current_stand_downs_with_symbol_includes_risk_guard(monkeypatch):
    monkeypatch.setattr(ks, "news_blackout_status",
                        lambda now=None: ks.StandDownStatus("news_blackout", False, "platform"))
    monkeypatch.setattr(ks, "drawdown_status",
                        lambda settings=None, rows=None: ks.StandDownStatus(
                            "drawdown_protection", False, "portfolio"))
    monkeypatch.setattr(ks, "risk_guard_status",
                        lambda symbol: ks.StandDownStatus("risk_guard_day_stop", True, "symbol"))
    out = ks.current_stand_downs(symbol="WTIUSD")
    names = {s.name for s in out}
    assert names == {"news_blackout", "drawdown_protection", "risk_guard_day_stop"}


def test_any_engaged_true_when_one_stand_down_is_engaged(monkeypatch):
    monkeypatch.setattr(ks, "current_stand_downs", lambda symbol=None, settings=None,
                        rows=None, now=None: [
                            ks.StandDownStatus("a", False, "platform"),
                            ks.StandDownStatus("b", True, "portfolio"),
                        ])
    assert ks.any_engaged() is True


def test_any_engaged_false_when_none_engaged(monkeypatch):
    monkeypatch.setattr(ks, "current_stand_downs", lambda symbol=None, settings=None,
                        rows=None, now=None: [
                            ks.StandDownStatus("a", False, "platform"),
                            ks.StandDownStatus("b", False, "portfolio"),
                        ])
    assert ks.any_engaged() is False


# --------------------------------------------------------------------------
# Real-function integration test -- no mocking, exercises the actual wired
# functions end-to-end (mirrors decision_gate.py's own integration test
# pattern).
# --------------------------------------------------------------------------

def test_current_stand_downs_real_functions_end_to_end():
    """No mocking at all: exercises the real news_guard.evaluate(),
    risk_guard.evaluate(), risk_guard.today_realized_r(), and
    portfolio_risk.portfolio_drawdown_r() against a small synthetic row
    set, confirming the module actually wires together and returns
    well-formed StandDownStatus objects (not just that mocks were called
    correctly)."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [{"status": "win", "result_r": 1.0, "closed": f"{today}T09:00:00",
            "symbol": "WTIUSD"}]
    out = ks.current_stand_downs(symbol="WTIUSD", rows=rows)
    assert len(out) == 3
    names = {s.name for s in out}
    assert names == {"news_blackout", "drawdown_protection", "risk_guard_day_stop"}
    for s in out:
        assert isinstance(s.engaged, bool)
        assert s.scope in ("symbol", "portfolio", "platform")
