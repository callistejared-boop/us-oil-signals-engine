"""Scan-cycle latency history - append-only JSONL record of per-stage
timing for every scan cycle (V2.2 Priority 1 Item 2).

Mirrors engine/regime_history.py's exact pattern (append -> rotate ->
tail), same fail-safe "a logging error must never disrupt trading logic"
posture. Records what engine/scan_latency.py's ScanTimer measured over one
full call to alert_signals.py::main() - one row per scan, not per symbol -
so "stage time" here always means "cumulative time this stage consumed
across every symbol/branch that touched it this scan", per the ScanTimer
docstring.
"""
from __future__ import annotations

import json
import pathlib
import statistics
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "scan_latency_history.jsonl"
MAX_LINES = 20000

VERSION = "1.0.0"


def _read_all() -> list:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []


def _rotate() -> None:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            HISTORY_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def record(stage_ms: dict, total_ms: float, symbol_count: int = 0,
           call_counts: dict = None) -> dict:
    """Append one scan's per-stage timing to history. Returns the record
    that was written (even on a write failure, so callers can still see
    what WOULD have been logged). Never raises."""
    try:
        stages = {k: round(float(v), 3) for k, v in (stage_ms or {}).items()}
    except Exception:  # noqa: BLE001
        stages = {}
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_ms": round(float(total_ms), 3) if total_ms is not None else None,
        "symbol_count": int(symbol_count or 0),
        "stages": stages,
        "call_counts": dict(call_counts or {}),
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def tail(n: int = 20) -> list:
    return _read_all()[-n:]


def _percentile(values: list, pct: float):
    """Nearest-rank percentile, sorted ascending. pct in [0, 100]. Returns
    None on empty input. Deliberately not statistics.quantiles(): nearest-
    rank is simpler to reason about for small-n scan-latency samples and
    matches how P95/P99 are conventionally reported for latency metrics."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round(pct / 100.0 * len(vals))) - 1))
    return vals[k]


def stage_stats(stage: str, n: int = 200) -> dict:
    """Aggregate metrics for one stage over the last `n` recorded scans:
    max, rolling average, P95, P99. Returns None fields (never raises) if
    there's no data yet for this stage."""
    rows = _read_all()[-n:]
    vals = [r.get("stages", {}).get(stage) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"stage": stage, "n": 0, "max_ms": None, "avg_ms": None,
                "p95_ms": None, "p99_ms": None}
    return {
        "stage": stage,
        "n": len(vals),
        "max_ms": round(max(vals), 3),
        "avg_ms": round(statistics.mean(vals), 3),
        "p95_ms": round(_percentile(vals, 95), 3),
        "p99_ms": round(_percentile(vals, 99), 3),
    }


def _row_ts(row: dict):
    try:
        return datetime.fromisoformat(row["ts"])
    except Exception:  # noqa: BLE001
        return None


def longest_scan(since: datetime = None) -> dict | None:
    """The single slowest recorded scan (by total_ms) at or after `since`
    (inclusive). Returns None if there's no data in range."""
    rows = _read_all()
    if since is not None:
        rows = [r for r in rows if _row_ts(r) and _row_ts(r) >= since]
    rows = [r for r in rows if r.get("total_ms") is not None]
    if not rows:
        return None
    return max(rows, key=lambda r: r["total_ms"])


def longest_today() -> dict | None:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return longest_scan(since=start)


def longest_this_week() -> dict | None:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return longest_scan(since=start)


def all_stage_stats(n: int = 200) -> dict:
    """Convenience: stage_stats() for every stage that appears in the last
    `n` scans, keyed by stage name."""
    rows = _read_all()[-n:]
    stages = set()
    for r in rows:
        stages.update((r.get("stages") or {}).keys())
    return {stage: stage_stats(stage, n=n) for stage in sorted(stages)}
