"""Monte Carlo bootstrap over a backtested trade sequence.

Answers the questions a bare backtest cannot:
  * How much of the result is sequence luck?
  * How deep can drawdowns plausibly get?
  * What is the probability of hitting a ruin threshold?

Method: resample the R-multiple series with replacement (same number of
trades per path), N paths, then report distribution percentiles.
"""
from __future__ import annotations

import numpy as np


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
    ruined = 0
    for p in range(n_paths):
        path = rng.choice(rs, size=n, replace=True)
        eq = path.cumsum()
        dd = eq - np.maximum.accumulate(eq)
        totals[p] = eq[-1]
        max_dds[p] = dd.min()
        if (eq <= ruin_r).any():
            ruined += 1

    pct = lambda a, q: round(float(np.percentile(a, q)), 2)
    return {
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
    }
