"""Staleness guard for dated context (e.g. fundamentals/geopolitics).

A trade note that prints week-old geopolitics as if current is dangerous.
This computes how old a dated block is and returns a level + banner so the
note can warn loudly and discount stale fundamental confidence.
"""
from datetime import date, datetime


def _parse(asof):
    if isinstance(asof, date):
        return asof
    return datetime.strptime(str(asof)[:10], "%Y-%m-%d").date()


def staleness(asof, warn_days=3, stale_days=7, today=None):
    """Return (age_days, level, banner). level in fresh|aging|stale."""
    today = today or date.today()
    try:
        age = (today - _parse(asof)).days
    except Exception:  # noqa: BLE001
        return (None, "stale", "!! FUNDAMENTALS DATE UNREADABLE - verify manually before trading.")
    if age < 0:
        age = 0
    if age >= stale_days:
        return (age, "stale",
                f"!! STALE FUNDAMENTALS ({age} days old) - geopolitics/inventory below "
                "may be outdated. Treat the TECHNICAL read as primary and re-verify news "
                "before trading.")
    if age >= warn_days:
        return (age, "aging",
                f"* Fundamentals are {age} days old - re-check headlines before acting.")
    return (age, "fresh", f"Fundamentals current (as-of is {age} day(s) old).")


def is_stale(asof, stale_days=7, today=None):
    return staleness(asof, stale_days=stale_days, today=today)[1] == "stale"
