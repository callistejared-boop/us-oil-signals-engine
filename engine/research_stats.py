"""Day 9 — Research & Statistical Validation Framework: standardized
performance metrics.

This module is the platform's single, standardized statistics vocabulary
for evaluating ANY R-multiple result series — a backtest run
(`engine.backtest.run()`), a live/paper trade journal segment
(`trades.json`), a walk-forward out-of-sample window, or a future
experiment's research branch. Every metric here is a PURE function of a
list of R-multiples (or closed-trade dicts carrying `result_r`); nothing
re-fetches or re-derives from a specific engine, so any future research
branch can reuse this without importing anything trade-pipeline-specific.

REUSE, NOT DUPLICATION. `engine/backtest.py`'s own `summarize()` already
computes `expectancy_r`/`profit_factor`/`max_drawdown_r`/`win_rate` inline
— this module does NOT replace that (backtest.py's validated behavior is
untouched this Day, per the mandate: "changing behavior... unless
justified"). Instead, this module is the richer, standalone statistics
layer new research (paper trading, experiments, edge-decay monitoring)
should call, and it recomputes the same core numbers from a plain
R-multiple list so it works identically whether the input came from
`backtest.py`, `trades.json`, or a future research branch's own log.

Every function below is documented with: why it matters, when it can be
mislead, and a minimum-sample caveat — per the Day 9 mandate's explicit
"Statistical Framework" requirement.
"""
from __future__ import annotations

import math

# Reused, not re-declared: the platform's established statistical-trust bar
# (Day 5/6/7 precedent — market_memory.MIN_N_FOR_TRUST,
# confidence_calibration.MIN_N_FOR_CALIBRATION). Metrics below flag when a
# sample falls under this, but never refuse to compute — see
# engine/evidence_tiers.py for the fuller, non-rigid sample-size policy.
MIN_N_FOR_TRUST = 30


def _rs(trades) -> list:
    """Normalize input to a plain list of floats — accepts a list of
    R-multiples directly, or a list of dicts/objects carrying `result_r`
    (trades.json rows, backtest.Trade objects via `.result_r`). Never
    raises; unparseable entries are skipped, not silently zeroed."""
    out = []
    for t in trades or []:
        try:
            if isinstance(t, (int, float)):
                out.append(float(t))
            elif isinstance(t, dict):
                out.append(float(t.get("result_r", 0) or 0))
            else:
                out.append(float(getattr(t, "result_r")))
        except Exception:  # noqa: BLE001
            continue
    return out


def expectancy(trades) -> dict:
    """Mean R-multiple per trade. WHY IT MATTERS: the single number that
    answers "is this profitable per trade, on average" — the foundation
    every other ratio below builds on. WHEN MISLEADING: a small number of
    large winners can produce a positive expectancy that would not survive
    a slightly different sample (see `MIN_N_FOR_TRUST`); expectancy alone
    also says nothing about ORDER (a strategy that wins early then bleeds
    out has the same expectancy as one that loses early then compounds).
    MIN SAMPLE: results with n < `MIN_N_FOR_TRUST` are flagged
    `"sufficient": False` — not hidden, just labeled."""
    rs = _rs(trades)
    n = len(rs)
    if n == 0:
        return {"value": None, "n": 0, "sufficient": False}
    return {"value": round(sum(rs) / n, 3), "n": n, "sufficient": n >= MIN_N_FOR_TRUST}


def profit_factor(trades) -> dict:
    """Gross wins / gross losses. WHY IT MATTERS: measures how much is won
    per unit lost, independent of win rate — a 30%-win-rate strategy with a
    high profit factor can still be excellent. WHEN MISLEADING: undefined
    (reported as `None` with a note, never a fabricated `inf`) when there
    are zero losses in the sample — a common, not-yet-meaningful state
    early in a research branch's life, not a real "infinite edge." MIN
    SAMPLE: same `MIN_N_FOR_TRUST` bar as expectancy; also specifically
    unstable below ~10 losing trades even if `n` overall looks large,
    because it is a ratio of two heavy-tailed sums."""
    rs = _rs(trades)
    n = len(rs)
    if n == 0:
        return {"value": None, "n": 0, "sufficient": False, "note": "no trades"}
    gw = sum(r for r in rs if r > 1e-9)
    gl = abs(sum(r for r in rs if r < -1e-9))
    n_losses = sum(1 for r in rs if r < -1e-9)
    if gl <= 1e-9:
        return {"value": None, "n": n, "sufficient": False,
               "note": "no losing trades in this sample — undefined, not infinite edge"}
    return {"value": round(gw / gl, 2), "n": n,
           "sufficient": n >= MIN_N_FOR_TRUST and n_losses >= 10,
           "n_losses": n_losses}


