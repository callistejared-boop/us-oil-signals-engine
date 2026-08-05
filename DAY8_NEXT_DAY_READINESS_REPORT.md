# Day 8 Next-Day Readiness Report

## Remaining risks

1. **`decision_audit.jsonl` is entirely unvalidated against real decision
   volume.** Every test uses synthetic snapshots; the actual shape/size of
   real accumulated rows (how many rejections vs. approvals per day, how
   large `config`/`platform_version` make each row) won't be known until
   this runs live for a while. Worth a real-data spot-check after a few
   days of live operation, not assumed to be fine indefinitely.
2. **This store will grow faster than any prior Day's history log.**
   `regime_history`/`confluence_history`/`confidence_history` each log
   roughly once per scan-per-symbol; `decision_audit.jsonl` additionally
   logs every REJECTION (regime-held, confluence-held, portfolio-held,
   risk-locked), which — especially during the frequent "no setup"/
   "already tracked" scans this platform's log shows are common — could
   still be modest, but is a strictly larger row count than any prior
   Day's store at the same trade volume. The `MAX_LINES=20000` rotation
   cap is the same as every other history log; worth confirming it's
   still generous enough once real rejection volume is observed.
3. **Two account-level gates remain un-snapshotted by design** (news
   blackout, pre-origination risk lock). If a future reviewer expects
   "every single ledger event has a matching DecisionSnapshot," this will
   surprise them — flagged here explicitly so it isn't rediscovered as a
   bug.
4. **`post_trade_review()`'s heuristic could be over-read if presented
   without its disclosure.** The `heuristic_disclosure` string travels
   with every output, but any future UI/report built on top of this
   function must preserve that context, not just the `assumptions_that_
   may_have_failed` list in isolation.
5. **Version coverage is six modules out of the full engine package.** If
   a future audit/compliance reviewer expects full-codebase version
   traceability, `component_versions()`'s `COMPONENT_MODULES` scoping
   will need revisiting — a deliberate scope choice today, not
   necessarily the permanent boundary.

## Open questions for the platform owner

1. Should the unified `decision_id`/ref pattern be extended to a
   dedicated `portfolio_history.jsonl`/`risk_history.jsonl` (mirroring
   regime/confluence/confidence), or is reading `portfolio_state`/
   `risk_assessment` off `ConfidenceAssessment`'s already-normalized
   summary (today's approach) sufficient indefinitely? This is the same
   open question Day 7's readiness report raised for `portfolio_history`
   specifically — Day 8 didn't close it, since `DecisionSnapshot` reuses
   the Confidence Engine's existing summary rather than adding a new
   dedicated log.
2. Should `component_versions()`'s scope grow beyond the six current
   decision-path modules? If full-codebase version traceability is a
   compliance requirement rather than a "nice to have," this should be
   scheduled explicitly rather than grown ad hoc.
3. Given the core decision architecture (origination → regime →
   confluence → risk/portfolio → confidence → market memory →
   explainability/audit) is now fully built per your own Day 7 strategic
   guidance, what's the priority for Day 9: begin the next intelligence
   layer, or let live decision volume accumulate first so
   `decision_audit.jsonl`/`confidence_history.jsonl`/
   `market_memory`'s comparable-trade pool all have more real data before
   building further on top of them? Both are reasonable; this is a
   sequencing preference, not a technical blocker — same framing Day 6's
   readiness report used for an analogous question.

## Prerequisites for future work building on the Explainability Engine

- `decision_audit.jsonl` needs real accumulated rows (both approved and
  rejected) before any aggregate research on `post_trade_review()`'s
  uncertainty-indicator heuristic (Sec.6 of `RESEARCH_EXPLAINABILITY.md`)
  means anything — currently zero, starting from today.
- Any future engine wanting "why did the platform do X" should call
  `explainability_engine.replay(decision_id)` directly rather than
  reimplementing a similar reconstruction — designed as a reusable, pure,
  deterministic function for exactly that reason, matching
  `market_memory.historical_context()`'s Day 7 precedent.
- If a future day wants the Explainability Engine to influence production
  decisions (e.g. auto-flagging a pattern of rejections for review), that
  is a deliberate, separate scope change requiring its own mandate — this
  Day's mandate was explicit that the system "does not generate trades"
  and only records/reconstructs/explains; changing that is a scope
  change, not a natural extension.

## Backlog items flagged during Day 8 (not implemented — explicitly deferred with reasoning)

| Item | Reasoning for deferral |
|---|---|
| Dedicated `portfolio_history.jsonl`/`risk_history.jsonl` | Out of Day 8's scope; `DecisionSnapshot` reuses `ConfidenceAssessment`'s existing normalized summary instead — same open item as Day 7's readiness report |
| Full-codebase `VERSION` coverage | Scoped to six decision-path modules this Day; expanding further is a separate, larger effort with unclear payoff until a concrete need (e.g. compliance review) exists |
| Snapshotting the two account-level pre-origination gates | No specific candidate opportunity exists at that point in the pipeline — a `DecisionSnapshot` with a fabricated direction would misrepresent the object |
| Aggregate uncertainty-indicator research (Sec.6 of the research report) | Requires real accumulated `decision_audit.jsonl` volume; zero today |
| Extending `decision_id` to Telegram/dashboard persisted storage | Neither currently persists a per-decision row at all — same open item carried from Day 7 |
| Indexing `find_by_ref()`/`find_by_trade_ref()` | Current O(n) scan is fine at current/near-term volumes; revisit if this store's growth (faster than other history logs — see Remaining risks #2) makes it a real cost |

## Verification before future work begins

- [x] Full test suite: 620/620 passing, 0 regressions
- [x] `decision_audit_history.py` confirmed to expose no update/delete
      function (structural test, not just documentation)
- [x] `git status` clean of stray data-file artifacts
- [x] `DecisionSnapshot` structurally confirmed to have no `allow`/
      `reject` field (cannot gate a trade) — by direct inspection of the
      dataclass definition, same pattern as Day 6's equivalent check
- [x] Every `log_decision_snapshot()` call site traced and confirmed to
      run strictly after the corresponding real gate/approval decision
- [x] `replay()` determinism confirmed both by automated test and a
      direct manual re-check against a live-built snapshot
- [x] `decision_audit.jsonl` state independently re-queried and confirmed
      empty immediately before writing this report
- [ ] Owner decision on the three open questions above, before any future
      day that would depend on them

## Milestone check: core decision architecture + explainability, per the platform owner's own Day 7 guidance

Your Day 7 closing guidance named seven layers and asked for a pause after
they were complete to build Explainability & Decision Audit before adding
more intelligence. That is now done:

| # | Layer | Status |
|---|---|---|
| 1 | Trade Origination | Done (pre-Day-3) |
| 2 | Market Regime | Done (Day 4) |
| 3 | Adaptive Confluence | Done (Day 5) |
| 4 | Risk & Portfolio Governance | Done (Day 3) |
| 5 | Confidence Assessment | Done (Day 6) |
| 6 | Market Memory | Done (Day 7) |
| 7 | Explainability & Decision Audit | Done (Day 8) |

Per your own words closing Day 7: "Before adding more intelligence, ensure
every decision made by the platform can be reconstructed, understood, and
audited end-to-end. That investment will make every future enhancement
easier to validate and maintain." That investment is now in place —
`replay()`, the audit graph, and both explanation reports give a concrete,
tested mechanism for validating whatever comes next. No Day 9 work has
been started; this section exists only to confirm the platform is in the
state you described when you set that expectation, and to hand back the
sequencing decision (open question #3 above) rather than assume it.
