"""Tests for the ICT kill-zone timing edge and combined context adjustment."""
import sys
import pathlib
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import session_edge as se, bias_adjust as ba  # noqa: E402


def test_london_killzone_boost():
    assert se.zone(8) == ("London kill zone", 4)


def test_ny_killzone_boost():
    assert se.zone(13)[1] == 4


def test_asian_penalty():
    assert se.zone(3)[1] == -3


def test_offhours_zero():
    assert se.zone(18)[1] == 0


def _buy(sym): return {"signal": "BUY", "strength": "HIGH", "why": "w", "asof": "2026-07-14"}


def test_context_caps_at_plus_eight():
    ny = datetime(2026, 7, 14, 13, tzinfo=timezone.utc)  # +4 session
    adj, delta, why = ba.apply_context("X", "long", 80, now=ny, load=_buy)  # +6 news
    assert delta == 8 and adj == 88 and "session" in why and "news" in why


def test_asian_offsets_bullish_news():
    asian = datetime(2026, 7, 14, 3, tzinfo=timezone.utc)  # -3 session
    adj, delta, _ = ba.apply_context("X", "long", 80, now=asian, load=_buy)  # +6 news
    assert delta == 3 and adj == 83


def test_context_caps_at_minus_eight():
    asian = datetime(2026, 7, 14, 3, tzinfo=timezone.utc)  # -3 session
    sell = lambda s: {"signal": "SELL", "strength": "HIGH", "why": "w", "asof": "2026-07-14"}
    adj, delta, _ = ba.apply_context("X", "long", 80, now=asian, load=sell)  # -6 news, -3 session = -9 -> -8
    assert delta == -8 and adj == 72
