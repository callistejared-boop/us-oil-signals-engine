"""Priority 5 Item 3 -- Trade lifecycle signal-to-outcome unified schema.

WHY THIS EXISTS. Today a single "trade story" is scattered across four
places that were each built for a different purpose and never designed to
be read as one chain: `decision_audit_history.py` (one immutable snapshot
per decision, keyed by `decision_id`, with `trade_ref` set only for fills),
`pending.py` (a two-stage watch-list -- `entry`/`void` events are returned
to the caller but never themselves persisted anywhere), `journal.py`
(`Trade.status` -- a flat string mutated in place by `settle()`, no history
of how it got there), and `broker/order_state.py` (a clean validated state
machine, but scoped to broker `Order` objects only, not signals). No module
in the codebase can answer "what happened to this opportunity, from the
moment it was detected to the moment it was learned from, in order" -- that
is the gap this module closes.

DESIGN. Reuses `engine/broker/order_state.py`'s exact pattern rather than
inventing a new one: an immutable, frozen `LifecycleRecord` dataclass; a
`VALID_TRANSITIONS` adjacency dict; a pure `transition()` function that
returns a NEW record (via `dataclasses.replace`) with the move appended to
an append-only `history` tuple; an `InvalidTransition` exception for any
move not in the graph. On top of that state machine sits a persistence
layer that mirrors `decision_audit_history.py`'s own JSONL append/rotate/
tail convention (`trade_lifecycle.jsonl`) -- every `transition()` call's
resulting record is written as a fresh, full row (never edited in place),
so the LAST row for a given `lifecycle_id` is always that chain's current,
complete state (including its full history), exactly like
`regime_history.py`'s "append a fresh snapshot, don't diff" convention.

STAGE GRAPH.

    DETECTED --> QUALIFIED --> PENDING --> ENTERED --> MANAGING --> CLOSED --> LEARNED
        |            |            |
        +-> REJECTED-+------------+
                                   |
                                   +-> VOIDED

  DETECTED   Layer-1 signal produced (signals.py). Always the first stage.
  QUALIFIED  Passed MAST confluence (Layer 2) -- became a candidate.
  REJECTED   Terminal. Failed a gate at ANY point (confluence, portfolio
             risk, risk lock, ...) before ever becoming a trade. Reachable
             from DETECTED, QUALIFIED, or PENDING -- this module does not
             distinguish WHY by stage name (the reason string + the
             upstream decision_audit_history row carry that detail; see
             `mark_rejected()`'s `reason=` parameter).
  PENDING    A confirmed-tier setup is watching for its limit level to be
             tapped (`pending.py`'s own two-stage lifecycle).
  VOIDED     Terminal. A pending setup aged out (`pending.MAX_WAIT_BARS`)
             without ever being tapped. Distinguished from REJECTED because
             it is a natural-expiry outcome, not a gate failure.
  ENTERED    The setup's level was tapped and the trade was actually
             logged (`journal.log_signal()`). `trade_ref` is set here.
  MANAGING   Optional intermediate bookkeeping stage for a live, still-open
             trade (this module does not currently populate it from
             `alert_signals.py` -- `journal.settle()` observes a trade only
             at its close, not at intermediate break-even/partial events --
             but the state machine supports it for future use, e.g. wiring
             `journal.py`'s own break-even/partial bookkeeping through this
             module later without a schema change).
  CLOSED     Terminal-ish. `journal.settle()` marked the trade
             win/loss/scratch/expired. `outcome` and `result_r` are set
             here from that exact settlement.
  LEARNED    Terminal. Reserved for a future post-trade-review/market-
             memory write confirming this trade's outcome was folded back
             into the research loop (Day 8's post-trade review, Day 7's
             Market Memory). Not populated by any wiring yet -- this module
             only defines the slot so a later day's work has somewhere to
             record it without another schema change.

ADVISORY-ONLY, ADDITIVE. This module is purely an observational overlay.
It has no read path from any gate, sizing, or publication decision, and it
never replaces `journal.py`/`pending.py`/`decision_audit_history.py`'s own
existing state (`Trade.status`, `pending.json`, `decision_audit.jsonl` are
all untouched, still the systems of record for their own domains). Every
public function here is fail-safe: it never raises past its own boundary
(matches this codebase's universal `log_*` helper posture -- see
`alert_signals.py`'s own docstrings for every other Day's integration)."""
from __future__ import annotations

import dataclasses
import json
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "trade_lifecycle.jsonl"
MAX_LINES = 20000

