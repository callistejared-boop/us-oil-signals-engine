# Day 12 Next-Day Readiness Report — Institutional Execution Simulator & Transaction Cost Model

## Most important thing to know

The platform can now estimate what a trade's REAL execution would have
cost — spread, slippage, latency, fill quality — for every future signal,
and can retroactively replay any historical trade under configurable
assumptions. But the single most important finding from this Day is a
limitation, not a feature: **"Observed Performance" in the new four-layer
research comparison is today numerically identical to "Raw Strategy,"**
because this platform has never routed a single trade through a real
broker. The execution model is a well-built, honestly-disclosed
assumption — not yet a validated one. Closing that gap is Day 13's job.

## What shipped

- `engine/execution/` — 8-file, 1,146-line isolated package: spread,
  slippage, latency, fill, execution-report, execution-history,
  comparison, and replay models.
- Per-trade execution context logged automatically at Stage-2 entry
  (`log_execution_context()`), visible in the Telegram alert as an
  `est. execution:` line, tagged with the same unified `execution_ref`
  ID as every other Day 4-11 advisory system.
- Reproducible historical replay (`replay.run_replay()`) under 7 named
  assumption profiles (typical/tight/wide/stressed/zero_liquidity/
  missing_data/stale_price), seeded for byte-identical repeat runs.
- Four-layer research comparison (`comparison.compare_layers()`): Raw
  Strategy -> Ideal Execution -> Realistic Execution -> Observed
  Performance, with the "Observed == Raw today" caveat disclosed
  prominently, not buried.
- Dashboard `execution_summary` key (advisory-only, structurally proven
  never to gate a trade).
- 159 new tests, including a dedicated 14-test stress suite covering all
  six mandate-named degraded conditions. Full suite: 1,049/1,049 passing,
  zero regressions.

## What did NOT move (explicitly out of scope this Day, by design)

- No live broker connection exists. Every "actual" price this package
  produces remains a modeled estimate, not a real fill — this was true
  before this Day and remains true after it. Day 13 is where this
  changes.
- No historical tick-level or real spread data was sourced or ingested.
  Every constant in the three models is a disclosed, illustrative,
  non-fitted assumption.
- No change to any trade-gating threshold, confluence score, confidence
  score, or macro label. The execution package sits entirely downstream
  of the decision to take a trade.
- Market-impact modeling (the platform's own order size moving price)
  was explicitly scoped out — reasonable at current retail position
  sizes, flagged in `RESEARCH_EXECUTION_MODEL.md` Section 6 as worth
  revisiting if sizing methodology changes.

## Remaining risks / gaps

1. **Every spread/slippage/latency constant is unvalidated.** They are
   reasonable, textbook-consistent, and clearly labeled — but no number
   in `spread_model.py`, `slippage_model.py`, or `latency_model.py` has
   been checked against a real fill, because none exists yet. Treat
   `cost_r`/`cost_bps` outputs as directional sensitivity signals, not
   precise cost forecasts, until Day 13 provides real comparison data.
2. **`human_reaction` latency (3-45 seconds, the dominant latency stage)
   is a single illustrative range for ALL users**, not personalized. A
   trader who acts on alerts within 5 seconds and one who takes 40
   seconds will see very different real execution quality that this
   model cannot currently distinguish between users.
3. **`_approx_exit_price()`'s reconstruction from `entry`/`stop`/
   `result_r` is an approximation**, not the platform's stored actual
   exit tick (which was never captured historically). Every replay
   report carries an `exit_price_is_approximate: True` flag for this
   reason — any downstream consumer of replay output must respect this
   flag rather than treating the reconstructed exit as ground truth.
4. **The four-layer comparison's most useful signal
   (`execution_drag.expectancy_delta`) has not yet been run against the
   platform's live `trades.json` and interpreted.** This Day built the
   tool; it did not yet produce or discuss a finding from running it. A
   natural immediate follow-up (before or alongside Day 13) is running
   `comparison.compare_layers()` against the current trade history and
   reviewing whether the modeled execution drag is large enough, relative
   to the strategy's own expectancy, to warrant extra caution.

## Open questions for the platform owner

1. Should `comparison.compare_layers()` be run now, against current
   `trades.json`, as a one-time research pass — independent of and
   before Day 13 — to get an early read on modeled execution drag? This
   would not require any new code, only running the existing tool and
   discussing the output.
2. For Day 13's broker abstraction layer: is a real live-account
   connection in scope, or is the intent strictly a realistic paper-
   trading layer first (as the roadmap's own phrasing, "paper trading
   first, live-ready architecture," suggests)? Confirming this shapes
   how much of Day 13 focuses on credential/security handling versus
   pure simulation-quality paper fills.
3. Is `human_reaction` latency something worth eventually asking users
   to self-report or calibrate (e.g., "I typically act within N
   seconds"), once Day 13 makes it possible to compare modeled latency
   against real observed reaction times?

## Prerequisites for Day 13 (Live Broker Abstraction Layer)

- The unified trade ID convention (`execution_ref` now included) is
  already in place and requires no further change for Day 13 to build
  on.
- `execution_history.jsonl`'s schema (normalized report fields) is
  stable and ready to be joined against real fill records once they
  exist, using the shared `ref` field.
- `RESEARCH_EXECUTION_MODEL.md` Section 5 already lays out the specific
  validation steps to run once Day 13 ships (trade-by-trade modeled-vs-
  real cost comparison, `human_reaction` empirical tracking, re-running
  the four-layer comparison with genuinely different Observed
  Performance data).
- No blocking dependency: Day 13 can begin without any further Day 12
  work.

## Backlog carried forward

- (Day 11 carryover) Any future macro-data source addition remains
  gated behind the same disclosed-assumption discipline applied again
  this Day.
- (New, Day 12) Run `comparison.compare_layers()` against live
  `trades.json` and document the finding — see Open Question 1 above.
- (New, Day 12) Once Day 13 exists: build the trade-by-trade modeled-
  vs-real cost validation described in `RESEARCH_EXECUTION_MODEL.md`
  Section 5.1 — the highest-value follow-up this Day's work enables.
- (New, Day 12) Consider whether `limit_fill_probability`'s default
  (65%) should eventually be replaced by the deterministic
  `price_path`-based check for setups where historical bar data is
  available, per `EXECUTION_SIMULATOR_SPECIFICATION.md` Section 5.2.

## Verification checklist (for the platform owner to spot-check)

- [ ] `grep -n "execution" engine/risk_guard.py engine/confluence.py engine/confidence_engine.py engine/bias_adjust.py engine/signals.py` returns nothing.
- [ ] `python -m pytest -q` (batched or full) shows 1,049 passed, 0 failed.
- [ ] `git status --porcelain` shows only the files listed in the Implementation Report — no stray data artifacts.
- [ ] `engine/journal.py`'s `Trade.entry`/`.stop`/`.target` fields are unchanged in meaning and never touched by execution simulation.
- [ ] `RESEARCH_EXECUTION_MODEL.md` Section 2's honesty note reads clearly and is not buried.

## Standing rule reaffirmed for Version 2.1

Every new feature from here forward must improve realism, measurement,
reliability, or statistical confidence — sitting alongside, not
replacing, the Day 10 rule of one Research & Validation day every 10
implementation days. Day 12 satisfies this new rule directly: it
improves realism (transaction costs now modeled instead of ignored) and
measurement (the four-layer comparison gives a first, if unvalidated,
read on execution drag).
