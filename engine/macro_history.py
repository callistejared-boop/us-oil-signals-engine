"""Day 11 — Macro History: append-only JSONL record of every macro
assessment.

Deliberately mirrors `engine/regime_history.py`'s exact pattern (append ->
rotate -> tail, `find_by_ref()` for the unified-trade-ID join) rather than
inventing a fourth persistence mechanism in this codebase (ledger.py,
regime_history.py, decision_audit_history.py, experiment_registry.py all
already establish it) — same append-only JSONL, same self-rotation, same
"a logging error must never disrupt trading logic" fail-safe posture, same
immutability guarantee (no update/delete function of any kind — corrections
are new rows, never edits, exactly like Day 8's decision_audit_history.py
and Day 9's experiment_registry.py before it).

NORMALIZED, NOT RAW: this stores the OUTPUT of `macro_regime.classify()`
(labels, macro_confidence, evidence_quality, a compact per-provider
freshness/availability snapshot) — never the full raw `facts` payload
`macro_providers.py` returns. Those facts are themselves cheap to
re-fetch/re-derive from the underlying feeds' OWN caches (rates_cache.json,
spread_cache.json, risk_sentiment_cache.json, etc. all already persist the
raw numbers) — duplicating them here would be exactly the kind of
redundant storage this codebase's standing "reuse existing histories,
avoid duplicate storage" discipline (Day 7's Market Memory, Day 9's
research_stats) exists to prevent.

`ref` (optional, default "" so this never requires a trade to exist):
the same unified trade-journal reference every other Day 6-9 history file
accepts — see `journal.make_ref()`. A macro assessment computed alongside
a specific candidate entry is tagged with that trade's `ref`; a routine
per-scan assessment (no specific trade yet) is logged with `ref=""`,
exactly mirroring `regime_history.record()`'s own dual-write convention.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "macro_history.jsonl"
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


def _normalize(assessment: dict) -> dict:
    """Strips a full macro assessment (as returned by
    `macro_engine.assess()`) down to the normalized, storage-worthy
    subset — labels/confidence/evidence-quality/a compact freshness
    snapshot per provider, never the raw `facts` blobs. Never raises."""
    try:
        providers = assessment.get("providers", {}) or {}
        provider_snapshot = {
            name: {
                "source_availability": p.get("source_availability"),
                "freshness_state": (p.get("freshness") or {}).get("state"),
                "uncertainty": p.get("uncertainty"),
            }
            for name, p in providers.items()
        }
        regime = assessment.get("regime", {}) or {}
        return {
            "labels": regime.get("labels", []),
            "macro_confidence": regime.get("macro_confidence"),
            "evidence_quality": regime.get("evidence_quality"),
            "provider_snapshot": provider_snapshot,
            "cross_asset_summary": (assessment.get("cross_asset") or {}).get("interpretation"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"labels": [], "macro_confidence": "low", "evidence_quality": "low",
               "provider_snapshot": {}, "error": f"normalize error: {exc}"}


def record(symbol: str, assessment: dict, ref: str = "") -> dict:
    """Append one normalized macro assessment to history. Never raises.
    Returns the record that was written (even on a write failure, so
    callers can still see what WOULD have been logged) — same convention
    as `regime_history.record()`."""
    now = datetime.now(timezone.utc)
    normalized = _normalize(assessment)
    rec = {
        "ts": now.isoformat(timespec="seconds"),
        "symbol": symbol,
        "ref": ref or "",
        **normalized,
        "version": {"macro_history": VERSION, "schema": SCHEMA_VERSION,
                    "macro_engine": assessment.get("version")},
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def find_by_ref(ref: str) -> dict | None:
    """Direct stable-reference lookup — the unified-trade-ID counterpart
    to `regime_history.find_by_ref()` / `confluence_history.find_by_ref()`
    / `confidence_history.find_by_ref()`."""
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


def label_history(symbol: str = None, n: int = 200) -> list:
    """Just the `labels` field over time — the input a future validation
    pass (e.g. 'did the platform perform differently under Risk-Off vs.
    Risk-On') would read, mirroring `regime_history.transitions()`'s role
    for the regime engine. Read-only; computes nothing new."""
    rows = tail(n=n, symbol=symbol)
    return [{"ts": r.get("ts"), "symbol": r.get("symbol"), "labels": r.get("labels", [])}
           for r in rows]


def replay(symbol: str = None, since_ts: str = None, until_ts: str = None) -> list:
    """Every recorded assessment for `symbol` within an optional
    [since_ts, until_ts) ISO-timestamp window, in original order — the
    same "read the append-only log back, change nothing" replay
    guarantee `decision_audit_history.py` (Day 8) established. Never
    raises."""
    try:
        rows = _read_all()
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        if since_ts:
            rows = [r for r in rows if r.get("ts", "") >= since_ts]
        if until_ts:
            rows = [r for r in rows if r.get("ts", "") < until_ts]
        return rows
    except Exception:  # noqa: BLE001
        return []


def all_rows() -> list:
    return _read_all()
