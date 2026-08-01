"""Tests for the bias-flip alerter."""
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import news_alerts as na  # noqa: E402


def _feed(sig, strength="HIGH"):
    return {"symbols": {"XAUUSD": {"label": "Gold", "signal": sig, "strength": strength,
                                   "why": "news flow", "headlines": [
                                       {"title": "Fed cut", "link": "http://x", "bias": "bullish", "score": 4}]}}}


def test_first_run_no_alert():
    ch, st = na.detect_flips(_feed("BUY"), {})
    assert ch == [] and st["XAUUSD"] == "BUY"


def test_real_flip_alerts():
    ch, st = na.detect_flips(_feed("SELL"), {"XAUUSD": "BUY"})
    assert len(ch) == 1 and ch[0]["old"] == "BUY" and ch[0]["new"] == "SELL"
    assert "NEWS BIAS FLIP" in na.build_alert_text(ch[0])


def test_unchanged_no_alert():
    ch, _ = na.detect_flips(_feed("BUY"), {"XAUUSD": "BUY"})
    assert ch == []


def test_flip_to_neutral_suppressed():
    ch, _ = na.detect_flips(_feed("NEUTRAL"), {"XAUUSD": "BUY"})
    assert ch == []


def test_low_strength_suppressed():
    ch, _ = na.detect_flips(_feed("SELL", "LOW"), {"XAUUSD": "BUY"})
    assert ch == []


def test_run_sends_and_persists(tmp_path):
    sent = []
    sp = tmp_path / "state.json"
    na.run(_feed("BUY"), lambda t: sent.append(t), state_path=sp)  # first run: record only
    assert sent == [] and json.loads(sp.read_text())["XAUUSD"] == "BUY"
    na.run(_feed("SELL"), lambda t: sent.append(t), state_path=sp)  # flip: alert
    assert len(sent) == 1 and json.loads(sp.read_text())["XAUUSD"] == "SELL"


def test_negation_scoring_end_to_end():
    from engine import fundamentals_feed as ff
    oil = ff.SYMBOLS["WTIUSD"]
    b1, _ = ff.score_title("US airstrike, Hormuz closed", oil["bull"], oil["bear"])
    b2, s2 = ff.score_title("Iran denies closing Hormuz", oil["bull"], oil["bear"])
    assert b1 == "bullish" and s2 == 0
