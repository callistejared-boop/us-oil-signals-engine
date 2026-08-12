"""Offline tests for engine/why_not.py (V2.2 Priority 3: Why-Not Engine
live-query extension -- closes EXPLAINABILITY_SPECIFICATION.md Sec.9.1/
Sec.12's disclosed gap using engine/kill_switch.py (already built,
already tested) + decision_audit_history.py + explain_rejection(), with
no new explanation-generation logic of its own.

Most tests monkeypatch `why_not.kill_switch.current_stand_downs` directly
(same isolation approach as tests/test_regime_transitions_report.py used
for regime_history) so why_not.py's own branching logic is tested
independently of kill_switch.py's internals -- those are already covered
by tests/test_kill_switch.py. Two end-to-end tests at the bottom exercise
the REAL kill_switch + decision_audit_history wiring, isolated to
tmp_path, to prove the pieces actually connect."""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import why_not as wn                       # noqa: E402
from engine import kill_switch as ks                    # noqa: E402
from engine import decision_audit_history as dah         # noqa: E402
from engine import news_guard                            # noqa: E402
from engine import risk_guard                             # noqa: E402
from engine import portfolio_risk as pr                    # noqa: E402


def _sd(name="x", engaged=False, scope="symbol", reason="", category=None, source="", detail=None):
    return ks.StandDownStatus(name=name, engaged=engaged, scope=scope, reason=reason,
                              category=category, source=source, detail=detail or {})


# --------------------------------------------------------------------------
# active_stand_down path
# --------------------------------------------------------------------------

def test_why_not_now_reports_single_engaged_stand_down(monkeypatch):
    monkeypatch.setattr(ks, "current_stand_downs",
                        lambda **kw: [_sd(name="news_blackout", engaged=True, scope="platform",
                                          reason="high-impact NFP (-10 min)")])
    out = wn.why_not_now("XAUUSD")
    assert out["answer_source"] == "active_stand_down"
    assert "news_blackout" in out["explanation"]
    assert "NFP" in out["explanation"]
    assert len(out["stand_downs"]) == 1


def test_why_not_now_reports_multiple_engaged_stand_downs_together(monkeypatch):
    monkeypatch.setattr(ks, "current_stand_downs",
                        lambda **kw: [_sd(name="news_blackout", engaged=True, scope="platform",
                                          reason="FOMC"),
                                     _sd(name="risk_guard_day_stop", engaged=True, scope="symbol",
                                        reason="day stop hit")])
    out = wn.why_not_now("BTCUSD")
    assert out["answer_source"] == "active_stand_down"
    assert "news_blackout" in out["explanation"]
    assert "risk_guard_day_stop" in out["explanation"]
    assert len(out["stand_downs"]) == 2


def test_why_not_now_stand_down_takes_precedence_over_recorded_decision(monkeypatch, tmp_path):
    """Even if a persisted decision exists for this symbol, an ENGAGED
    stand-down is checked first and wins -- it is the more current truth."""
    monkeypatch.setattr(ks, "current_stand_downs",
                        lambda **kw: [_sd(name="drawdown_protection", engaged=True,
                                          scope="portfolio", reason="trailing dd cap hit")])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "XAUUSD", "decision_id": "XAUUSD-1", "final_action": "rejected",
               "rejection": {"category": "weak_evidence", "reason": "MAST held"}})
    out = wn.why_not_now("XAUUSD")
    assert out["answer_source"] == "active_stand_down"


# --------------------------------------------------------------------------
# fallback to most recent recorded decision
# --------------------------------------------------------------------------

def test_why_not_now_falls_back_to_recorded_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "WTIUSD", "decision_id": "WTIUSD-1", "final_action": "rejected",
               "rejection": {"category": "weak_evidence", "reason": "MAST held (score 40)"}})
    out = wn.why_not_now("WTIUSD")
    assert out["answer_source"] == "recorded_rejection"
    assert out["explanation"]["rejection_category"] == "weak_evidence"
    assert "MAST held" in out["explanation"]["rejection_reason"]


