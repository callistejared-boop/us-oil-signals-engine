# Institutional Execution Simulator & Transaction Cost Model — Specification (Day 12)

Version: 1.0.0 | Status: Implemented, tested, advisory-integrated | Date: 2026-08-03

## 1. Purpose and scope

Days 1-11 built a decision engine: when to trade, why, whether risk is
acceptable, what the broader macro environment looks like. None of that
models what execution would actually have looked like in the real
market — every R-multiple in `trades.json` has always implicitly assumed
a perfect fill at the exact intended price, with zero spread, zero
slippage, and zero delay. That assumption can distort research
conclusions (an edge that looks profitable on paper can evaporate once
realistic costs are subtracted). This package closes that gap.

**GOVERNING PRINCIPLE**, identical in spirit to every prior advisory
system's own framing (Day 4's Market Regime, Day 11's Macro Engine):
this package never originates a trade, never gates a trade, never
resizes a trade, and never changes a trade's own intended entry, stop,
or target. It answers "how good was/would execution have been?" — never
"should this trade be taken?"

**HONESTY NOTE, load-bearing for everything below**: this platform has
no live broker connection. That is explicitly Day 13's job ("Live Broker
Abstraction Layer"). Every "actual entry"/"actual exit"/execution cost
figure this package produces is a MODELED ESTIMATE built from disclosed,
documented assumptions — never a truly observed fill from a real broker.
Every module's docstring says so, every function's output carries an
`is_estimate: True` flag, and `RESEARCH_EXECUTION_MODEL.md` restates it
in the research-integration context where it matters most (Section 12).

## 2. Package structure

```
engine/execution/
    __init__.py            # package docstring, governing principle
    spread_model.py         # session/volatility/symbol/news-dependent spread estimate
    slippage_model.py       # normal/adverse/favorable slippage, liquidity shocks, partial fills
    latency_model.py        # signal -> execution delay estimate, separate timestamps
    fill_model.py           # order-type-aware fill simulation (market/limit/stop)
    execution_report.py     # per-trade fill-quality report + descriptive execution score
    execution_history.py    # immutable, normalized, append-only persistence
    comparison.py           # Raw -> Ideal -> Realistic -> Observed research bridge
    replay.py               # reproducible historical replay under configurable assumptions
```

Package isolation was the mandate's own explicit recommendation:
execution modeling will keep growing (a real broker-specific profile at
Day 13, more order types, more liquidity scenarios) and keeping it
isolated now avoids a future refactor. 1,146 lines across 8 files.

## 3. Data flow

```
spread_model + slippage_model + latency_model
        |
        v
   fill_model.simulate_fill()   <- one order leg (entry or exit)
        |
        v
execution_report.build_trade_execution_report()  <- entry leg + optional exit leg
        |                                            + descriptive score
        v
execution_history.record()  <- persisted, normalized, immutable
        |
        v
  dashboard "execution_summary" / Telegram "est. execution:" line
```

`replay.py` and `comparison.py` sit alongside this chain, not inside it —
they call `execution_report.py` repeatedly across historical trades
rather than being called by the live entry-alert path.

## 4. Spread, slippage, and latency: disclosed assumption models

None of the three ingredient models fetch live data. This platform has
no live spread feed, no tick-level fill data, and no measured
infrastructure latency — building any of these against real numbers
requires Day 13's broker layer. Until then, every constant is a
documented, illustrative, non-fitted assumption:

