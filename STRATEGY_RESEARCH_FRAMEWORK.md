# Strategy-Specific Research & Validation Framework — Design

Research & Validation Cycle #2. Design document. Depends on
`STRATEGY_FRAMEWORK_SPECIFICATION.md`'s `strategy` tagging proposal —
this document specifies HOW each strategy earns promotion once that
tagging exists, reusing Day 9's research infrastructure rather than
building a second one.

## 1. Governing rule: never mix strategy statistics

Stated directly because the mandate states it directly: **swing,
day-trading, and scalping statistics must never be combined into one
dataset.** A swing strategy's -0.5R stop and 3-day hold and a scalping
strategy's -0.1R stop and 15-minute hold are not comparable observations
of the same phenomenon — averaging their R-multiples together would
produce a number that describes neither. Every metric in Sec.3 must be
computed with a `strategy` filter applied, never in aggregate across
strategies.

This is directly enforceable with the schema change proposed in
`STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.2: once `Trade.strategy`
exists, `engine/research_stats.py`'s functions take a `strategy`
parameter and filter `trades.json` (or the appropriate history file) to
matching rows before computing anything. Until that schema change
lands, this rule is aspirational — today's platform has no strategy tag
to filter by, so it is structurally IMPOSSIBLE to violate this rule
only because it is also structurally impossible to follow it. That is
itself the strongest argument for prioritizing the schema change early
(see `STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.9, step 1).

## 2. One dataset, many filtered views — not N separate trade journals

A tempting but wrong design would be separate `trades_swing.json`/
`trades_day.json`/`trades_scalp.json` files. This is explicitly NOT
recommended: it would fragment the unified trade-ID system Days 6-13
each extended, require N copies of every history-file join, and make
cross-strategy portfolio-risk aggregation (`STRATEGY_FRAMEWORK_
SPECIFICATION.md` Sec.7) much harder, not easier. **One `trades.json`,
one `strategy` field, N filtered views** — the same pattern this
platform already uses for `symbol` (one file, filtered per-symbol
everywhere it matters) extended to a second dimension.

## 3. Metrics — computed per-strategy, per the mandate's own list

All ten already exist in `engine/research_stats.py` (Day 9) — none of
these are new metrics, only a new filter dimension applied to existing,
tested functions:

