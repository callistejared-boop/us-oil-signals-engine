# Day 6 Next-Day Readiness Report

## Remaining risks

1. **The composite formula is entirely unvalidated against real outcomes.**
   `overall_confidence`'s five-term formula (Sec.3.1 of
   `CONFIDENCE_ENGINE_SPECIFICATION.md`) passed every unit test asserting
   its INTERNAL consistency (each term moves the score in its documented
   direction), but zero real trades have been scored by it yet. Treat
   every `overall_confidence` value produced in the near term as
   provisional — the framework exists specifically to catch and correct
   this once data arrives, but that hasn't happened yet.
2. **`is_calibrated` will read `False` on every message for a long time.**
   This is intentional and honest, but worth flagging so it isn't mistaken
   for a bug when reviewing early live output — the platform needs ~30
   matched trades in a single confidence bucket before any bucket can show
   `True`, and total historical trade count across ALL four symbols is
   only ~100 since inception.
3. **The two `confluence.py` observability fixes are the first edits to
   that file since the Day 5 audit.** They were pre-approved by name in
   the Day 6 mandate and scoped tightly, but any future day that needs to
   touch `confluence.py` again should re-read `CONFLUENCE_SPECIFICATION.md`
   §2 first — the file's independence findings are sensitive to exactly
   which labels exist and how they're worded (see the label-matching
   regression test).
4. **Regime data still lacks a `ref` field**, so `Trade.confluence_ref`/
   `confidence_ref` exist but there is no equivalent `Trade.regime_ref`.
   A future day extending `regime_history.py` the same way should also
   consider whether journal.py should grow a third `ref` field, or whether
   two is enough given regime's advisory-only status (Day 4).
5. **`dashboard_publish.py`'s confidence block adds two extra function
   calls (`regime_engine.classify()`, `portfolio_risk.evaluate()`) to every
   dashboard payload build.** Both are already cheap (used elsewhere in
   the same file/process), but if the dashboard is ever built for many
   symbols on a tight refresh interval, this is worth profiling — not
   measured this session.

## Open questions for the platform owner

1. Should `regime_history.py` be extended with a `ref` parameter to match
   `confluence_history.py`'s Day 6 addition, closing the last remaining
   timestamp-joined history log? This is the most direct, lowest-risk
   follow-up to today's work — the pattern (add an optional `ref=""`
   keyword param, backward compatible) is now proven twice.
2. Given that `overall_confidence`'s formula cannot be validated
   term-by-term at current trade volumes (see
   `RESEARCH_CONFIDENCE_ENGINE.md` §6), is the priority for future days to
   (a) let more live data accumulate before building anything further on
   top of the Confidence Engine, or (b) proceed with whatever Day 7 has
   planned in parallel, treating calibration as a background process that
   improves on its own timeline? Both are reasonable; this is a
   sequencing preference, not a technical blocker.
3. `confidence_calibration.report()` and the pre-existing `calibration.report()`
   now both exist, calibrating two different (but related) numbers. Once
   real data exists, should these be surfaced side-by-side somewhere (e.g.
   the hourly briefing or self-review page) so an operator can see whether
   the Day 6 composite actually improves on raw Layer-1 calibration? This
   is flagged as the single most direct value-add test in
   `RESEARCH_CONFIDENCE_ENGINE.md` §7 but wasn't built into any UI this
   session.

## Prerequisites for future work building on the Confidence Engine

- `confidence_history.jsonl` needs real accumulated rows with matched
  outcomes before `recommend_recalibration()`'s output means anything —
  currently near-zero, starting from today.
- Any future engine wanting a "how confident is the platform right now"
  signal should call `confidence_engine.assess()` directly rather than
  reimplementing a similar synthesis — this was explicitly designed as a
  reusable, parameter-driven pure function for exactly that reason.
- If a future day wants to gate publication on confidence (turning the
  currently-informational-only engine into a filter), that would be a
  deliberate, separate design decision requiring its own mandate — the
  Day 6 mandate was explicit that this engine "does not create trade
  ideas" and evaluates only AFTER a decision is already made; changing
  that is a scope change, not a natural extension.

## Backlog items flagged during Day 6 (not implemented — explicitly deferred with reasoning)

| Item | Reasoning for deferral |
|---|---|
| `regime_history.py` `ref` parameter | Out of the Day 6 mandate's explicit "Trade Journal Integration" scope (confluence + confidence only); flagged as the natural next step |
| Statistically fit the composite formula's weights | No labeled outcome data exists yet to fit against — premature by construction |
| Run `confidence_calibration.report()` against real data | Blocked on data volume (n≥30 per bucket), not on code readiness |
| Side-by-side raw-vs-composite calibration comparison UI | No UI work was in scope for Day 6; flagged as the highest-value future research step |
| Gate publication on `overall_confidence`/tier | Explicit scope boundary in the Day 6 mandate ("does not create trade ideas... without replacing any upstream decision") — would require a new, separate mandate |
| Term-by-term validation of the five formula components | Requires substantially more data than bucket-level calibration; not realistic at current trade volumes |

## Verification before future work begins

- [x] Full test suite: 513/513 passing, 0 regressions
- [x] `engine/confluence.py`'s score/gate logic confirmed unchanged (only
      label text and one new persisted field added)
- [x] `git status` clean of stray data-file artifacts
- [x] `ConfidenceAssessment` structurally confirmed to have no `allow`/
      `reject` field (cannot gate a trade)
- [x] `trade.id == trade.confluence_ref == trade.confidence_ref` confirmed
      by construction (traced in code) and by unit test
- [x] `trades.json` / `confidence_history.jsonl` state independently
      re-queried and confirmed immediately before writing this report
- [ ] Owner decision on regime's `ref` extension and the calibration-
      comparison UI question above, before any future day that would
      depend on either