def test_why_not_now_uses_most_recent_rejection_when_several_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "WTIUSD", "decision_id": "WTIUSD-1", "final_action": "rejected",
               "rejection": {"category": "risk_lock", "reason": "old"}})
    dah.record({"symbol": "WTIUSD", "decision_id": "WTIUSD-2", "final_action": "rejected",
               "rejection": {"category": "weak_evidence", "reason": "newest"}})
    out = wn.why_not_now("WTIUSD")
    assert out["explanation"]["rejection_reason"] == "newest"


def test_why_not_now_reports_recorded_approval_when_not_a_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "BTCUSD", "decision_id": "BTCUSD-1", "final_action": "approved_heads_up"})
    out = wn.why_not_now("BTCUSD")
    assert out["answer_source"] == "recorded_approval"
    assert out["most_recent_decision_id"] == "BTCUSD-1"


def test_why_not_now_ignores_decisions_for_other_symbols(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "XAUUSD", "decision_id": "XAUUSD-1", "final_action": "rejected",
               "rejection": {"category": "weak_evidence", "reason": "not this symbol"}})
    out = wn.why_not_now("BTCUSD")
    assert out["answer_source"] == "no_data"


# --------------------------------------------------------------------------
# no_data path
# --------------------------------------------------------------------------

def test_why_not_now_no_data_when_nothing_engaged_and_no_history(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    out = wn.why_not_now("XAUUSD")
    assert out["answer_source"] == "no_data"
    assert "note" in out


# --------------------------------------------------------------------------
# fail-open contract
# --------------------------------------------------------------------------

def test_why_not_now_never_raises_when_kill_switch_errors(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(ks, "current_stand_downs", _boom)
    out = wn.why_not_now("XAUUSD")
    assert out["answer_source"] == "error"
    assert out["symbol"] == "XAUUSD"


def test_why_not_now_never_raises_on_garbage_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(ks, "current_stand_downs", lambda **kw: [_sd(engaged=False)])
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    out = wn.why_not_now(None)  # type: ignore[arg-type]
    assert out["answer_source"] in ("no_data", "error")


# --------------------------------------------------------------------------
# end-to-end: real kill_switch + real decision_audit_history wiring
# --------------------------------------------------------------------------

def test_end_to_end_real_stand_down_wins_over_history(monkeypatch, tmp_path):
    """No mocking of why_not.py or kill_switch.py's own logic -- only the
    underlying news_guard/risk_guard/portfolio_risk calls kill_switch.py
    itself wraps (same pattern test_kill_switch.py uses), proving the real
    call chain why_not -> kill_switch -> news_guard produces the right
    answer."""
    monkeypatch.setattr(news_guard, "evaluate",
                        lambda now=None: {"ok": True, "blackout": True,
                                          "active": ("NFP", -5)})
    monkeypatch.setattr(risk_guard, "evaluate", lambda symbol: {"locked": False, "reason": ""})
    monkeypatch.setattr(risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(pr, "portfolio_drawdown_r",
                        lambda rows, window=30, max_age_days=30.0: 0.0)
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")

    out = wn.why_not_now("XAUUSD", settings=SimpleNamespace(), rows=[])
    assert out["answer_source"] == "active_stand_down"
    assert "news_blackout" in out["explanation"]


def test_end_to_end_real_no_stand_down_falls_back_to_real_explain_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(news_guard, "evaluate",
                        lambda now=None: {"ok": True, "blackout": False, "active": None})
    monkeypatch.setattr(risk_guard, "evaluate", lambda symbol: {"locked": False, "reason": ""})
    monkeypatch.setattr(risk_guard, "today_realized_r", lambda rows, symbol=None: 0.0)
    monkeypatch.setattr(pr, "portfolio_drawdown_r",
                        lambda rows, window=30, max_age_days=30.0: 0.0)
    monkeypatch.setattr(dah, "HISTORY_PATH", tmp_path / "decision_audit.jsonl")
    dah.record({"symbol": "WTIUSD", "decision_id": "WTIUSD-9", "final_action": "rejected",
               "rejection": {"category": "risk_lock", "reason": "daily loss lock"},
               "stage": "market_regime_assessment"})

    out = wn.why_not_now("WTIUSD", settings=SimpleNamespace(), rows=[])
    assert out["answer_source"] == "recorded_rejection"
    assert out["explanation"]["rejection_category"] == "risk_lock"
    assert out["explanation"]["stage_reached"] == "market_regime_assessment"
