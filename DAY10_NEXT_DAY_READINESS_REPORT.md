# Day 10 Next-Day Readiness Report

## The most important thing in this report

Experiment #0001 ("Observed Edge Deterioration Investigation") is
**registered, evidenced, and concluded at `performance_review` with
`decision = "research_further"`.** The deterioration Day 9 flagged is
**real and only ~25-30% explained by a genuine data-quality issue this
investigation discovered** (a settlement-methodology drift — see below).
Most of the decline remains unexplained. **This is not a verdict that the
platform's edge has decayed, and not a verdict that it hasn't** — it is an
honest "we don't know yet, and here specifically is what would let us
know," which is exactly what a Day-10-scoped investigation was supposed to
produce.

| Signal | Prior (69, as stored) | Prior (69, restated to current methodology) | Recent (30) |
|---|---|---|---|
| Expectancy | +1.22R | **+0.91R** | **-0.01R** |
| Profit factor | 3.47 | **2.85** | **0.99** |
| Win rate | 49.3% | 49.3% (unaffected — win formula, not win/loss outcome) | **26.7%** |
| Avg holding time | 63.9 min | — | **23.5 min** |

Full detail: `PERFORMANCE_INVESTIGATION_0001.md`.

## A new finding this Day surfaced, not previously known

Cross-checking every win's `result_r` against `engine/journal.py::_manage(
)`'s actual formula revealed that **88% of the prior window's wins (30 of
34) were settled under an older, simpler rule** (full target credited
directly, no partial banking) that predates the current breakeven/partial-
banking rule — and the switch happened **mid-way through the prior window
itself** (`2026-07-09` -> `2026-07-12`), never retroactively reapplied.
This was reconstructed entirely from stored `entry`/`stop`/`target` data,
independently verified, and is NOT a hypothesis — it's a directly-provable
fact about the dataset. It explains a real, quantified fraction of the
apparent decline (prior expectancy drops from +1.22R to +0.91R once
restated) but does not come close to explaining the recent window's
-0.01R.

## Remaining risks

1. **The core question — has genuine edge decay occurred? — is still
   open.** Two of the eight named root-cause hypotheses (Regime Shift,
   Risk Controls) could not be tested at all due to missing metadata, not
   because they were ruled out. This investigation cannot responsibly
   close the question with the data currently being logged.
2. **`trades.json`'s historical records still contain the legacy-rule
   values.** They were NOT corrected this Day (deliberately — see
   `DAY10_IMPLEMENTATION_REPORT.md` decision #2). Any future ad hoc
   look at `trades.json`'s raw numbers (outside `edge_investigation.py`'s
   restated view) will still show the inflated legacy-rule wins unless
   this is fixed or the reader knows to restate them.
3. **`confluence_score`/`confluence_ref`/`confidence_ref`/`regime_ref` are
   essentially never populated in the live journal** — not just for old
   trades (expected, pre-dates the ref system) but seemingly not being
   stamped consistently going forward either. This limits BOTH future
   investigations like this one AND the Day 6/7/8 systems' own ability to
   join back to specific trades for review.
4. **The permutation test's p-values (0.012 expectancy, 0.032 win rate)
   carry a real post-hoc-selection caveat** — don't over-quote them as a
   clean significance result in any future summary of this investigation.
5. **Session-effect and confidence-tier findings are drawn from small
   sub-samples** (n=7-9 per session, n=5 for the Exceptional-tier collapse)
   — directionally consistent with everything else in this report, but not
   independently conclusive at this size.

## Open questions for the platform owner

1. **Should `trades.json`'s legacy-rule wins be retroactively restated to
   the current methodology?** This investigation deliberately did NOT do
   this (Sec.9 of `PERFORMANCE_INVESTIGATION_0001.md`) — it's a real data
   change deserving its own explicit decision and its own experiment-
   registry entry, not a side effect of an investigation. Recommended as a
   small, well-scoped Day 11+ item if approved.
2. **Should the session-effect finding (Asian/London degradation) become
   its own dedicated experiment** — proposed via `experiment_registry.
   propose()`, run through `historical_testing` -> `walk_forward_testing`
   -> `paper_trading` before any production consideration — given it's the
   most concrete, actionable lead this investigation produced?
3. **Should regime/risk-guard metadata tagging coverage be improved before
   attempting hypotheses #2 and #6 again?** Without it, any future
   investigation into this same question will hit the identical wall.
4. **Given the deterioration is real and only partially explained, should
   Macro Intelligence (now Day 11) proceed as originally planned, or should
   the platform owner want one more narrowly-scoped session-effect/
   metadata-quality pass first?** This report recommends proceeding to Day
   11 as planned — Experiment #0001 concluded with specific, scoped, non-
   urgent follow-up items (Sec.8 of the investigation doc), none of which
   block new capability work, and the Day 10 mandate's own "no production
   changes made solely because of the investigation" criterion has been
   met — but the decision is the platform owner's.

## Prerequisites for future work building on this investigation

- Any future experiment addressing the settlement-methodology drift,
  session effects, or metadata-quality gaps should start with
  `experiment_registry.propose()` — a filled `Hypothesis` — exactly as
  Experiment #0001 did, per the Day 9 framework's own standing requirement.
- Any future segment or root-cause analysis on `trades.json` should reuse
  `engine.edge_investigation`'s functions (`data_quality_review()`,
  `restated_comparison()`, `segment_performance()`,
  `variance_permutation_test()`) rather than recomputing ad hoc — they are
  tested, reproducible, and already account for the settlement-methodology
  drift.
- If regime/guard-action tagging coverage is improved going forward, this
  investigation's two "inconclusive — data gap" hypotheses (Regime Shift,
  Risk Controls) should be re-run once enough newly-tagged trades
  accumulate — not treated as permanently closed.

## The permanent process rule adopted this Day

Per the platform owner's explicit request: **every 10 implementation days,
one dedicated Research & Validation day is scheduled before any new
production capability is added.** Recorded as standing policy in
`PROJECT_SUMMARY_AND_ROADMAP.md`. Days 9-10 count as this cycle's
instance (Day 9 built the framework, Day 10 was its first real use). The
next scheduled instance falls around Day 20, absent an earlier signal (as
happened here) that pulls one forward — any future roadmap planning should
check against this before scheduling ten consecutive new-capability days.

## Backlog items flagged during Day 10 (not implemented — explicitly deferred with reasoning)

| Item | Reasoning for deferral |
|---|---|
| Retroactively restate `trades.json`'s legacy-rule wins | Real data change, deserves its own explicit decision and registry entry — not a side effect of an investigation |
| Session-aware filter (Asian/London) as its own experiment | Concrete, evidence-backed lead, but needs its own full lifecycle (historical -> walk-forward -> paper trading) before any production consideration |
| Backfill/improve regime_trend/regime_vol/guard_action tagging coverage | Prerequisite for ever responsibly testing the Regime Shift / Risk Controls hypotheses |
| Investigate why confluence_score/confluence_ref/confidence_ref/regime_ref are ~0% populated in the live journal | Limits both this kind of investigation and the Day 6/7/8 systems' own trade-level review capability |
| Fix duplicate-`id` collisions (`journal.make_ref()` minute-granularity) | Reference-integrity issue for future ref-based lookups; would need its own scoped design (sub-minute disambiguator or explicit multi-row-per-id handling) |

## Verification before future work begins

- [x] Full test suite: 732/732 passing, 0 regressions
- [x] Zero production-path files reference `engine.edge_investigation`
      (grep-verified)
- [x] `trades.json`, `alert_signals.py`, `engine/journal.py`, `engine/
      dashboard_publish.py` confirmed byte-for-byte unchanged (mtime
      inspection, in addition to the grep check above)
- [x] Experiment #0001 fully registered (4 records: proposal, 2 stage
      transitions, 1 correction) with `decision = "research_further"`
- [x] Every finding independently reproduced by direct re-run against live
      `trades.json`, not just quoted from the test suite
- [x] `git status` clean of stray data-file artifacts
- [x] The Day 10 mandate's explicit success criterion — "no production
      changes made solely because of the investigation" — verified
      structurally, not just asserted
- [ ] Owner decision on the four open questions above, before Day 11
      (Macro Intelligence) begins