- **`spread_model.py`**: `BASE_SPREAD` gives one "typical, normal
  conditions" spread per symbol (e.g. XAUUSD $0.35/oz, WTIUSD $0.04/bbl),
  then applies three independent multipliers: `SESSION_MULTIPLIER`
  (Asian/off-session sessions widen 1.5-1.8x vs. London/NY's 1.0x),
  a volatility multiplier keyed off `engine.regime.atr_percentile()`
  (reused, not recomputed — the live call site passes the same 4H
  regime classification `e_reg` already computed for other purposes),
  and `NEWS_MULTIPLIER` (2.5x during an active `news_guard` blackout,
  reusing the platform's existing blackout flag rather than a new
  calendar check).
- **`slippage_model.py`**: draws a signed price delta from a
  documented (min, max) fraction-of-spread range per order type, with a
  disclosed adverse-vs-favorable probability split (`BASE_ADVERSE_PROB`:
  market 55%, stop 70%, limit 10%) and a separate, capped liquidity-shock
  probability model (`shock_probability()`) that compounds a 1% base
  rate with news/session/volatility risk factors, never exceeding 40%.
- **`latency_model.py`**: five named stages (`signal_generation`,
  `telegram_delivery`, `human_reaction`, `broker_api`,
  `order_execution`), each an illustrative (min, max) millisecond range.
  `human_reaction` — the dominant, most variable stage — is included
  because this platform is Telegram-alert-based, not auto-trading: a
  human reads `build_entry()`'s "Price tapped X — take LONG now" message
  and manually places the order. It's included by default for market/
  stop orders and excluded for limit orders (modeled as pre-positioned
  ahead of the trigger, the ICT/SMC convention).

**Reproducibility**: every random draw takes an optional
`rng: random.Random`. Live callers omit it (falls back to an unseeded,
module-shared instance); `replay.py` and every test pass an explicitly
seeded one.

## 5. Order-type behavior (`fill_model.py`)

| Order type | Fill condition | Slippage skew | Notes |
|---|---|---|---|
| Market | Immediate, unless a stress condition blocks it | 55% adverse / 45% favorable | Pays the spread; latency-induced adverse selection |
| Stop | Same as market (this platform's own alert semantics mean the trigger is already met at signal time) | 70% adverse / 30% favorable, wider magnitude range | Stop-run/gap risk |
| Limit | Deterministic from a supplied `price_path` (did High/Low actually cross the limit?), or a disclosed 65% probabilistic default when no price path is given | 10% adverse / 90% favorable-or-exact | A liquidity shock can still "gap through" a resting limit order — the one case a limit fill can be adverse |

`_side()` derives the actual transaction side (buy/sell) from
`(direction, leg)`: long entry = buy, long exit = sell, short entry =
sell, short exit = buy. Adverse slippage always means "paid more" for a
buy and "received less" for a sell — the sign convention is applied
uniformly rather than duplicated per order type.

## 6. Fail-safe stress handling

Per the mandate's explicit testing requirements, six stress conditions
are structurally supported, not just tested incidentally:

| Condition | Behavior |
|---|---|
| Zero liquidity | `filled: False`, `actual_price: None`, disclosed reason — never a fabricated fill |
| Missing market data | Short-circuits before any spread/latency computation; `filled: False`, `actual_price: None` |
| Stale price | Does not block the fill; widens the slippage magnitude by `STALE_PRICE_PENALTY_MULT` (1.5x) and sets `stale_price_caveat: True` |
| High volatility | `atr_pct` feeds both the spread's volatility multiplier and the slippage shock-probability model |
| Delayed fills | `latency_model.py`'s per-stage breakdown + a separate `estimated_execution_timestamp`, distinct from the signal's own timestamp |
| Partial fills | Surfaced via `slippage_model.py`'s `partial_fill`/`fill_fraction` fields, most likely during a liquidity shock (`SHOCK_PARTIAL_FILL_PROB` = 35%) |

`missing_data` takes priority over every other flag (checked first,
returns immediately) — a genuinely missing price makes every other
condition moot.

## 7. Execution Score: measures fill quality, not strategy quality

`execution_report.py`'s `score_execution()` produces one of five
descriptive labels — Excellent / Good / Average / Poor / Failed — from
cost relative to the trade's own planned risk (R, `|entry - stop|`, this
platform's native unit) when a stop is available, falling back to
cost-in-basis-points-of-price otherwise. Both threshold tables
(`SCORE_BANDS_R`, `SCORE_BANDS_BPS`) are simple, disclosed, non-fitted
bands — not calibrated against this platform's own trade history and not
a probability. "Failed" is categorically distinct from "Poor": Failed
means the order never filled at all; Poor means it filled but expensively.

**A losing trade can score Excellent** (the strategy was wrong, the fill
was clean) **and a winning trade can score Poor** (the strategy was
right despite paying a lot to get in) — this is by design, and it is the
entire point of keeping this score structurally separate from
`engine.confluence`'s score and `engine.confidence_engine`'s assessment.
Grep-verified: neither of those two modules, nor `engine.risk_guard`,
`engine.bias_adjust`, nor `engine.signals`, contain any reference to
`engine.execution` at all (Section 10).

## 8. Historical replay (`replay.py`)

Named, disclosed assumption profiles (`PROFILES`: `typical`, `tight`,
`wide`, `stressed`, `zero_liquidity`, `missing_data`, `stale_price`) map
directly onto `execution_report.py`'s existing parameters — this is a
convenience layer, not a new calculation. The mandate's own worked
example — "WTI, London session, typical spread, average slippage, normal
latency" — maps to:

```python
replay.run_replay(rows=trades, symbol="WTIUSD", session="London KZ", profile="typical")
```

**Reproducibility is structural, not incidental**: one shared, explicitly
seeded `random.Random(seed)` is advanced sequentially across every trade
in the replay, and every trade's own stored `opened` timestamp is always
passed as `signal_ts` — no function in the chain ever falls back to
wall-clock `datetime.now()`. Given the same `rows`/`symbol`/`session`/
`profile`/`seed`, two runs produce byte-identical output
(`test_run_replay_reproducible_same_seed`).

**Exit price reconstruction**: `trades.json` stores `result_r`, not the
literal historical exit tick (partial-banking exits aren't persisted
per-trade). `_approx_exit_price()` reconstructs an illustrative exit
price from `entry`/`stop`/`result_r` — disclosed as an approximation,
mirroring Day 10's own `restate_win_to_current_methodology()`
reconstruction-from-stored-fields pattern, not the stored actual exit.

## 9. Research integration (`comparison.py`)

```
Raw Strategy -> Ideal Execution -> Realistic Execution -> Observed Performance
```

Reuses `engine.research_stats.full_report()` (Day 9) for every layer's
statistics rather than reimplementing expectancy/profit-factor/drawdown
math. See `RESEARCH_EXECUTION_MODEL.md` Section 2 for the full,
precisely-stated definition of each layer and the important honesty note
about why three of the four layers are numerically identical today.

## 10. Advisory integration — additive only

1. **`alert_signals.py`**: `log_execution_context(sym, direction, entry,
   stop, target, atr_pct, news_blackout, session, when, ref)` is called
   once per Stage-2 entry, immediately after `log_macro_context()`,
   using `e_reg.get("atr_pct")` (the already-computed 4H regime
   classification), `blackout` (the already-computed news-guard flag),
   and `e_session` (already-computed session label) — no new upstream
   computation was added to obtain these inputs. It simulates the
   entry-leg fill only (not the exit — the outcome doesn't exist yet at
   entry time), records the report, and returns it for `build_entry()`
   to optionally append as an `est. execution:` line, positioned
   directly below the existing `macro:` line.
2. **`engine/journal.py`**: `Trade.execution_ref` (default `""`) and
   `log_signal(..., execution_ref="")` follow the exact pattern of
   `macro_ref`/`regime_ref`/`confluence_ref`/`confidence_ref` — when the
   caller passes the same `make_ref()`-derived string to all five, the
   platform's unified-ID invariant now reads `id == regime_ref ==
   confluence_ref == confidence_ref == macro_ref == execution_ref`.
   **`Trade.entry`/`.stop`/`.target` are never overwritten with a
   simulated fill price** — those remain the strategy's INTENDED levels,
   exactly as before Day 12; only the new `execution_ref`-linked history
   row carries the simulated actual price.
3. **`engine/dashboard_publish.py`**: exposes `"execution_summary"` in
   the dashboard payload, reading `execution_history.last_for(symbol)`
   — the last RECORDED report, never a fresh simulate — so viewing the
   dashboard never triggers another simulation.

### Structural proof of "advisory only, never gates"

```
$ grep -n "execution" engine/risk_guard.py engine/confluence.py \
    engine/confidence_engine.py engine/bias_adjust.py engine/signals.py
(no matches at all — not even the bare word "execution" appears in any
 of these five files, so there is no ambiguity to disambiguate here,
 unlike Day 11's "macro" naming collision)
```

None of the five modules capable of rejecting, resizing, scoring, or
originating a trade reference the execution package in any way.
`log_execution_context()` is called from the same post-decision logging
block as `log_macro_context()`/`log_market_memory_context()` — after
every gate (risk lock, portfolio risk) has already run — and its own
exception path (`return None`) means a total execution-simulator failure
silently produces `None` for `build_entry()`'s optional line; the entry
alert still fires on schedule.

## 11. Assumptions and known limitations

- **No live spread, slippage, or latency data exists anywhere in this
  platform.** Every constant in `spread_model.py`, `slippage_model.py`,
  and `latency_model.py` is an illustrative, disclosed, non-fitted
  assumption — not measured from this platform's own infrastructure or
  any specific broker. Day 13's broker layer is the first opportunity to
  replace any of these with real observed data.
- **The execution simulator never actually executed anything.** Every
  "actual entry"/"actual exit" is a MODELED ESTIMATE. See
  `RESEARCH_EXECUTION_MODEL.md` Section 2's honesty note for why
  "Observed Performance" and "Raw Strategy" are numerically identical
  today in the four-layer comparison.
- **Exit-price reconstruction in `replay.py` is an approximation**, not
  the stored actual exit tick (never persisted per-trade in
  `trades.json`). See Section 8.
- **`limit_fill_probability` (65% default) is a disclosed assumption**,
  not derived from ICT/SMC confluence quality or any measure of how
  "good" a limit level is — a limit order at a high-conviction level and
  one at a low-conviction level are modeled identically unless the
  caller supplies real subsequent price data via `price_path`.
- **The execution score's threshold bands (`SCORE_BANDS_R`,
  `SCORE_BANDS_BPS`) are simple and disclosed, not fitted or validated**
  against any outcome — they make cost visible in a human-readable
  label, nothing more.
- **`human_reaction` latency (3-45 seconds) is the single largest,
  least-certain component of the entire model.** It is also the
  component most likely to differ from any individual trader's actual
  behavior — a fast, attentive trader and a slow, distracted one produce
  very different real execution, and this model cannot distinguish them.

## 12. Testing summary

159 new offline tests across 12 files, zero live-network dependency:

| File | Tests |
|---|---|
| `test_spread_model.py` | 16 |
| `test_slippage_model.py` | 17 |
| `test_latency_model.py` | 12 |
| `test_fill_model.py` | 24 |
| `test_execution_report.py` | 18 |
| `test_execution_replay.py` | 16 |
| `test_execution_comparison.py` | 12 |
| `test_execution_history.py` | 14 |
| `test_journal_execution.py` | 4 |
| `test_alert_signals_execution.py` | 9 |
| `test_dashboard_publish.py` (+3 new) | 3 |
| `test_execution_stress.py` (dedicated stress suite) | 14 |
| **Total new** | **159** |

`test_execution_stress.py` exists specifically to make the mandate's
"Stress test: zero liquidity, high volatility, stale prices, delayed
fills, partial fills, missing market data" requirement visible and
explicit as its own file, in addition to the same scenarios already
being covered inside `test_fill_model.py`'s own unit tests.

Full-suite regression (batched to fit the 45s tool cap, per the
established Day-10/11 workaround): **1,049/1,049 passing** (890
pre-Day-12 baseline + 159 new), zero regressions.