| Metric | Existing function | Per-strategy meaning |
|---|---|---|
| Expectancy | `expectancy`/`avg_r_multiple` | Mean R, filtered to one strategy's trades |
| Profit factor | `profit_factor` | Gross wins/losses, one strategy |
| Win rate | `win_rate` | Always read alongside expectancy/profit factor per Day 9's own disclosure — doubly true across strategies with very different win-rate/R-multiple shapes (scalping's likely higher win rate + smaller R vs. swing's likely lower win rate + larger R) |
| Drawdown | `max_drawdown` | Realized-sequence peak-to-trough, one strategy's own equity path — mixing strategies here would show a drawdown that never actually happened to any single capital allocation |
| Sharpe-like / Sortino-like | `sharpe_like`/`sortino_like` | Per-strategy — a high-frequency scalping strategy's per-trade Sharpe-like figure is not comparable to a low-frequency swing strategy's without the annualization basis Day 9 explicitly disclosed as unresolved (`RESEARCH_VALIDATION_SPECIFICATION.md` Sec.14 item 5) — this problem gets WORSE across strategies with very different trade frequencies, worth flagging as a prerequisite before cross-strategy Sharpe comparison is attempted |
| Average R | `avg_r_multiple` | Same as expectancy |
| Average holding time | NEW — see Sec.4 | Not currently tracked as a first-class metric anywhere; proposed here |
| Execution quality | Day 12's `execution_report`/comparison functions | Per-strategy — directly relevant given `SCALPING_ENGINE_DESIGN.md` Sec.6's finding that execution assumptions matter disproportionately to tight-stop strategies |
| Market-regime performance | `engine.market_memory.performance_by_strategy_regime()` (Day 7) | **Already named `performance_by_strategy_regime` today** — worth flagging directly: Day 7's function name anticipated this need, but "strategy" in its current implementation actually means REGIME-CLASSIFIED STRATEGY LABEL (e.g. "ict_smc_mast"), not the swing/day/scalp distinction this document proposes. These are two different senses of "strategy" that will collide once both exist — see Sec.6 |
| Session performance | `engine.session_edge`/`session_model` + `research_stats` | Per-strategy — scalping's session sensitivity is likely much higher than swing's (per `STRATEGY_FRAMEWORK_SPECIFICATION.md`'s `preferred_sessions` field) |
| Symbol performance | Existing per-symbol filtering, extended with the strategy dimension | Two-dimensional filter: `(symbol, strategy)`, not just `strategy` alone — a Scalping Profile might work on XAUUSD and not on BTCUSD, and that distinction matters |

## 4. New metric proposed: average holding time

Not currently a first-class `research_stats.py` function. Proposed:

```python
def avg_holding_time_minutes(trades) -> dict:
    """Mean (closed_ts - opened_ts) in minutes across trades, same
    {"value","n","sufficient"} shape as every other research_stats
    function. Requires both opened/closed timestamps to be present and
    parseable; trades missing either are excluded and counted separately
    (not silently dropped) — same disclosure discipline as every other
    function in this module."""
```

This is directly motivated by this cycle's own Day 10 cross-check
finding real value: `PERFORMANCE_INVESTIGATION_0001.md` found average
holding time collapsed from 63.9 minutes (prior window) to 23.5 minutes
(recent window) as part of diagnosing the edge-decay condition — holding
time was informative there even without a formal strategy framework. It
would be a first-class, tracked metric under this design, not an ad hoc
one-off calculation.

## 5. Independent promotion per strategy

Per the mandate: "Each strategy must earn promotion independently."
This reuses Day 9's experiment lifecycle and Day 9's evidence-tier
system exactly, applied per-strategy rather than per-feature:

- Each `StrategyProfile` (Swing v1, Day v1, Scalp v1, ...) is its own
  `experiment_registry` entry, its own hypothesis
  (`STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.6's `status` field mirrors
  the registry's own lifecycle stages), and its own evidence-tier
  assessment (`engine.evidence_tiers.assess()`, reused unmodified).
- A strategy reaching `moderate_confidence` or `production_ready_
  evidence` on ITS OWN filtered dataset says nothing about any other
  strategy's evidence tier — no shared pooling, ever, per Sec.1's
  governing rule.
- Sample-size floors (Day 9's `MIN_N_FOR_TRUST = 30`) apply
  PER-STRATEGY. A platform with 90 total trades split 30/30/30 across
  three strategies has THREE marginally-sufficient samples, not one
  comfortably-sufficient one — this is a real, likely binding
  constraint given Sec.7's finding about current live data volume.

## 6. Naming collision to resolve before implementation

Flagged directly, not silently worked around (this platform's own
naming-disambiguation discipline, precedented by Day 11's "macro"
collision and Day 13's "paper_mode" collision): `engine.market_memory.
performance_by_strategy_regime()`'s "strategy" parameter currently means
something like "ict_smc_mast" (an origination-method label,
`config.regime_strategy`), NOT swing/day/scalp. Once
`Trade.strategy` exists with the swing/day/scalp meaning, this function
and this new field will both use the word "strategy" for different
concepts in the same codebase. **Recommendation**: rename the existing
parameter to `origination_method` (or similar) when this schema change
lands, freeing "strategy" exclusively for the swing/day/scalp sense —
a small, mechanical rename, not a behavior change, best done in the
SAME implementation Day that adds `Trade.strategy` so the collision
never actually exists in shipped code.

## 7. Current data-volume reality check (grounds this whole document)

Per `RESEARCH_VALIDATION_CYCLE_2_REPORT.md` Sec.0/2: `trades.json` has
102 total trades, ALL predating this design, all implicitly one
undeclared "strategy" (today's ambient swing/day hybrid). There is
**zero existing data to retroactively tag as Scalping** — a Scalping
Profile, once implemented, starts from n=0 and must accumulate its own
sample before ANY of Sec.3's metrics clear Day 9's `sufficient` bar.
This is stated plainly so the roadmap (`VERSION_2.2_ROADMAP.md`)
doesn't implicitly assume strategy-segmented statistical confidence is
available sooner than it actually can be.

## 8. What this document does NOT propose

- No new statistical metric beyond Sec.4's holding-time addition —
  everything else reuses Day 9's `research_stats.py` unmodified, just
  filtered.
- No change to `evidence_tiers.py`'s five-tier definitions — reused
  exactly as-is, per-strategy.
- No production promotion recommendation for any strategy — that
  decision remains the platform owner's, per every prior Day's
  standing rule, once real per-strategy evidence exists to review.
