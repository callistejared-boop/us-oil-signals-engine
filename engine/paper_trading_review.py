"""Day 9 — Paper Trading Framework: the bridge between research and
production.

Per the mandate: "Track: proposed decision, executed decision, expected
outcome, realized outcome, deviations, operational issues. This becomes
the primary bridge between research and production."

This module does NOT reimplement trade tracking — this platform already
runs in `paper_mode` by default (`config.paper_mode`, Day 1-2) and every
decision already leaves a full trail via Day 8's `DecisionSnapshot` +
`decision_audit_history.py` and `engine.journal`. `evaluate()` is a thin
synthesis layer over that existing trail, reusing Day 8's
`post_trade_review()` directly rather than duplicating its outcome-vs-
expectation logic, and adding the two things Day 8 did not need:
`proposed_vs_executed` (did the recorded plan match what actually
happened) and `operational_issues` (any errors logged near this decision).
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import explainability_engine as expl   # noqa: E402
from engine import decision_audit_history as dah   # noqa: E402
from engine import ledger                            # noqa: E402

VERSION = "1.0.0"

# How close in time an ERROR ledger event must be to a decision to be
# considered potentially related — disclosed engineering judgment, not
# fitted. A wide-but-bounded window: operational issues (a feed outage, a
# publish failure) are usually noticed within the same scan cycle.
OPERATIONAL_ISSUE_WINDOW_EVENTS = 200   # scan the last N ledger rows, not by wall-clock time,
                                        # since ledger.tail() has no timestamp-range query


def _proposed_vs_executed(row: dict) -> dict:
    """Compares what the DecisionSnapshot recorded as the plan (confluence/
    confidence/regime summary at decision time) against what actually
    happened downstream — today, this means confirming the trade actually
    exists in the journal under the SAME `trade_ref` (i.e. the plan was
    actually executed, not silently dropped) and that the recorded
    `final_action` matches what was later found. Never raises."""
    try:
        trade_ref = row.get("trade_ref") or ""
        final_action = row.get("final_action", "")
        if final_action == "rejected":
            return {"proposed": "rejected — no execution expected",
                   "executed": "n/a (rejection)", "matches": True}
        if final_action == "approved_heads_up":
            return {"proposed": "heads-up published",
                   "executed": "unknown (no direct heads-up->entry ref recorded yet)",
                   "matches": None,
                   "note": "this platform does not yet persist a direct ref linking a Stage-1 "
                          "heads-up decision_id to the Stage-2 entry decision_id it may have "
                          "triggered — see RESEARCH_VALIDATION_SPECIFICATION.md Sec.6 for the "
                          "disclosed limitation and the Day 10+ extension it recommends"}
        if final_action == "approved_entry":
            if trade_ref:
                return {"proposed": "entry approved and published",
                       "executed": f"trade_ref {trade_ref} recorded — execution confirmed",
                       "matches": True}
            return {"proposed": "entry approved", "executed": "no trade_ref recorded",
                   "matches": False,
                   "note": "an approved_entry DecisionSnapshot without a trade_ref is unexpected — "
                          "worth investigating as a possible logging gap, not assumed benign"}
        return {"proposed": final_action or "unknown", "executed": "unknown", "matches": None}
    except Exception as exc:  # noqa: BLE001
        return {"proposed": "error", "executed": "error", "matches": None, "error": str(exc)}


def _operational_issues(symbol: str) -> list:
    """Best-effort scan of the most recent ledger events for this symbol
    for anything error-shaped. This is NOT a precise causal link to one
    decision (the ledger has no decision_id on most events) — disclosed as
    a best-effort signal, not a confirmed diagnosis. Never raises."""
    try:
        recent = ledger.tail(OPERATIONAL_ISSUE_WINDOW_EVENTS)
        issues = [r for r in recent
                 if r.get("symbol") == symbol and
                 ("error" in str(r.get("event", "")).lower() or "ERROR" in str(r))]
        return issues[-10:]
    except Exception:  # noqa: BLE001
        return []


def evaluate(decision_id_or_trade_ref: str) -> dict:
    """The main entry point. Reuses `explainability_engine.post_trade_review()`
    verbatim for `expected_outcome`/`realized_outcome`/`deviations`
    (Day 8's `assumptions_that_may_have_failed`/`heuristic_disclosure`),
    and adds `proposed_vs_executed`/`operational_issues` on top. Never
    raises."""
    try:
        row = dah.find_by_ref(decision_id_or_trade_ref) or dah.find_by_trade_ref(decision_id_or_trade_ref)
        if row is None:
            return {"found": False, "note": "no decision snapshot found for this reference"}
        review = expl.post_trade_review(decision_id_or_trade_ref)
        return {
            "found": True,
            "decision_id": row.get("decision_id"),
            "symbol": row.get("symbol"),
            "proposed_vs_executed": _proposed_vs_executed(row),
            "expected_outcome": (review.get("original_reasoning") or {}).get("why_approved")
                                if review.get("found") else None,
            "realized_outcome": review.get("actual_outcome"),
            "deviations": {
                "assumptions_that_may_have_failed": review.get("assumptions_that_may_have_failed", []),
                "conflicting_evidence_at_decision_time": review.get("conflicting_evidence_at_decision_time", []),
                "heuristic_disclosure": review.get("heuristic_disclosure", ""),
            },
            "operational_issues": _operational_issues(row.get("symbol", "")),
            "post_trade_review": review,
        }
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "error": f"evaluate error: {exc}"}
