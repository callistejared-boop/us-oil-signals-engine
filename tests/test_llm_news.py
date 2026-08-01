"""Tests for the Claude news analyst (offline - no key, no network)."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import llm_news as ln  # noqa: E402
from engine import fundamentals_feed as ff  # noqa: E402


def test_parse_valid_json():
    d = ln._parse('here you go {"signal":"BUY","strength":"HIGH","score":7,"why":"supply risk"} thanks')
    assert d["signal"] == "BUY" and d["strength"] == "HIGH" and d["score"] == 7 and d["source"] == "claude-llm"


def test_parse_rejects_bad_signal():
    assert ln._parse('{"signal":"MAYBE","strength":"HIGH","score":3}') is None


def test_parse_rejects_garbage():
    assert ln._parse("no json here") is None


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(ln, "_env", lambda k, d="": "")
    assert ln.score_headlines("Gold", ["Fed cuts rates"]) is None


def test_no_headlines_returns_none(monkeypatch):
    monkeypatch.setattr(ln, "_env", lambda k, d="": "sk-key" if k == "ANTHROPIC_API_KEY" else d)
    assert ln.score_headlines("Gold", []) is None


def test_build_symbol_applies_llm_override(monkeypatch):
    # force the feed to see one headline, and Claude to override to SELL
    monkeypatch.setattr(ff, "_fetch", lambda url, timeout: (
        b"<?xml version='1.0'?><rss version='2.0'><channel>"
        b"<item><title>OPEC floods market, glut fears</title><link>x</link></channel></rss>"))
    import engine.llm_news as _ln
    monkeypatch.setattr(_ln, "score_headlines",
                        lambda label, titles: {"signal": "SELL", "strength": "HIGH", "score": -7,
                                               "why": "oversupply", "source": "claude-llm"})
    cfg = ff.SYMBOLS["WTIUSD"]
    res = ff.build_symbol(cfg)
    assert res is not None and res["signal"] == "SELL" and res["source"] == "claude-llm"
    assert res["why"].startswith("[Claude]")
