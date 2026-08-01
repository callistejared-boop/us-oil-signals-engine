"""Tests for TradingView confirmation folding."""
import sys
import json
import pathlib
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import tv_signals as tv  # noqa: E402

NOW = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)


def _seed(tmp_path, monkeypatch, recs):
    p = tmp_path / "tv.json"
    p.write_text(json.dumps(recs))
    monkeypatch.setattr(tv, "STORE", p)


def test_latest_fresh(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"ts": (NOW - timedelta(minutes=10)).isoformat(), "symbol": "XAUUSD", "action": "buy"}])
    assert tv.latest("XAUUSD", now=NOW) == "buy"


def test_latest_ignores_stale(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"ts": (NOW - timedelta(minutes=200)).isoformat(), "symbol": "XAUUSD", "action": "buy"}])
    assert tv.latest("XAUUSD", now=NOW) is None


def test_confirmation_agrees(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"ts": (NOW - timedelta(minutes=5)).isoformat(), "symbol": "WTIUSD", "action": "buy"}])
    d, why = tv.confirmation("WTIUSD", "long", now=NOW)
    assert d == 2 and "agrees" in why


def test_confirmation_conflicts(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"ts": (NOW - timedelta(minutes=5)).isoformat(), "symbol": "WTIUSD", "action": "sell"}])
    d, why = tv.confirmation("WTIUSD", "long", now=NOW)
    assert d == -2 and "conflicts" in why


def test_no_tv_data_is_neutral(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [])
    assert tv.confirmation("WTIUSD", "long", now=NOW) == (0, "")
