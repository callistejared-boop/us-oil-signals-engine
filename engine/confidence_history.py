"""Confidence history — append-only JSONL record of every Confidence Engine
assessment. Day 6.

Mirrors engine/ledger.py's / engine/regime_history.py's (Day 4) /
engine/confluence_history.py's (Day 5) exact append/rotate/tail pattern
rather than inventing a new persistence mechanism.

Records are immutable once written: "Design the storage so future
calibration and research can be performed without modifying historical
records" (Day 6 mandate). Trade outcomes are never written back into this
file — they are joined at READ time by `confidence_calibration.py`, either
via the stable `ref` field (preferred — see journal.py's Trade.id format,
`f"{symbol}-{timestamp}"`, which alert_signals.py now computes once and
passes to both this store and the trade journal, see Day 6 Phase 4) or,
when `ref` is unavailable (e.g. Stage-1 heads-up assessments that never
become a filled trade), by the nearest-timestamp join Day 4/5 already
established (`confluence_analysis.join_trades_with_confluence` pattern,
reused here as `join_trades_with_confidence`).
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "confidence_history.jsonl"
MAX_LINES = 20000


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


def record(assessment, ref: str = "") -> dict:
    """Append one ConfidenceAssessment. `assessment` may be a
    confidence_engine.ConfidenceAssessment instance (has `.as_dict()`) or a
    plain dict with the same shape. `ref`, when known, is the deterministic
    trade-journal id this assessment corresponds to — pass it whenever a
    Stage-2 ENTRY is being logged so future calibration can join directly
    instead of falling back to a timestamp match. Never raises."""
    try:
        d = assessment.as_dict() if hasattr(assessment, "as_dict") else dict(assessment)
    except Exception:  # noqa: BLE001
        d = {}
    rec = dict(d)
    rec["ref"] = ref or ""
    rec["recorded"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def tail(n: int = 20, symbol: str = None) -> list:
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def all_rows() -> list:
    """Full history — the input to confidence_calibration.py's join/
    calibration functions."""
    return _read_all()


def find_by_ref(ref: str) -> dict | None:
    """Direct stable-reference lookup (Day 6's improvement over the
    nearest-timestamp join pattern) — O(n) scan of the history file, fine at
    current data volumes; revisit with an index if confidence_history.jsonl
    ever grows large enough for this to matter."""
    if not ref:
        return None
    for r in reversed(_read_all()):
        if r.get("ref") == ref:
            return r
    return None
