"""Regime history — append-only JSONL record of every regime classification.

Deliberately mirrors engine/ledger.py's exact pattern (append -> rotate ->
tail) rather than inventing a new persistence mechanism — same
append-only-JSONL, same self-rotation, same fail-safe "a logging error must
never disrupt trading logic" posture. Kept as its own file/module (not
folded into ledger.py) because it needs one extra piece of behavior
ledger.py doesn't: reading the LAST recorded regime for a symbol, so a new
classification can detect whether a transition just happened and compute
how long the previous regime persisted.
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "regime_history.jsonl"
MAX_LINES = 20000   # higher than ledger.py's 5000: this is the dataset Day 4's
                    # own "statistical validation plan" (RESEARCH section) and
                    # any future transition-probability calibration depend on.


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


def last_for(symbol: str, timeframe: str = "strategic"):
    """Most recent recorded entry for this symbol/timeframe-scope, or None."""
    rows = [r for r in _read_all()
            if r.get("symbol") == symbol and r.get("timeframe") == timeframe]
    return rows[-1] if rows else None


def record(symbol: str, timeframe: str, result: dict, ref: str = "") -> dict:
    """Append one regime classification to history. Computes `duration_s`
    (time since the previous entry for this symbol/timeframe) and
    `transition_event` (True if `primary` changed from the previous entry)
    itself, from the on-disk history — the caller does not need to track
    state between calls. Returns the record that was written (even on a
    write failure, so callers can still see what WOULD have been logged).
    Never raises.

    `ref` (Day 7, optional, default "" so every pre-existing call site is
    unaffected): the unified trade-journal reference — see
    journal.make_ref() — attached whenever this classification corresponds
    to a specific trade, not just a routine per-scan snapshot. `last_for()`/
    `transitions()` still operate over ALL rows for a symbol/timeframe
    regardless of `ref`, so a trade-tagged row participates in transition
    detection exactly like a scan row would (see
    MARKET_MEMORY_SPECIFICATION.md Sec.2 for the full reference
    architecture and why this is a small, disclosed trade-off rather than a
    separate record type)."""
    now = datetime.now(timezone.utc)
    prev = last_for(symbol, timeframe)
    duration_s = None
    transition = False
    from_primary = None
    if prev:
        try:
            prev_ts = datetime.fromisoformat(prev["ts"])
            duration_s = round((now - prev_ts).total_seconds(), 1)
        except Exception:  # noqa: BLE001
            duration_s = None
        from_primary = prev.get("primary")
        transition = bool(from_primary) and from_primary != result.get("primary")
    rec = {
        "ts": now.isoformat(timespec="seconds"),
        "symbol": symbol,
        "timeframe": timeframe,
        "primary": result.get("primary"),
        "confidence": result.get("confidence"),
        "quality_score": result.get("quality_score"),
        "transition_risk": result.get("transition_risk"),
        "transition_label": result.get("transition_label"),
        "duration_s_since_prev": duration_s,
        "transition_event": transition,
        "transition_from": from_primary if transition else None,
        "ref": ref or "",
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def find_by_ref(ref: str) -> dict | None:
    """Day 7: direct stable-reference lookup — the unified-trade-ID
    counterpart to confluence_history.find_by_ref() /
    confidence_history.find_by_ref() (Day 6)."""
    if not ref:
        return None
    for r in reversed(_read_all()):
        if r.get("ref") == ref:
            return r
    return None


def tail(n: int = 20, symbol: str = None) -> list:
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def transitions(symbol: str = None, n: int = 50) -> list:
    """Just the rows where a regime change was detected — the input a future
    transition-probability calibration pass would train on."""
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return [r for r in rows if r.get("transition_event")][-n:]