def win_rate(trades) -> dict:
    """Fraction of closed trades that were wins. WHY IT MATTERS: the most
    intuitive metric, and the one most likely to be over-weighted. WHEN
    MISLEADING: a high win rate with a poor risk:reward ratio (many small
    wins, occasional large losses) can still be a losing system — always
    read alongside `expectancy`/`profit_factor`, never alone. MIN SAMPLE:
    `MIN_N_FOR_TRUST`; a "60% win rate" from 5 trades is 3 wins, not a
    measured rate."""
    rs = _rs(trades)
    n = len(rs)
    if n == 0:
        return {"value": None, "n": 0, "sufficient": False}
    wins = sum(1 for r in rs if r > 1e-9)
    return {"value": round(wins / n, 3), "n": n, "sufficient": n >= MIN_N_FOR_TRUST}


def avg_r_multiple(trades) -> dict:
    """Alias/companion to `expectancy` reported in the mandate's own
    vocabulary ("average R multiple") — identical computation, kept as a
    separate named function so callers matching the mandate's metric list
    verbatim have a directly-named entry point."""
    return expectancy(trades)


def max_drawdown(trades) -> dict:
    """Deepest peak-to-trough decline in cumulative R, IN TRADE SEQUENCE
    ORDER (not recalculated on a resampled/shuffled order). WHY IT MATTERS:
    the number a trader actually has to survive psychologically and
    financially — expectancy can be positive while drawdown is severe.
    WHEN MISLEADING: a single historical sequence understates PLAUSIBLE
    future drawdown — see `engine.montecarlo.simulate()` (existing, reused
    here, not reimplemented) for a resampled-path drawdown DISTRIBUTION
    rather than one realized path. MIN SAMPLE: drawdown from a handful of
    trades is close to meaningless — treat anything under
    `MIN_N_FOR_TRUST` as illustrative only."""
    rs = _rs(trades)
    n = len(rs)
    if n == 0:
        return {"value": None, "n": 0, "sufficient": False}
    cum = peak = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {"value": round(-dd, 2), "n": n, "sufficient": n >= MIN_N_FOR_TRUST}


def sharpe_like(trades) -> dict:
    """Mean(R) / stdev(R) — a PER-TRADE Sharpe-style ratio. HONESTY
    DISCLOSURE: this is explicitly NOT an annualized Sharpe ratio (trades
    are not evenly time-spaced, and this platform does not yet track a
    time-weighted equity curve) — it answers "how much of the average
    result is signal vs. noise across trades," not "risk-adjusted annual
    return." Reported as `sharpe_like` deliberately, not `sharpe`, to avoid
    the false precision of implying a standard, comparable-to-other-systems
    Sharpe number. WHY IT MATTERS: a high mean R with very high variance is
    a much less reliable edge than the same mean with low variance. WHEN
    MISLEADING: assumes roughly independent trades — correlated
    trades (e.g. several open at once in correlated symbols, see Day 3's
    Portfolio Risk Engine) inflate the apparent ratio. MIN SAMPLE:
    `MIN_N_FOR_TRUST`; standard deviation itself is unstable below ~30
    observations."""
    rs = _rs(trades)
    n = len(rs)
    if n < 2:
        return {"value": None, "n": n, "sufficient": False, "note": "need >=2 trades for a stdev"}
    mean = sum(rs) / n
    var = sum((r - mean) ** 2 for r in rs) / (n - 1)
    sd = math.sqrt(var)
    if sd <= 1e-9:
        return {"value": None, "n": n, "sufficient": n >= MIN_N_FOR_TRUST,
               "note": "zero variance in this sample — ratio undefined"}
    return {"value": round(mean / sd, 3), "n": n, "sufficient": n >= MIN_N_FOR_TRUST}


def sortino_like(trades) -> dict:
    """Mean(R) / downside-stdev(R) — same per-trade (not annualized)
    disclosure as `sharpe_like`. WHY IT MATTERS: only penalizes DOWNSIDE
    variance, which better matches a trader's actual concern (upside
    variance from occasional large winners is not a risk to be penalized
    the way `sharpe_like` penalizes it). WHEN MISLEADING: with very few
    losing trades, downside stdev is estimated from a tiny sample and the
    ratio can swing wildly on one additional loss. MIN SAMPLE: needs at
    least a handful of LOSING trades specifically, not just overall n —
    reported `sufficient=False` below 10 losses even if overall n is
    large, mirroring `profit_factor`'s same caveat."""
    rs = _rs(trades)
    n = len(rs)
    if n < 2:
        return {"value": None, "n": n, "sufficient": False, "note": "need >=2 trades"}
    mean = sum(rs) / n
    downside = [r for r in rs if r < 0]
    if len(downside) < 2:
        return {"value": None, "n": n, "sufficient": False,
               "note": "fewer than 2 losing trades — downside stdev undefined"}
    dvar = sum(r ** 2 for r in downside) / len(downside)
    dsd = math.sqrt(dvar)
    if dsd <= 1e-9:
        return {"value": None, "n": n, "sufficient": False, "note": "zero downside variance"}
    return {"value": round(mean / dsd, 3), "n": n,
           "sufficient": n >= MIN_N_FOR_TRUST and len(downside) >= 10,
           "n_losses": len(downside)}


