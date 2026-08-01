"""Tests for the fundamentals staleness guard."""
import sys
import pathlib
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine.freshness import staleness, is_stale  # noqa: E402

TODAY = date(2026, 7, 13)


def test_fresh():
    age, level, _ = staleness("2026-07-13", today=TODAY)
    assert age == 0 and level == "fresh"


def test_aging():
    age, level, _ = staleness("2026-07-10", today=TODAY)
    assert age == 3 and level == "aging"


def test_stale():
    age, level, banner = staleness("2026-07-05", today=TODAY)
    assert age == 8 and level == "stale" and "STALE" in banner


def test_unreadable_is_stale():
    age, level, _ = staleness("not-a-date", today=TODAY)
    assert age is None and level == "stale"


def test_is_stale_helper():
    assert is_stale("2026-06-01", today=TODAY) is True
    assert is_stale("2026-07-12", today=TODAY) is False
