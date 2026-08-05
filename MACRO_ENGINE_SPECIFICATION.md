# Macro Intelligence Engine — Specification (Day 11)

Version: 1.0.0 | Status: Implemented, tested, advisory-integrated | Date: 2026-08-03

## 1. Purpose and scope

The Macro Intelligence Engine answers one question: **"What is happening in
the broader macro environment right now?"** It never answers "should this
trade be taken?" It does not originate trades, does not gate trades, does
not adjust confidence or confluence scores, and is never in the critical
path between a signal and an alert. It is read-only context, logged
alongside trades for later review, exactly like the Market Regime Engine
(Day 4), the Confidence Engine's evidence inputs (Day 6), and the
Explainability Engine (Day 8) before it.

This specification covers the five-module architecture built to the
user's Day 11 tightened build order:

```
Providers -> Macro Regime -> Cross-Asset Context -> Macro Assessment -> Explainability
```

## 2. Module map

| Module | Role | LOC (approx) | Imports from |
|---|---|---|---|
| `engine/rates_feed.py` | New live data: US Treasury yields, curve shape, TLT, TIP/IEF inflation-expectations proxy | ~190 | yfinance (via existing pattern) |
| `engine/macro_reference.py` | Curated reference data: central bank stances, geopolitical flags, economic prints | ~140 | none (JSON file) |
| `engine/macro_calendar.py` | Economic calendar wrapper — classifies existing `news_guard` events | ~150 | `engine.news_guard` |
| `engine/macro_cross_asset.py` | 11 named cross-asset relationships, qualitative | ~330 | `engine.correlation`, `engine.risk_sentiment`, `engine.eia_feed`, `engine.spread_feed`, `engine.rates_feed`, `engine.correlation_dynamic` |
| `engine/macro_providers.py` | **The single abstraction layer.** 10 mandate providers + 2 supplementary wrappers, standardized shape | ~420 | all of the above |
| `engine/macro_regime.py` | Descriptive classifier — labels, not scores | ~180 | none directly (reads a `providers` dict passed in) |
| `engine/macro_history.py` | Immutable, normalized, append-only JSONL persistence | ~170 | none |
| `engine/macro_engine.py` | Top-level orchestrator + explainability narrative | ~135 | `macro_providers`, `macro_regime`, `macro_history` |

Advisory integration touches three existing files: `alert_signals.py`
(logs one assessment per Stage-2 entry), `engine/journal.py` (adds
`macro_ref` field), `engine/dashboard_publish.py` (surfaces the last
recorded assessment).

## 3. The abstraction-layer rule

Per the user's explicit Phase-1 priority: **no downstream module imports
`rates_feed`, `macro_reference`, `macro_calendar`, `macro_cross_asset`,
`risk_sentiment`, `correlation`, `correlation_dynamic`, `spread_feed`,
`seasonality`, `cot_feed`, `eia_feed`, or `fundamentals_feed` directly.**
`macro_regime.py`, `macro_engine.py`, and every caller outside the engine
(`alert_signals.py`, `dashboard_publish.py`) go through
`macro_providers.py` only. This was verified structurally:

```
$ grep -L "macro_providers" engine/macro_regime.py engine/macro_engine.py
(empty — both import macro_providers, either directly or via the caller
 passing its output in)
$ grep -c "^from engine import (rates_feed\|risk_sentiment\|correlation\b" \
    engine/macro_regime.py engine/macro_engine.py alert_signals.py
0 0 0
```

`macro_regime.classify()` takes a pre-fetched `providers` dict as its
argument rather than fetching anything itself — it never imports a feed
module, so there is nothing to accidentally bypass.

## 4. Standardized provider shape

Every one of the 12 functions returned by `macro_providers.py`
(`get_provider()` / `get_all()`) returns exactly this shape:

