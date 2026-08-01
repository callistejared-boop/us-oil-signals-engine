"""Tests for folding live news bias into signal confidence."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import bias_adjust as ba  # noqa: E402


def _buy(strength): return lambda sym: {"signal": "BUY", "strength": strength, "why": "w", "asof": "2026-07-13"}
def _sell(strength): return lambda sym: {"signal": "SELL", "strength": strength, "why": "w", "asof": "2026-07-13"}
def _none(sym): return None
def _neutral(sym): return {"signal": "NEUTRAL", "strength": "LOW", "why": "w", "asof": "2026-07-13"}


def test_agree_long_buy_high_adds_six():
    adj, d, _ = ba.apply("X", "long", 80, load=_buy("HIGH"))
    assert d == 6 and adj == 86


def test_conflict_long_sell_med_subtracts_three():
    adj, d, why = ba.apply("X", "long", 80, load=_sell("MED"))
    assert d == -3 and adj == 77 and "CONFLICTS" in why


def test_agree_short_sell_high():
    adj, d, _ = ba.apply("X", "short", 80, load=_sell("HIGH"))
    assert d == 6 and adj == 86


def test_no_news_zero_delta():
    adj, d, _ = ba.apply("X", "long", 80, load=_none)
    assert d == 0 and adj == 80


def test_neutral_zero_delta():
    adj, d, _ = ba.apply("X", "long", 80, load=_neutral)
    assert d == 0 and adj == 80


def test_bounds_capped_at_100():
    adj, _, _ = ba.apply("X", "long", 97, load=_buy("HIGH"))
    assert adj == 100


def test_grade_uses_adjusted_confidence():
    # base 84 (would be A) + 6 news -> 90 -> A+
    assert ba.grade_from(90, "confirmed") == "A+"
    assert ba.grade_from(84, "confirmed") == "A"
    assert ba.grade_from(70, "watch") == "C (watch)"


def test_delta_never_exceeds_six():
    for load in (_buy("HIGH"), _sell("HIGH"), _buy("MED"), _sell("LOW")):
        _, d, _ = ba.apply("X", "long", 50, load=load)
        assert -6 <= d <= 6