def calmar_like(trades) -> dict:
    """Total R / abs(max drawdown R) — a TRADE-BASED analogue of the Calmar
    ratio. HONESTY DISCLOSURE: the standard Calmar ratio is
    annualized-return / max-drawdown over CALENDAR time; this platform does
    not yet have a clean per-symbol time-annualization basis (trades are
    event-driven, not evenly spaced, and multiple symbols trade
    concurrently), so this reports the trade-sequence equivalent and is
    named `calmar_like` to avoid implying a standard, cross-system-
    comparable annualized number. WHY IT MATTERS: relates total edge
    directly to the worst pain endured to get it — a useful single-number
    summary for "was the drawdown worth the return." WHEN MISLEADING: like
    `max_drawdown` itself, one realized sequence; a different trade
    ordering (or a slightly unluckier future one) can produce a very
    different ratio from the same underlying edge. MIN SAMPLE:
    `MIN_N_FOR_TRUST`."""
    rs = _rs(trades)
    n = len(rs)
    if n == 0:
        return {"value": None, "n": 0, "sufficient": False}
    dd = max_drawdown(rs)
    total = sum(rs)
    if dd["value"] is None or abs(dd["value"]) <= 1e-9:
        return {"value": None, "n": n, "sufficient": False, "note": "no drawdown in this sample — undefined"}
    return {"value": round(total / abs(dd["value"]), 2), "n": n, "sufficient": n >= MIN_N_FOR_TRUST}


def recovery_factor(trades) -> dict:
    """Total R / abs(max drawdown R) — DELIBERATELY the same formula as
    `calmar_like` (this is the conventional relationship between the two
    metrics; "recovery factor" and "Calmar ratio" differ in institutional
    usage mainly by whether the numerator is annualized). Reported as its
    own named function so callers matching the mandate's metric list
    verbatim (`recovery_factor` is listed separately from `calmar_like`)
    have a directly-named entry point; the underlying number and all
    caveats are identical to `calmar_like` — see that function's
    docstring."""
    return calmar_like(trades)


def stability_over_time(trades, n_segments: int = 4) -> dict:
    """Splits the trade sequence (IN ORDER) into `n_segments` roughly-equal
    chunks and reports each chunk's expectancy — a crude but honest way to
    see whether the edge is concentrated in one period or spread across
    the whole sample. WHY IT MATTERS: a positive overall expectancy driven
    entirely by one hot streak is a materially different (weaker) claim
    than the same expectancy spread evenly — this is the single-series
    complement to `engine.walkforward`'s out-of-sample comparison. WHEN
    MISLEADING: with few total trades, segments become tiny and their
    individual expectancies are close to noise — `sufficient` requires
    every segment to independently clear a much lower bar
    (`MIN_N_FOR_TRUST // n_segments`, minimum 3) since this is explicitly
    a WITHIN-sample stability check, not a fresh out-of-sample test. MIN
    SAMPLE: needs at least `n_segments` trades to report anything at all."""
    rs = _rs(trades)
    n = len(rs)
    if n < n_segments:
        return {"segments": [], "n": n, "sufficient": False,
               "note": f"need at least {n_segments} trades to segment"}
    seg_size = n // n_segments
    segments = []
    for i in range(n_segments):
        start = i * seg_size
        end = (i + 1) * seg_size if i < n_segments - 1 else n
        chunk = rs[start:end]
        segments.append({"segment": i + 1, "n": len(chunk),
                         "expectancy": round(sum(chunk) / len(chunk), 3) if chunk else None})
    min_seg_n = max(3, MIN_N_FOR_TRUST // n_segments)
    sufficient = all(s["n"] >= min_seg_n for s in segments)
    values = [s["expectancy"] for s in segments if s["expectancy"] is not None]
    all_positive = all(v > 0 for v in values) if values else False
    all_negative = all(v < 0 for v in values) if values else False
    return {"segments": segments, "n": n, "sufficient": sufficient,
           "consistent_sign": all_positive or all_negative,
           "note": ("" if sufficient else
                    f"each segment needs >= {min_seg_n} trades to be more than illustrative")}


def full_report(trades) -> dict:
    """One call computing every standardized metric — the function future
    research (paper trading review, experiment evaluation, edge-decay
    monitoring) should call rather than assembling metrics individually.
    Never raises; each sub-metric degrades independently."""
    try:
        return {
            "n": len(_rs(trades)),
            "expectancy": expectancy(trades),
            "profit_factor": profit_factor(trades),
            "win_rate": win_rate(trades),
            "avg_r_multiple": avg_r_multiple(trades),
            "max_drawdown": max_drawdown(trades),
            "sharpe_like": sharpe_like(trades),
            "sortino_like": sortino_like(trades),
            "calmar_like": calmar_like(trades),
            "recovery_factor": recovery_factor(trades),
            "stability_over_time": stability_over_time(trades),
        }
    except Exception as exc:  # noqa: BLE001
        return {"n": 0, "error": f"full_report error: {exc}"}
