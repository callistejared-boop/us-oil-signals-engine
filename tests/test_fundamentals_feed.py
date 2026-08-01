"""Offline tests for the live fundamentals feed (no network)."""
import sys
import json
import pathlib
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import fundamentals_feed as ff  # noqa: E402

SAMPLE = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>US launches airstrike on Iran, Strait of Hormuz disruption deepens</title><link>http://x/1</link><pubDate>Mon, 13 Jul 2026</pubDate></item>
<item><title>Ceasefire and truce hopes rise as Iran signals de-escalation</title><link>http://x/2</link><pubDate>Mon, 13 Jul 2026</pubDate></item>
<item><title>OPEC agrees to boost output in August</title><link>http://x/3</link><pubDate>Sun, 12 Jul 2026</pubDate></item>
<item><title>Gold steady ahead of Fed minutes</title><link>http://x/5</link><pubDate>Mon, 13 Jul 2026</pubDate></item>
</channel></rss>"""


def test_parse_rss_extracts_items():
    items = ff.parse_rss(SAMPLE)
    assert len(items) == 4
    assert items[0]["title"].startswith("US launches")
    assert items[0]["link"] == "http://x/1"


def test_parse_rss_bad_xml_is_empty():
    assert ff.parse_rss(b"not xml at all") == []


def test_score_bullish_supply_risk():
    bias, s = ff.score_title("US airstrike on Iran, Hormuz disruption")
    assert bias == "bullish" and s > 0


def test_score_bearish_resolution():
    bias, s = ff.score_title("Ceasefire and truce end the conflict; oil eases")
    assert bias == "bearish" and s < 0


def test_score_neutral_offtopic():
    bias, s = ff.score_title("Gold steady ahead of Fed minutes")
    assert bias == "neutral" and s == 0


def test_load_feed_fresh(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"asof": date.today().isoformat(), "net_bias": "bullish",
                             "counts": {"bullish": 1, "bearish": 0, "neutral": 0},
                             "n_total": 1, "n_scored": 1, "headlines": []}))
    assert ff.load_feed(p) is not None


def test_load_feed_stale_returns_none(tmp_path):
    p = tmp_path / "f.json"
    old = (date.today() - timedelta(days=10)).isoformat()
    p.write_text(json.dumps({"asof": old, "net_bias": "bullish",
                             "counts": {"bullish": 1, "bearish": 0, "neutral": 0},
                             "n_total": 1, "n_scored": 1, "headlines": []}))
    assert ff.load_feed(p) is None


def test_load_feed_missing_returns_none(tmp_path):
    assert ff.load_feed(tmp_path / "nope.json") is None
