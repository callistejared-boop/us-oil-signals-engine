# Scalping Engine — Research Design

Research & Validation Cycle #2. **Design document only — nothing here
is implemented.** Depends on `STRATEGY_FRAMEWORK_SPECIFICATION.md`'s
`StrategyProfile` concept; the Scalping Engine is proposed as the first
consumer of a non-default (non-Swing) profile, and the most
architecturally distinct of the three named strategies.

## 1. What the Scalping Engine is (and is not)

It is a **thin orchestration layer**, not a new signal-origination
engine. Per the mandate's own instruction, it should reuse the existing
ICT/SMC Origination Engine (`engine/ict.py`, `engine/ict_confluence.py`,
`engine/structure.py`, `engine/breaker_blocks.py`) — the same structural
detection this platform already uses for swing/day setups — pointed at
a shorter timeframe hierarchy and gated by a tighter, scalp-specific
`StrategyProfile`. It is NOT a separate pattern-recognition system, and
it does not duplicate any of Confluence's 17 sources — it consumes them.

## 2. Integration points (mandate-specified, mapped to real modules)

| Mandate requirement | Concrete integration |
|---|---|
| Reuse ICT/SMC Origination Engine | `engine.ict`/`engine.ict_confluence`/`engine.structure`/`engine.breaker_blocks`, called with the Scalping Profile's `origination_timeframe` (e.g. 5m/15m) instead of the swing default |
| Integrate with Confluence Engine | `engine.confluence.evaluate()` called with `min_score=strategy_profile.confluence_min_score` — a scalping-specific bar, likely set differently from swing's (a research question, not assumed higher or lower without evidence) |
| Integrate with Confidence Engine | `engine.confidence_engine` scores every scalp candidate identically to swing/day candidates — same calibration machinery, different `confidence_min_for_publication` threshold per the active profile |
| Integrate with Portfolio Risk | `engine.portfolio_risk.py`, extended per `STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.7 to track strategy-level exposure separately — scalping's `max_concurrent_positions` and rapid turnover make this the strategy most likely to interact with portfolio-risk limits in ways swing rarely does |
| Integrate with Data Health | Before originating a scalp candidate, check `feed_monitor`'s current report for the relevant `market_data:{symbol}` feed status — scalping's `latency_sensitivity="high"` makes it the strategy MOST sensitive to a Stale/Expired price feed, more so than swing (a stale feed is a bigger problem for a 5-minute hold than a 3-day hold). Still advisory: a Degraded feed should surface as a warning annotation on the candidate, never silently block it, consistent with Data Health's platform-wide never-gates rule — but the Scalping Engine is the natural first candidate for the platform owner to consider whether stricter feed-health gating is warranted for this style specifically (a future, separate decision, not decided here) |
| Integrate with Market Regime | `engine.regime_engine.classify()` at the profile's own `regime_timeframe` — scalping should prefer specific regime labels (see Sec.4) distinct from swing's preferences, using the SAME classifier, different acceptance criteria |

## 3. Proposed module layout

```
engine/scalping/
    __init__.py          # governing principle, disambiguation vs. the
                          # swing/day origination path
    candidate.py          # ScalpCandidate assembly: calls ICT/SMC origination
                          # at the profile's timeframe, tags with strategy="scalp_v1"
    management.py         # rapid trade management rules specific to short
                          # holds (see Sec.5) — reuses journal.py's existing
                          # _manage() rule VOCABULARY, does not fork it
    latency_gate.py        # optional advisory check consulting Data Health's
                          # feed freshness + Day 12's latency_model before
                          # surfacing a candidate — warn, never block
    scalp_history.py       # thin wrapper over the SAME journal.py persistence,
                          # filtered by strategy="scalp_v1" — NOT a separate
                          # trades file (see STRATEGY_RESEARCH_FRAMEWORK.md
                          # Sec.2 on why one dataset, many filtered views)
