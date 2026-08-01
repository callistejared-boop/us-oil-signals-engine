"""Offline tests for multi-pair feed signals + interface render."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import fundamentals_feed as ff  # noqa: E402
import news_bias  # noqa: E402


def test_all_symbols_have_config():
    for sym in ("WTIUSD", "XAUUSD", "EURUSD", "BTCUSD"):
        cfg = ff.SYMBOLS[sym]
        assert cfg["queries"] and cfg["bull"] and cfg["bear"]


def test_gold_rate_cut_is_bullish():
    bias, s = ff.score_title("Fed signals rate cut, dollar falls; gold safe haven demand",
                             ff.SYMBOLS["XAUUSD"]["bull"], ff.SYMBOLS["XAUUSD"]["bear"])
    assert bias == "bullish" and s > 0


def test_btc_hack_is_bearish():
    bias, s = ff.score_title("Major exchange hack triggers crypto selloff and liquidation",
                             ff.SYMBOLS["BTCUSD"]["bull"], ff.SYMBOLS["BTCUSD"]["bear"])
    assert bias == "bearish" and s < 0


def test_signal_thresholds():
    assert ff._signal(5) == "BUY"
    assert ff._signal(-5) == "SELL"
    assert ff._signal(0) == "NEUTRAL"


def test_render_handles_empty():
    out = news_bias.render(None)
    assert "No live data yet" in out and "<html" in out


def test_render_handles_symbols():
    data = {"generated": "2026-07-13T10:00:00+00:00", "symbols": {
        "XAUUSD": {"label": "Gold", "signal": "BUY", "net_bias": "bullish", "net_score": 8,
                   "counts": {"bullish": 3, "bearish": 1, "neutral": 0}, "n_total": 4,
                   "why": "BUY bias - bullish flow", "headlines": [
                       {"title": "Rate cut lifts gold", "link": "http://x", "bias": "bullish", "score": 4}]}}}
    out = news_bias.render(data)
    assert "Gold" in out and "BUY" in out and "Rate cut lifts gold" in out


def test_stale_feed_shows_watchdog_banner():
    old = {"generated": "2020-01-01T00:00:00+00:00", "symbols": {
        "XAUUSD": {"label": "Gold", "signal": "BUY", "strength": "HIGH", "net_score": 8,
                   "counts": {"bullish": 3, "bearish": 1, "neutral": 0}, "n_total": 4,
                   "why": "w", "headlines": []}}}
    assert "FEED STALE" in news_bias.render(old)


def test_fresh_feed_no_watchdog_banner():
    from datetime import datetime, timezone
    fresh = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbols": {
        "XAUUSD": {"label": "Gold", "signal": "BUY", "strength": "HIGH", "net_score": 8,
                   "counts": {"bullish": 3, "bearish": 1, "neutral": 0}, "n_total": 4,
                   "why": "w", "headlines": []}}}
    assert "FEED STALE" not in news_bias.render(fresh)
