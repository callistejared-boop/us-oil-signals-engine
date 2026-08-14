# Promotion Pipeline Enforcement — engine/promotion_gate.py

**V2.2 Priority 5, Item 1**

## 1. What the gap matrix flagged

`PHASE0_GAP_MATRIX.md`:

> Promotion Pipeline | Designed, not enforced (`experiment_registry.py` +
> `STRATEGY_RESEARCH_FRAMEWORK.md`/`RESEARCH_VALIDATION_SPECIFICATION.md`)
> | No programmatic stage-gating | Build enforcement layer on existing
> design. (Needs the Shadow-mode decision resolved first.)

The Shadow-mode decision (Priority 4 Item 2) is resolved
(`SHADOW_MODE_VS_PAPER_BROKER_DECISION.md`), so this Item was unblocked.

## 2. Reading the existing design before building anything

`RESEARCH_VALIDATION_SPECIFICATION.md` Sec.2, verbatim:

> Every stage has documented entry/exit criteria
> (`experiment_registry.STAGE_CRITERIA`) — descriptive guidance surfaced
> to researchers ..., NOT programmatically enforced. This is a deliberate
> choice: the mandate's governing principle is that this framework governs
> research, not production, and heavy-handed programmatic gating of a
> RESEARCH workflow would itself be a form of production-like rigidity
> this framework is meant to avoid. A human ... makes every promotion
> decision; the registry records it.

`engine/evidence_tiers.py`'s own docstring is equally explicit: tiers are
"descriptive labels, not gates — nothing in this codebase blocks on a
tier." And `experiment_registry.transition()` is documented to never
refuse a write, for any stage, in any order — the same "disclose, don't
hide" convention this whole research framework uses.

**This meant a literal "prevent a strategy from being marked
production-ready" write-blocking gate would have contradicted an
explicit, already-recorded design decision** — not an oversight, a
deliberate choice with its own stated rationale. Overriding it silently
would have been the wrong call.

## 3. What "enforcement" means here instead

The actual gap was narrower than "nothing stops a bad promotion": it was
that nothing could ANSWER, programmatically, whether a given promotion
was legitimate. That question was previously only answerable by a human
reading the full `experiment_registry.jsonl` history by hand, one
experiment at a time.

`engine/promotion_gate.py` (new, additive, no changes to
`experiment_registry.py`) answers it:

- `evaluate(experiment_id)` replays one experiment's full history against
  the required stage sequence (`research_proposal` through
  `performance_review` — every stage before `production_recommendation`,
  `idea` excluded since it's documented as optional) and returns
  `eligible_for_production`, exactly which stages are missing, whether
  the hypothesis was ever completed, whether evidence was recorded at
  `paper_trading`/`performance_review`, and — only if the experiment's
  CURRENT stage actually claims `production_recommendation`/
  `controlled_release`/`ongoing_monitoring` — whether that promotion was
  `premature_promotion`.
- `audit_all()` sweeps every experiment in the registry and returns only
  the ones flagged premature — a retroactive-disclosure view.
- `summary()` — the dashboard-ready aggregate (counts + flagged list +
  `healthy: bool`), wired additively into
  `research_dashboard.build_research_payload()` as a new
  `promotion_pipeline_audit` key, following that function's existing
  per-section `try/except` discipline so one failure can't blank the rest
  of the payload.

Nothing here can block or delay an `experiment_registry.transition()`
call — proven by a dedicated test
(`test_promotion_gate_never_blocks_experiment_registry_writes`) that
transitions a flagrantly incomplete experiment straight to
`production_recommendation` and confirms the write still succeeds. This
is the same "warn, don't block" precedent as
`config.portfolio_risk_mode = "warn"` and `range_guard.py`'s
`SUPPRESS_MODE` — the violation becomes impossible to miss, without
being the thing that stops the action. A future promotion-approval
workflow (human or automated) is expected to call `evaluate()` before
acting on a `production_recommendation`, but that remains a choice for
that future caller to make, per the framework's own stated governing
principle.

## 4. Test coverage

`tests/test_promotion_gate.py`, 13 tests: legitimate full-path promotion
is eligible and never flagged (2 tests), skipped stages / incomplete
hypothesis / missing evidence at `paper_trading` or `performance_review`
/ invalid stage records each independently block eligibility and surface
in `blocking_reasons` (5 tests), `audit_all()` correctly separates a
legitimate promotion from a premature one (1 test), an experiment still
mid-research is never flagged premature just for being incomplete (1
test — `premature_promotion` only evaluates promoted-or-beyond current
stages), `idea` being absent doesn't block eligibility since it's
documented optional (1 test), the write-non-blocking structural proof (1
test), and `summary()`'s healthy/unhealthy aggregate behavior (2 tests).

Full suite: 1559/1559 passing (1546 prior + 13 new).
