# Alpha Signals — Institutional Architecture Audit & Roadmap
*Chief Quant Architect review. Tonight's validated increment + ranked path to institutional grade.*

---

## 0. Executive summary

The platform was already a coherent, tested, self-running signal engine (24 engine modules, 77 passing tests, live Claude news, 5-minute automation). Tonight I added **three institutional-core subsystems — all additive, tested, and backward-compatible** (nothing removed):

1. **Market-regime detection** (`engine/regime.py`) — trend/range + volatility expansion/contraction + Wyckoff-style phase.
2. **Risk & exposure layer** (`engine/risk.py`) — volatility-normalized position sizing + portfolio-exposure cap.
3. **Confidence calibration** (`engine/calibration.py`) — predicted-vs-realized probability, Brier score, empirical calibrated map.

Test count went **77 → 89** (12 new, all passing). The WTI note now shows regime, a **calibrated** probability, and volatility-scaled sizing.

**The single most important result:** calibration proved the engine's raw confidence score is **not currently a valid probability** — see §3. That is the highest-priority fix and it is now measurable and monitorable, exactly as your prompt requires.

---

## 1. AUDIT — findings ranked by (impact × effort)

| # | Finding | Area | Impact | Effort | Status |
|---|---------|------|--------|--------|--------|
| 1 | **Confidence score mis-calibrated** (Brier 0.39, worse than coin flip; 90-100 bucket wins 44%) | Statistical validity | 🔴 Critical | Med | **Measured tonight**; fix = recalibrate/rework |
| 2 | No **regime awareness** — same logic in trend & chop | Trading logic | 🔴 High | Low | **Built tonight** |
| 3 | No **volatility-normalized sizing / exposure cap** | Risk mgmt | 🔴 High | Low | **Built tonight** |
| 4 | No **correlation engine** (DXY/yields/VIX vs gold/EUR) | Trading logic | 🟠 Med-High | Med | Roadmap §4 |
| 5 | No **walk-forward / out-of-sample** validation harness | Statistical validity | 🟠 Med-High | Med | Roadmap §4 |
| 6 | No **Bayesian probability updating** (priors → posteriors) | ML readiness | 🟠 Med | Med | Roadmap §4 |
| 7 | Mount/sync fragility on large edits (environmental) | Reliability | 🟡 Low | n/a | Mitigated (atomic writes, salvage, tests) |
| 8 | Some duplicated small helpers (session_of, seg) across scripts | Code quality | 🟡 Low | Low | Roadmap (consolidate into engine.stats) |
| 9 | No structured **logging / run ledger** (only result .txt files) | Operational resilience | 🟡 Med | Low | Roadmap §4 |
| 10 | No **broker execution abstraction** (paper/live) | Automation | 🟡 Med | High | Roadmap §4 (deliberately last) |

Confirmed healthy: architecture (clean modular `engine/` package), security (secrets only in local `.env`, never handled), reliability (graceful fallbacks everywhere, crash-proof journal), automation (scheduled + self-monitoring), UX (one menu, explainable outputs).

---

## 2. DELIVERED TONIGHT — full spec per subsystem

### A) Market-regime detection — `engine/regime.py`
- **Problem:** ICT/SMC setups behave differently in trending vs ranging and high vs low volatility; the engine treated all conditions identically.
- **Root cause:** no regime classifier existed.
- **Solution:** Kaufman Efficiency Ratio (net move ÷ path) → trend/range; ATR percentile → expansion/contraction; range-position → accumulation/distribution/markup/markdown. Pure function of price.
- **Expected impact:** better setup weighting (fade range-bound signals, respect trend), higher expectancy, explainability.
- **Risks:** thresholds (ER 0.35, ATR 30/70pct) are sensible defaults, not yet optimized → mitigated by exposing them and *not* hard-gating trades yet.
- **Implementation:** additive module; surfaced in the WTI note §1.
- **Tests:** `tests/test_regime.py` — ER trend vs random, uptrend/range classification, thin-data → "unknown". Passing.
- **Success metric:** once wired to gate/weight, measure expectancy by regime in the self-review.

### B) Risk & exposure — `engine/risk.py`
- **Problem:** no capital-preservation layer; size wasn't volatility-normalized; no aggregate-risk cap.
- **Root cause:** engine focused on signal generation, not portfolio risk.
- **Solution:** fixed-fractional sizing (risk exactly X% of equity per trade), volatility scaling (shrink risk 25% in expansion), and a portfolio-exposure function with a 6% aggregate cap + concentration flag.
- **Expected impact:** lower drawdown, consistent execution, capital preservation — the prompt's stated priorities over win rate.
- **Risks:** value-per-point differs per instrument/broker → parameterized; sizing is advisory only (never executes).
- **Implementation:** additive; surfaced in the WTI note (volatility-scaled size line).
- **Tests:** `tests/test_risk.py` — sizing math, vol scaling, zero-risk safety, cap breach + concentration. Passing.
- **Success metric:** realized max-drawdown and per-trade risk variance drop once sizing is adopted.

