"""Offline tests for engine/decision_gate.py (V2.2 Priority 2: Master
Decision Gate). Every test monkeypatches the SAME functions
alert_signals.py itself calls (risk_guard.evaluate, portfolio_risk.evaluate,
apply_regime_gate is exercised directly, unmocked, since it's already a
pure function with its own dedicated test file) so these tests prove
decision_gate.py's classification matches alert_signals.py's actual inline
behavior for every branch, not just that decision_gate.py is internally
consistent."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_gate as dg  # noqa: E402
from engine import portfolio_risk as pr  # noqa: E402
from engine import explainability_engine as expl  # noqa: E402


class _CR:
    """Minimal confluence-read stand-in — only the attributes
    decision_gate.py actually reads."""
    def __init__(self, final_tier="confirmed", score=80, disagree=None):
        self.final_tier = final_tier
        self.score = score
        self.disagree = disagree or []


def _allow_pr(**overrides):
    v = {"allow": True, "would_block": False, "mode": "block", "category": None,
        "reason": "", "detail": {}, "generated": ""}
    v.update(overrides)
    return v


def _reject_pr(category, reason="rejected", **overrides):
    v = {"allow": False, "would_block": True, "mode": "block", "category": category,
        "reason": reason, "detail": {}, "generated": ""}
    v.update(overrides)
    return v


def _no_lock():
    return {"locked": False, "reason": "", "day_r": 0.0}


def _locked(reason="DAILY LOSS limit hit"):
    return {"locked": True, "reason": reason, "day_r": -2.0}


# --------------------------------------------------------------- GateVerdict

def test_gate_verdict_rejects_unknown_action():
    with pytest.raises(ValueError):
        dg.GateVerdict(action="not_a_real_action", stage="entry")


def test_gate_verdict_passed_property():
    assert dg.GateVerdict(dg.ENTER, "entry").passed is True
    assert dg.GateVerdict(dg.WAIT, "origination").passed is True
    assert dg.GateVerdict(dg.HOLD, "origination").passed is False
    assert dg.GateVerdict(dg.REJECT, "entry").passed is False
    assert dg.GateVerdict(dg.BLOCKED, "entry").passed is False
    assert dg.GateVerdict(dg.STAND_DOWN, "entry").passed is False


# ------------------------------------------------------- origination gate

def test_origination_blocked_on_news_blackout(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={}, cr=_CR(),
        news_state={"blackout": True})
    assert v.action == dg.BLOCKED
    assert v.category == expl.NEWS_BLACKOUT


def test_origination_blocked_on_risk_guard_lock(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _locked("DAILY LOSS limit hit"))
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={}, cr=_CR(),
        news_state={"blackout": False})
    assert v.action == dg.BLOCKED
    assert v.category == expl.RISK_LOCK
    assert "DAILY LOSS" in v.reason


def test_origination_held_on_regime_block_mode(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0,
        mkt_regime={"quality_score": 10, "primary": "Range", "compatibility": "avoid"},
        cr=_CR(), news_state={"blackout": False},
        regime_mode="block", regime_min_quality=30)
    assert v.action == dg.HOLD
    assert v.category == pr.MARKET_REGIME_UNSUITABLE


def test_origination_not_held_on_regime_advisory_mode_even_at_zero_quality(monkeypatch):
    """Advisory (the platform's actual default) never blocks, regardless
    of quality_score — matches apply_regime_gate's own tested behavior."""
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0,
        mkt_regime={"quality_score": 0, "primary": "Range", "compatibility": "avoid"},
        cr=_CR(), news_state={"blackout": False}, regime_mode="advisory")
    assert v.action == dg.WAIT


def test_origination_held_on_weak_confluence(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90},
        cr=_CR(final_tier="watch", score=40), news_state={"blackout": False})
    assert v.action == dg.HOLD
    assert v.category == expl.WEAK_EVIDENCE
    assert "watch" in v.reason and "40" in v.reason


def test_origination_held_on_none_confluence_result(monkeypatch):
    """cr=None (confluence engine errored) must classify the same as an
    unconfirmed tier, not raise — mirrors alert_signals.py's own
    `cr = None` fallback on a confluence exception."""
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90},
        cr=None, news_state={"blackout": False})
    assert v.action == dg.HOLD
    assert v.category == expl.WEAK_EVIDENCE


def test_origination_rejected_on_portfolio_risk_category(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate",
                        lambda *a, **k: _reject_pr(pr.CORRELATION_TOO_HIGH, "too correlated"))
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90}, cr=_CR(),
        news_state={"blackout": False})
    assert v.action == dg.REJECT
    assert v.category == pr.CORRELATION_TOO_HIGH
    assert v.reason == "too correlated"


def test_origination_drawdown_protection_maps_to_stand_down(monkeypatch):
    """DRAWDOWN_PROTECTION covers portfolio_risk.evaluate()'s checks #4
    (portfolio-wide day-stop) and #5 (trailing drawdown cap) -- both pure
    functions of portfolio state, independent of this candidate's own
    direction. A genuine platform-wide stand-down."""
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate",
                        lambda *a, **k: _reject_pr(pr.DRAWDOWN_PROTECTION))
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90}, cr=_CR(),
        news_state={"blackout": False})
    assert v.action == dg.STAND_DOWN
    assert v.category == pr.DRAWDOWN_PROTECTION


