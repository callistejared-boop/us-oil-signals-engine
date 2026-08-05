# Day 15 — Next-Day Readiness Report

## Immediate actions for the platform owner (before Day 16)

These need a human, not more agent time — either credentials/dashboard
access this sandbox doesn't have, or a data-correctness judgment call:

1. **Verify `TWELVEDATA_API_KEY`** in the repo's Actions secrets — check
   it's present, current, and not rate-limited/exhausted. This is the
   leading (evidence-backed, not certain) suspect for the market-data
   fetch failures. If it checks out, the next step is inspecting a
   recent `entry-scan.yml` run's actual step logs (requires GitHub
   sign-in) to see the real per-symbol error, since this sandbox
   couldn't reach either TwelveData or yfinance to test directly.
2. **Review and resolve the 3 duplicate open BTCUSD positions**
   (`BTCUSD-2026-07-17T13:15:00`, identical ID, in `trades.json`) and
   the 1 stale pending XAUUSD setup (`pending.json`, created 2026-07-17)
   — these will independently block new long-direction trades via the
   portfolio exposure cap even once #1 is fixed. Decide whether these
   reflect real open exposure that should be actively managed, or
   defects that should be closed/removed.
3. **Watch the first few live runs after this Day's fixes ship** —
   specifically: does `heartbeat-watchdog.yml`'s new `actions/cache/
   restore@v4` step actually retrieve `entry-scan.yml`'s cache (this
   sandbox validated the YAML but couldn't execute it); does the
   expanded persist step in `entry-scan.yml` successfully commit the 15
   previously-orphaned history files without conflicts (they're new to
   git, so the first commit adding them is a slightly different code
   path than the routine "diff and update" pattern the always-tracked
   files use).
4. **Review DAY15_GIT_HYGIENE_REPORT.md's commit plan** and either
   execute it directly or ask for it to be run — 227 files across 15
   logical commits are staged-and-verified, ready to go, currently
   sitting unstaged in the working tree.

## What's now unblocked for Day 16 (Strategy Framework) — conditionally

The mandate's own sequencing was: Day 15 operational health first, Day
16 Strategy Framework only after. That gate is **partially, not fully,
cleared**:

- The evidence-persistence gap (the single biggest blocker to Day 16-17
  ever having real data to validate against) is fixed in code, but
  unverified in production — needs at least one real live run to confirm.
- The trade-ID chain is confirmed working, which directly de-risks
  `STRATEGY_FRAMEWORK_SPECIFICATION.md`'s own proposed `Trade.strategy`
  field addition (Research & Validation Cycle #2) — that schema change
  can proceed with confidence the join it depends on already works.
- The market-data fetch issue and the phantom-position issue are BOTH
  still open. Starting Day 16's schema work doesn't require them to be
  resolved (it's a design/schema change, not something that needs live
  trades flowing yet) — but Day 17's Scalping Engine and any paper-
  trading validation of new strategies genuinely does need real trades
  flowing again first, per this Day's own findings.

**Recommendation**: proceed with Day 16's `Trade.strategy` schema design
work if desired — it's independent of the two open operational issues.
Hold Day 17's Scalping Engine implementation (not just its design, which
is already done per Cycle #2) until Items 1-2 above are confirmed
resolved by the platform owner, consistent with `SCALPING_ENGINE_
DESIGN.md` Sec.7's own recommendation not to paper-trade a new strategy
until the data feeding it is trustworthy.

## Open items carried forward (not this Day's to fix)

- Confluence engine did not produce a usable result against the
  synthetic trace data (DAY15_PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md)
  — disclosed as a limitation of synthetic test data, not confirmed as a
  platform defect. Worth an independent check once real live data flows
  again.
- Every Technical Debt Register item from Research & Validation Cycle #2
  remains open and unaffected by this Day's work (this Day added no new
  items to that register — everything found here is either already
  tracked there or specific enough to live in these Day 15 documents
  instead).
- `.gitignore` has no explicit rule for the 15 newly-tracked files
  (Sec.3, DAY15_GIT_HYGIENE_REPORT.md) — not a gap requiring action,
  since they're now intentionally tracked, not ignored, but worth
  knowing the ambiguity was resolved this way if it's ever questioned.
