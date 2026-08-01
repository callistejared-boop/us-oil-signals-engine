"""Letter-grade translation for the MAST confluence score.

Single source of truth for "is this an A+ trade or a C trade" language used
in the Telegram messages, the hourly note, and the live dashboard. Built on
top of confluence.py's 0-100 score + tier — this module adds no new
judgment of its own, it only relabels what confluence.py already decided so
the grade shown everywhere is always consistent with the actual gate logic.

Grading is intentionally tier-aware, not score-only: a "rejected" read (a
hard gate failed — bad breakout, overextended, RR too thin, etc.) is never
called a trade at all, regardless of how the soft-scored components landed,
because Layer 1 + the hard gates already decided this isn't tradeable.
"""
from __future__ import annotations

from dataclasses import dataclass

# (min_score, grade, label) — checked high to low, only within tradeable tiers
_CONFIRMED_BANDS = [
    (90, "A+", "Highest confluence — every major confirmation layer agrees"),
    (80, "A",  "Strong confluence — broad agreement across confirmation layers"),
    (70, "B+", "Confirmed setup — meets the minimum institutional bar"),
]
_WATCH_BANDS = [
    (60, "B",  "Developing — structure present, not yet enough confluence to act"),
    (50, "C+", "Early / weak — worth watching, not an entry"),
    (0,  "C",  "Low confluence — informational only"),
]


@dataclass
class Grade:
    letter: str
    label: str
    tradeable: bool
    score: int
    tier: str


def grade_for(score: int, tier: str) -> Grade:
    """tier is one of 'confirmed' | 'watch' | 'rejected' (confluence.py's
    final_tier). Returns a Grade; never raises."""
    score = max(0, min(100, int(score or 0)))
    tier = (tier or "").lower()

    if tier == "rejected":
        return Grade("NO TRADE", "Hard gate failed — setup rejected, do not enter",
                     False, score, tier)

    if tier == "confirmed":
        for floor, letter, label in _CONFIRMED_BANDS:
            if score >= floor:
                return Grade(letter, label, True, score, tier)
        # confirmed but somehow under 70 shouldn't happen (confluence.py
        # downgrades confirmed->watch below min_score) — fail safe anyway
        return Grade("B+", "Confirmed setup", True, score, tier)

    # watch tier (or unknown/None) -> never tradeable, informational grade
    for floor, letter, label in _WATCH_BANDS:
        if score >= floor:
            return Grade(letter, label, False, score, tier)
    return Grade("C", "Low confluence — informational only", False, score, tier)


def grade_line(score: int, tier: str) -> str:
    g = grade_for(score, tier)
    if g.tradeable:
        return f"Grade: {g.letter} ({g.score}/100) — {g.label}"
    return f"Grade: {g.letter} ({g.score}/100) — {g.label}"


if __name__ == "__main__":
    for s, t in [(95, "confirmed"), (82, "confirmed"), (71, "confirmed"),
                (65, "watch"), (55, "watch"), (30, "watch"), (80, "rejected")]:
        print(t, s, "->", grade_line(s, t))
