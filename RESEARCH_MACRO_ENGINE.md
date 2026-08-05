# Research Note: Macro Intelligence Engine (Day 11)

Version: 1.0.0 | Date: 2026-08-03

Per standing practice (Days 4-10), this note separates what is empirically
supported from what is a textbook assumption not yet validated on this
platform's own data, and lays out the validation plan that closes the
gap.

## 1. What the Macro Engine currently does

Produces a descriptive read of the macro environment (regime labels,
cross-asset context, provider-level facts) for a symbol/direction at the
moment a trade candidate reaches Stage-2 entry, logs it immutably, and
surfaces it as additional context on the entry alert and dashboard. It
makes no trading decision and has no measurable effect on trade outcomes
today, by construction (see `MACRO_ENGINE_SPECIFICATION.md` Section 10
for the structural proof).

## 2. Supported vs. assumed relationships

### 2.1 Textbook relationships used as-is (well-established, not
platform-specific research)

These are standard macro/cross-asset relationships taught in institutional
market-context frameworks. They are not unique claims this platform is
making — they're widely-cited priors, encoded here as simple sign/trend
rules:

- Gold inversely tracks the US dollar (DXY) and real yields.
- WTI crude inversely tracks the US dollar; inventory draws are bullish,
  builds are bearish; widening crack spreads signal refiner demand.
- Bitcoin has historically shown positive correlation with broad risk
  appetite and negative correlation with the dollar, and some sensitivity
  to financial-conditions/liquidity proxies (though this relationship has
  been notably unstable across different market regimes historically).
- Equities and the VIX move inversely.
- Government bonds rally (yields fall) during risk-off flight-to-quality
  episodes.
- Rising nominal yields with rising central-bank hawkishness signal a
  tightening macro regime; the reverse signals easing.

**None of these have been backtested against this platform's own trade
outcomes.** They are encoded as the *content* of the descriptive labels,
not as a validated predictive signal.

### 2.2 Explicitly disclosed proxies (not the real underlying series)

- **Inflation-expectations proxy**: the `inflation` provider's
  market-implied signal is the TIP/IEF ETF ratio trend, not a
  breakeven-inflation-rate calculation or the actual CPI print. It is a
  reasonable market-based proxy but will diverge from "true" inflation
  expectations during periods of ETF-specific flow distortion (e.g. large
  rebalancing flows). The curated CPI print (`macro_reference`) is kept
  as a separate fact specifically so these two are never confused.
- **BTC-liquidity proxy**: `btc_vs_liquidity()` uses the Treasury
  yield-curve slope trend (steepening/flattening) as a stand-in for
  broader financial-conditions/liquidity — a real but indirect proxy;
  it does not incorporate Fed balance-sheet size, reverse repo volume, or
  bank reserves, which are the more direct liquidity measures used in
  institutional research.
- **Sovereign-bonds provider**: uses TLT (a 20+ year Treasury ETF) price
  trend as the yield proxy, not the 10Y or 30Y yield directly (the
  `interest_rates` provider already covers 10Y/3M via `^TNX`/`^IRX`, so
  `sovereign_bonds` intentionally captures the long end via price rather
  than duplicating the same yield series).

### 2.3 Deliberately thin: employment

No continuous employment series exists in this architecture. NFP is
monthly and event-driven; representing it as a smooth trend would require
either interpolation (misleading — implies information that doesn't
exist between releases) or a fabricated proxy (violates the platform's
"never fabricate information" discipline, the same reasoning applied at
Day 9/10 to trade-data integrity). The `employment` provider is
therefore intentionally limited to the last known print plus the next
scheduled release date.

## 3. What "Macro Confidence" and "Evidence Quality" are (and are not)

Both fields are simple, disclosed, count-based rules — not calibrated
probabilities and not validated against any outcome:

- `macro_confidence` = do this run's independent label-producing signals
  agree with each other?
- `evidence_quality` = what fraction of this run's providers actually had
  usable data?

Neither has been checked for calibration (e.g., "when macro_confidence is
'high', are the labels actually more often 'correct' in some measurable
sense?"). That question doesn't yet have a clean operational definition
here, because the Macro Engine doesn't currently attach an outcome to a
label — a label like "Risk-On" isn't a prediction with a resolvable
right/wrong answer the way a trade's R-multiple is. Section 4 below
proposes how a future research pass could construct one.

## 4. Validation plan (future research, not yet run)

This is a plan, not a result — consistent with the Day 9/10 precedent of
disclosing what hasn't been checked rather than implying it has:

1. **Accumulate macro history alongside trade outcomes.** Once
   `macro_history.jsonl` has enough rows linked via `macro_ref` to closed
   trades in `trades.json` (the same unified-ID join every prior Day's
   history file supports), a future Research Day could ask purely
   observational questions: "did trades logged during a 'Risk-Off' label
   perform differently from trades logged during 'Risk-On'?" This is
   explicitly NOT a trading rule to build yet — it's the first
   correlational check, same caution the platform applied to Market
   Memory (Day 7) and the Confidence Engine's calibration curve (Day 6).
2. **Check `evidence_quality` against label stability.** A prediction
   this design implies but hasn't tested: runs with `evidence_quality:
   low` should produce labels that flip more often run-to-run than runs
   with `evidence_quality: high`. `macro_history.label_history()` already
   captures the time series needed to check this once enough history
   accumulates.
3. **Backtest the 11 cross-asset relationships' directional accuracy
   independently of any trade.** E.g., "when `gold_vs_real_yields`
   reports `supports: False` for a long, does spot gold in fact
   underperform over the following N days, historically?" This is
   answerable with pure price history (no dependency on this platform's
   own trade log) and would be the first genuinely platform-specific
   validation of relationships that are currently just textbook priors
   (Section 2.1).
4. **Revisit the BTC-liquidity proxy once real network access exists.**
   The current `curve_slope_trend` proxy was designed and tested entirely
   in an environment with zero live Yahoo Finance access; before trusting
   it in production, compare it qualitatively for a few weeks against a
   more standard liquidity measure (e.g., a published financial
   conditions index) to sanity-check the proxy hasn't drifted from what
   it was meant to represent.
5. **Operator data-quality audit.** `macro_reference.json`'s central-bank
   and geopolitical sections ship with placeholder `"example": True`
   entries. Before any of the research above is meaningful, an operator
   needs to populate real curated data — otherwise `central_bank_policy`
   and `geopolitical` will silently contribute nothing (`not_configured`)
   to every regime classification, understating `evidence_quality` for
   the entire assessment.

## 5. Explicit non-goals (per the Day 11 mandate)

- This engine will never become a weighted scoring system. If a future
  validation pass (Section 4) finds a genuinely predictive relationship,
  the correct home for that finding is a *new, separately-designed and
  separately-validated* module — not a retrofit of `macro_regime.py`'s
  labels into a score.
- This engine will never gate, resize, or override an ICT/SMC-originated
  trade. Even a strongly validated macro relationship would only ever
  become advisory context, consistent with how Market Regime (Day 4) and
  Market Memory (Day 7) remain advisory today despite having their own
  research notes discussing potential predictive value.

## 6. Summary

The Macro Intelligence Engine is production-ready as a **descriptive,
advisory-only context layer**: every provider degrades safely, no
provider fabricates data it doesn't have, and the entire engine is
structurally proven to sit outside every trade-affecting decision. What
it is *not* yet is a validated predictive system — no relationship here
(textbook or proxy) has been checked against this platform's own
outcomes, and Section 4's plan is the roadmap for closing that gap
without ever crossing into the "another weighted scoring engine" the
Day 11 mandate explicitly ruled out.
