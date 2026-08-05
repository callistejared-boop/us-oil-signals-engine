"""Day 12 — Execution History: append-only JSONL record of every
per-trade execution report.

Mirrors `engine/macro_history.py`'s exact pattern (Day 11), which itself
mirrors `regime_history.py`/`confluence_history.py`/`confidence_history.py`
before it — same self-rotating append-only JSONL, same `find_by_ref()`
unified-trade-ID join, same immutability guarantee (no update/delete
function of any kind). This is the fourth-generation instance of this
exact pattern in this codebase; see MACRO_ENGINE_SPECIFICATION.md Sec.8
for the precedent this follows.

NORMALIZED, NOT RAW: stores the execution_report's summary fields
(scores, prices, costs, fill flags) but drops the deeply-nested
`entry_detail`/`exit_detail` spread/slippage/latency breakdowns — those
are cheap to regenerate from `replay.py` with the same seed if ever
needed for a specific trade, so persisting them twice would repeat the
"avoid duplicate storage" mistake this codebase has deliberately avoided
since Day 7.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
HISTORY_PATH = ROOT / "execution_history.jsonl"
MAX_LINES = 20000

VERSION = "1.0.0"
SCHEMA_VERSION = 1


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


def _normalize(report: dict) -> dict:
    """Strips a full execution_report.py report down to the normalized,
    storage-worthy subset. Never raises."""
    try:
        return {
            "execution_score": report.get("execution_score"),
            "intended_entry": report.get("intended_entry"),
            "actual_entry": report.get("actual_entry"),
            "entry_filled": report.get("entry_filled"),
            "expected_exit": report.get("expected_exit"),
            "actual_exit": report.get("actual_exit"),
            "exit_filled": report.get("exit_filled"),
            "total_execution_cost": report.get("total_execution_cost"),
            "cost_r": report.get("cost_r"),
            "cost_bps": report.get("cost_bps"),
            "both_legs_filled": report.get("both_legs_filled"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"execution_score": "Unknown", "error": f"normalize error: {exc}"}


def record(symbol: str, report: dict, ref: str = "") -> dict:
    """Append one normalized execution report to history. Never raises.
    Returns the record written (even on a write failure) — same
    convention as `macro_history.record()`."""
    now = datetime.now(timezone.utc)
    normalized = _normalize(report)
    rec = {
        "ts": now.isoformat(timespec="seconds"),
        "symbol": symbol,
        "ref": ref or "",
        **normalized,
        "version": {"execution_history": VERSION, "schema": SCHEMA_VERSION},
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def find_by_ref(ref: str) -> dict | None:
    if not ref:
        return None
    for r in reversed(_read_all()):
        if r.get("ref") == ref:
            return r
    return None


def last_for(symbol: str) -> dict | None:
    rows = [r for r in _read_all() if r.get("symbol") == symbol]
    return rows[-1] if rows else None


def tail(n: int = 20, symbol: str = None) -> list:
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def all_rows() -> list:
    return _read_all()
