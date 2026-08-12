"""Offline tests for Day 6's trade-journal integration: journal.make_ref()
and Trade.confluence_ref / Trade.confidence_ref. Mirrors
tests/test_journal_regime.py's exact fixture pattern (Day 4)."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from engine import journal as J
from engine import bias_adjust as ba


class _Sig:
    symbol = "WTIUSD"; direction = "long"; entry = 73.9; stop = 73.6
    target = 74.8; rr = 3.0; confidence = 80


def test_trade_has_day6_ref_fields():
    for f in ("confluence_ref", "confidence_ref"):
        assert f in J.Trade.__dataclass_fields__
        assert J.Trade.__dataclass_fields__[f].default == ""


def test_make_ref_format_matches_trade_id(tmp_path, monkeypatch):
    """The whole point of Day 6's design: make_ref() produces the exact
    same string log_signal() uses for the row's own `id`, so a caller that
    computes make_ref() once and passes it through to both history logs and
    log_signal() gets id == confluence_ref == confidence_ref by
    construction."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    ref = J.make_ref("XAUUSD", when)
    assert ref == "XAUUSD-2026-08-03T10:00:00"


def test_log_signal_stores_refs(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    when = pd.Timestamp("2026-08-03 10:00:00")
    ref = J.make_ref("WTIUSD", when)
    ok = J.log_signal(_Sig(), when, confluence_ref=ref, confidence_ref=ref)
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["id"] == ref
    assert rec["confluence_ref"] == ref
    assert rec["confidence_ref"] == ref


def test_log_signal_refs_optional_default_empty(tmp_path, monkeypatch):
    """Backward compatibility: log_signal() callers that don't pass
    confluence_ref/confidence_ref (i.e. every pre-Day-6 call site, and any
    future caller that simply doesn't have one) still work exactly as
    before — the new fields default to "" rather than becoming required."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-08-03 10:00:00")) is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["confluence_ref"] == "" and rec["confidence_ref"] == ""


def test_backward_compatible_read_of_pre_day6_rows(tmp_path, monkeypatch):
    """A trades.json row written before Day 6 (no confluence_ref/
    confidence_ref keys at all) must still load and be usable — journal.py
    reads rows as plain dicts, never reconstructs a Trade() from disk, so
    missing keys are fine as long as callers use .get() with a default,
    exactly like every other field this platform has added over time
    (news_signal, regime_trend, confluence_score, ...)."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    legacy_row = {
        "id": "XAUUSD-2026-07-01T09:00:00", "opened": "2026-07-01 09:00:00",
        "direction": "long", "entry": 2000.0, "stop": 1990.0, "target": 2030.0,
        "rr": 3.0, "confidence": 80, "symbol": "XAUUSD", "status": "win",
        "result_r": 2.0,
        # deliberately NO confluence_ref / confidence_ref keys
    }
    (tmp_path / "t.json").write_text(json.dumps([legacy_row]), encoding="utf-8")
    rows = J._load()
    assert len(rows) == 1
    assert rows[0].get("confluence_ref", "") == ""   # safe default, no KeyError
    assert rows[0]["status"] == "win"                # existing fields unaffected


def test_confluence_history_record_accepts_ref(tmp_path, monkeypatch):
    from engine import confluence_history as cfh
    monkeypatch.setattr(cfh, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    ref = J.make_ref("XAUUSD", pd.Timestamp("2026-08-03 10:00:00"))
    rec = cfh.record("XAUUSD", "long", 82, "confirmed", ["price action"], [], {}, [], ref=ref)
    assert rec["ref"] == ref
    found = cfh.find_by_ref(ref)
    assert found is not None and found["score"] == 82


def test_confluence_history_find_by_ref_missing_returns_none(tmp_path, monkeypatch):
    from engine import confluence_history as cfh
    monkeypatch.setattr(cfh, "HISTORY_PATH", tmp_path / "confluence_history.jsonl")
    assert cfh.find_by_ref("does-not-exist") is None
    assert cfh.find_by_ref("") is None
