# Day 9 Next-Day Readiness Report

## The most important thing in this report

Running the new `edge_decay_monitor.check()` against the platform's real,
live `trades.json` (not synthetic test data) surfaces four real,
current findings:

| Signal | Prior (69 trades) | Recent (last 30 trades) |
|---|---|---|
| Expectancy | +1.22R | **-0.01R** |
| Profit factor | 3.47 | **0.99** |
| Max drawdown | -5.0R | **-12.0R** |
| Within-window consistency | — | **inconsistent across sub-segments** |

This is exactly the kind of signal this framework was built to surface —
and per its own governing principle, it was reported here and NOT acted
on. No threshold changed, no strategy paused, no config touched. This is
now the platform owner's decision to make, not a code change to ship
quietly inside a routine update. See
`RESEARCH_VALIDATION_SPECIFICATION.md` Sec.9.1 for the full context and
`DAY9_VALIDATION_REPORT.md` Sec.4 for independent re-confirmation that
this reproduces, not a one-off artifact.

Worth being direct about what this could mean, without overclaiming: it
could be recent-sample noise (30 trades is exactly this platform's own
statistical-trust floor, not a large margin above it), a genuine
regime/edge shift, or a combination. `evidence_tiers.assess()` would
currently rate this recent window as, at best, `moderate_confidence` on
sample size alone — and the inconsistency flag suggests it may not even
clear `preliminary_evidence` once representativeness/consistency are
weighed. This is not a verdict. It is the first real signal this
framework has ever produced, and it arrived on the same day the framework
shipped.

## Remaining risks

1. **The edge-decay finding above is unresolved.** Whatever caused it
   (if anything beyond sample noise) is still active in production —
   this framework can flag it but cannot investigate or fix it.
2. **`experiment_registry.jsonl` has zero entries.** Every future
   proposed change should be logged through it starting now, or the
   registry will simply be unused tooling rather than the governance
   layer it's meant to be.
3. **No direct ref links a Stage-1 heads-up to its Stage-2 entry** —
   `paper_trading_review.py`'s "proposed vs. executed" comparison is
   incomplete for heads-up decisions specifically until this is closed.
4. **`research_stats.py`'s Sharpe/Sortino/Calmar-like metrics are
   per-trade, not time-annualized** — fine for cross-experiment
   comparison on this platform, but would need real annualization work
   before being quoted to anyone expecting a standard institutional
   number.
5. **The backtest-quality review (Sec.4 of the spec) found real, if
   modest, gaps** (no slippage model, flat, non-session-conditioned
   spread) — not urgent, but worth remembering these exist before trusting
   a backtest's exact numbers too precisely.

## Open questions for the platform owner

1. **What should happen with the edge-decay finding above?** Options
   include: (a) treat it as noise and keep monitoring, (b) investigate
   which specific trades/conditions drove the recent 30, (c) formally log
   it as the FIRST entry in `experiment_registry.py` (an "idea": why did
   expectancy fall, is it regime-related) and let it go through the
   lifecycle properly. This report recommends (c) as the one most
   consistent with the framework you just asked for, but the decision is
   yours.
2. Should the Stage-1-to-Stage-2 ref gap (open item #3 above) be closed
   before or after Day 10's Macro Intelligence work? It's a small,
   well-scoped extension (mirrors the regime/confluence/confidence ref
   pattern exactly) but touches `alert_signals.py`, which Day 9
   deliberately left untouched.
3. Now that a formal hypothesis/lifecycle process exists, should Day 10's
   Macro Intelligence work be the FIRST feature actually required to pass
   through it — i.e., should Day 10 open with a logged `Hypothesis` before
   any code is written, rather than treating this framework as
   retroactive-only? This report recommends yes, per your own closing
   words on this mandate ("Every future enhancement... will have a clear,
   evidence-based path from idea to production").

## Prerequisites for future work building on this framework

- Any future proposed change (Macro Intelligence included) should start
  with `experiment_registry.propose()` — a filled `Hypothesis` — before
  implementation begins, not after.
- Any future research branch's backtest/paper-trading results should be
  evaluated via `research_stats.full_report()` +
  `evidence_tiers.assess()`, not ad hoc metrics, so every experiment's
  evidence is comparable on the same terms.
- If a future day wants `edge_decay_monitor.py` to do more than flag
  (e.g. auto-pause a symbol on severe decay), that is a deliberate,
  separate scope change requiring its own mandate — this Day's mandate
  was explicit that the framework "recommends investigation," not
  automatic production changes.

## Backlog items flagged during Day 9 (not implemented — explicitly deferred with reasoning)

| Item | Reasoning for deferral |
|---|---|
| Investigate the edge-decay finding | Explicitly handed back to the platform owner (see "most important thing" above) — this framework's job is to flag, not diagnose |
| Stage-1 heads-up -> Stage-2 entry direct ref | Touches `alert_signals.py`, which Day 9 deliberately left untouched; well-scoped, mirrors an existing proven pattern |
| Slippage / variable spread modeling in `backtest.py` | A candidate future EXPERIMENT — must pass through this Day's own lifecycle, not be silently added |
| Time-annualized Sharpe/Sortino/Calmar | Requires a clean per-symbol annualization basis this platform doesn't have yet; itself a candidate future experiment |
| Auto-pause / automatic production response to edge decay | Explicit scope boundary in the Day 9 mandate ("recommends investigation... not automatic production changes") — would require a new, separate mandate |

## Verification before future work begins

- [x] Full test suite: 703/703 passing, 0 regressions
- [x] Zero production-path files reference any Day 9 module (grep-verified)
- [x] `experiment_registry.py` confirmed to expose no update/delete
      function (structural test, not just documentation)
- [x] `expanding_window_series()` confirmed look-ahead-safe by direct
      trace and dedicated test
- [x] `git status` clean of stray data-file artifacts
- [x] Edge-decay finding independently re-confirmed against live
      `trades.json`, not a one-off test artifact
- [ ] Owner decision on the edge-decay finding and the three open
      questions above, before Day 10 begins
