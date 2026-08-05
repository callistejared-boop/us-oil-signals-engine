# Research: Market Regime Engine — Historical Contribution & Validation Plan

Day 4 deliverable (2026-08-03). Companion to `MARKET_REGIME_SPECIFICATION.md`.

## 1. What data actually exists to analyze

Queried `trades.json` directly (102 rows: 42 win, 54 loss, 3 scratch, 3
still open). Findings, stated plainly rather than dressed up:

- **99 closed trades total**, but only **10 carry any regime tag**
  (`regime_trend`/`regime_vol`, added to the journal schema partway through
  this platform's history — see `journal.py`'s `Trade` dataclass). The other
  89 closed trades (including the entire original 42-trade backtest) predate
  regime tagging and cannot be attributed to a regime at all.
- Of those 10 tagged trades, **every single one is tagged `regime_trend
  == "range"`.** Zero are tagged `"trend"`. This is not a finding about
  trending vs. ranging performance — it just means the live/paper-mode
  window captured so far happened to occur entirely during periods the OLD,
  single-timeframe `regime.classify()` call scored as ranging. There is
  currently **no data at all** to compare trend-regime performance against
  range-regime performance.
- This 10-trade sample also predates the Day 4 Market Regime Engine itself
  (which did not exist until today) — it reflects the old coarse
  single-timeframe classifier (`trend`/`range` + `expansion`/`contraction`/
  `normal`), not the new multi-timeframe taxonomy (Strong Bull Trend,
  Distribution, etc.). There is **zero historical data yet** tagged with the
  new taxonomy — `regime_history.jsonl` starts empty as of this Day 4 change
  and only begins accumulating from today's first live scan forward.

**Bottom line: the mandate's four research questions (which regimes
contribute most to expectancy, which strategies perform best under which
regime, which regimes underperform, and refinement recommendations) cannot
be answered with statistical confidence today, because the historical
dataset that would answer them does not exist yet.** What follows is (a) the
directional signal in the small amount of data that does exist, presented
with its sample size stated honestly, and (b) the concrete plan to build the
real answer as data accumulates — which is what Day 4 mandate itself asks
for when it says the recommendations should be "based on observed data
rather than assumptions."

## 2. What the 10-trade tagged sample shows (directional only — not actionable)

| `regime_vol` | n | Sum R | Expectancy |
|---|---|---|---|
| `contraction` | 5 | -2.00 | **-0.40R** |
| `normal` | 4 | +4.00 | **+1.00R** |
| `expansion` | 1 | -1.00 | -1.00R (single trade) |

Directionally, this is consistent with the Day 4 compatibility matrix's own
reasoning (§6 of `MARKET_REGIME_SPECIFICATION.md`): low-volatility,
range-bound/choppy conditions (`contraction`) look worse than normal
conditions for this strategy, and the matrix already independently
classifies `Range` as "discouraged" for exactly that structural reason (more
false BOS signals in low-ER conditions). **But n=4 and n=5 are both below
this platform's own stated statistical bar** — `calibration.py`'s `min_n=8`
precedent and `RISK_RULES.md`'s 30-closed-trade forward-test requirement
both exist specifically because samples this small produce unreliable
estimates. This is supporting circumstantial context for the compatibility
matrix's a-priori reasoning, not independent statistical proof of it.

For completeness, per-symbol expectancy across all 99 closed trades
(regime-tagged or not) — not new to Day 4, but relevant background the
regime engine's per-symbol validation should eventually be checked against:

| Symbol | n | Expectancy |
|---|---|---|
| XAUUSD | 38 | +1.06R |
| EURUSD | 10 | +0.98R |
| BTCUSD | 33 | +0.81R |
| WTIUSD | 17 | +0.18R |

WTIUSD's materially lower expectancy than the other three symbols is a
pre-existing observation (not caused by or specific to the regime engine)
worth keeping in mind when the regime-conditional analysis in §3 eventually
has enough WTIUSD samples to run per-symbol — a platform-wide effect and a
regime-specific effect could otherwise be conflated.

## 3. Statistical Validation Plan

Per the Day 4 mandate's own closing recommendation: *"Ask Claude to compare
performance with and without the Regime Engine during replay and forward
testing. A regime filter should only remain in production if it demonstrates
an improvement in metrics such as expectancy, drawdown, profit factor, or
risk-adjusted returns."* This is the concrete plan to do that.

### 3.1 Data collection (starts today, automatic, no action needed)

Every live scan (`alert_signals.py`, both stages, and `hourly_briefing.py`)
now calls `regime_engine.classify()` and records the result to
`regime_history.jsonl` via `regime_history.record()` — see
`MARKET_REGIME_SPECIFICATION.md` §7. This runs unconditionally regardless of
`regime_filter_mode`, so the evidence needed to evaluate whether filtering
helps accumulates whether or not filtering is enabled. This is precisely why
the default is `"advisory"`: shipping `"block"` today would mean discarding
signals before we ever learn whether discarding them was correct.

