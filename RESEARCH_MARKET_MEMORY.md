# RESEARCH REPORT — Market Memory Engine (Day 7)

Companion to `MARKET_MEMORY_SPECIFICATION.md`. Follows the same honesty
convention established Day 4-6: where data are insufficient, this report
states that explicitly rather than drawing unsupported conclusions.

## 1. What the real data actually contains today

Queried directly from `trades.json` (2026-08-03, immediately before
writing this report):

| Metric | Value |
|---|---|
| Total trade rows | 102 |
| Closed trades | 99 |
| Records with `regime_ref`/`confluence_ref`/`confidence_ref` matched | 0 |
| Records with `regime` recoverable via trade-row fallback (`regime_trend`/`regime_vol`) | 13 |
| Records with no recoverable regime/confluence/confidence data at all | 89 |

**Every existing trade predates the unified trade ID** (it was introduced
this Day and Day 6) — `data_completeness` is `"missing"` or, at best,
`"trade_row_only"` for all 102 `MemoryRecord`s that can be assembled today.
This is the same finding pattern as Day 4/5/6: the engine is fully built
and tested, but the richest version of its own data doesn't exist yet
because the fields it depends on only started being populated today.

## 2. What can be assessed today: exploratory session/regime patterns

Even with `trade_row_only` (or missing) completeness, `MemoryRecord`s
still carry `session` (always derivable — Sec.5 of the spec) and
`regime_trend`/`regime_vol` (present on 13 of 102 rows). Running the
performance-analytics functions over all 99 closed trades today:

**By session** (`performance_by_session()`):

| Session | n | Win rate | Avg result_r | Trustworthy (n≥30)? |
|---|---|---|---|---|
| off-session | 43 | 44.2% | +0.81R | Yes |
| Asian | 31 | 38.7% | +0.62R | Yes |
| London KZ | 13 | 30.8% | +0.60R | No |
| New York KZ | 12 | 58.3% | +1.82R | No |

**By strategy/regime** (`performance_by_strategy_regime()`):

| Strategy | Regime | n | Win rate | Avg result_r | Trustworthy? |
|---|---|---|---|---|---|
| ict_smc_mast | unknown (no regime tag) | 89 | 43.8% | +0.93R | Yes |
| ict_smc_mast | range | 10 | 30.0% | +0.10R | No |

**Honest reading of this table**: two session buckets (off-session, Asian)
clear the `MIN_N_FOR_TRUST=30` bar and show a real, if unremarkable,
positive expectancy despite a sub-50% win rate — consistent with this
platform's asymmetric RR management (break-even at +1R, partial at +2R)
rather than any claim about session quality specifically. The New York
kill-zone bucket's apparently much stronger 58.3%/+1.82R is based on only
12 trades — **explicitly flagged as untrustworthy by the framework itself**
(`sufficient: False`), not presented as a finding. This is a textbook case
of why the `MIN_N_FOR_TRUST` gate exists: a naive read of this table would
conclude "trade New York KZ preferentially," which the sample size cannot
actually support.

The regime table is even thinner: 89 of 99 closed trades have no regime
tag at all (predating Day 4), leaving only 10 range-tagged trades to
compare against — nowhere near enough to say anything about strategy
performance BY regime, which is the mandate's own headline research
question. **This cannot yet be answered.**

## 3. Similarity methodology

