"""Offline tests for the V2.2 Priority 2 Item 4 `strategy` field on
engine.journal.Trade / engine.journal.log_signal() — mirrors
test_journal_execution.py's (Day 12) pattern for the analogous
`execution_ref` field. See STRATEGY_FRAMEWORK_SPECIFICATION.md Sec.2-3
and engine/strategy_registry.py for why this field exists and what it is
NOT (it is not regime_strategy/config.regime_strategy, and it is not yet
the full StrategyProfile — see that module's own docstring).
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from engine import journal as J
from engine import bias_adjust as ba


class _Sig:
    symbol = "XAUUSD"; direction = "long"; entry = 2350.0; stop = 2340.0
    target = 2380.0; rr = 3.0; confidence = 75


def test_trade_has_strategy_field():
    assert "strategy" in J.Trade.__dataclass_fields__
    assert J.Trade.__dataclass_fields__["strategy"].default == ""


def test_log_signal_stamps_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    ok = J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00"),
                      strategy="ict_smc_mast")
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["strategy"] == "ict_smc_mast"


def test_log_signal_strategy_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00")) is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["strategy"] == ""


def test_log_signal_strategy_none_coerced_to_empty_string(tmp_path, monkeypatch):
    # Fail-safe posture matching every other ref field: a None strategy
    # (e.g. an upstream lookup failure) must never raise, and persists as
    # "" rather than the literal string "None".
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    ok = J.log_signal(_Sig(), pd.Timestamp("2026-08-03 12:00:00"), strategy=None)
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["strategy"] == ""