### C) Confidence calibration — `engine/calibration.py`
- **Problem:** the confidence score was assumed predictive but never validated against outcomes.
- **Root cause:** no reliability measurement.
- **Solution:** reliability table (predicted vs realized win rate per bucket), Brier score, and an empirical `calibrated_probability()` map that replaces the raw score once a bucket has ≥8 trades (falls back to raw when thin).
- **Expected impact:** honest, sized-on-reality probabilities; directly satisfies "every probability must be measurable, testable, calibrated."
- **Risks:** small sample per bucket → guarded with min-n and explicit "thin/not trustworthy" flags.
- **Implementation:** additive; WTI note now prints `model% → calibrated%`; `R_CALIBRATION.bat` runs the full report.
- **Tests:** `tests/test_calibration.py` — reliability/Brier, calibrated map from history, thin-data fallback. Passing.
- **Success metric:** Brier score trending toward < 0.25 as the confidence model is reworked.

---

## 3. THE KEY FINDING (act on this first)

Calibration on your **89 live trades**:

```
Brier score: 0.3865   (0=perfect; 0.25=coin flip)  -> WORSE THAN RANDOM
bucket    predicted  realized   n
70-79       75%        46%      46
80-89       85%        38%      16
90-100      95%        44%      27   <- highest confidence, still 44%
```

**Interpretation:** the raw confidence number does **not** rank trades by win probability — high-confidence trades win no more than mid-confidence ones. Institutional consequence: **do not size by raw confidence.** Two correct responses (roadmap §4, ranked):
1. **Short term (safe, now):** size off the *calibrated* map, not the raw score. (Already exposed via `calibrated_probability()`.)
2. **Proper fix:** rework the confidence model — likely the factor weights are wrong or the sample mixes regimes. Validate with walk-forward before trusting any new weights. Do **not** overfit to 89 trades.

This is the platform's highest-ROI improvement, and it is now a monitored metric.

---

## 4. RANKED ROADMAP (remaining institutional capabilities)

Each is scoped to your statistical-validity guardrails (must improve expectancy, be significant, be monitorable, degrade gracefully).

**Tier 1 — highest impact, do next**
1. **Recalibrate/rework the confidence model** using the calibration harness (built) + walk-forward. *Impact: critical. Effort: med.*
2. **Walk-forward validation harness** — rolling in-sample/out-of-sample so every weight change is validated, not fitted. *Impact: high. Effort: med.*
3. **Regime-gating** — use `regime.py` to weight/stand-aside (e.g., skip mean-reversion entries in strong trend). Measure expectancy-by-regime first. *Impact: high. Effort: low-med.*

**Tier 2 — strong institutional value**
4. **Correlation engine** — DXY (dollar), US10Y yields, VIX, Brent-WTI spread; flag when a trade fights its macro driver (e.g., long gold into a strong dollar). *Impact: high. Effort: med.* Feasible via yfinance.
5. **Bayesian probability updating** — treat each factor as evidence; posterior = prior × likelihoods, calibrated on history. Replaces the heuristic ±point nudges with a principled model. *Impact: high. Effort: med-high.*
6. **Dynamic position sizing by calibrated edge** — size ∝ (calibrated_p × payoff), Kelly-fraction-capped. *Impact: high. Effort: low* (builds on `risk.py` + `calibration.py`).

**Tier 3 — scale & operations**
7. **Structured logging / run ledger** (JSONL) for every scan → observability + post-hoc analysis. *Effort: low.*
8. **AI post-trade coaching** — Claude reviews each closed trade vs its thesis and logs a lesson (uses the key you added). *Effort: low-med.*
9. **Liquidity-event calendar** (FOMC/CPI/OPEC/EIA) as a hard risk gate. *Effort: med.*
10. **Broker execution abstraction** (paper→live, MT5/API) — deliberately last; requires the calibration + risk layers proven first. *Effort: high.*

**Explicitly deferred (anti-overfitting):** adding more indicators/patterns before #1–#2 are done. The data says the problem is *calibration and validation*, not a shortage of signals.

---

## 5. Engineering posture (maintained)
- Backward compatibility: 100% — every prior feature still runs; the three modules are additive.
- Tests: 89 passing (unit-level for all new math). Integration via the live feed + note.
- Graceful degradation: regime → "unknown", risk → zero-safe, calibration → raw fallback, all on bad/thin input.
- Rollback: new modules are independent files; deleting them + reverting the 4 note lines fully restores the prior state.

*Research/education only — not financial advice.*
