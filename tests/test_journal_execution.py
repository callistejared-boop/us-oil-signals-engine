"""Offline tests for the Day 12 `execution_ref` field on
engine.journal.Trade / engine.journal.log_signal() — mirrors
test_journal_macro.py's (Day 11) pattern for the analogous `macro_ref`.
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from engine import journal as J
from engine import bias_adjust as ba


class _Sig:
    symbol = "XAUUSD"; direction = "long"; entry = 2350.0; stop = 2340.0
    target = 2380.0; rr = 3.0; confidence = 75


def test_trade_has_execution_ref_field():
    assert "execution_ref" in J.Trade.__dataclass_fields__
    assert J.Trade.__dataclass_fields__["execution_ref"].default == ""


def test_log_signal_stamps_execution_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    ok = J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00"),
                      execution_ref="XAUUSD-20260803120000")
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["execution_ref"] == "XAUUSD-20260803120000"


def test_log_signal_execution_ref_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00")) is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["execution_ref"] == ""


def test_log_signal_unified_id_equals_execution_ref_by_convention(tmp_path, monkeypatch):
    """The platform's standing invariant, now extended once more: id ==
    regime_ref == confluence_ref == confidence_ref == macro_ref ==
    execution_ref, when the caller passes the same make_ref()-derived
    string to all five (as alert_signals.py's Stage-2 entry flow does)."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    when = pd.Timestamp("2026-08-03 12:00:00")
    ref = J.make_ref(_Sig.symbol, when)
    ok = J.log_signal(_Sig(), when, confluence_ref=ref, confidence_ref=ref,
                      regime_ref=ref, macro_ref=ref, execution_ref=ref)
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert (rec["id"] == rec["regime_ref"] == rec["confluence_ref"]
           == rec["confidence_ref"] == rec["macro_ref"] == rec["execution_ref"])
