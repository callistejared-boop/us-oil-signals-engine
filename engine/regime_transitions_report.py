"""V2.2 Priority 3 — Regime Transition Reporting.

`PHASE0_FORENSIC_AUDIT.md` Section P listed "explicit regime-transition
event detection/logging (e.g. a logged TRENDING->RANGING event)" as a
missing capability, recommending "extend regime_engine.py's existing
transition_risk score into a discrete logged event." Auditing
engine/regime_history.py before building anything showed that discrete
event already exists -- `record()` (Day 4, unchanged since) computes
`transition_event` (bool), `transition_from`, and `duration_s_since_prev`
on every call by comparing against `last_for()`'s previous entry, and
`transitions()` already filters history down to just those event rows.
This is wired into the LIVE pipeline: alert_signals.py::main() calls
`rhist.record(sym, "strategic", mkt_regime)` every scan cycle, for every
symbol. Checking the live regime_history.jsonl confirms this isn't
theoretical -- 42 real transition events recorded across 595
classifications as of this check (e.g. "WTIUSD: Range -> Distribution").

So the audit's framing was inaccurate for this item: nothing needed
re-building. What auditing DID surface is a real, narrower gap -- grepping
the codebase for `transition_event`, `transition_from`, and
`duration_s_since_prev` outside regime_history.py itself and its own test
file returns zero hits. The data is detected, logged, and queryable via
`transitions()`, but nothing anywhere turns it into something a person
would actually look at -- no dashboard section, no alert, no explainability
mention. It's fully-functional, tested, live infrastructure that nobody
can currently see.

This module closes that specific, narrower gap: a thin, read-only
formatting/reporting layer on top of the untouched `regime_history.py`
data, in the same spirit as grade.py ("this module adds no new judgment
of its own, it only relabels what confluence.py already decided"). It
does not change transition detection, does not add new persisted state,
and is not wired into alert_signals.py's control flow -- same additive
posture as decision_gate.py, kill_switch.py, and opportunity_ranking.py.
A future dashboard/explainability/Telegram integration can call
`recent_transitions_summary()` directly; that wiring decision is left for
later, same as the other Priority 2/3 modules.
"""
from __future__ import annotations

from . import regime_history as rhist


def format_transition(row: dict) -> str:
    """One human-readable line for a single transition row (a dict as
    returned by regime_history.transitions()/tail()). Never raises --
    missing fields degrade to '?' rather than throwing, matching this
    codebase's general fail-open posture for advisory/reporting code."""
    symbol = row.get("symbol") or "?"
    frm = row.get("transition_from") or "?"
    to = row.get("primary") or "?"
    ts = row.get("ts") or "?"
    dur = row.get("duration_s_since_prev")
    if dur is not None:
        mins = dur / 60.0
        if mins >= 60:
            dur_str = f"after {mins / 60:.1f}h in {frm}"
        else:
            dur_str = f"after {mins:.0f}min in {frm}"
    else:
        dur_str = f"from {frm}"
    return f"{symbol}: {frm} -> {to} ({dur_str}) at {ts}"


def recent_transitions_summary(symbol: "str | None" = None, n: int = 10) -> list:
    """Human-readable summaries of the most recent N transition events,
    most recent last (same ordering regime_history.transitions() already
    returns). Thin wrapper -- all detection/filtering logic stays in
    regime_history.py; this only formats. Never raises; [] on no data or
    any read failure (regime_history._read_all() already fails safe to []
    on a corrupt/missing file)."""
    rows = rhist.transitions(symbol=symbol, n=n)
    return [format_transition(r) for r in rows]


def transition_frequency(symbol: str, hours: float = 24.0) -> dict:
    """Count of transition events for `symbol` within the trailing
    `hours` window, plus the most recent one if any -- a quick "is this
    symbol's regime flip-flopping or stable right now" read. Pulls a
    generous tail (200 rows) rather than the full history, matching the
    'never raises, degrades gracefully' posture used throughout this
    codebase's advisory reporting."""
    from datetime import datetime, timezone, timedelta
    rows = rhist.transitions(symbol=symbol, n=200)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    in_window = []
    for r in rows:
        ts = r.get("ts")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts)
        except Exception:  # noqa: BLE001
            continue
        if t >= cutoff:
            in_window.append(r)
    return {
        "symbol": symbol,
        "window_hours": hours,
        "count": len(in_window),
        "most_recent": format_transition(in_window[-1]) if in_window else None,
    }