VERSION = "1.0.0"


class Stage:
    DETECTED = "detected"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    PENDING = "pending"
    VOIDED = "voided"
    ENTERED = "entered"
    MANAGING = "managing"
    CLOSED = "closed"
    LEARNED = "learned"

    TERMINAL = (REJECTED, VOIDED, CLOSED, LEARNED)
    ALL = (DETECTED, QUALIFIED, REJECTED, PENDING, VOIDED, ENTERED,
           MANAGING, CLOSED, LEARNED)


VALID_TRANSITIONS = {
    Stage.DETECTED: {Stage.QUALIFIED, Stage.REJECTED},
    Stage.QUALIFIED: {Stage.PENDING, Stage.ENTERED, Stage.REJECTED},
    Stage.PENDING: {Stage.ENTERED, Stage.VOIDED, Stage.REJECTED},
    Stage.ENTERED: {Stage.MANAGING, Stage.CLOSED},
    Stage.MANAGING: {Stage.CLOSED},
    Stage.CLOSED: {Stage.LEARNED},
    Stage.REJECTED: set(),
    Stage.VOIDED: set(),
    Stage.LEARNED: set(),
}


class InvalidTransition(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LifecycleRecord:
    """One symbol/direction opportunity's full chain state at a point in
    time. `lifecycle_id` is the stable key for the whole chain -- by design
    it is set to whichever of `decision_audit_history`'s `decision_id` /
    `pending.Pending.id` / `journal.Trade.id` was assigned FIRST for this
    opportunity (all three already share the exact same
    `f"{symbol}-{timestamp}"` construction -- see `journal.make_ref()` --
    so no new ID scheme is introduced here, this module just picks
    whichever one came first as the chain's anchor)."""
    lifecycle_id: str
    symbol: str
    direction: str
    stage: str
    trade_ref: str = ""      # set once ENTERED; == journal.Trade.id
    decision_id: str = ""    # most recent decision_audit_history decision_id, if any
    outcome: str = ""        # win | loss | scratch | expired (set at CLOSED)
    result_r: float = 0.0
    history: tuple = field(default_factory=tuple)
    created_ts: str = ""
    updated_ts: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["history"] = list(d["history"])
        return d


def new_lifecycle(lifecycle_id: str, symbol: str, direction: str,
                  reason: str = "", decision_id: str = "") -> LifecycleRecord:
    """Constructs a brand-new chain in `Stage.DETECTED`. Pure -- never
    raises (invalid inputs are the caller's responsibility, same
    convention as `order_state.new_order()`)."""
    ts = _now_iso()
    return LifecycleRecord(
        lifecycle_id=lifecycle_id, symbol=symbol, direction=direction,
        stage=Stage.DETECTED, decision_id=decision_id or lifecycle_id,
        history=({"stage": Stage.DETECTED, "ts": ts, "reason": reason},),
        created_ts=ts, updated_ts=ts,
    )


def can_transition(from_stage: str, to_stage: str) -> bool:
    return to_stage in VALID_TRANSITIONS.get(from_stage, set())


def transition(record: LifecycleRecord, to_stage: str, reason: str = "",
               **changes) -> LifecycleRecord:
    """Returns a NEW `LifecycleRecord` moved to `to_stage`, with the move
    appended to `history`. `**changes` may set any other field at the same
    time (`trade_ref=`, `outcome=`, `result_r=`, `decision_id=`) so, e.g.,
    the ENTERED transition can set `trade_ref` atomically with the stage
    change. Raises `InvalidTransition` if the move isn't in
    `VALID_TRANSITIONS` -- exact mirror of
    `order_state.transition()`/`InvalidTransition`."""
    if not can_transition(record.stage, to_stage):
        raise InvalidTransition(
            f"cannot move lifecycle {record.lifecycle_id!r} from "
            f"{record.stage!r} to {to_stage!r}")
    ts = _now_iso()
    new_history = record.history + ({"stage": to_stage, "ts": ts, "reason": reason},)
    return dataclasses.replace(record, stage=to_stage, history=new_history,
                               updated_ts=ts, **changes)


def is_terminal(stage: str) -> bool:
    return stage in Stage.TERMINAL


# --------------------------------------------------------------------------
# Persistence -- mirrors decision_audit_history.py's append/rotate/tail
# convention exactly. Every transition() result is written as a fresh, full
# row; nothing is ever edited in place.
# --------------------------------------------------------------------------

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


def record(rec: LifecycleRecord) -> dict:
    """Append one `LifecycleRecord` snapshot. Never raises; returns the
    dict that would have been written even if the write itself failed
    (same convention as `decision_audit_history.record()`)."""
    row = rec.as_dict()
    row.setdefault("record_type", "lifecycle")
    row["recorded"] = _now_iso()
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return row


def all_rows() -> list:
    return _read_all()


def tail(n: int = 20, symbol: str | None = None) -> list:
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def latest_for(lifecycle_id: str) -> dict | None:
    """The most recent persisted row for `lifecycle_id` -- its full current
    state (since every row is a complete snapshot, not a diff). O(n) scan,
    same disclosed trade-off as every other `find_by_ref()` in this
    codebase."""
    if not lifecycle_id:
        return None
    for r in reversed(_read_all()):
        if r.get("lifecycle_id") == lifecycle_id:
            return r
    return None


def find_by_trade_ref(trade_ref: str) -> dict | None:
    """Most recent row whose `trade_ref` matches -- the join point used by
    `sync_closures()` to find the chain for a journal row that just
    closed."""
    if not trade_ref:
        return None
    for r in reversed(_read_all()):
        if r.get("trade_ref") == trade_ref:
            return r
    return None


def chain_for(lifecycle_id: str) -> list:
    """Every persisted row for `lifecycle_id`, in write order -- the full
    physical audit trail (as opposed to `latest_for()`'s single current
    snapshot, whose own embedded `history` already logically contains the
    same information more compactly)."""
    if not lifecycle_id:
        return []
    return [r for r in _read_all() if r.get("lifecycle_id") == lifecycle_id]


def _rehydrate(row: dict) -> LifecycleRecord:
    return LifecycleRecord(
        lifecycle_id=row.get("lifecycle_id", ""), symbol=row.get("symbol", ""),
        direction=row.get("direction", ""), stage=row.get("stage", Stage.DETECTED),
        trade_ref=row.get("trade_ref", ""), decision_id=row.get("decision_id", ""),
        outcome=row.get("outcome", ""), result_r=float(row.get("result_r", 0.0) or 0.0),
        history=tuple(row.get("history", []) or ()),
        created_ts=row.get("created_ts", ""), updated_ts=row.get("updated_ts", ""),
    )


# --------------------------------------------------------------------------
# High-level, fail-safe helpers -- the actual call surface `alert_signals.py`
# uses. Each mirrors the "never raises, returns None on any failure" posture
# of every other `log_*` helper in this codebase.
# --------------------------------------------------------------------------

def seed_qualified(lifecycle_id: str, symbol: str, direction: str,
                   reason: str = "") -> dict | None:
    """DETECTED -> QUALIFIED in one call, for the common case where a
    signal was just confirmed to have passed confluence and this is the
    first time its chain is being recorded."""
    try:
        rec = new_lifecycle(lifecycle_id, symbol, direction, reason=reason)
        rec = transition(rec, Stage.QUALIFIED, reason=reason)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def seed_rejected(lifecycle_id: str, symbol: str, direction: str,
                  reason: str = "") -> dict | None:
    """DETECTED -> REJECTED in one call, for a signal that never even
    reached the heads-up stage (e.g. failed confluence outright)."""
    try:
        rec = new_lifecycle(lifecycle_id, symbol, direction, reason=reason)
        rec = transition(rec, Stage.REJECTED, reason=reason)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def mark_pending(lifecycle_id: str, symbol: str, direction: str,
                 reason: str = "") -> dict | None:
    """QUALIFIED -> PENDING. Defensive: if no prior chain is found for
    `lifecycle_id` (should not happen in normal operation -- the heads-up
    decision snapshot is always recorded first -- but this module must
    never assume upstream ordering), seeds a fresh QUALIFIED chain first
    so the call still succeeds rather than silently vanishing."""
    try:
        row = latest_for(lifecycle_id)
        rec = _rehydrate(row) if row else transition(
            new_lifecycle(lifecycle_id, symbol, direction, reason="(seeded defensively)"),
            Stage.QUALIFIED, reason="(seeded defensively)")
        rec = transition(rec, Stage.PENDING, reason=reason)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def mark_rejected(lifecycle_id: str, reason: str = "") -> dict | None:
    """-> REJECTED, from whatever stage the chain is currently in
    (DETECTED, QUALIFIED, or PENDING all allow it). Covers every reject
    call site in `alert_signals.py` uniformly -- the WHY lives in `reason`
    and in the upstream `decision_audit_history` row, not in a different
    target stage name per gate."""
    try:
        row = latest_for(lifecycle_id)
        if row is None:
            return None
        rec = transition(_rehydrate(row), Stage.REJECTED, reason=reason)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def mark_entered(lifecycle_id: str, trade_ref: str, symbol: str, direction: str,
                 reason: str = "") -> dict | None:
    """PENDING -> ENTERED, setting `trade_ref` atomically. Defensive same
    as `mark_pending()`: seeds QUALIFIED->PENDING first if no prior chain
    is found."""
    try:
        row = latest_for(lifecycle_id)
        rec = _rehydrate(row) if row else transition(transition(
            new_lifecycle(lifecycle_id, symbol, direction, reason="(seeded defensively)"),
            Stage.QUALIFIED, reason="(seeded defensively)"),
            Stage.PENDING, reason="(seeded defensively)")
        rec = transition(rec, Stage.ENTERED, reason=reason, trade_ref=trade_ref)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def mark_voided(lifecycle_id: str, reason: str = "") -> dict | None:
    """PENDING -> VOIDED (aged out without ever tapping)."""
    try:
        row = latest_for(lifecycle_id)
        if row is None:
            return None
        rec = transition(_rehydrate(row), Stage.VOIDED, reason=reason)
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def close_by_trade_ref(trade_ref: str, outcome: str, result_r: float,
                       reason: str = "") -> dict | None:
    """ENTERED/MANAGING -> CLOSED, keyed by `trade_ref` (== journal
    `Trade.id`) rather than `lifecycle_id`, since the caller (journal
    settlement) only knows the trade's own id, not the chain's original
    heads-up-time id."""
    try:
        row = find_by_trade_ref(trade_ref)
        if row is None:
            return None
        rec = transition(_rehydrate(row), Stage.CLOSED, reason=reason,
                         outcome=str(outcome or ""), result_r=float(result_r or 0.0))
        return record(rec)
    except Exception:  # noqa: BLE001
        return None


def stage_summary(days: int = 14, symbol: str | None = None) -> dict:
    """A count-by-current-stage snapshot across recent chains -- the
    dashboard-facing view of this module (mirrors
    qualification_diagnostics.py's own summary()-style aggregation, not a
    new pattern). Counts the LATEST row per lifecycle_id within the window
    (a chain that transitioned twice is counted once, at its current
    stage), not every physical row. Never raises."""
    from collections import Counter
    from datetime import datetime, timedelta, timezone
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = _read_all()
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        latest_by_id: dict = {}
        for r in rows:
            try:
                ts = r.get("updated_ts") or r.get("recorded") or ""
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except Exception:  # noqa: BLE001
                dt = None
            if dt is not None and dt < cutoff:
                continue
            lid = r.get("lifecycle_id")
            if not lid:
                continue
            latest_by_id[lid] = r  # rows are already in write order, last wins
        counts = Counter(r.get("stage", "") for r in latest_by_id.values())
        return {
            "version": VERSION, "window_days": days, "symbol": symbol or "all",
            "total_chains": len(latest_by_id),
            "by_stage": dict(counts),
            "advisory_only": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def sync_closures(symbol: str, rows: "list | None" = None) -> list:
    """Scans closed trades for `symbol` (from `trades.json` via
    `journal._load()` unless `rows` is given for offline testing) and
    closes any lifecycle chain that has a `trade_ref` but isn't CLOSED/
    LEARNED yet. Mirrors `paper_broker.PaperBroker.sync_closures()`'s exact
    idempotency idiom: check an "already done" condition per row, skip if
    so. This is what `alert_signals.py` calls right after
    `journal.settle()` each scan (same call site as
    `sync_paper_broker_closures()`). Never raises; skips a row on
    individual error rather than aborting the whole scan."""
    out = []
    try:
        if rows is None:
            from engine import journal as jr
            rows = jr._load()
        for row in rows:
            try:
                if row.get("symbol", "XAUUSD") != symbol:
                    continue
                if row.get("status") not in ("win", "loss", "scratch", "expired"):
                    continue
                trade_ref = row.get("id") or ""
                if not trade_ref:
                    continue
                existing = find_by_trade_ref(trade_ref)
                if existing is not None and existing.get("stage") in (Stage.CLOSED, Stage.LEARNED):
                    continue
                result = close_by_trade_ref(
                    trade_ref, outcome=row.get("status", ""),
                    result_r=row.get("result_r", 0.0),
                    reason="journal.settle() closure sync")
                if result is not None:
                    out.append(result)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return out