### 3.2 Minimum sample size before drawing conclusions

Mirroring `calibration.py`'s `min_n=8` and `RISK_RULES.md`'s 30-trade bar:
**do not treat any regime-conditional comparison below n=30 closed trades
per bucket as reliable**, and prefer n≥30 for the specific regime label
being evaluated (e.g., 30 closed trades that occurred during "Strong Bull
Trend" specifically), not 30 trades in aggregate.

### 3.3 The actual with/without comparison

Once `regime_history.jsonl` has accumulated alongside enough newly-closed,
regime-tagged trades (journal logging currently only tags the OLD
single-TF snapshot — see `MARKET_REGIME_SPECIFICATION.md` §8 limitation #2
— so this comparison will initially need to join `trades.json` rows to the
nearest-in-time `regime_history.jsonl` record by symbol+timestamp rather
than a direct field lookup, until/unless the journal schema is extended):

1. For every closed trade, find the regime classification in effect at
   entry time (nearest `regime_history.jsonl` record for that symbol at or
   before the trade's `opened` timestamp).
2. Compute expectancy, win rate, profit factor, and max drawdown (reusing
   `forward_report.py`'s existing `drawdown_r()` — do not reimplement),
   split by: (a) `compatibility` tier (preferred/acceptable/discouraged/
   prohibited), (b) `primary` label, (c) `quality_score` bucket (e.g.
   quartiles).
3. **The "without" baseline is what already happened** — no `regime_filter_mode`
   was enforced (default `"advisory"`), so every trade in the dataset already
   represents "no regime filter applied." The "with" simulation is
   retrospective: replay the same closed-trade history and ask "would
   `apply_regime_gate()` in `"block"` mode, at the historical
   `regime_min_quality_for_block` threshold, have suppressed this trade?" —
   then recompute expectancy/drawdown/profit-factor on the surviving subset.
4. Compare the two distributions. Promotion criteria (do not change the
   default without ALL of):
   - Expectancy strictly higher on the filtered subset, not just
     directionally different, at n≥30 per compared bucket.
   - Trailing drawdown (`forward_report.drawdown_r`) not worse on the
     filtered subset.
   - The number of trades removed by filtering is not so large that the
     remaining sample becomes statistically unreliable on its own (a filter
     that "improves" expectancy by cutting the sample to n=5 has not proven
     anything).
5. If criteria are met for a specific regime label or compatibility tier
   (not necessarily all of them at once), the promotion is: raise
   `regime_min_quality_for_block` for THAT case specifically, or flip
   `regime_filter_mode` to `"block"` platform-wide if the effect holds
   across all/most regimes and symbols. If criteria are not met, the
   correct action per the mandate's own words is to "revise or remove," not
   to keep an unproven filter running by default.

### 3.4 What "revise" could mean if the flat weights in §5/§6.1 of the spec turn out wrong

Once enough transition events exist in `regime_history.jsonl`
(`regime_history.transitions()`), the transition-risk weights (0.4/0.3/0.2)
and the quality-score base values (80/60/35/10) documented as heuristics in
`MARKET_REGIME_SPECIFICATION.md` §5/§6.1 become fittable: a logistic
regression or simple frequency table of "given these three factors' values,
did a transition actually occur within N bars?" would replace the current
domain-reasonable constants with calibrated ones. Flagged as a Day 5+
candidate, not attempted here — there is not yet a single transition event
recorded (the history file is brand new).

## 4. Recommendations for future refinement (grounded in what was actually observed, not assumed)

1. **Do not enable `regime_filter_mode="block"` yet.** Ship `"advisory"`
   (already the default) and let data accumulate. This is the direct,
   evidence-grounded consequence of §1-§2 above, not a generic caution.
2. **Extend `journal.py`'s `Trade` dataclass to store the Day 4 taxonomy
   directly** (`regime_primary`, `regime_quality_score`, `regime_compatibility`
   fields) rather than relying on nearest-timestamp joins against
   `regime_history.jsonl` for the §3.3 analysis. This is a schema change
   outside Day 4's "integration, not a redesign" scope (same category of
   deferral as Day 3's `risk_cash`/`units` field gap), but it would make the
   §3 validation meaningfully easier and less error-prone once enough
   trades have closed to run it.
3. **Revisit the weekly-timeframe data-window limitation** (§8 of the spec)
   before trusting the "strategic" anchor's fallback-to-daily behavior
   long-term — if a longer-history feed becomes available, re-verify that
   `1w` classifications look sane on real data before making the weekly
   timeframe load-bearing for anything.
4. **Re-run this research report after the first 30 regime-tagged closed
   trades exist**, following the plan in §3, and update the promotion
   decision based on actual results rather than the current directional-only
   read.
