# Day 4 Next-Day Readiness Report

2026-08-03. Remaining risks, open questions, and prerequisites for Day 5
(Adaptive Confluence redesign, per the V2 roadmap sequence).

## Remaining risks

1. **The evidence base for regime filtering doesn't exist yet.**
   `RESEARCH_REGIME_ENGINE.md` is explicit about this: 10 of 99 closed
   trades are regime-tagged, and all 10 share one label. `regime_filter_mode`
   correctly defaults to `"advisory"` as a result, but this means Day 4's
   engine is, today, a logging/context system rather than an active filter.
   That is the correct, evidence-first state to ship in — but it is worth
   being direct that the mandate's core question ("does regime filtering
   help?") remains genuinely open until real data accumulates.

2. **Weekly-timeframe data limitation compounds over time, not just today.**
   As long as the live data feeds provide only ~60 days of 15-minute bars,
   the "strategic" anchor will keep falling back to daily indefinitely, not
   just during this initial rollout. If a longer-history feed is never
   added, the weekly tier of the mandate's requested MTF structure stays
   permanently unrealized in practice (falling back gracefully, not
   silently broken, but still a real gap against the original design ask).

3. **Two parallel regime data sources now exist**: the OLD single-timeframe
   snapshot in `journal.py`'s `Trade.regime_trend`/`regime_vol` fields, and
   the NEW multi-timeframe classification in `regime_history.jsonl`. This
   was a deliberate, conservative Day 4 choice (see Implementation Report
   decision #3), but it does mean a future analyst joining the two datasets
   needs to know both exist and why they're not the same thing — flagged
   here explicitly so it isn't rediscovered confused later.

4. **`regime_filter_mode="block"` at the Day 4 default threshold
   (`regime_min_quality_for_block=30`) has never run against live data.**
   If it's ever enabled before the §3 validation plan runs, the 30-point
   threshold is itself an untested guess, not a calibrated cutoff — treat
   enabling `"block"` mode and calibrating the threshold as two separate
   decisions, not one.

## Open questions for the platform owner

1. Is it acceptable that the Regime Engine ships as advisory-only (logging,
   not filtering) for now? This was the evidence-first call made per the
   mandate's own closing recommendation, but it does mean no immediate
   behavior change to live trading — only new observability.
2. Should `journal.py`'s `Trade` dataclass be extended with the new
   taxonomy fields (`regime_primary`, `regime_quality_score`,
   `regime_compatibility`) now, ahead of the Day 4 mandate's "integration,
   not a redesign" scope, to make the eventual with/without validation
   analysis (RESEARCH_REGIME_ENGINE.md §3) cleaner? Or wait and do the
   nearest-timestamp join approach when the time comes?
3. Is a longer-history data feed (beyond the current ~60-day yfinance
   window) worth pursuing specifically to make the weekly timeframe
   load-bearing, or is daily-as-strategic-anchor an acceptable permanent
   state given the platform's trading horizon?

## Prerequisites for Day 5 (Adaptive Confluence redesign)

Per the V2 roadmap sequence, Day 5 focuses on Adaptive Confluence. Relevant
context this session surfaced that Day 5 should account for:

- `engine/confluence.py` (MAST, 27 confirmation sources) was read but
  **not modified** in Day 4 — it remains exactly as characterized in the
  Day 1 audit. Day 5 is the first day this file is expected to actually
  change.
- The Day 4 Regime Engine's `quality_score` and `compatibility` fields are
  natural candidate INPUTS to an adaptive confluence scoring scheme (e.g.,
  weighting confirmation sources differently by regime, or adjusting
  `confluence_min_score` dynamically) — but per Day 4's own "don't alter
  core ICT/SMC logic" constraint, no such wiring was done here. This is
  explicitly Day 5's territory, not pre-empted.
- The `MARKET_REGIME_SPECIFICATION.md` §6 compatibility matrix is
  structured as one dict entry per strategy specifically so that if Day 5
  introduces confluence-tier-specific behavior (e.g., treating a
  "confirmed-with-regime-conflict" tier differently from a
  "confirmed-and-regime-aligned" tier), it can reuse the existing
  `compatibility` field from `regime_engine.classify()`'s output rather than
  inventing a new signal.
- Continue the same evidence-first discipline `range_guard.py`,
  `portfolio_risk_mode`, and `regime_filter_mode` have all now established:
  any new confluence-weighting behavior driven by regime context should
  default to informational/logged until backtested, per the Additional
  Instruction that has applied since Day 3 and was reaffirmed by Day 4's
  own closing recommendation.

## Backlog items flagged during Day 4 (not implemented — explicitly deferred with reasoning)

| Item | Why deferred | Where documented |
|---|---|---|
| Extend `journal.py`'s `Trade` dataclass with the new regime taxonomy fields | Schema change, outside "integration not redesign" scope for a single day; needs its own reviewed change | `RESEARCH_REGIME_ENGINE.md` §4.2, Implementation Report decision #3 |
| Calibrate `STRONG_ER`, transition-risk weights, and quality-score base values against real transition events | Zero transition events exist yet — `regime_history.jsonl` starts empty today | `MARKET_REGIME_SPECIFICATION.md` §5/§6.1, `RESEARCH_REGIME_ENGINE.md` §3.4 |
| Thread `session_label` into the live `classify()` calls for a sharper Illiquid tag | Would add an extra `ict.read(df)` call per scan for a marginal precision gain; not a correctness issue today | `MARKET_REGIME_SPECIFICATION.md` §8, limitation #3 |
| Longer-history data feed for a trustworthy weekly timeframe | Requires a new data source decision, outside this session's scope | `MARKET_REGIME_SPECIFICATION.md` §8, limitation #1; open question #3 above |
| Enable `regime_filter_mode="block"` | No evidence yet — see §3 of `RESEARCH_REGIME_ENGINE.md` for the exact promotion criteria required first | `RESEARCH_REGIME_ENGINE.md` §3 |

## Verification before Day 5 begins

- [x] Full test suite green (390/390)
- [x] No regressions in the pre-existing 348
- [x] No stray files left behind by the new test suite
- [x] `MARKET_REGIME_SPECIFICATION.md`, `RESEARCH_REGIME_ENGINE.md`,
      `ARCHITECTURE_SPECIFICATION.md`, and `PROJECT_SUMMARY_AND_ROADMAP.md`
      all reflect the final, as-shipped code
- [ ] **Operator action optional, not blocking:** decide open questions
      #1–3 above whenever convenient; none of them block Day 5 from
      starting, since Day 4 ships in a safe, non-blocking default state.
