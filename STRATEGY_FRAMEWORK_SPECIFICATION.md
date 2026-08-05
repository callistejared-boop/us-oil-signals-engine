# Multi-Strategy Framework — Design Specification

Research & Validation Cycle #2. **This is a design document, not an
implementation.** Nothing described here has been built; nothing in
this platform's live code changes as a result of this document. Per the
mandate's own framing, this is architecture proposed for a future
implementation Day (or Days), to be evaluated, sequenced, and approved
by the platform owner before any code is written — consistent with this
platform's standing "no feature earns its place without going through
the research lifecycle" discipline (`RESEARCH_VALIDATION_SPECIFICATION.md`).

## 1. Governing principle

**Strategy selection is configuration, not code branching.** Today,
this platform has exactly one implicit strategy — a swing/day-trade
hybrid defined by whatever constants happen to live in `engine/signals.py`,
`engine/risk.py`, `engine/journal.py::_manage()`, and a handful of other
modules. There is no single place that says "this is the Swing
Profile" — it is smeared across the codebase as ambient defaults. The
Multi-Strategy Framework's job is to make "which strategy is active"
into ONE explicit, versioned configuration object that every stage of
the pipeline reads from, the same way Day 14's `engine/data_health/
registry.py` made "which feeds exist" into one explicit registry instead
of implicit knowledge scattered across modules. That precedent — a
registry of declared objects, consulted by reference, never hard-coded
— is the direct architectural ancestor of this design.

## 2. The additional recommendation, adopted as a design requirement

The platform owner's own stated recommendation is treated here as
load-bearing, not optional: **strategy becomes a first-class concept
alongside symbol.** Concretely, this means:

1. **`Trade` gains a `strategy` field** (`engine/journal.py`), populated
   at `log_signal()` time from the active `StrategyProfile.profile_id`,
   the same way `symbol` already is. This is the single most important
   schema change this design proposes — everything else follows from
   it.
2. **Every history file this platform already has gains an implicit
   `strategy` tag** wherever it currently carries a `symbol` tag —
   `regime_history.jsonl`, `confluence_history.jsonl`,
   `confidence_history.jsonl`, `macro_history.jsonl`,
   `execution_history.jsonl`, `broker_history.jsonl`'s four stores,
   `decision_audit_history.jsonl`. No new files, no new persistence
   pattern — the existing append-only JSONL convention already supports
   an extra field with zero structural change, exactly like `broker_ref`
   was added to `Trade` in Day 13 without touching the persistence
   mechanism.
3. **`engine/research_stats.py`, `engine/evidence_tiers.py`, and
   `engine/edge_decay_monitor.py` gain a `strategy` filter parameter**,
   defaulting to "all" for backward compatibility but intended to be
   called per-strategy going forward — see `STRATEGY_RESEARCH_FRAMEWORK.md`
   for the full "never mix strategy statistics" design.
4. **`engine/dashboard_publish.py`'s payload gains a `strategy` field**
   per signal, and the dashboard's `institutional`/`paper_trading`/
   `data_health` panels each become filterable by strategy in the
   frontend (a `webapp/` concern, out of scope for this repo, but the
   payload should carry the tag either way).

This is a genuinely large schema change touched across most of the
platform's history files. It should NOT be done piecemeal alongside
unrelated feature work — it deserves its own dedicated implementation
Day, scoped exactly like Day 6/7's unified-trade-ID work was scoped,
with the same "extend an existing ref pattern, don't invent a new one"
discipline.

## 3. `StrategyProfile` — the configuration object

```python
@dataclass(frozen=True)
class StrategyProfile:
    profile_id: str            # "swing_v1", "day_v1", "scalp_v1" — versioned, see Sec.6
    display_name: str
    style: str                 # "swing" | "day" | "scalp"

    # --- timeframe hierarchy ---
    origination_timeframe: str       # e.g. "15m" for scalp, "1h" for swing
    confirmation_timeframes: tuple   # e.g. ("4h","1d") for swing, ("5m",) for scalp
    regime_timeframe: str            # which timeframe regime_engine.classify() should read

    # --- risk rules ---
    risk_pct_per_trade: float
    max_daily_loss_r: float
    max_open_per_symbol: int
    max_concurrent_positions: int    # NEW — see Sec.7, scalping needs this more than swing does

    # --- stop / target methodology (never hard-coded distances — see Sec.5) ---
    stop_methodology: str      # "structure" | "atr_multiple" | "fixed_distance"
    stop_param: float          # interpreted per stop_methodology
    target_methodology: str    # "structure" | "r_multiple" | "atr_multiple"
    target_param: float
    min_reward_risk_ratio: float

    # --- position sizing ---
    sizing_methodology: str    # "fixed_risk_pct" | "confidence_scaled" | "volatility_scaled"

    # --- holding time / management ---
    max_holding_minutes: Optional[int]     # None = no cap (swing)
    management_rules: tuple    # e.g. ("breakeven_at_1r", "bank_50pct_at_2r") — reuses
                                # journal.py's existing _manage() rule vocabulary,
                                # made per-profile instead of hard-coded

    # --- execution assumptions (Day 12/13 integration point) ---
    execution_profile: str     # "typical" | "tight_spread_low_latency" | ... —
                                # maps to engine.execution.replay.PROFILES (Day 12,
                                # already exists, already extensible — reused, not duplicated)
    latency_sensitivity: str   # "low" | "medium" | "high" — scalping is "high"

    # --- confidence / confluence thresholds ---
    confluence_min_score: int          # today: one global config.confluence_min_score;
                                        # this makes it per-profile
    confidence_min_for_publication: Optional[float]

    # --- market/session/volatility/liquidity preferences ---
    preferred_symbols: tuple
    preferred_sessions: tuple          # reuses engine.session_edge/session_model's
                                        # existing session taxonomy
    preferred_volatility_regime: tuple # reuses engine.regime_engine's existing labels
    min_liquidity_tier: str            # reuses engine.liquidity_strength's existing tiers

    # --- portfolio exposure rules ---
    max_portfolio_risk_pct: float      # feeds engine.portfolio_risk.py, per-strategy
                                        # instead of one global figure

    # --- versioning + provenance ---
    version: str                # semver-style, e.g. "1.0.0"
    created: str                 # ISO date
    status: str                  # "research" | "paper_validated" | "production" — see Sec.6
