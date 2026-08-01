"""Tests for news-context stamping on trade entries."""
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402
from engine import journal as J  # noqa: E402
from engine import bias_adjust as ba  # noqa: E402


class _Sig:
    symbol = "WTIUSD"; direction = "long"; entry = 73.9; stop = 73.6
    target = 74.8; rr = 3.0; confidence = 84


def test_trade_has_news_fields():
    for f in ("news_signal", "news_strength", "news_delta"):
        assert f in J.Trade.__dataclass_fields__


def test_news_stamp_failsafe():
    # unknown symbol -> no feed -> neutral stamp, never raises
    assert J._news_stamp("ZZZ", "long") == ("", "", 0)


def test_log_signal_stamps_news(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda sym, **k: {"signal": "BUY", "strength": "HIGH"})
    monkeypatch.setattr(ba, "adjustment", lambda sym, d, **k: (6, "agrees"))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-07-14 10:00:00")) is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["news_signal"] == "BUY" and rec["news_strength"] == "HIGH" and rec["news_delta"] == 6
