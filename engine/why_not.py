"""V2.2 Priority 3 — Why-Not Engine live-query extension.

`explain_rejection()`/`explain_approval()`/`replay()` (Day 8,
engine/explainability_engine.py) already answer "why was THIS recorded
decision rejected/approved" comprehensively and well — nothing about that
code needed rebuilding (confirmed by reading it in full before writing
anything here). Auditing EXPLAINABILITY_SPECIFICATION.md against
PHASE0_FORENSIC_AUDIT.md's own reference ("Section 10", the doc's
"Dashboard integration" section) confirmed `dashboard_publish.py`'s
decision-audit payload matches what Sec.10 documents — no bug there
either.

The actual, disclosed gap is Sec.9.1/Sec.12 item 1 of that same spec:
two account-level gates — the platform-wide news blackout and the
per-symbol risk-guard day-stop lock checked BEFORE Layer 1 origination
runs — are, by deliberate and documented design, never turned into a
`DecisionSnapshot` (there is no specific candidate direction/opportunity
yet at the point either one fires, so a snapshot would misrepresent what
"a decision" means). That design choice was correct and is left
unchanged here. But it leaves a real, honest hole: if someone asks "why
wasn't I alerted on XAUUSD just now" during a news blackout or a Stage-1
risk lock, `decision_audit_history` has NOTHING to find — `explain_rejection()`
can't answer a question about a decision that, correctly, was never
recorded.

This module closes that hole with a live QUERY, not a new recording
mechanism: `why_not_now(symbol)` first checks `engine.kill_switch`'s
already-built (V2.2 Priority 2), already-tested stand-down reporter — the
exact live truth those two un-snapshotted gates represent — and only
falls back to the most recent PERSISTED decision (via
`decision_audit_history.tail()` + `explain_rejection()`, zero new
explanation logic) if nothing is currently standing the platform down.
Nothing here duplicates `kill_switch.py`, `decision_audit_history.py`, or
`explainability_engine.py` — it is a thin synthesis layer over the three,
in the same additive, standalone, not-wired-into-live-control-flow spirit
as every other Priority 2/3 module this cycle.
"""
from __future__ import annotations

from dataclasses import asdict

from . import decision_audit_history as dah
from . import explainability_engine as expl
from . import kill_switch


def _stand_down_dict(s) -> dict:
    try:
        return asdict(s)
    except Exception:  # noqa: BLE001
        return {"name": getattr(s, "name", ""), "engaged": bool(getattr(s, "engaged", False)),
               "scope": getattr(s, "scope", ""), "reason": getattr(s, "reason", "")}


def _stand_down_explanation(engaged: list) -> str:
    if not engaged:
        return ""
    parts = [f"{s.name} ({s.scope}): {s.reason}" if s.reason else f"{s.name} ({s.scope})"
            for s in engaged]
    return "Currently standing down — " + "; ".join(parts)


def why_not_now(symbol: str, *, settings=None, rows=None, now=None) -> dict:
    """Answer "why hasn't/wouldn't `symbol` get a signal right now" without
    requiring a persisted decision to already exist. Checks live
    account/symbol-level stand-downs FIRST (the exact gap
    `decision_audit_history` cannot answer — see module docstring), then
    falls back to the most recent recorded decision for this symbol, if
    any. Never raises — matches every other advisory module's fail-open
    contract this cycle; a total failure still returns a valid,
    clearly-labeled dict rather than raising."""
    try:
        stand_downs = kill_switch.current_stand_downs(
            symbol=symbol, settings=settings, rows=rows, now=now)
        engaged = [s for s in stand_downs if s.engaged]
        if engaged:
            return {
                "symbol": symbol,
                "answer_source": "active_stand_down",
                "explanation": _stand_down_explanation(engaged),
                "stand_downs": [_stand_down_dict(s) for s in stand_downs],
            }

        recent = dah.tail(1, symbol=symbol)
        row = recent[-1] if recent else None
        if row is None:
            return {
                "symbol": symbol,
                "answer_source": "no_data",
                "stand_downs": [_stand_down_dict(s) for s in stand_downs],
                "note": (
                    "No active platform/symbol stand-down and no recorded decision for "
                    "this symbol. Most likely no qualifying setup has been identified this "
                    "session yet — Layer 1 origination (ICT/SMC) simply hasn't found one. "
                    "(News blackout and the pre-origination risk lock are, by design, the "
                    "only two gates that would ALSO produce no recorded decision even when "
                    "they are the actual reason — see EXPLAINABILITY_SPECIFICATION.md "
                    "Sec.9.1 — but those are already ruled out above since no stand-down is "
                    "currently engaged.)"),
            }

        if row.get("final_action") == "rejected":
            return {
                "symbol": symbol,
                "answer_source": "recorded_rejection",
                "stand_downs": [_stand_down_dict(s) for s in stand_downs],
                "explanation": expl.explain_rejection(row),
            }

        return {
            "symbol": symbol,
            "answer_source": "recorded_approval",
            "stand_downs": [_stand_down_dict(s) for s in stand_downs],
            "note": (
                f"No active stand-down, and the most recent recorded decision for "
                f"{symbol} was '{row.get('final_action')}', not a rejection — there is no "
                f"active rejection to explain right now."),
            "most_recent_decision_id": row.get("decision_id"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "answer_source": "error", "error": f"why_not_now error: {exc}"}