```

Four small modules, mirroring this platform's established "one
responsibility per file" convention (Day 12's `engine/execution/`, Day
14's `engine/data_health/`). No module here reimplements pattern
detection, confluence scoring, confidence calibration, risk sizing, or
execution modeling — every one of those is reused by reference.

## 4. Research parameters (explicitly NOT hard-coded)

Per the mandate: "Do not hard-code values such as 10-20 pip stops or
40-50 pip targets. Instead, make these configurable by symbol and
strategy profile so they can be validated through research." The
Scalping `StrategyProfile` instance(s) — plural, because XAUUSD/WTIUSD/
BTCUSD/EURUSD likely warrant DIFFERENT scalp parameters, not one
global scalping config — would declare:

- `stop_methodology` / `stop_param`: candidate approaches to research,
  not prescribed here — structure-based (nearest liquidity level/order
  block, reusing `engine.liquidity_strength`/`engine.breaker_blocks`
  directly) is the most defensible starting hypothesis given this
  platform's existing ICT/SMC foundation, but an ATR-multiple approach
  is a legitimate alternative to test against it. **Which one wins
  should be a research finding, not an assumption baked into this
  design.**
- `target_methodology` / `target_param`: same posture — likely a
  tighter, faster-realized R-multiple target given the mandate's own
  framing ("larger reward-to-risk targets" relative to the tight
  stop, "rapid trade management," "lower holding times"), but the exact
  multiple is a research question.
- `max_holding_minutes`: a real, enforceable cap distinct from swing's
  unbounded hold — candidate values (5/15/30 minutes) should be
  compared empirically, not assumed.
- `latency_sensitivity="high"`: this is the one field this design DOES
  assert directly, because it is definitionally true of scalping as a
  style, not an empirical question — a 5-minute hold is far more
  exposed to Day 12's modeled latency/slippage than a multi-day swing
  hold, so the Execution Simulator's assumptions matter proportionally
  more here (see Sec.6).

## 5. Rapid trade management

Reuses `engine/journal.py::_manage()`'s existing rule VOCABULARY
(breakeven-at-1R, partial-bank-at-2R, runner-to-target) rather than
inventing a new management grammar — but scalping's `management_rules`
tuple would likely select a DIFFERENT subset/timing of those same rules
(e.g., breakeven sooner, given the mandate's "rapid trade management"
emphasis). This should be validated the same way every other parameter
in this design is: proposed, backtested, paper-traded, not assumed
correct because it sounds reasonable.

## 6. Why execution quality matters disproportionately here

Per the mandate: "higher emphasis on execution quality and latency."
This is the direct, concrete link to Day 12/13's work: a scalping
strategy with a tight stop and a short hold is far more sensitive to
the Execution Simulator's spread/slippage/latency assumptions than a
swing strategy is — a few pips of realistic slippage that barely dents
a 40-pip swing target could meaningfully erode a tight scalp target.
This is exactly why `STRATEGY_FRAMEWORK_SPECIFICATION.md`'s
`execution_profile` field exists per-`StrategyProfile` — a Scalping
Profile should likely be evaluated against Day 12's
`"tight_spread_low_latency"`-style profile AND against a more
conservative one, to understand how sensitive its apparent edge is to
execution-cost assumptions BEFORE any paper-trading or production
consideration. This is precisely the kind of question
`research_bridge.compare_evidence_sources()` (Day 13) already exists to
answer — reused, not reinvented, for this strategy specifically.

## 7. Why concurrency and the Paper Broker's position model matter most here

Cross-referencing `STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.7: scalping
is the style most likely to want MULTIPLE concurrent, rapid-turnover
positions on the same symbol (its own `max_concurrent_positions` field
exists specifically for this), which is exactly the scenario Day 13's
symbol-aggregate (not per-trade) Paper Broker position model handles
worst. **Recommendation, not a decision**: the Scalping Engine should
not be paper-traded concurrently with itself (multiple open scalp
positions on one symbol) until the Paper Broker's position model is
extended to per-trade or per-`(symbol, strategy)` granularity — running
it before that would produce paper-trading evidence that looks like one
blended position when it was actually several, undermining exactly the
kind of clean evidence this framework exists to produce.

## 8. What this design explicitly does NOT propose

- No new ML/statistical pattern-detection model — pure reuse of
  existing ICT/SMC structural detection at a shorter timeframe.
- No change to Confluence's 17 sources, Confidence's calibration
  model, or Data Health's registry — all consumed as-is.
- No stricter Data Health gating by default — advisory-only, same as
  every other strategy, with the note in Sec.2 that this is the
  strategy most worth revisiting that decision for, later, with
  evidence.
- No production recommendation of any kind. This is a research design
  for a future implementation Day to pick up, scope, and run through
  the full lifecycle (`idea -> research_proposal -> ... ->
  paper_trading -> performance_review`) like any other experiment on
  this platform.
