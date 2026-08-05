"""Day 12 — Historical Replay.

Runs the execution simulator against historical trades under
CONFIGURABLE, NAMED assumption profiles (e.g. "WTI, London session,
typical spread, average slippage, normal latency" — the mandate's own
example maps directly to `run_replay(symbol="WTIUSD", session="London
KZ", profile="typical")`). Every replay is fully reproducible: given the
same `rows`, `symbol`, `session`, `profile`, and `seed`, two runs produce
byte-identical output. This is enforced by (1) using one shared,
explicitly-seeded `random.Random(seed)` advanced sequentially across
every trade in the replay, and (2) always passing each trade's own
stored timestamp as `signal_ts` into the fill simulation so no function
in the chain ever falls back to wall-clock `datetime.now()` — the same
"never let live time leak into a reproducible calculation" discipline
`edge_investigation.py`'s `variance_permutation_test()` established at
Day 10 for its own seeded permutation test.

Data source: reuses `engine.journal`'s own `trades.json` storage via
`store.load_array()` — the identical access pattern `edge_decay_monitor`
and `edge_investigation` (Day 9/10) already use — rather than adding a
second read path. Every function also accepts an explicit `rows=`
override (this codebase's standing offline-testing convention).

Exit price reconstruction: `trades.json` stores `result_r`, not the
literal historical exit tick (the partial-banking exit price isn't
persisted per-trade). `_approx_exit_price()` reconstructs an
ILLUSTRATIVE exit price from `entry`/`stop`/`result_r` — disclosed as an
approximation, not the stored actual exit, mirroring Day 10's own
`restate_win_to_current_methodology()` reconstruction-from-stored-fields
pattern.
"""
from __future__ import annotations

import random

from . import execution_report as er
from . import spread_model as spr

VERSION = "1.0.0"

# Named, disclosed assumption profiles. Each maps to the same
# atr_pct/news_blackout/stress-flag inputs `execution_report.py` already
# accepts — this is a convenience layer, not a new calculation.
PROFILES = {
    "typical": {"atr_pct": 0.5, "news_blackout": False, "stress": {}},
    "tight": {"atr_pct": 0.2, "news_blackout": False, "stress": {}},
    "wide": {"atr_pct": 0.85, "news_blackout": False, "stress": {}},
    "stressed": {"atr_pct": 0.95, "news_blackout": True, "stress": {}},
    "zero_liquidity": {"atr_pct": 0.5, "news_blackout": False,
                       "stress": {"zero_liquidity": True}},
    "missing_data": {"atr_pct": 0.5, "news_blackout": False,
                     "stress": {"missing_data": True}},
    "stale_price": {"atr_pct": 0.5, "news_blackout": False,
                    "stress": {"stale_price": True}},
}


def _approx_exit_price(entry: float, stop: float, direction: str, result_r: float) -> float:
    """Reconstructs an illustrative exit price from stored entry/stop/
    result_r. NOT the stored actual exit tick (not persisted per-trade) —
    see module docstring. Never raises."""
    try:
        risk = abs(float(entry) - float(stop))
        sign = 1 if direction == "long" else -1
        return round(float(entry) + sign * risk * float(result_r), 8)
    except Exception:  # noqa: BLE001
        return entry


def approx_exit_price(entry: float, stop: float, direction: str, result_r: float) -> float:
    """Public alias of `_approx_exit_price()` — Day 13's
    `engine.broker.paper_broker.PaperBroker.sync_closures()` reuses this
    EXACT reconstruction (rather than duplicating the formula) so a
    trade's synthetic exit price is identical whether it's read through
    this Day's replay tooling or Day 13's Paper Broker closing logic.
    Kept as a thin wrapper (not a rename) so existing Day 12 tests that
    reference the private `_approx_exit_price` name continue to pass
    unchanged."""
    return _approx_exit_price(entry, stop, direction, result_r)


def _load_trades():
    """Reuses engine.journal's own storage, the same access pattern as
    engine.edge_decay_monitor/edge_investigation (Day 9/10). Never
    raises — returns [] on any failure so a replay never crashes because
    the journal file is missing/corrupt."""
    try:
        from engine import journal, store
        return store.load_array(journal.STORE)
    except Exception:  # noqa: BLE001
        return []


def run_replay(rows: list | None = None, symbol: str | None = None,
               session: str | None = None, profile: str = "typical",
               seed: int = 42, entry_order_type: str = "market",
               exit_order_type: str = "market", include_exit: bool = True) -> dict:
    """Runs the execution simulator across historical trades under one
    named, disclosed assumption profile. Reproducible given the same
    inputs. Never raises — degrades to an empty-but-valid report on any
    failure."""
    try:
        prof = PROFILES.get(profile, PROFILES["typical"])
        source_rows = rows if rows is not None else _load_trades()
        if symbol:
            source_rows = [r for r in source_rows if r.get("symbol") == symbol]

        rng = random.Random(seed)
        reports = []
        for row in source_rows:
            try:
                entry = row.get("entry")
                stop = row.get("stop")
                direction = row.get("direction", "long")
                if entry is None or stop is None:
                    continue
                import pandas as pd
                signal_ts = pd.Timestamp(row.get("opened")) if row.get("opened") else None
                sess = session or spr.session_for(signal_ts)

                exit_price = None
                status = row.get("status", "")
                if include_exit and status in ("win", "loss", "scratch"):
                    exit_price = _approx_exit_price(entry, stop, direction,
                                                    row.get("result_r", 0.0))

                report = er.build_trade_execution_report(
                    row.get("symbol", symbol or "XAUUSD"), direction, entry,
                    exit_price=exit_price, stop_price=stop, signal_ts=signal_ts,
                    entry_order_type=entry_order_type, exit_order_type=exit_order_type,
                    atr_pct=prof["atr_pct"], news_blackout=prof["news_blackout"],
                    session=sess, rng=rng, **prof["stress"])
                report["trade_id"] = row.get("id", "")
                report["trade_status"] = status
                report["exit_price_is_approximate"] = exit_price is not None
                # Carried through verbatim (not re-derived from the reconstructed
                # exit price, which isn't cleanly invertible) so downstream
                # research code — comparison.py's four-layer report — can read
                # the trade's ORIGINAL stored result_r without recomputing it.
                report["stored_result_r"] = (float(row.get("result_r"))
                                             if row.get("result_r") is not None else None)
                reports.append(report)
            except Exception:  # noqa: BLE001
                continue

        scores = [r["execution_score"] for r in reports]
        score_counts = {label: scores.count(label)
                        for label in ("Excellent", "Good", "Average", "Poor", "Failed", "Unknown")}
        cost_rs = [r["cost_r"] for r in reports if r.get("cost_r") is not None]
        avg_cost_r = round(sum(cost_rs) / len(cost_rs), 6) if cost_rs else None

        return {
            "profile": profile, "profile_assumptions": prof, "seed": seed,
            "symbol_filter": symbol, "session_override": session,
            "n_trades_replayed": len(reports),
            "score_distribution": score_counts,
            "avg_cost_r": avg_cost_r,
            "reports": reports,
            "reproducible": True,
            "note": ("Same rows + symbol + session + profile + seed always reproduces this "
                    "exact output — see module docstring for how. Exit prices are "
                    "reconstructed approximations, not stored actual exit ticks."),
            "is_estimate": True, "source": "engine.execution.replay",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "profile": profile, "seed": seed, "n_trades_replayed": 0,
            "score_distribution": {}, "reports": [], "reproducible": True,
            "error": f"run_replay error: {exc}",
            "is_estimate": True, "source": "engine.execution.replay",
        }
