"""V2.2 Priority 5, Item 1 — Promotion Pipeline enforcement layer.

`RESEARCH_VALIDATION_SPECIFICATION.md` Sec.2 and `engine/evidence_tiers.py`
both state a deliberate design choice: `experiment_registry.transition()`
never blocks a write, and evidence tiers are "descriptive labels, not
gates." That choice stands — this module does NOT change it. Nothing here
adds a mutator, and nothing here prevents `experiment_registry.transition()`
from recording any stage, in any order, at any time. Blocking the
append-only research record would contradict the framework's own stated
governing principle ("this framework governs research, not production")
and its "disclose, don't hide" convention (see
`SHADOW_MODE_VS_PAPER_BROKER_DECISION.md` for the same discipline applied
to a different Priority 4/5 decision).

What WAS a genuine gap (`PHASE0_GAP_MATRIX.md`: "Promotion Pipeline |
Designed, not enforced ... No programmatic stage-gating | Build
enforcement layer on existing design"): there was no programmatic way to
ask "did this experiment actually earn its current stage, or did someone
(or some future automation) skip straight to `production_recommendation`
without walk-forward or paper evidence?" That question was previously
answerable only by a human re-reading the full JSONL history by hand.

This module answers it programmatically, read-only:

- `evaluate(experiment_id)` replays one experiment's full history against
  the required stage sequence and returns a structured verdict —
  `eligible_for_production`, exactly which required stages are missing,
  whether the hypothesis was ever completed, whether evidence was
  recorded at `paper_trading`/`performance_review`, and (if the
  experiment's CURRENT stage is `production_recommendation`,
  `controlled_release`, or `ongoing_monitoring`) whether that promotion
  was premature.
- `audit_all()` sweeps every experiment in the registry and surfaces only
  the ones flagged `premature_promotion` — the retroactive-disclosure
  view: violations become visible instead of silently sitting in a JSONL
  file nobody re-audits.

This is "enforcement" in the same sense `config.portfolio_risk_mode =
"warn"` and `range_guard.py`'s `SUPPRESS_MODE` are enforcement: it makes
the violation impossible to miss, without being the thing that blocks the
action. A future caller (a controlled-release automation script, a
promotion-approval UI, `research_dashboard.py`) can and should call
`evaluate()` BEFORE acting on a `production_recommendation`, but nothing
in `experiment_registry.py` is changed to force that — per the framework's
own stated principle, that remains a human decision this module informs.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import experiment_registry as er  # noqa: E402

VERSION = "1.0.0"

# Every stage that must be reached before `production_recommendation` is
# legitimate, per `RESEARCH_VALIDATION_SPECIFICATION.md` Sec.2's own
# lifecycle diagram. "idea" is deliberately excluded — `log_idea()` is
# documented as the "lightest-weight" optional entry point, and `propose()`
# can legitimately be called directly without a prior `log_idea()` call
# (see `experiment_registry.propose()`'s own docstring/signature: it
# accepts an optional pre-existing `experiment_id` but does not require
# one). Requiring "idea" would flag every experiment that (correctly)
# started at `research_proposal` as illegitimate.
_PROMOTION_STAGE = "production_recommendation"
_PROMOTION_IDX = er.LIFECYCLE_STAGES.index(_PROMOTION_STAGE)
REQUIRED_BEFORE_PROMOTION = [s for s in er.LIFECYCLE_STAGES[1:_PROMOTION_IDX]]
_PROMOTED_OR_BEYOND = {"production_recommendation", "controlled_release", "ongoing_monitoring"}


def evaluate(experiment_id: str) -> dict:
    """Replay one experiment's full append-only history and assess
    whether its current stage was legitimately earned. Never raises, never
    writes — pure read + derive, same discipline as
    `experiment_registry.current_state()` itself."""
    try:
        rows = er.history(experiment_id)
        if not rows:
            return {"experiment_id": experiment_id, "found": False,
                    "version": VERSION}

        state = er.current_state(experiment_id)
        current_stage = state.get("current_stage") if state else None

        reached: list = []
        invalid_stage_records: list = []
        hypothesis_complete = None
        evidence_by_stage: dict = {}

        for r in rows:
            stage = r.get("stage")
            if r.get("record_type") == "proposal":
                if stage in er.ALL_STAGES and stage not in reached:
                    reached.append(stage)
                if r.get("hypothesis") is not None:
                    hypothesis_complete = bool(r.get("complete"))
            elif r.get("record_type") == "stage_transition":
                if r.get("valid_stage", True) and stage in er.ALL_STAGES:
                    if stage not in reached:
                        reached.append(stage)
                    if r.get("evidence"):
                        evidence_by_stage[stage] = r["evidence"]
                else:
                    invalid_stage_records.append(
                        {"stage": stage, "recorded": r.get("recorded")})

        reached_set = set(reached)
        missing_required = [s for s in REQUIRED_BEFORE_PROMOTION if s not in reached_set]
        evidence_at_paper = evidence_by_stage.get("paper_trading")
        evidence_at_review = evidence_by_stage.get("performance_review")

        blocking_reasons = []
        if missing_required:
            blocking_reasons.append(
                "missing required stage(s): " + ", ".join(missing_required))
        if hypothesis_complete is None:
            blocking_reasons.append(
                "no hypothesis recorded (propose() was never called)")
        elif hypothesis_complete is False:
            blocking_reasons.append(
                "hypothesis recorded but incomplete (missing measurable_success_criteria "
                "and/or rollback_criteria)")
        if not evidence_at_paper:
            blocking_reasons.append(
                "no evidence recorded at the paper_trading stage transition")
        if not evidence_at_review:
            blocking_reasons.append(
                "no evidence recorded at the performance_review stage transition")
        if invalid_stage_records:
            blocking_reasons.append(
                f"{len(invalid_stage_records)} invalid/unrecognized stage record(s) in history")

        eligible_for_production = len(blocking_reasons) == 0
        is_promoted_or_beyond = current_stage in _PROMOTED_OR_BEYOND

        return {
            "experiment_id": experiment_id,
            "found": True,
            "current_stage": current_stage,
            "stages_reached": reached,
            "required_before_promotion": REQUIRED_BEFORE_PROMOTION,
            "missing_required_stages": missing_required,
            "hypothesis_complete": hypothesis_complete,
            "evidence_recorded_at_paper_trading": bool(evidence_at_paper),
            "evidence_recorded_at_performance_review": bool(evidence_at_review),
            "invalid_stage_records": invalid_stage_records,
            "eligible_for_production": eligible_for_production,
            "premature_promotion": bool(is_promoted_or_beyond and not eligible_for_production),
            "blocking_reasons": blocking_reasons,
            "version": VERSION,
        }
    except Exception as exc:  # noqa: BLE001
        return {"experiment_id": experiment_id, "found": False,
                "error": str(exc), "version": VERSION}


def audit_all() -> list:
    """Sweep every experiment in the registry; return only the ones whose
    current stage is `production_recommendation`/`controlled_release`/
    `ongoing_monitoring` but that did NOT legitimately earn it — the
    retroactive-disclosure view. An empty list is the healthy state.
    Never raises."""
    try:
        return [v for eid in er.all_experiment_ids()
               if (v := evaluate(eid)).get("premature_promotion")]
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]


def summary() -> dict:
    """Aggregate view for `research_dashboard.py` — counts plus the
    flagged list, wrapped so one failure can't blank the whole research
    payload (same `errors`-dict discipline as
    `research_dashboard.build_research_payload()`)."""
    try:
        ids = er.all_experiment_ids()
        flagged = audit_all()
        return {
            "note": "Programmatic check of whether each experiment's current stage was "
                   "legitimately earned per the required idea->...->performance_review "
                   "sequence before production_recommendation. Informational — does not "
                   "block experiment_registry writes or any production behavior.",
            "experiments_evaluated": len(ids),
            "flagged_premature_promotions": flagged,
            "healthy": len(flagged) == 0,
            "version": VERSION,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "version": VERSION}
