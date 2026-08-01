import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import correlation as co


def test_gold_long_fights_rising_dollar():
    assert co.macro_alignment("XAUUSD", "long", "up")["aligned"] is False


def test_gold_short_aligns_rising_dollar():
    assert co.macro_alignment("XAUUSD", "short", "up")["aligned"] is True


def test_btc_long_aligns_falling_dollar():
    assert co.macro_alignment("BTCUSD", "long", "down")["aligned"] is True


def test_flat_or_insensitive_is_none():
    assert co.macro_alignment("WTIUSD", "long", "flat")["aligned"] is None
    assert co.macro_alignment("SPX", "long", "up")["aligned"] is None


def test_read_macro_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(co, "MACRO_PATH", tmp_path / "nope.json")
    assert co.read_macro() is None


def test_macro_note_no_data(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda **k: None)
    assert "n/a" in co.macro_note("XAUUSD", "long")
