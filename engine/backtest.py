"""Event-driven backtest with professional trade management.

Entry: limit at the setup level (pessimistic touch fill).
Management: after +1R the stop moves to break-even; at +2R half the position
is banked; the runner targets the final level. This converts many
"ran to +2R then reversed" losers into +1R wins — raising the win rate and
smoothing equity — which is exactly why desks manage trades this way.

Result in R multiples; stop wins ties. Spread/slippage modelled per trade.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .signals import analyze, Signal

VALIDITY_BARS = 96
SCAN_EVERY = 4
WINDOW = 6000
COOLDOWN_BARS = 16
MAX_DAILY_LOSSES = 2
SPREAD_USD = 0.30


@dataclass
class Trade:
    signal: Signal
    fill_time: pd.Timestamp
    exit_time: pd.Timestamp
    result_r: float
    outcome: str   # win | loss | scratch


def manage_exit(hi, lo, direction, entry, stop, target):
    """Break-even after +1R, bank 50% at +2R, runner to target.
    Returns (result_r, exit_index)."""
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0, 0
    finalR = abs(target - entry) / risk
    be = partial = False
    n = len(hi)
    for j in range(n):
        cur_stop = entry if be else stop
        if direction == "long":
            if lo[j] <= cur_stop:
                if partial:
                    return 0.5 * 2.0 + 0.5 * (0.0 if be else -1.0), j
                return (0.0 if be else -1.0), j
            if hi[j] >= target:
                return 0.5 * 2.0 + 0.5 * finalR, j
            if not be and hi[j] >= entry + risk:
                be = True
            if not partial and hi[j] >= entry + 2 * risk:
                partial = True
        else:
            if hi[j] >= cur_stop:
                if partial:
                    return 0.5 * 2.0 + 0.5 * (0.0 if be else -1.0), j
                return (0.0 if be else -1.0), j
            if lo[j] <= target:
                return 0.5 * 2.0 + 0.5 * finalR, j
            if not be and lo[j] <= entry - risk:
                be = True
            if not partial and lo[j] <= entry - 2 * risk:
                partial = True
    if partial:
        return 0.5 * 2.0, n - 1
    return 0.0, n - 1


def run(df15, start=None, end=None, verbose=False):
    end_data = df15.loc[:end] if end else df15
    if start is not None:
        first = int(end_data.index.searchsorted(pd.Timestamp(start)))
        lo0 = max(0, first - WINDOW)
        data = end_data.iloc[lo0:]
        scan_from = first - lo0
    else:
        data = end_data
        scan_from = WINDOW
    high = data["High"].values
    low = data["Low"].values
    n = len(data)
    trades = []
    daily = {}
    i = max(scan_from, WINDOW)
    while i < n - 1:
        day = data.index[i].date()
        if daily.get(day, 0) >= MAX_DAILY_LOSSES:
            i += SCAN_EVERY
            continue
        sig = analyze(data.iloc[i - WINDOW:i + 1])
        if sig is None:
            i += SCAN_EVERY
            continue
        filled = None
        for j in range(i + 1, min(i + 1 + VALIDITY_BARS, n)):
            if sig.direction == "long":
                if low[j] <= sig.entry:
                    filled = j
                    break
            else:
                if high[j] >= sig.entry:
                    filled = j
                    break
        if filled is None:
            i += SCAN_EVERY
            continue
        ru = abs(sig.entry - sig.stop)
        res, off = manage_exit(high[filled + 1:], low[filled + 1:],
                               sig.direction, sig.entry, sig.stop, sig.target)
        if ru > 0:
            res -= SPREAD_USD / ru
        exit_at = min(filled + 1 + off, n - 1)
        outcome = "win" if res > 1e-9 else "loss" if res < -1e-9 else "scratch"
        trades.append(Trade(sig, data.index[filled], data.index[exit_at], res, outcome))
        if verbose:
            print(f"{sig.time} {sig.direction} -> {outcome} {res:+.2f}R")
        if res < -1e-9:
            d = data.index[exit_at].date()
            daily[d] = daily.get(d, 0) + 1
            i = exit_at + COOLDOWN_BARS
        else:
            i = exit_at + 1
    return summarize(trades)


def summarize(trades):
    closed = [t for t in trades if t.outcome in ("win", "loss", "scratch")]
    n = len(closed)
    if n == 0:
        return {"trades": 0, "note": "no closed trades", "trade_list": trades}
    rs = np.array([t.result_r for t in closed])
    wins = rs[rs > 1e-9]
    losses = rs[rs < -1e-9]
    scr = rs[np.abs(rs) <= 1e-9]
    eq = rs.cumsum()
    dd = eq - np.maximum.accumulate(eq)
    gw = wins.sum()
    gl = abs(losses.sum())
    return {
        "trades": n,
        "win_rate": round(len(wins) / n, 3),
        "loss_rate": round(len(losses) / n, 3),
        "scratch_rate": round(len(scr) / n, 3),
        "no_loss_rate": round((len(wins) + len(scr)) / n, 3),
        "avg_win_r": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss_r": round(float(losses.mean()) if len(losses) else 0.0, 2),
        "expectancy_r": round(float(rs.mean()), 3),
        "profit_factor": round(gw / gl, 2) if gl else float("inf"),
        "total_r": round(float(rs.sum()), 2),
        "max_drawdown_r": round(float(dd.min()), 2),
        "trade_list": trades,
    }
