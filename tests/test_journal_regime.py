import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from engine import journal as J
from engine import bias_adjust as ba


class _Sig:
    symbol = "WTIUSD"; direction = "long"; entry = 73.9; stop = 73.6
    target = 74.8; rr = 3.0; confidence = 80


def test_trade_has_regime_fields():
    for f in ("regime_trend", "regime_vol"):
        assert f in J.Trade.__dataclass_fields__


def test_log_signal_stamps_regime(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    ok = J.log_signal(_Sig(), pd.Timestamp("2026-07-17 13:00:00"),
                      regime={"trend": "trend", "vol": "expansion"})
    assert ok is True
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["regime_trend"] == "trend" and rec["regime_vol"] == "expansion"


def test_log_signal_regime_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))
    assert J.log_signal(_Sig(), pd.Timestamp("2026-07-17 13:00:00")) is True  # no regime arg
    rec = json.loads((tmp_path / "t.json").read_text())[0]
    assert rec["regime_trend"] == ""
