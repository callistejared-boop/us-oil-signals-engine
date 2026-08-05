"""Anomaly detection — simple, disclosed statistical checks only.

Explicitly NOT predictive modeling. This module answers "does this data
look operationally wrong" (frozen feed, implausible single-bar jump,
a gap in the timeline), never "is the market about to move." Every
threshold here is a disclosed engineering judgment, same posture as
every other qualitative constant in this codebase (Day 6's confidence
tiers, Day 9's `EXPECTANCY_DECLINE_R`) — not fitted to historical data,
not claimed to be statistically optimal.
"""
from __future__ import annotations

from .completeness import NONE_, MINOR, MAJOR, CRITICAL

# A price series repeating the exact same value this many consecutive
# bars in a row is very unlikely to be genuine market data at typical
# intraday sampling — far more likely a frozen/stuck feed.
FROZEN_BAR_THRESHOLD = 6

# A single-bar move bigger than this many standard deviations of the
# series' own recent bar-to-bar changes is flagged for review — not
# blocked, not interpreted, just surfaced.
ZSCORE_THRESHOLD = 6.0


def check_frozen_price(closes, threshold: int = FROZEN_BAR_THRESHOLD) -> dict:
    """Detects N consecutive identical closing prices — the signature of
    a stuck/frozen feed rather than a genuinely quiet market (real quiet
    markets still show sub-pip/sub-tick drift almost every bar)."""
    try:
        values = list(closes) if closes is not None else []
        if len(values) < threshold:
            return {"severity": NONE_, "frozen_run_length": 0, "detail": "insufficient bars to assess"}
        run = 1
        best = 1
        for i in range(1, len(values)):
            if values[i] == values[i - 1]:
                run += 1
                best = max(best, run)
            else:
                run = 1
        if best >= threshold:
            severity = CRITICAL if best >= threshold * 2 else MAJOR
        else:
            severity = NONE_
        return {"severity": severity, "frozen_run_length": best, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "frozen_run_length": None, "detail": f"anomaly check error: {exc}"}


def check_price_jump(closes, threshold: float = ZSCORE_THRESHOLD) -> dict:
    """Flags the single largest bar-to-bar change if it's an extreme
    outlier relative to the series' own recent volatility (z-score on
    simple differences). Needs at least 10 bars to compute a meaningful
    standard deviation; returns NONE_/insufficient-data below that."""
    try:
        values = list(closes) if closes is not None else []
        if len(values) < 10:
            return {"severity": NONE_, "max_abs_zscore": None, "detail": "insufficient bars to assess"}
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        n = len(diffs)
        mean = sum(diffs) / n
        variance = sum((d - mean) ** 2 for d in diffs) / n
        std = variance ** 0.5
        if std == 0:
            return {"severity": NONE_, "max_abs_zscore": 0.0, "detail": "zero variance in bar-to-bar changes"}
        zscores = [abs((d - mean) / std) for d in diffs]
        max_z = max(zscores)
        if max_z >= threshold * 1.5:
            severity = CRITICAL
        elif max_z >= threshold:
            severity = MAJOR
        else:
            severity = NONE_
        return {"severity": severity, "max_abs_zscore": round(max_z, 2), "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "max_abs_zscore": None, "detail": f"anomaly check error: {exc}"}


def check_timeline_gaps(timestamps, expected_interval_minutes: float, tolerance_multiplier: float = 3.0) -> dict:
    """Flags gaps in a bar timeline materially larger than the expected
    sampling interval — e.g. a 15-min feed that silently skipped several
    bars. `timestamps` must be sortable/subtractable (pandas Timestamps
    or datetimes)."""
    try:
        ts = sorted(t for t in (timestamps or []) if t is not None)
        if len(ts) < 2 or not expected_interval_minutes:
            return {"severity": NONE_, "largest_gap_minutes": None, "gap_count": 0, "detail": "insufficient data to assess"}
        threshold_minutes = expected_interval_minutes * tolerance_multiplier
        gaps = []
        for i in range(1, len(ts)):
            delta = ts[i] - ts[i - 1]
            minutes = delta.total_seconds() / 60.0 if hasattr(delta, "total_seconds") else float(delta)
            if minutes > threshold_minutes:
                gaps.append(minutes)
        if not gaps:
            return {"severity": NONE_, "largest_gap_minutes": None, "gap_count": 0, "detail": None}
        largest = max(gaps)
        severity = CRITICAL if largest > threshold_minutes * 3 else MAJOR
        return {"severity": severity, "largest_gap_minutes": round(largest, 1), "gap_count": len(gaps), "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "largest_gap_minutes": None, "gap_count": None, "detail": f"anomaly check error: {exc}"}
