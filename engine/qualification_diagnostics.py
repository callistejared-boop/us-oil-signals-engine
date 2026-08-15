"""V2.2 Priority 5 (extension) — Qualification Diagnostics.

Audit trigger: a live diagnostic pass on 2026-08-15 found 79/79 decisions
recorded in `decision_audit.jsonl` since 2026-08-06 were rejected — zero
approvals across all 4 symbols in 9+ tracked days, 82% of those rejections
at the `confluence_assessment` stage. That picture was reconstructed by
hand (one-off JSONL parsing in a shell session) because no standing view
answers "why is qualification rate so low, and by how much" as a queryable
report. This module IS that view.

Read-only, reuses existing infrastructure exactly as it already exists —
no new persistence, no new scoring logic, no config change, no production
behavior touched (same posture as `promotion_gate.py` and
`opportunity_ranking.py` this cycle):

  - `engine.decision_audit_history` (Day 8) — every Stage-1/Stage-2
    decision, `final_action`/`stage`/`rejection.category`/
    `confluence_summary.score`.
  - `engine.ledger` (existing) — `run_ledger.jsonl`'s `confluence_held`
    events carry the full `disagree` list (the denormalized
    `confluence_summary` in `decision_audit.jsonl` only stores
    `agree_count`/`disagree_count`, not the names — see
    `decision_audit_history.py`'s own module docstring for why that
    summary is deliberately small). `ledger.py` only exposes `tail(n)`,
    capped at `ledger.MAX_LINES` (5000) by its own rotation — this module
    calls `tail(ledger.MAX_LINES)` to see everything currently retained,
    and discloses that cap rather than silently assuming a longer history
    exists.
  - `engine.regime_history` (Day 4) — most recent regime read per symbol,
    for context on whether a low qualification rate coincides with
    genuinely low-quality (choppy/ranging) market conditions.
  - `engine.kill_switch` (V2.2 Priority 2) — current portfolio-wide
    stand-down state, since a `drawdown_protection` stand-down produces
    the exact same symptom (zero approvals) as a confluence/threshold
    issue but has a completely different fix.
"""
from __future__ import annotations

import pathlib
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import decision_audit_history as dah   # noqa: E402
from engine import ledger                          # noqa: E402
from engine import regime_history as rh            # noqa: E402
from engine import kill_switch                     # noqa: E402
from engine import markets, config                 # noqa: E402

VERSION = "1.0.0"


def _parse_ts(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:  # noqa: BLE001
        return None


def _within_window(row: dict, cutoff) -> bool:
    ts = _parse_ts(row.get("recorded") or row.get("ts") or "")
    return ts is not None and ts >= cutoff


def rejection_summary(days: int = 14) -> dict:
    """Breaks down every DecisionSnapshot recorded in the last `days` days
    by final_action, by rejection stage, by rejection category, and the
    confluence score distribution among candidates that reached
    `confluence_assessment`. Never raises — a read failure degrades to an
    empty, clearly-labeled result rather than blanking the caller."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = [r for r in dah.all_rows() if _within_window(r, cutoff)]
        rejected = [r for r in rows if r.get("final_action") == "rejected"]
        stage_counts = Counter(r.get("stage") for r in rejected)
        category_counts = Counter((r.get("rejection") or {}).get("category") for r in rejected)

        scores = sorted(
            s for r in rows if r.get("stage") == "confluence_assessment"
            for s in [(r.get("confluence_summary") or {}).get("score")]
            if isinstance(s, (int, float)))

        score_stats = None
        if scores:
            n = len(scores)
            score_stats = {
                "n": n, "min": scores[0], "median": scores[n // 2], "max": scores[-1],
                "near_threshold_60_to_70": sum(1 for s in scores if 60 <= s < 70),
            }

        return {
            "days": days,
            "decisions_in_window": len(rows),
            "final_action_counts": dict(Counter(r.get("final_action") for r in rows)),
            "rejection_stage_counts": dict(stage_counts),
            "rejection_category_counts": {k or "unlabeled": v for k, v in category_counts.items()},
            "confluence_score_distribution": score_stats,
        }
    except Exception as exc:  # noqa: BLE001
        return {"days": days, "error": str(exc)}


def disagree_frequency(top: int = 15) -> dict:
    """Which MAST confirmation sources most often disagree on a held
    candidate, over every `confluence_held` event `ledger.py` currently
    retains. Disclosed limitation: `ledger.py` rotates at `ledger.MAX_LINES`
    — this is "most recent retained history," not necessarily the full
    lifetime record. Never raises."""
    try:
        rows = ledger.tail(ledger.MAX_LINES)
        held = [r for r in rows if r.get("event") == "confluence_held"]
        counts = Counter()
        for r in held:
            for d in r.get("disagree", []) or []:
                counts[d] += 1
        return {
            "ledger_events_scanned": len(rows),
            "ledger_retention_cap": ledger.MAX_LINES,
            "confluence_held_events": len(held),
            "top_disagreeing_checks": counts.most_common(top),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def current_regime_snapshot(symbols=None) -> dict:
    """Most recently RECORDED regime read per symbol (Day 4's own
    `regime_history.last_for()`, never a fresh recompute — same posture as
    `dashboard_publish.py`'s `macro_advisory`). Context for whether a low
    qualification rate coincides with genuinely low-quality market
    conditions platform-wide, not just one symbol. Never raises — a
    missing/errored symbol is reported as `None`, not silently dropped."""
    out = {}
    syms = symbols if symbols is not None else markets.symbols(config.load())
    for sym in syms:
        try:
            row = rh.last_for(sym)
            out[sym] = ({
                "primary": row.get("primary") or (row.get("result") or {}).get("primary"),
                "quality_score": row.get("quality_score") or (row.get("result") or {}).get("quality_score"),
                "confidence": row.get("confidence") or (row.get("result") or {}).get("confidence"),
                "recorded": row.get("ts") or row.get("recorded"),
            } if row else None)
        except Exception as exc:  # noqa: BLE001
            out[sym] = {"error": str(exc)}
    return out


def summary(days: int = 14, symbols=None) -> dict:
    """The full diagnostic payload — every section wrapped independently
    (same `errors`-dict discipline as `research_dashboard.build_research_
    payload()`) so one failure can't blank the rest. Advisory only: this
    never blocks, gates, or changes any live decision — it only makes an
    already-recorded pattern visible without requiring a human to re-parse
    JSONL by hand."""
    try:
        stand_downs = [
            {"name": s.name, "engaged": s.engaged, "scope": s.scope, "reason": s.reason}
            for s in kill_switch.current_stand_downs(settings=config.load())]
    except Exception as exc:  # noqa: BLE001
        stand_downs = [{"error": str(exc)}]

    return {
        "advisory_only": True,
        "note": "Why qualification rate is what it is — rejection patterns and their "
               "likely cause (confluence bar vs. portfolio stand-down vs. market regime). "
               "Never blocks, gates, or changes any live decision.",
        "version": VERSION,
        "rejection_summary": rejection_summary(days),
        "disagree_frequency": disagree_frequency(),
        "current_regime": current_regime_snapshot(symbols),
        "current_stand_downs": stand_downs,
    }
