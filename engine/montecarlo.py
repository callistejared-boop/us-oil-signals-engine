"""Monte Carlo bootstrap over a backtested trade sequence.

Answers the questions a bare backtest cannot:
  * How much of the result is sequence luck?
  * How deep can drawdowns plausibly get?
  * What is the probability of hitting a ruin threshold?
  * If a max drawdown happens, how many trades does it typically take
    to recover from it? (V2.2 Priority 4 extension — the one metric
    PHASE0_FORENSIC_AUDIT.md Section P flagged as missing against the
    spec's stated requirements; median/95th-percentile/tail drawdown and
    probability of ruin were already present and are unchanged here.)

Method: resample the R-multiple series with replacement (same number of
trades per path), N paths, then report distribution percentiles.
"""
from __future__ import annotations

import numpy as np


def _recovery_trades(eq: np.ndarray) -> float | None:
    """Trades from the pre-drawdown peak to the first point equity
    revisits (or exceeds) that peak. `eq` is a path's cumulative-R
    equity curve. Returns None if the path never recovers (censored —
    the drawdown is still open at the end of the simulated path)."""
    running_peak = np.maximum.accumulate(eq)
    dd = eq - running_peak
    trough_idx = int(np.argmin(dd))
    if dd[trough_idx] >= 0:
        return 0.0  # never drew down at all
    peak_level = running_peak[trough_idx]
    # Look for the first index at/after the trough where equity is back
    # at or above the peak level that preceded the drawdown.
    recovered = np.where(eq[trough_idx:] >= peak_level)[0]
    if recovered.size == 0:
        return None
    # Find the trade index the peak was actually set at (last index
    # before/at trough where eq == peak_level), so "trades to recover"
    # measures from the peak, not from trade 0.
    peak_idx = int(np.where(eq[:trough_idx + 1] == peak_level)[0][-1])
    recovery_idx = trough_idx + int(recovered[0])
    return float(recovery_idx - peak_idx)


def simulate(rs: list[float] | np.ndarray, n_paths: int = 5000,
             ruin_r: float = -20.0, seed: int = 42) -> dict:
    """Bootstrap `n_paths` alternative orderings/redraws of the trades."""
    rs = np.asarray(rs, dtype=float)
    if rs.size < 10:
        return {"note": f"only {rs.size} trades — Monte Carlo not meaningful"}
    rng = np.random.default_rng(seed)
    n = rs.size

    totals = np.empty(n_paths)
    max_dds = np.empty(n_paths)
    recovery_trades = []
    never_recovered = 0
    ruined = 0
    for p in range(n_paths):
        path = rng.choice(rs, size=n, replace=True)
        eq = path.cumsum()
        dd = eq - np.maximum.accumulate(eq)
        totals[p] = eq[-1]
        max_dds[p] = dd.min()
        if (eq <= ruin_r).any():
            ruined += 1

        rec = _recovery_trades(eq)
        if rec is None:
            never_recovered += 1
        elif rec > 0:
            recovery_trades.append(rec)

    pct = lambda a, q: round(float(np.percentile(a, q)), 2)
    out = {
        "paths": n_paths,
        "trades_per_path": int(n),
        "total_r_p5": pct(totals, 5),
        "total_r_p25": pct(totals, 25),
        "total_r_p50": pct(totals, 50),
        "total_r_p75": pct(totals, 75),
        "total_r_p95": pct(totals, 95),
        "prob_negative": round(float((totals < 0).mean()), 3),
        "max_dd_p50": pct(max_dds, 50),
        "max_dd_p95": pct(max_dds, 5),   # 95th worst drawdown (more negative)
        "prob_ruin": round(ruined / n_paths, 4),
        "ruin_threshold_r": ruin_r,
        "prob_never_recovered": round(never_recovered / n_paths, 4),
    }
    if recovery_trades:
        rt = np.asarray(recovery_trades, dtype=float)
        out["recovery_trades_p50"] = pct(rt, 50)
        out["recovery_trades_p95"] = pct(rt, 95)
    else:
        out["recovery_trades_p50"] = None
        out["recovery_trades_p95"] = None
    return out
