"""Sub-day, 5-state freshness classification for operational feed health.

NOT the same module as `engine/freshness.py` (Day 1-2's day-granularity,
3-state dated-context banner) — see `engine/data_health/__init__.py` for
the full disambiguation. This module answers "is this specific feed's
already-fetched data recent enough to act on," at minute granularity,
across every feed this platform has, including market price bars.

States, from best to worst:

- Fresh   — age <= expected_freshness_minutes
- Aging   — age <= expected_freshness_minutes * AGING_MULTIPLIER
- Stale   — age <= expected_freshness_minutes * STALE_MULTIPLIER
- Expired — older than that
- Unknown — age could not be determined (missing file, unreadable
  timestamp, or a feed with no persisted freshness signal at all) — this
  is NOT the same as Expired. Unknown means "we cannot assess," Expired
  means "we assessed it and it's too old." Conflating the two would
  overstate confidence in a genuine blind spot.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

FRESH = "fresh"
AGING = "aging"
STALE = "stale"
EXPIRED = "expired"
UNKNOWN = "unknown"

ALL_STATES = (FRESH, AGING, STALE, EXPIRED, UNKNOWN)

AGING_MULTIPLIER = 1.5
STALE_MULTIPLIER = 3.0
# beyond STALE_MULTIPLIER * expected -> EXPIRED


def classify(age_minutes, expected_freshness_minutes) -> str:
    """Pure classification — no I/O. age_minutes=None or
    expected_freshness_minutes in (None, 0) -> UNKNOWN (nothing to compare
    against, not a fault)."""
    try:
        if age_minutes is None or expected_freshness_minutes in (None, 0):
            return UNKNOWN
        if age_minutes < 0:
            return UNKNOWN  # clock skew / bad timestamp — don't pretend it's fresh
        if age_minutes <= expected_freshness_minutes:
            return FRESH
        if age_minutes <= expected_freshness_minutes * AGING_MULTIPLIER:
            return AGING
        if age_minutes <= expected_freshness_minutes * STALE_MULTIPLIER:
            return STALE
        return EXPIRED
    except Exception:  # noqa: BLE001
        return UNKNOWN


def _now():
    return datetime.now(timezone.utc)


def age_minutes_from_mtime(relative_path: str):
    """Filesystem mtime -> age in minutes. Returns None (not 0, not a
    fault) if the file doesn't exist or can't be read — 'no data yet' is
    a legitimate, common state (many caches don't exist until first use)."""
    try:
        p = ROOT / relative_path
        if not p.exists():
            return None
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return (_now() - mtime).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


def age_minutes_from_json_field(relative_path: str, field: str, iso: bool = True):
    """Reads a JSON file and computes age from one of its own embedded
    timestamp fields, rather than filesystem mtime — useful when a cache
    file records its own 'generated' timestamp. Returns None on any
    failure (missing file, missing field, bad format)."""
    try:
        p = ROOT / relative_path
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get(field) if isinstance(data, dict) else None
        if not raw:
            return None
        if iso:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        return (_now() - ts).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


OBSERVATIONS_PATH = ROOT / "data_health_observations.jsonl"
_MAX_OBSERVATION_LINES = 2000


def record_observation(feed_id: str, ok: bool, detail: str = "") -> None:
    """For OBSERVED-kind feeds (no persisted cache file of their own —
    e.g. news_guard's live calendar fetch, fundamentals_feed's headline
    pull): the call site that was ALREADY making this live call for its
    own reasons (alert_signals.py's Stage-2 flow) reports the outcome
    here. This is the one place in the whole package that records
    something about a live call — and it never triggers the call itself,
    only logs the result of a call made elsewhere. One line per
    observation, keyed by feed_id, most-recent-wins when read back via
    `age_minutes_from_observation()`. Never raises."""
    try:
        row = {"ts": _now().isoformat(timespec="seconds"), "feed_id": feed_id,
               "ok": bool(ok), "detail": str(detail or "")}
        with open(OBSERVATIONS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        _rotate_observations()
    except Exception:  # noqa: BLE001
        pass


def _rotate_observations() -> None:
    try:
        lines = OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_OBSERVATION_LINES:
            OBSERVATIONS_PATH.write_text("\n".join(lines[-_MAX_OBSERVATION_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def last_observation(feed_id: str):
    """Most recent observation row for one feed_id, or None if none
    recorded yet (a legitimate 'never observed this run' state, not a
    fault)."""
    try:
        if not OBSERVATIONS_PATH.exists():
            return None
        lines = OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("feed_id") == feed_id:
                return row
        return None
    except Exception:  # noqa: BLE001
        return None


def age_minutes_from_observation(feed_id: str):
    """Age in minutes since the last recorded observation for feed_id, or
    None if no observation has ever been recorded."""
    try:
        row = last_observation(feed_id)
        if row is None:
            return None
        ts = datetime.fromisoformat(row["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (_now() - ts).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


def freshness_block(age_minutes, expected_freshness_minutes, state_override=None) -> dict:
    """Standardized freshness block, mirroring
    `engine/macro_providers.py`'s `_freshness_from_iso`/`_freshness_reference`/
    `_freshness_computed` shape convention so downstream consumers see a
    familiar dict regardless of which module produced it."""
    state = state_override or classify(age_minutes, expected_freshness_minutes)
    return {
        "age_minutes": round(age_minutes, 1) if isinstance(age_minutes, (int, float)) else None,
        "expected_freshness_minutes": expected_freshness_minutes,
        "state": state,
    }