```

Every field above maps to a constant, threshold, or piece of ambient
logic that ALREADY EXISTS somewhere in this codebase today — this
design's job is to collect them into one declared object per strategy,
not to invent new trading logic. This mirrors Day 14's registry design
almost exactly: `FeedSpec` didn't invent new data sources, it declared
the ones that already existed.

## 4. Strategy selection — config-driven, not hard-coded

Proposed mechanism, directly modeled on `engine/data_health/registry.py`'s
pattern:

```python
# engine/strategy/registry.py (proposed)
_PROFILES: dict[str, StrategyProfile] = {}
def register(profile: StrategyProfile) -> None: ...
def get(profile_id: str) -> StrategyProfile | None: ...
def active_profile(settings) -> StrategyProfile:
    """Reads settings.active_strategy_profile (a new Settings field,
    e.g. 'swing_v1'), looks it up in the registry. Falls back to a
    disclosed default profile if unset or unknown — never raises,
    same fail-safe posture as every other config read in this codebase."""
```

`alert_signals.py`'s per-symbol scan loop would call `active_profile(s)`
once per scan (or, for the multi-strategy future described in Sec. 7,
once per configured strategy) and thread the resulting `StrategyProfile`
through the existing pipeline — `regime_engine.classify(df, sym,
strategy=strategy_profile.regime_timeframe, ...)`,
`confluence.evaluate(..., min_score=strategy_profile.confluence_min_
score)`, `journal.log_signal(..., strategy=strategy_profile.profile_id)`,
and so on. **No module needs to know which strategy is active by name
— every module just reads the field it needs off the `StrategyProfile`
object it's handed**, exactly like no module in Day 14's package needs
to know a feed's name to check its freshness, it just reads the
`FeedSpec` it's given.

This satisfies the mandate's explicit requirement directly: "The
platform should determine which strategy is active based on
configuration — not by hard-coded logic."

## 5. Why nothing is hard-coded

The mandate is explicit: "Do not hard-code values such as 10-20 pip
stops or 40-50 pip targets. Instead, make these configurable by symbol
and strategy profile so they can be validated through research." This
design satisfies that by construction — `stop_param`/`target_param` are
`StrategyProfile` fields, and a future implementation would key them by
`(profile_id, symbol)` (reusing `engine.markets.MARKETS`'s existing
per-symbol table as the join key, the same way Day 12's execution model
already keys spread/slippage assumptions per symbol). A Scalping Profile
for XAUUSD and a Scalping Profile for BTCUSD would have DIFFERENT
`stop_param` values, both declared, both researchable, neither hard-coded
into any function body.

## 6. Versioning

`StrategyProfile.version` + `status` together give every profile a
promotion path mirroring Day 9's own experiment lifecycle (`idea ->
research_proposal -> ... -> production_recommendation ->
controlled_release`) rather than inventing a second parallel promotion
system:

- `status="research"` — profile exists, can be backtested/paper-traded,
  never live.
- `status="paper_validated"` — has been through Day 13's Paper Broker
  for a defined evaluation window (see `STRATEGY_RESEARCH_FRAMEWORK.md`
  for what "validated" requires statistically) but not yet live.
- `status="production"` — approved by the platform owner for live
  trading, per this platform's existing "a human makes every promotion
  decision, the registry records it" principle (Day 9).

A profile's version history should be append-only, same JSONL
convention as everything else — `strategy_profile_history.jsonl`
recording every `register()`/status-transition event, never a
mutated-in-place config file, so a strategy's exact parameters at the
time any given trade fired can always be reconstructed. This is the
same immutability discipline Day 8's `decision_audit_history.py` and
Day 9's `experiment_registry.py` already established — reused, not
reinvented.

## 7. Multiple strategies running concurrently — the portfolio-risk question

The mandate's scope (Swing, Day, Scalping) implies these could run
CONCURRENTLY on the same symbol (e.g., a Swing position open on XAUUSD
while a Scalping profile also scans XAUUSD intraday). This raises a
real architectural question this design flags rather than silently
resolves:

- **`engine/portfolio_risk.py`'s existing aggregation is symbol-based,
  not strategy-based.** A concurrent swing + scalp position on the same
  symbol would today look like one aggregate exposure. This design
  proposes `portfolio_risk.py` gain a `strategy`-aware exposure
  dimension — total risk should be checked BOTH per-symbol (existing)
  AND per-strategy (new) AND on the true combined basis (new) — three
  numbers, not one, surfaced separately (same "disclose, don't collapse"
  posture as every other qualitative table in this codebase).
- **Day 13's Paper Broker position engine is explicitly symbol-
  aggregate, not per-trade** (a disclosed Day 13 limitation, carried
  forward unresolved — see `DAY13_NEXT_DAY_READINESS_REPORT.md`
  "Remaining risks" item 1). Multi-strategy concurrency on one symbol
  makes this limitation materially more important than it was when it
  was first disclosed — a swing and a scalp position on the same symbol
  would currently blend into one Paper Broker position, which is
  actively misleading for strategy-segmented research. **This is the
  single most important prerequisite this design surfaces**: the
  Paper Broker's position model should move to per-trade (or at minimum
  per-`(symbol, strategy)`) tracking before multi-strategy concurrency
  is enabled in paper trading, or paper-trading evidence for concurrent
  strategies will be unreliable by construction.
- **`engine/risk_guard.py`'s daily-loss lock is per-symbol** (Day 3-era
  design, confirmed unchanged this cycle). A strategy-aware version
  would need to decide whether a scalping strategy's daily loss should
  lock out swing trading on the same symbol, or be tracked
  independently — a real risk-policy decision for the platform owner,
  not something this design should decide unilaterally.

## 8. What does NOT change

- The existing single-implicit-strategy behavior remains the DEFAULT if
  no `StrategyProfile` is configured — this design is additive, not a
  breaking change to how the platform runs today.
- No gating module's fail-safe posture changes — a missing/misconfigured
  `StrategyProfile` should fail open to the existing default behavior,
  never block a scan, per this platform's standing discipline.
- Confluence's 17 sources, Confidence's calibration model, Market
  Memory's similarity engine, Macro Intelligence's 10 providers, and
  Data Health's registry are all strategy-agnostic infrastructure —
  they don't need strategy-awareness themselves, only the THRESHOLDS
  and PARAMETERS a strategy profile feeds into them need to vary.

## 9. Recommended sequencing (not a commitment, an input to Version 2.2 planning)

1. `Trade.strategy` field + `StrategyProfile`/registry scaffolding
   (small, additive, same shape as every prior Day's schema extension).
2. Wire the Swing Profile as the FIRST registered profile, matching
   today's actual implicit defaults exactly — a pure refactor with zero
   behavior change, verified by a regression test asserting identical
   output before/after.
3. Day Trading Profile — same origination engine, tighter timeframe
   hierarchy, shorter `max_holding_minutes`.
4. Scalping Engine — see `SCALPING_ENGINE_DESIGN.md`, the most
   architecturally distinct of the three (Sec. 7's concurrency
   prerequisite applies most strongly here).
5. Portfolio-risk strategy-awareness (Sec. 7) — should land before or
   alongside step 4, not after, if concurrent strategies are intended
   from the start.

This sequencing is a recommendation for the platform owner's roadmap
planning, not a schedule this document commits to — see
`VERSION_2.2_ROADMAP.md` for how this fits against the platform's other
measured-finding-driven priorities.
