"""Decision audit history — append-only JSONL record of every
DecisionSnapshot. Day 8.

Mirrors engine/ledger.py's / engine/regime_history.py's (Day 4) /
engine/confluence_history.py's (Day 5) / engine/confidence_history.py's
(Day 6) exact append/rotate/tail pattern rather than inventing a new
persistence mechanism.

IMMUTABILITY. Records are never edited or overwritten after creation — this
module deliberately exposes no update/delete function of any kind, only
`record()` (append), `record_correction()` (append a NEW, explicitly-linked
row), and read-only lookups. Per the Day 8 mandate ("The snapshot must never
be edited after creation. Corrections should be stored as subsequent
records, not by altering history."), a correction is its own row with
`record_type="correction"` and `corrects_ref` pointing at the row it amends
— `history_for_ref()` returns the original plus every correction, in
write order, so a reviewer always sees the full correction trail rather
than a silently-altered original. See
`tests/test_decision_audit_history.py::test_no_mutator_besides_record_exists`
for the structural proof this module has no update path, not just a
documented promise.

WHY A NEW STORE (disclosed, not silently assumed). No existing log captures
a REJECTED decision at all today — regime/confluence/confidence history
only ever record a classification/read, not "what happened to this
opportunity and why." A DecisionSnapshot is deliberately NOT a duplicate of
those logs' full detail: it stores REF POINTERS into
regime_history.jsonl/confluence_history.jsonl/confidence_history.jsonl
(the same pattern `engine/journal.py`'s `Trade` dataclass already uses for
`regime_ref`/`confluence_ref`/`confidence_ref`) plus a small, denormalized
SUMMARY of each (frozen at decision time, because those upstream logs'
`last_for()`-style reads can change over time and a decision record must
stay historically accurate to the moment the decision was made — see
EXPLAINABILITY_SPECIFICATION.md Sec.3 for the full storage-design
rationale). This is the same "small denormalized summary + ref pointer to
full detail" trade-off `Trade` already makes, not a new pattern.
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "decision_audit.jsonl"
MAX_LINES = 20000


def _as_dict(x) -> dict:
    try:
        return x.as_dict() if hasattr(x, "as_dict") else dict(x)
    except Exception:  # noqa: BLE001
        return {}


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


def record(snapshot) -> dict:
    """Append one DecisionSnapshot (dataclass instance or plain dict, same
    convention as confidence_history.record()). Never raises; returns the
    record that would have been written even if the write itself failed."""
    d = _as_dict(snapshot)
    rec = dict(d)
    rec.setdefault("record_type", "decision")
    rec["recorded"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def record_correction(decision_id: str, note: str, corrected_fields: dict) -> dict:
    """Append a correction row rather than editing history. `decision_id`
    is the `decision_id` of the row being corrected; `corrected_fields` is a
    plain dict of {field: new_value} — interpretive, not automatically
    applied anywhere (a reviewer reading `history_for_ref()` sees both the
    original and the correction and can judge for themselves). Never
    raises."""
    rec = {
        "record_type": "correction",
        "corrects_ref": decision_id or "",
        "note": str(note or ""),
        "corrected_fields": dict(corrected_fields or {}),
        "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
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
    """Full history — the input to replay()/audit-graph tooling and any
    future research pass."""
    return _read_all()


def find_by_ref(decision_id: str) -> dict | None:
    """Direct lookup of the ORIGINAL decision row by its `decision_id`
    (every decision — approved, heads-up, or rejected — gets one; see
    EXPLAINABILITY_SPECIFICATION.md Sec.2). O(n) scan, fine at current data
    volumes (same disclosed trade-off as every other `find_by_ref()` in this
    codebase — see MARKET_MEMORY_SPECIFICATION.md Sec.3.2)."""
    if not decision_id:
        return None
    for r in reversed(_read_all()):
        if r.get("record_type", "decision") == "decision" and r.get("decision_id") == decision_id:
            return r
    return None


def find_by_trade_ref(trade_ref: str) -> dict | None:
    """Direct lookup by the UNIFIED TRADE ID (`trade_ref`) — non-empty only
    for decisions that correspond 1:1 to an actual filled trade (Stage-2
    entries). Distinct from `decision_id`, which every decision has
    regardless of whether it became a trade — see module docstring and
    EXPLAINABILITY_SPECIFICATION.md Sec.2 for why the two are not the same
    field."""
    if not trade_ref:
        return None
    for r in reversed(_read_all()):
        if r.get("record_type", "decision") == "decision" and r.get("trade_ref") == trade_ref:
            return r
    return None


def history_for_ref(decision_id: str) -> list:
    """The original decision row plus every correction that references it,
    in write order (oldest first) — the full, unaltered audit trail for one
    decision. Empty list if `decision_id` matches nothing."""
    if not decision_id:
        return []
    out = []
    for r in _read_all():
        rt = r.get("record_type", "decision")
        if rt == "decision" and r.get("decision_id") == decision_id:
            out.append(r)
        elif rt == "correction" and r.get("corrects_ref") == decision_id:
            out.append(r)
    return out