def test_origination_trade_frequency_control_maps_to_reject_not_stand_down(monkeypatch):
    """Regression: TRADE_FREQUENCY_CONTROL is portfolio_risk.evaluate()'s
    check #2 ("simultaneous directional exposure",
    `dirs[direction] + 1 > max_dir`) -- it depends on THIS candidate's
    own direction, so a same-symbol candidate proposed in the opposite
    direction at the same instant would NOT get this rejection. That
    makes it a per-candidate REJECT, not a platform-wide STAND_DOWN,
    despite the category name sounding stand-down-like. Caught during
    review of decision_gate.py's own STAND_DOWN_CATEGORIES set, which
    originally (incorrectly) included this category -- fixed before it
    was ever wired into anything."""
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate",
                        lambda *a, **k: _reject_pr(pr.TRADE_FREQUENCY_CONTROL))
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90}, cr=_CR(),
        news_state={"blackout": False})
    assert v.action == dg.REJECT
    assert v.category == pr.TRADE_FREQUENCY_CONTROL


def test_origination_waits_when_everything_passes(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={"quality_score": 90}, cr=_CR(),
        news_state={"blackout": False})
    assert v.action == dg.WAIT
    assert v.category is None
    assert v.passed is True


def test_origination_short_circuits_before_portfolio_risk_on_blackout(monkeypatch):
    """Blackout must short-circuit before risk_guard/portfolio_risk are
    even consulted -- same ordering as alert_signals.py's Stage-1
    (`if blackout: ...; continue` runs before risk_guard.evaluate())."""
    calls = {"risk_guard": 0, "pr": 0}

    def _rg(sym):
        calls["risk_guard"] += 1
        return _no_lock()

    def _pr(*a, **k):
        calls["pr"] += 1
        return _allow_pr()

    monkeypatch.setattr(dg.risk_guard, "evaluate", _rg)
    monkeypatch.setattr(dg.pr, "evaluate", _pr)
    v = dg.evaluate_origination_gate(
        "XAUUSD", "long", 2000.0, 1990.0, mkt_regime={}, cr=_CR(),
        news_state={"blackout": True})
    assert v.action == dg.BLOCKED
    assert calls == {"risk_guard": 0, "pr": 0}


# -------------------------------------------------------------- entry gate

def test_entry_blocked_on_news_blackout(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_entry_gate("XAUUSD", "long", 2000.0, 1990.0,
                               news_state={"blackout": True})
    assert v.action == dg.BLOCKED
    assert v.category == expl.NEWS_BLACKOUT


def test_entry_blocked_on_risk_guard_lock(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _locked())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_entry_gate("XAUUSD", "long", 2000.0, 1990.0,
                               news_state={"blackout": False})
    assert v.action == dg.BLOCKED
    assert v.category == expl.RISK_LOCK


def test_entry_rejected_on_portfolio_risk(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate",
                        lambda *a, **k: _reject_pr(pr.PORTFOLIO_EXPOSURE_EXCEEDED))
    v = dg.evaluate_entry_gate("XAUUSD", "long", 2000.0, 1990.0,
                               news_state={"blackout": False})
    assert v.action == dg.REJECT
    assert v.category == pr.PORTFOLIO_EXPOSURE_EXCEEDED


def test_entry_stand_down_on_drawdown_protection(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate",
                        lambda *a, **k: _reject_pr(pr.DRAWDOWN_PROTECTION))
    v = dg.evaluate_entry_gate("XAUUSD", "long", 2000.0, 1990.0,
                               news_state={"blackout": False})
    assert v.action == dg.STAND_DOWN
    assert v.category == pr.DRAWDOWN_PROTECTION


def test_entry_approved_when_everything_passes(monkeypatch):
    monkeypatch.setattr(dg.risk_guard, "evaluate", lambda sym: _no_lock())
    monkeypatch.setattr(dg.pr, "evaluate", lambda *a, **k: _allow_pr())
    v = dg.evaluate_entry_gate("XAUUSD", "long", 2000.0, 1990.0,
                               news_state={"blackout": False})
    assert v.action == dg.ENTER
    assert v.category is None
    assert v.passed is True


def test_entry_gate_does_not_reference_regime_or_confluence_at_all(monkeypatch):
    """Stage-2 must never consult mkt_regime/cr -- decision_gate.py's
    evaluate_entry_gate signature deliberately has no such parameters,
    matching alert_signals.py's own Stage-2, which does not re-run the
    regime/confluence gate a pending setup already cleared at Stage-1."""
    import inspect
    params = inspect.signature(dg.evaluate_entry_gate).parameters
    assert "mkt_regime" not in params
    assert "cr" not in params


# --------------------------------------------------------- real-function
# integration checks: NOT monkeypatched -- calls the actual
# risk_guard.evaluate()/portfolio_risk.evaluate() the live pipeline calls,
# with rows engineered to force a known outcome, to prove decision_gate.py
# is wired to the real functions and not just to a mock-friendly interface.

def test_entry_gate_real_risk_guard_lock_end_to_end():
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [{"status": "loss", "result_r": -1.0, "closed": f"{today}T09:00:00",
            "symbol": "WTIUSD"},
           {"status": "loss", "result_r": -1.0, "closed": f"{today}T10:00:00",
            "symbol": "WTIUSD"}]
    import engine.risk_guard as rg
    orig = rg.evaluate   # capture BEFORE patching -- rg IS dg.risk_guard (same
                          # module singleton), so patching dg.risk_guard.evaluate
                          # also replaces rg.evaluate; the replacement must not
                          # call through the now-patched name or it recurses
                          # into itself instead of the real implementation.

    def _real_locked(sym):
        return orig(sym, rows=rows, max_daily_loss_r=2, max_open=1, today=today)
    dg.risk_guard.evaluate = _real_locked
    try:
        v = dg.evaluate_entry_gate("WTIUSD", "long", 80.0, 79.0,
                                   news_state={"blackout": False})
    finally:
        dg.risk_guard.evaluate = orig
    assert v.action == dg.BLOCKED
    assert v.category == expl.RISK_LOCK
    assert "DAILY LOSS" in v.reason