`similarity()`'s seven-dimension weighted comparison (Sec.4 of the spec)
was validated only structurally today — unit tests confirm identical
feature vectors score 1.0, completely disjoint vectors score 0.0, and
partial confluence-profile overlap scores between the two via Jaccard
overlap. **No claim is made that these weights (or even these seven
dimensions) are the RIGHT ones for finding genuinely predictive historical
comparisons** — they are an engineering-judgment starting point, exactly
like every other disclosed-not-fitted formula in this codebase (Day 4's
transition-risk weights, Day 5's quality-score weights, Day 6's
confidence-composite weights, this Day's own similarity weights).

## 4. Historical evidence framework and sample-size requirements

Two thresholds, both disclosed and reused from established precedent:

- `MIN_N_FOR_CONTEXT = 5` — below this, `historical_context()` refuses to
  report ANY aggregate number at all, stating explicitly that the sample
  is too small to describe even directionally.
- `MIN_N_FOR_TRUST = 30` — matches Day 5/6's bar for "statistically
  trustworthy." Between 5 and 30 comparable trades, `historical_context()`
  DOES report an aggregate but labels it `"sparse"` and appends an explicit
  note that it is descriptive, not confirmatory.

`memory_quality()`'s `confidence_label` (`insufficient`/`sparse`/
`moderate`/`rich`) is the single field every consumer (Confidence Engine's
`memory_context`, the dashboard's `market_memory_advisory` block) should
check before treating a comparison as meaningful. Given §1's findings,
every `MemoryRecord`-based comparison made today will show, at best,
`data_completeness_rate` near 0% (the completeness axis specifically,
independent of raw sample size) — worth surfacing prominently rather than
letting a decent `n` mask thin underlying data quality.

## 5. Validation methodology and the calibration-comparison activation trigger

Per the platform owner's explicit Day 7 instruction, the raw-vs-composite
calibration comparison (`confidence_calibration.raw_vs_composite_comparison()`,
see `MARKET_MEMORY_SPECIFICATION.md` Sec.8) is built but deliberately
inactive. **Activation trigger, stated explicitly so it isn't left
ambiguous**: this function should be wired into a live report/dashboard
only once `join_trades_with_confidence()` (Day 6) returns ≥30 matched
trades — the same `MIN_N_FOR_CALIBRATION` bar the function itself already
enforces before returning `"active": True`. Today it returns `n=0`
(§1's finding: zero trades have a `confidence_ref`), so activation is not
yet due regardless of how this function is wired.

The proper validation methodology for the SIMILARITY framework itself
(distinct from calibration) would be: once enough matched, ref-linked
trades accumulate, hold out a rolling window of recent trades, run
`find_similar()` against everything BEFORE that window (this is exactly
what the look-ahead guard already enforces at the single-trade level — a
backtest-style validation would just run it repeatedly across a rolling
window), and check whether the comparable set's aggregate win rate/
expectancy actually predicted the held-out window's realized outcomes
better than a naive baseline (e.g. the platform's overall win rate). This
has not been run — there isn't enough ref-linked data yet to run it
meaningfully.

## 6. Expected limitations

1. **Every finding in §2 is descriptive of the PAST 99 trades, not
   predictive** — none of it has been validated against held-out data,
   and most buckets don't even clear the trust bar.
2. **The seven similarity dimensions and their weights are unvalidated**
   (§3) — this is a design, not a finding.
3. **Regime/confluence/confidence completeness will remain near-zero for
   existing trades permanently** — `MemoryRecord`s for pre-Day-6/7 trades
   can never be retroactively enriched (the underlying history rows were
   never recorded); only trades from this deployment forward will have
   full completeness.
4. **No dedicated portfolio history log exists** (spec Sec.2.1/Sec.6) —
   `portfolio_context` will remain the least complete field even for new,
   fully ref-linked trades until (if) that gap is closed.
5. **The volatility-taxonomy mismatch** between live and historical
   fallback data (spec Sec.6 item 3) means similarity comparisons on the
   `volatility` dimension are slightly less precise than the other
   dimensions until unified.

## 7. Future enhancements

- Once ref-linked trade volume grows, revisit whether all seven similarity
  dimensions independently add predictive value, or whether some should be
  dropped/reweighted (the same "smallest evidence set that consistently
  improves expectancy" question Day 5 asked of confluence sources, now
  applicable to similarity dimensions).
- Consider a dedicated `portfolio_history.jsonl` (Sec.2.1) so
  `portfolio_context` doesn't depend on `confidence_ref` resolving.
- Consider an index for `find_by_ref()` if/when trade volume grows enough
  that the current O(n) scan becomes a measurable cost (not yet — see
  spec Sec.3.2's benchmark).
- Run the rolling-window similarity validation described in §5 once
  sufficient ref-linked data exists.
- Activate `raw_vs_composite_comparison()` in a live report once it
  reports `n >= 30` (§5).

## 8. Explicit statement on insufficient data

Per the mandate's own instruction: **where data are insufficient, this
report states that explicitly rather than drawing unsupported
conclusions.** The two session buckets that clear `MIN_N_FOR_TRUST` in §2
are the only numbers in this report meeting this platform's own
established statistical bar — and even those describe the past, not a
validated prediction. Every other number in this report (the New York
kill-zone session, the regime breakdown, anything the similarity framework
would return today) is explicitly marked insufficient or sparse by the
framework itself, and should be read that way rather than as a finding.
