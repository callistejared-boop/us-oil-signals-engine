"""Heartbeat monitor — process-level liveness, distinct from per-feed data
freshness (that's `freshness.py`'s job). Tracks the six things the
mandate names: scheduler execution, provider responsiveness, processing
latency, queue health, dashboard publishing, journal persistence.

REUSE, NOT DUPLICATION: `heartbeat_watchdog.py` (repo root, added
2026-07-28) already implements `heartbeat_age_minutes()` — the exact
function that reads `alert_heartbeat.txt`'s own embedded timestamp and
tolerates a missing file as "not launched yet" rather than a fault. This
module imports and calls that function directly rather than
re-parsing the heartbeat file a second way. `heartbeat_watchdog.py`'s own
Telegram-DM behavior (`STALE_MINUTES = 45`, one DM, never a channel post)
is untouched — this module only OBSERVES the same age value, it does not
alert on its own.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import heartbeat_watchdog as _hbw  # reused directly, not reimplemented
except Exception:  # noqa: BLE001
    _hbw = None

from . import freshness as fr

HEARTBEAT_HISTORY = ROOT / "data_health_heartbeat_history.jsonl"
MAX_LINES = 5000

# Mirrors heartbeat_watchdog.STALE_MINUTES if importable; falls back to
# the same disclosed constant if the import above failed for any reason.
STALE_MINUTES = getattr(_hbw, "STALE_MINUTES", 45)
DASHBOARD_PUBLISH_HEARTBEAT = ROOT / "dashboard_publish_heartbeat.json"
JOURNAL_PATH = "trades.json"


def scheduler_status() -> dict:
    """Liveness of the primary scan loop (entry-scan.yml, */15 * * * *),
    via the pre-existing heartbeat_age_minutes(). None (file missing) is
    reported as UNKNOWN, matching heartbeat_watchdog's own 'not launched
    yet, nothing to check' posture — not treated as a fault."""
    try:
        age = _hbw.heartbeat_age_minutes() if _hbw is not None else None
    except Exception:  # noqa: BLE001
        age = None
    state = fr.classify(age, STALE_MINUTES)
    return fr.freshness_block(age, STALE_MINUTES, state_override=state)


def dashboard_publish_status() -> dict:
    """Age since the last successful dashboard payload publish. Reads
    dashboard_publish_heartbeat.json's own 'published_at' field — a NEW
    file, written by dashboard_publish.py as of this Day (see Phase 8
    integration); prior Days had no persisted publish timestamp at all,
    a gap identified during this Day's Phase 1 audit."""
    age = fr.age_minutes_from_json_field(DASHBOARD_PUBLISH_HEARTBEAT.name, "published_at")
    expected = 45
    return fr.freshness_block(age, expected)


def journal_persistence_status() -> dict:
    """Age since trades.json was last written — the platform's core
    decision/outcome ledger. A long gap here does not necessarily mean a
    fault (no new trades may have triggered), but it is disclosed as an
    observation, not interpreted as good or bad on its own."""
    age = fr.age_minutes_from_mtime(JOURNAL_PATH)
    expected = 180
    return fr.freshness_block(age, expected)


@dataclass(frozen=True)
class HeartbeatRecord:
    ts: str
    scheduler: dict
    dashboard_publish: dict
    journal_persistence: dict
    processing_latency_seconds: Optional[float] = None
    queue_depth: Optional[int] = None
    provider_fresh_count: Optional[int] = None
    provider_total_count: Optional[int] = None
    note: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_status(processing_latency_seconds: Optional[float] = None,
                    queue_depth: Optional[int] = None,
                    provider_fresh_count: Optional[int] = None,
                    provider_total_count: Optional[int] = None,
                    note: str = "") -> dict:
    """Read-only assembly of one heartbeat snapshot from all six tracked
    signals — does NOT write to the persisted history. Used both as the
    read-only view for `dashboard_snapshot()` (a dashboard page load must
    never itself count as a 'beat') and as the row `record_beat()` below
    persists. Never raises."""
    try:
        rec = HeartbeatRecord(
            ts=_now_iso(),
            scheduler=scheduler_status(),
            dashboard_publish=dashboard_publish_status(),
            journal_persistence=journal_persistence_status(),
            processing_latency_seconds=processing_latency_seconds,
            queue_depth=queue_depth,
            provider_fresh_count=provider_fresh_count,
            provider_total_count=provider_total_count,
            note=note,
        )
        return {
            "ts": rec.ts,
            "scheduler": rec.scheduler,
            "dashboard_publish": rec.dashboard_publish,
            "journal_persistence": rec.journal_persistence,
            "processing_latency_seconds": rec.processing_latency_seconds,
            "queue_depth": rec.queue_depth,
            "provider_fresh_count": rec.provider_fresh_count,
            "provider_total_count": rec.provider_total_count,
            "note": rec.note,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ts": _now_iso(), "error": f"current_status failed: {exc}"}


def record_beat(processing_latency_seconds: Optional[float] = None,
                 queue_depth: Optional[int] = None,
                 provider_fresh_count: Optional[int] = None,
                 provider_total_count: Optional[int] = None,
                 note: str = "") -> dict:
    """Assembles one heartbeat record (via `current_status()`) and
    APPENDS it to the persisted history. Call this once per actual scan
    (see `alert_signals.py`'s `log_data_health()`), never once per
    dashboard page load — `dashboard_snapshot()` uses `current_status()`
    directly instead, precisely so rendering the dashboard doesn't itself
    inflate the heartbeat history. Never raises."""
    try:
        row = current_status(processing_latency_seconds, queue_depth,
                              provider_fresh_count, provider_total_count, note)
        with open(HEARTBEAT_HISTORY, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        _rotate()
        return row
    except Exception as exc:  # noqa: BLE001
        return {"ts": _now_iso(), "error": f"record_beat failed: {exc}"}


def _rotate() -> None:
    try:
        lines = HEARTBEAT_HISTORY.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            HEARTBEAT_HISTORY.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def tail(n: int = 20) -> list:
    try:
        lines = HEARTBEAT_HISTORY.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []
