"""Offline tests for the Day 13 `broker_ref` field on
engine.journal.Trade / engine.journal.log_signal() — mirrors
test_journal_execution.py's (Day 12) pattern for the analogous
`execution_ref`.
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from engine import journal as J
from engine import bias_adjust as ba


class _Sig:
    symbol = "XAUUSD"; direction = "long"; entry = 2350.0; stop = 2340.0
    target = 2380.0; rr = 3.0; confidence = 75


def test_trade_has_broker_ref_field():
    assert "broker_ref" in J.Trade.__dataclass_fields__
    assert J.Trade.__dataclass_fields__["broker_ref"].default == ""


def test_log_signal_stamps_broker_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    ok = J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00"),
                      broker_ref="XAUUSD-20260803120000")
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["broker_ref"] == "XAUUSD-20260803120000"


def test_log_signal_broker_ref_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00")) is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["broker_ref"] == ""


def test_log_signal_unified_id_equals_broker_ref_by_convention(tmp_path, monkeypatch):
    """The platform's standing invariant, now extended once more: id ==
    regime_ref == confluence_ref == confidence_ref == macro_ref ==
    execution_ref == broker_ref, when the caller passes the same
    make_ref()-derived string to all six (as alert_signals.py's Stage-2
    entry flow does)."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    when = pd.Timestamp("2026-08-03 12:00:00")
    ref = J.make_ref(_Sig.symbol, when)
    ok = J.log_signal(_Sig(), when, confluence_ref=ref, confidence_ref=ref,
                      regime_ref=ref, macro_ref=ref, execution_ref=ref, broker_ref=ref)
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert (rec["id"] == rec["regime_ref"] == rec["confluence_ref"] == rec["confidence_ref"]
           == rec["macro_ref"] == rec["execution_ref"] == rec["broker_ref"])


def test_broker_ref_never_overwrites_entry_stop_target(tmp_path, monkeypatch):
    """Same discipline as Day 12's execution_ref: the broker_ref is
    purely an ID join, never a source of truth for the trade's own
    intended levels."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    when = pd.Timestamp("2026-08-03 12:00:00")
    J.log_signal(_Sig(), when, broker_ref="some-broker-ref")
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["entry"] == 2350.0
    assert rec["stop"] == 2340.0
    assert rec["target"] == 2380.0