```python
{
  "provider": "interest_rates",       # stable, machine-readable name
  "symbol": "XAUUSD" | None,          # None for market-wide providers
  "facts": {...},                     # structured data points
  "interpretation": "...",            # human-readable reading of the facts
  "freshness": {
      "updated": "2026-08-03T11:43:00+00:00" | None,
      "age_minutes": 17.2 | None,
      "state": "fresh" | "stale" | "reference_data" | "computed" | "missing",
  },
  "source_availability": "available" | "unavailable" | "not_configured",
  "uncertainty": "low" | "medium" | "high" | "unknown",
  "source": "engine.rates_feed",
}
```

This directly implements the user's two design recommendations:

- **Data Freshness** (`freshness` field): distinguishes a fresh live read
  ("Rates / Updated: 17 minutes ago / Freshness: Fresh") from reference
  data ("Central Bank / Updated: 12 days ago / Freshness: Reference Data")
  from an unconfigured or failed source ("Crack Spread / Unavailable /
  Freshness: Missing"). `get_all()` degrades one provider to `missing`
  without touching the other nine — verified by
  `test_get_all_never_raises_when_a_provider_errors`.
- **Macro Confidence vs. Evidence Quality**: kept as two separate fields
  on the regime output (Section 6), not folded into this shape, so the
  distinction survives all the way to the final assessment.

## 5. The 10 mandate providers (plus 2 supplementary)

| Provider | Underlying source | Notes |
|---|---|---|
| `interest_rates` | `rates_feed.rates()` | 10Y (`^TNX`), 3M (`^IRX`), curve slope/shape, trends |
| `central_bank_policy` | `macro_reference.all_central_bank_stances()` | Fed/ECB/BOE/BOJ/PBOC — operator-curated, never fabricated |
| `inflation` | `rates_feed.inflation_expectation_proxy()` + `macro_reference.economic_print("CPI")` | **Two distinct facts, never blended**: a live market-implied proxy (TIP/IEF ratio trend) and a curated last-known CPI print |
| `employment` | `macro_reference.economic_print("NFP")` + `macro_calendar.next_event(category="employment")` | No continuous numeric series exists for NFP (monthly/event-driven) — represented as last print + next scheduled release, never a fabricated series |
| `energy_fundamentals` | `eia_feed.read_cached()` | WTIUSD only; explicitly "not applicable" for other symbols |
| `currency_markets` | `correlation.read_macro()` | DXY trend/price — reuses the existing macro reader |
| `sovereign_bonds` | `rates_feed.bonds()` | TLT price/trend as a Treasury-bond proxy |
| `volatility` | `risk_sentiment.read()` | VIX/SPX regime |
| `geopolitical` | `macro_reference.geopolitical_flags()` + `fundamentals_feed.load_feed()` | Curated flags plus an acute-news-signal check |
| `cross_asset` | `macro_cross_asset.for_symbol()` + `_traded_pair_context()` | The 11 named relationships (Section 7) plus supplementary traded-pair correlation context |
| `seasonality` *(supplementary)* | `seasonality.read()` | Not in the mandate's 10 — exposed here anyway so "everything flows through macro_providers.py" has zero exceptions |
| `calendar_summary` *(supplementary)* | `macro_calendar.summary()` | Same reasoning |

## 6. Macro Regime: descriptive, not scored

Per the explicit prohibition — "Do not create another weighted scoring
engine" — `macro_regime.classify()` produces **labels**, not a number.
Eight possible labels, not mutually exclusive:

`Inflationary, Disinflationary, Tightening, Easing, Risk-On, Risk-Off,
Neutral, Mixed`

Rules are simple, disclosed, and count-based — never weighted:

- **Risk-On/Risk-Off/Mixed** comes straight from the `volatility`
  provider's own regime field.
- **Tightening/Easing/Mixed** aggregates up to three independent signals
  (interest-rate trend, bond-price trend, central-bank stance direction);
  "Mixed" is emitted, not suppressed, when they disagree.
- **Inflationary/Disinflationary** comes from the `inflation` provider's
  market-implied proxy trend only (the curated CPI print is disclosed
  separately in `facts`, never blended into this label).
- If nothing clears a minimal evidence bar, the label is `Neutral` — an
  honest "no signal" answer, not a forced guess.

Two fields are deliberately kept separate, per the user's own design
recommendation:

- **`macro_confidence`** — how internally consistent this run's labels
  are (do independent signals agree, or fight each other?). A simple
  disclosed rule: any "Mixed" candidate, or more low-confidence hints
  than high ones, pulls this to `low`; all-high hints yields `high`;
  otherwise `medium`.
- **`evidence_quality`** — what fraction of this run's providers actually
  had usable (fresh/reference/computed) data, independent of what the
  labels say. A label built entirely on missing data can never look as
  trustworthy as the same label built on five fresh readings.

**Neither field is the trading Confidence Engine's score, and neither
ever feeds it** — verified structurally:
`grep -n "macro_engine\|macro_regime\|macro_providers\|macro_history"
engine/confidence_engine.py engine/bias_adjust.py` returns zero matches.
Note: `engine/confidence_engine.py` and `engine/confluence.py` DO contain
the word "macro" — that is a pre-existing, Day-1-era feature (DXY
correlation alignment, `engine.correlation.macro_alignment()`) that
predates and is unrelated to the Day 11 Macro Intelligence Engine; the
precise check above confirms none of the Day 11 modules themselves
(`macro_engine`/`macro_regime`/`macro_providers`/`macro_history`) are
referenced by either file.

## 7. The 11 cross-asset relationships

`engine/macro_cross_asset.py` represents each relationship qualitatively
(sign/trend reasoning over a documented textbook basis), matching how
`correlation.py`/`spread_feed.py`/`risk_sentiment.py` already represent
their own cross-asset reads — none of them compute a live Pearson
correlation, so this module doesn't invent one either:

| Relationship | Basis | Underlying source |
|---|---|---|
| Gold vs. DXY | Inverse — dollar strength is a headwind for gold | `correlation.read_macro()` |
| Gold vs. Real Yields | Inverse — rising real yields raise the opportunity cost of holding gold | `rates_feed.rates()` + `.inflation_expectation_proxy()` |
| Gold vs. Treasury Yields | Inverse, nominal-yield version of the above | `rates_feed.rates()` |
| WTI vs. USD | Inverse — dollar-denominated commodity | `correlation.read_macro()` |
| WTI vs. Inventories | Draws bullish, builds bearish | `eia_feed.read_cached()` |
| WTI vs. Crack Spreads | Widening spreads signal refiner demand pull-through | `spread_feed.read()` |
| BTC vs. Liquidity | Steepening curve / easier financial conditions historically support risk assets including BTC | `rates_feed.rates()` (yield-curve slope trend, proxy) |
| BTC vs. Risk Appetite | Tracks broad risk-on/risk-off regime | `risk_sentiment.read()` |
| BTC vs. Dollar | Weak-dollar tailwind, same direction as gold's | `correlation.read_macro()` |
| Equities vs. Volatility | Classic inverse VIX/SPX relationship | `risk_sentiment.read()` |
| Bonds vs. Risk Assets | Flight-to-quality in risk-off; flags the unusual case when both rise together | `rates_feed.bonds()` + `risk_sentiment.read()` |

Each function's own `for_symbol()` filters to the 5 relationships
relevant to the traded symbol (`XAUUSD`, `WTIUSD`, `BTCUSD`, `EURUSD`),
never runs all 11 for every symbol.

## 8. Macro History: immutable, normalized

`engine/macro_history.py` mirrors the exact append-only JSONL pattern
already established by `regime_history.py` (Day 4), `confluence_history.py`
(Day 5), `confidence_history.py` (Day 6), and `decision_audit_history.py`
(Day 8) — same self-rotating file (`MAX_LINES=20000`), same
`find_by_ref()` unified-trade-ID lookup, same **no update/delete
function of any kind** — corrections are new rows, never edits.

Critically, it stores the **normalized output** of a macro assessment
(labels, macro_confidence, evidence_quality, a compact per-provider
freshness/availability snapshot), never the raw `facts` payload. Those
facts are cheap to re-derive from the underlying feeds' own caches
(`rates_cache.json`, `spread_cache.json`, `risk_sentiment_cache.json`,
etc. all already persist the raw numbers) — duplicating them here would
be exactly the kind of redundant storage the platform's standing "reuse
existing histories, avoid duplicate storage" discipline (established by
Day 7's Market Memory, reaffirmed at Day 9) exists to prevent.

## 9. Macro Engine: orchestration only

`engine/macro_engine.py` performs **no calculations of its own**. Every
number or label it returns was already computed by `macro_providers.py`
(facts) or `macro_regime.py` (labels); this file's only job is to call
them in the mandated order, assemble the result, and produce the
explainability narrative:

```python
def assess(symbol, direction="long"):
    providers = mp.get_all(symbol, direction=direction)   # Providers
    regime = mr.classify(providers, symbol=symbol)         # Macro Regime
    cross_asset = providers.get("cross_asset", {})         # Cross-Asset Context
    ...                                                     # -> Macro Assessment
    assessment["explainability"] = explain(assessment)      # Explainability
    return assessment
```

`test_assess_does_not_perform_its_own_calculations` structurally
verifies this: the `providers` dict `macro_engine.assess()` returns is
the exact same object `macro_providers.get_all()` produced (object
identity, `is`, not just equality) — proving nothing was recomputed in
between.

`explain()` answers the mandate's five questions purely from data
already present in the assessment — it never re-fetches, never
re-derives, and avoids deterministic language ("reads as"/"consistent
with", never "will"/"is guaranteed to").

## 10. Advisory integration — additive only

Three touch points, all additive, none gating:

1. **`alert_signals.py`**: `log_macro_context(sym, direction, ref)` is
   called once per Stage-2 entry (not every scan — macro context is
   direction-dependent, so a routine no-trade snapshot would need
   recomputing anyway and nothing reads it today). It computes one
   assessment, records it to `macro_history.jsonl`, logs to the audit
   ledger, and returns the assessment for `build_entry()` to optionally
   append as an informational line. `build_entry()`'s new `macro=` line
   sits directly below the existing `confidence:` line and is omitted
   entirely (not shown as an empty/error line) when no assessment or no
   labels are available.
2. **`engine/journal.py`**: `Trade.macro_ref` (default `""`) and
   `log_signal(..., macro_ref="")` follow the exact pattern of
   `confluence_ref`/`confidence_ref`/`regime_ref` — when the caller
   passes the same `make_ref()`-derived string to all four, the
   platform's standing invariant holds: `id == regime_ref ==
   confluence_ref == confidence_ref == macro_ref`.
3. **`engine/dashboard_publish.py`**: exposes `"macro_advisory"` in the
   dashboard payload, reading the **last recorded** assessment via
   `macro_engine.last_assessment(symbol)` — never a fresh live
   recompute — so viewing the dashboard never triggers another round of
   provider fetches.

### Structural proof of "advisory only, never gates"

```
$ grep -n "macro_engine\|macro_regime\|macro_providers\|macro_history" \
    engine/risk_guard.py engine/confluence.py engine/confidence_engine.py \
    engine/bias_adjust.py engine/signals.py
(no matches — exit code 1)
```

(Note: `engine/confluence.py` and `engine/confidence_engine.py` DO
contain the standalone word "macro" — that's the pre-existing, Day-1-era
DXY-correlation-alignment confluence factor, `engine.correlation
.macro_alignment()`, unrelated to and predating the Day 11 engine. The
precise grep above, targeting the four Day 11 module names specifically,
is the real proof and returns zero matches in all five files.)

None of the five modules that can reject, resize, or score a trade
(`risk_guard.py`, `confluence.py`, `confidence_engine.py`,
`bias_adjust.py`, `signals.py`) import or reference the Day 11 macro
engine at all. `log_macro_context()` itself is called *after* Stage-2 entry has
already been decided (see the call site in `alert_signals.py`, positioned
alongside `log_market_memory_context()` and `log_confidence_assessment()`
— all three are post-decision observational logging, not pre-decision
inputs) and its own exception path (`return None`) means a total macro
engine failure silently produces a `None` for `build_entry()`'s optional
line — the entry alert still fires on schedule.

## 11. Assumptions and known limitations

- **Sandbox has zero live network access to Yahoo Finance.** Every
  yfinance-backed function (`rates_feed`'s three functions,
  `macro_cross_asset`'s liquidity/real-yields relationships) was verified
  end-to-end to degrade to `None`/`missing` rather than raise, but was
  never exercised against genuinely live, fresh data in this environment.
  Production deployment (where the platform already has working yfinance
  access per Days 1-10) is the first real-data validation.
- **`central_bank_policy`, `geopolitical` flags, and the curated CPI/NFP
  prints in `macro_reference.json` require manual operator updates.**
  The file ships with `"example": True` placeholder entries that
  `macro_reference.py` deliberately reports as `not_configured` rather
  than fabricating a plausible-looking stance — this is a real gap, not
  a hidden one, and should be the first thing an operator does before
  relying on `central_bank_policy` or `geopolitical` in production.
- **Employment has no continuous numeric series** by design (NFP is
  monthly/event-driven) — the provider is deliberately thinner than the
  other nine rather than inventing a fabricated proxy series.
- **The 11 cross-asset relationships are qualitative, not statistically
  fitted.** No relationship here has been backtested for correlation
  strength or lag structure — see `RESEARCH_MACRO_ENGINE.md` Section 4
  for the validation plan this implies.
- **`macro_confidence` and `evidence_quality` are simple disclosed
  count-based rules, not calibrated probabilities.** They have not been
  validated against any outcome — they exist to make internal
  consistency and data reliability visible, not to predict anything.
- **One stale/unavailable provider never invalidates the whole
  assessment** (verified: `test_get_all_never_raises_when_a_provider_errors`)
  but a run with many unavailable providers still produces `labels` —
  callers must check `evidence_quality` rather than assume a returned
  label implies strong evidence.

## 12. Testing summary

158 new offline tests across 10 files, zero live-network dependency
(every yfinance/requests-backed call is monkeypatched):

| File | Tests |
|---|---|
| `test_rates_feed.py` | 14 |
| `test_macro_reference.py` | 11 |
| `test_macro_calendar.py` | 18 |
| `test_macro_cross_asset.py` | 21 |
| `test_macro_providers.py` | 23 |
| `test_macro_regime.py` | 23 |
| `test_macro_history.py` | 20 |
| `test_macro_engine.py` | 12 |
| `test_journal_macro.py` | 4 |
| `test_alert_signals_macro.py` | 9 |
| `test_dashboard_publish.py` (+3 new) | 3 |
| **Total new** | **158** |

Full-suite regression (batched to fit the 45s tool cap, per the
established Day-10/11 workaround): **890/890 passing** (732 pre-Day-11
baseline + 158 new), zero regressions.

## 13. Bug found and fixed during Day 11 testing

`engine/dashboard_publish.py`'s `build_payload()` had a local variable
named `macro` (`macro = co.read_macro()`, used for the existing DXY-based
guard evaluation) inside the same function scope as the new
`"macro_advisory": _safe_note(lambda: macro.last_assessment(symbol), ...)`
line. Because Python resolves a closure's free variables at the
enclosing *function's* scope rather than line-by-line, this local
assignment shadowed the module-level `macro_engine` import for the
entire function — any code path that reached the `macro_advisory` line
without first reaching the `macro = co.read_macro()` line raised
`UnboundLocalError`. This was caught by
`test_build_payload_includes_macro_advisory_from_last_recorded_assessment`
and `test_build_payload_macro_advisory_none_when_no_history_yet`, both of
which failed on first run. Fixed by renaming the local variable to
`dxy_macro`; both tests pass after the fix, and the existing 9
`test_dashboard_publish.py` tests (predating this change) still pass —
zero collateral regressions.
