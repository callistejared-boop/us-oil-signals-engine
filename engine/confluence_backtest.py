"""V2.2 Priority 5 (extension) — Confluence-Aware Backtest Bridge.

Audit finding (2026-08-15 live diagnostic, see
QUALIFICATION_DIAGNOSTICS_NOTE.md): 82% of live rejections in the tracked
window happened at the `confluence_assessment` stage — MAST's score/
hard-gate filter. Reading `engine/backtest.py` in full confirmed it calls
ONLY `engine.signals.analyze()` (Layer 1 ICT/SMC) — it has NEVER
incorporated `engine.confluence.py`'s scoring or hard-gate logic. That
means the single filter currently blocking the large majority of live
candidates has never been validated against historical data at all: its
70-point score bar and five hard gates (`Breakout confirmation`, `Mean
Reversion context`, `News risk acceptable`, `Minimum Risk:Reward met`,
`Liquidity objective`) were never backtested.

This module closes that gap WITHOUT changing `backtest.py`'s own default
behavior — extract-and-reuse, same posture as every other Priority 2-5
module this cycle. It replays `backtest.py`'s own `trade_list` (produced
unmodified) through `confluence.analyze()` at the SAME historical decision
point each signal fired, using each `Trade`'s own `signal.time` to
relocate the exact bar index and reconstruct the exact
`data.iloc[i-WINDOW:i+1]` slice `backtest.run()` used internally. This
lets a caller ask, for the first time, "how would this filter's threshold
have performed against real historical outcomes?"

Methodology disclosure (not silently glossed over): `confluence.analyze()`
re-runs Layer 1 internally at `signals.WATCH_THRESHOLD` (55), while
`backtest.py`'s own signal used `signals.PUBLISH_THRESHOLD` (70) — WATCH
is strictly more permissive, so it should reliably re-find whatever
PUBLISH-threshold signal `backtest.py` already found at that bar. Each
replayed trade's direction/entry is verified against the original; a
mismatch is flagged (`"mismatch"`) and excluded from aggregate stats
rather than silently reconciled or dropped, so a caller can see how often
it happens.

This is HISTORICAL_TESTING-stage evidence for `engine.experiment_registry`
— it does not decide anything, change any config default, or touch
production. See `CONFLUENCE_BACKTEST_EXPERIMENT_NOTE.md` for the
registered experiment and its findings.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import backtest as bt        # noqa: E402
from engine import confluence as cf      # noqa: E402

VERSION = "1.0.0"
ENTRY_TOL = 0.0015


def _locate_bar(df15, when) -> "int | None":
    try:
        loc = df15.index.get_loc(when)
        return int(loc) if isinstance(loc, (int, np.integer)) else None
    except Exception:  # noqa: BLE001
        return None


def replay_with_confluence(df15, symbol: str, trades: list, window: int = bt.WINDOW) -> list:
    """For each `backtest.Trade`, reconstruct the confluence read at its
    own decision point. Returns one dict per input trade — nothing is
    silently dropped, even on error (`"status": "error"`) or a
    direction/entry mismatch against the original signal
    (`"status": "mismatch"`) — so a caller always sees what happened to
    every trade it passed in. Never raises."""
    out = []
    for t in trades:
        try:
            sig = t.signal
            i = _locate_bar(df15, sig.time)
            if i is None or i - window < 0:
                out.append({"status": "error", "trade": t, "reason": "bar not locatable"})
                continue
            df_slice = df15.iloc[i - window:i + 1]
            cr = cf.analyze(df_slice, symbol=symbol)
            if cr is None:
                out.append({"status": "error", "trade": t, "reason": "confluence found no signal"})
                continue
            entry_tol = max(abs(sig.entry) * ENTRY_TOL, 1e-9)
            cr_entry = getattr(cr.sig, "entry", None) if cr.sig is not None else None
            direction_mismatch = cr.direction != sig.direction
            entry_mismatch = cr_entry is None or abs(cr_entry - sig.entry) > entry_tol
            if direction_mismatch or entry_mismatch:
                out.append({"status": "mismatch", "trade": t, "confluence": cr})
                continue
            out.append({"status": "ok", "trade": t, "confluence": cr,
                       "score": cr.score, "base_tier": cr.base_tier,
                       "final_tier": cr.final_tier,
                       "hard_gate_rejected": cr.final_tier == "rejected"})
        except Exception as exc:  # noqa: BLE001
            out.append({"status": "error", "trade": t, "reason": str(exc)})
    return out


def would_qualify(replayed_row: dict, min_score: int) -> bool:
    """Whether this replayed trade would have qualified (base_tier
    confirmed, no hard-gate rejection, score >= min_score) under a given
    threshold — matches `confluence.analyze()`'s own downgrade logic
    exactly (`elif sig.tier == "confirmed" and score < min_score: final_tier
    = "watch"`), just evaluated post-hoc for any threshold value instead of
    the one `confluence.analyze()` was called with. Never raises."""
    try:
        if replayed_row.get("status") != "ok":
            return False
        if replayed_row.get("hard_gate_rejected"):
            return False
        if replayed_row.get("base_tier") != "confirmed":
            return False
        return replayed_row.get("score", -1) >= min_score
    except Exception:  # noqa: BLE001
        return False


def compare_thresholds(df15, symbol: str, trades: list, thresholds=(0, 50, 55, 60, 65, 70, 75, 80),
                       window: int = bt.WINDOW) -> dict:
    """The core deliverable: one `confluence.analyze()` pass per trade
    (expensive; done once), then every threshold in `thresholds` is
    derived from that same pass and scored with `backtest.summarize()`
    (reused unmodified — never reimplemented) over the qualifying subset.
    Returns `{"replay_status": {...}, "by_threshold": {threshold: summary}}`.
    Never raises; a summarize() failure for one threshold doesn't block
    the others."""
    replayed = replay_with_confluence(df15, symbol, trades, window=window)
    status_counts = {}
    for r in replayed:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    by_threshold = {}
    for th in thresholds:
        try:
            subset = [r["trade"] for r in replayed if would_qualify(r, th)]
            by_threshold[th] = bt.summarize(subset)
        except Exception as exc:  # noqa: BLE001
            by_threshold[th] = {"error": str(exc)}

    baseline = bt.summarize([r["trade"] for r in replayed if r["status"] in ("ok", "mismatch")])

    return {
        "version": VERSION,
        "total_trades_replayed": len(trades),
        "replay_status_counts": status_counts,
        "baseline_no_confluence_filter": baseline,
        "by_threshold": by_threshold,
    }
