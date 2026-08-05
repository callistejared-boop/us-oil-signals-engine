"""Offline tests for alert_signals.py's Day 13 integration points:
log_paper_broker_submission(), sync_paper_broker_closures(), and
build_entry()'s new "paper broker" line. Mirrors
test_alert_signals_execution.py's (Day 12) pattern of testing the
extracted functions directly with monkeypatched collaborators — the
real PaperBroker/broker_history are never touched here (that's what
tests/test_paper_broker.py is for)."""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402


def _rec():
    return {"symbol": "XAUUSD", "direction": "long", "entry": 2000.0, "stop": 1990.0,
           "target": 2030.0, "rr": 3.0, "invalidation": "close below 1985"}


def _fake_order(status="filled", quantity=0.1, avg_fill_price=2000.05):
    return SimpleNamespace(status=status, quantity=quantity, avg_fill_price=avg_fill_price,
                           order_id="ord-fake")


# --- log_paper_broker_submission() -----------------------------------------

def test_log_paper_broker_submission_records_and_returns(monkeypatch):
    captured = {}
    fake_broker = SimpleNamespace(account_id="paper-default",
                                  submit_order=lambda req: _fake_order())
    monkeypatch.setattr(als, "_broker", lambda: fake_broker)
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: captured.update(d)))

    out = als.log_paper_broker_submission("XAUUSD", "long", 2000.0, 1990.0, 2030.0,
                                          ref="XAUUSD-2026-08-03T10:00:00")
    assert out is not None
    assert out.status == "filled"
    assert captured["event"] == "broker_order"
    assert captured["ref"] == "XAUUSD-2026-08-03T10:00:00"
    assert captured["status"] == "filled"


def test_log_paper_broker_submission_never_raises_when_broker_accessor_blows_up(monkeypatch):
    def boom():
        raise RuntimeError("broker unavailable")
    monkeypatch.setattr(als, "_broker", boom)
    out = als.log_paper_broker_submission("XAUUSD", "long", 2000.0, 1990.0, 2030.0)
    assert out is None


def test_log_paper_broker_submission_never_raises_when_submit_order_blows_up(monkeypatch):
    def boom(req):
        raise RuntimeError("submit_order blew up")
    fake_broker = SimpleNamespace(account_id="paper-default", submit_order=boom)
    monkeypatch.setattr(als, "_broker", lambda: fake_broker)
    out = als.log_paper_broker_submission("XAUUSD", "long", 2000.0, 1990.0, 2030.0)
    assert out is None


def test_log_paper_broker_submission_maps_direction_to_side(monkeypatch):
    captured_reqs = []
    fake_broker = SimpleNamespace(account_id="paper-default",
                                  submit_order=lambda req: captured_reqs.append(req) or _fake_order())
    monkeypatch.setattr(als, "_broker", lambda: fake_broker)
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: None))
    als.log_paper_broker_submission("XAUUSD", "short", 2000.0, 2010.0, 1970.0)
    assert captured_reqs[0].side == "sell"


# --- sync_paper_broker_closures() -------------------------------------------

def test_sync_paper_broker_closures_calls_broker_and_logs(monkeypatch):
    logged = []
    fake_broker = SimpleNamespace(
        sync_closures=lambda sym, rows=None: [{"closed": True, "ref": "r1", "realized_pnl_delta": 50.0}])
    monkeypatch.setattr(als, "_broker", lambda: fake_broker)
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))
    out = als.sync_paper_broker_closures("XAUUSD")
    assert len(out) == 1
    assert logged[0]["event"] == "broker_close"
    assert logged[0]["ref"] == "r1"


def test_sync_paper_broker_closures_skips_ledger_log_when_nothing_closed(monkeypatch):
    logged = []
    fake_broker = SimpleNamespace(sync_closures=lambda sym, rows=None: [])
    monkeypatch.setattr(als, "_broker", lambda: fake_broker)
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))
    out = als.sync_paper_broker_closures("XAUUSD")
    assert out == []
    assert logged == []


def test_sync_paper_broker_closures_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("broker accessor blew up")
    monkeypatch.setattr(als, "_broker", boom)
    assert als.sync_paper_broker_closures("XAUUSD") == []


# --- build_entry()'s "paper broker" line (advisory-only, never gates) ------

def test_build_entry_shows_broker_line_when_present():
    text = als.build_entry(_rec(), lt=None, broker=_fake_order(status="filled", quantity=0.1,
                                                                avg_fill_price=2000.05))
    assert "paper broker: filled" in text
    assert "qty 0.1 lot" in text
    assert "avg fill 2000.05" in text


def test_build_entry_omits_broker_line_when_none():
    text = als.build_entry(_rec(), lt=None, broker=None)
    assert "paper broker:" not in text


def test_build_entry_broker_line_omits_avg_fill_when_rejected():
    text = als.build_entry(_rec(), lt=None,
                           broker=_fake_order(status="rejected", quantity=0.0, avg_fill_price=None))
    assert "paper broker: rejected" in text
    assert "avg fill" not in text


def test_build_entry_broker_line_coexists_with_execution_macro_confidence():
    from engine import confidence_engine as ce
    assessment = ce.ConfidenceAssessment(
        symbol="XAUUSD", direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=78, tier="High Confidence",
        probability_label="internal decision-quality estimate",
        calibrated_probability=None, is_calibrated=False,
        evidence_quality=70, evidence_diversity=60, market_quality=75,
        regime_confidence=65, confluence_quality=70,
        portfolio_status={"allow": True}, risk_status={"guard_action": "allow"},
    )
    macro = {"regime": {"labels": ["Risk-On"], "macro_confidence": "medium",
                        "evidence_quality": "medium"}}
    execution = {"execution_score": "Good", "cost_r": 0.08, "entry_filled": True,
                "entry_detail": {"spread": {"estimated_spread": 0.35}}}
    text = als.build_entry(_rec(), lt=None, confidence=assessment, macro=macro,
                           execution=execution, broker=_fake_order())
    assert "confidence: High Confidence" in text
    assert "macro: Risk-On" in text
    assert "est. execution: Good" in text
    assert "paper broker: filled" in text


def test_build_entry_never_raises_when_broker_missing_avg_fill_price_attr():
    text = als.build_entry(_rec(), lt=None,
                           broker=SimpleNamespace(status="working", quantity=0.0, avg_fill_price=None))
    assert isinstance(text, str)
