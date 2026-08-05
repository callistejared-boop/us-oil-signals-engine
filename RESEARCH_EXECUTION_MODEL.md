# Research Note: Execution Simulator & Transaction Cost Model (Day 12)

Version: 1.0.0 | Date: 2026-08-03

Per standing practice (Days 4-11), this note separates what is
structurally implemented and verified from what remains an unvalidated
assumption, and lays out what changes once Day 13's broker layer exists.

## 1. What the Execution Simulator currently does

Simulates the fill (price, cost, latency, quality) a market/limit/stop
order would realistically have received, given disclosed session/
volatility/news-driven spread and slippage assumptions. It never affects
which trades are taken or how they're sized — every number it produces
is logged for later review, exactly like every other Day 4-11 advisory
system.

## 2. The four-layer comparison, precisely defined

```
Raw Strategy -> Ideal Execution -> Realistic Execution -> Observed Performance
```

- **Raw Strategy**: `result_r` exactly as stored in `trades.json` — the
  strategy's theoretical edge if every fill happened exactly at the
  intended price, zero cost.
- **Ideal Execution**: identical to Raw Strategy by definition (zero
  execution cost assumed). Included as its own explicit layer, with the
  identity relationship disclosed rather than hidden, so the comparison
  always shows all four stages the mandate named.
- **Realistic Execution**: Raw Strategy's `result_r`, minus this Day's
  modeled execution cost (`cost_r`, in the same R units) for that trade.
  **This is the one genuinely new number Day 12 introduces.**
- **Observed Performance**: also `result_r` exactly as stored — same as
  Raw Strategy.

### The honesty note this comparison depends on

**Raw Strategy and Observed Performance are numerically IDENTICAL
today.** `trades.json`'s `result_r` has never had any execution cost
subtracted from it, because there is no live broker connection — nothing
has ever actually been "observed" through a real fill. The gap this
comparison surfaces between Realistic Execution and the other three
layers measures **how much execution cost was invisible until this Day**,
not a live strategy-vs-reality gap for historical trades — those trades
were never routed through this simulator in real time; the simulation is
retroactive.

Once Day 13 ships a real (or realistic paper) broker connection,
Observed Performance will diverge from Raw Strategy for the first time,
and this module's job becomes genuinely comparing four DIFFERENT
numbers instead of three identical ones and one new one. **This is the
single most important caveat in this entire research note** — a reader
who skips it could easily misinterpret "Observed Performance ==
Raw Strategy" as evidence execution costs don't matter, when it actually
means execution has literally never been measured on a real fill.

## 3. What is disclosed assumption vs. what could be validated

### 3.1 Pure assumption, cannot be validated without Day 13

- Every constant in `spread_model.py`'s `BASE_SPREAD` table, every
  multiplier in `SESSION_MULTIPLIER`/the volatility bucket table/
  `NEWS_MULTIPLIER`.
- Every constant in `slippage_model.py`: `BASE_ADVERSE_PROB`,
  `NORMAL_SLIPPAGE_FRACTION`, the shock-probability model's base rate
  and multipliers.
- Every constant in `latency_model.py`'s `STAGE_RANGES_MS`, especially
  `human_reaction` (3-45 seconds) — the single largest, most uncertain
  component, and one that will vary enormously by individual trader
  behavior in ways this model cannot observe or personalize.

None of these can be checked against reality until real fills exist to
compare against. They are reasonable, documented, illustrative figures —
not measurements.

### 3.2 Could be validated today, has not been

- **Whether the spread multipliers' RELATIVE ordering is directionally
  correct** (Asian session wider than London/NY; high volatility wider
  than low) is a well-established textbook claim, not unique to this
  platform, and is unlikely to be wrong in direction even if the
  magnitudes are off. This has not been formally checked against any
  third-party published spread data for these specific instruments.
- **Whether `limit_fill_probability` (65% default) is a reasonable
  number for this platform's own ICT/SMC limit-order setups** (typically
  placed at a fair-value-gap or order-block level, not an arbitrary
  price) has not been checked. A future research pass could compare the
  probabilistic assumption against the deterministic `price_path`-based
  check (Section 5.2 of `EXECUTION_SIMULATOR_SPECIFICATION.md`) once
  enough historical bar data is assembled for past limit-style setups.

## 4. What the four-layer comparison can and cannot tell you today

**Can tell you**: given the disclosed assumption model, how much of the
platform's historical apparent edge would likely have been consumed by
realistic transaction costs. This is a useful sensitivity check — if
`execution_drag.expectancy_delta` is large relative to Raw Strategy's own
expectancy, that is a signal the strategy's edge may be thin enough that
execution quality matters a great deal, worth flagging for extra caution
even before Day 13's real data exists.

**Cannot tell you**: whether the strategy is actually profitable after
REAL costs. That question can only be answered once Day 13 provides
either live broker fills or a realistic paper-trading connection with
actual quoted spreads.

## 5. Validation plan (future research, not yet run)

1. **Once Day 13 ships, compare this Day's modeled cost against real
   observed cost, trade by trade.** This is the single most valuable
   validation available — it would tell us directly how well-calibrated
   `spread_model.py`/`slippage_model.py`/`latency_model.py`'s assumptions
   actually are, and where they're wrong.
2. **Backtest the spread/session relationship against real historical
   spread data**, if a data source for that becomes available
   independent of Day 13 (some data vendors publish historical spread
   series separately from tick data).
3. **Track `human_reaction` empirically** once Day 13 exists — if the
   broker layer can record the actual gap between alert-sent and
   order-placed timestamps for real trades, this becomes a directly
   measurable quantity instead of an assumption, and `latency_model.py`
   could be updated to use the measured distribution instead of the
   current illustrative range.
4. **Re-run the four-layer comparison once real Observed Performance
   data exists** and check whether Realistic Execution (the modeled
   estimate) or Raw Strategy (the zero-cost assumption) is the better
   predictor of what actually happens — this is the first time this
   platform will be able to ask "was our execution-cost model any good?"
   as an answerable, evidence-based question rather than a disclosed
   assumption.

## 6. Explicit non-goals (per the Day 12 mandate and standing platform discipline)

- This module will never gate, resize, or override a trade based on
  predicted execution quality. Even a strongly validated cost model
  would only ever become advisory context — the same posture every prior
  Day 4-11 advisory system maintains.
- This module will never claim a simulated fill is a real one. Every
  output is labeled `is_estimate: True`, and every report's own `note`
  field restates the "no live broker connection" caveat.
- This module does not attempt to model market impact (the effect this
  platform's own order size might have on price) — retail-scale position
  sizes on liquid instruments (gold, oil, major forex, BTC) make this a
  reasonable simplification for now, but it should be revisited if
  position sizing methodology ever changes materially.

## 7. Summary

The Execution Simulator is production-ready as a **descriptive,
advisory-only cost-modeling layer**: every scenario degrades safely
(zero liquidity, missing data, stale prices all produce honest
`filled: False` results rather than fabricated fills), no constant
pretends to be measured when it's actually assumed, and the whole system
is structurally proven to sit outside every trade-affecting decision.
What it is not yet is a validated cost model — no number here has been
checked against a real fill, because no real fill has ever occurred on
this platform. Section 5's plan is the roadmap for closing that gap, and
it depends entirely on Day 13's broker layer existing first.
