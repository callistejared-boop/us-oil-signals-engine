"""Day 12 — Research Integration: the four-layer comparison.

    Raw Strategy -> Ideal Execution -> Realistic Execution -> Observed Performance

Reuses `engine.research_stats.full_report()` (Day 9) for every layer's
statistics — this module does not reimplement expectancy/profit-
factor/drawdown math, it only assembles the four R-multiple series those
functions run against.

Layer definitions, stated precisely (this precision matters — see the
honesty note below):

  - RAW STRATEGY: the trade's `result_r` exactly as stored in
    `trades.json` — the strategy's theoretical edge if every fill
    happened exactly at the intended price, with zero cost.
  - IDEAL EXECUTION: by definition, identical to Raw Strategy (zero
    execution cost assumed). Included as its own explicit layer rather
    than silently skipped, so the comparison table always shows all four
    stages the mandate asked for, with the identity relationship
    disclosed rather than hidden.
  - REALISTIC EXECUTION: Raw Strategy's `result_r`, minus this Day's
    modeled execution cost (`replay.py`'s `cost_r`, expressed in the same
    R units) for that trade. This is the one genuinely NEW number this
    Day introduces.
  - OBSERVED PERFORMANCE: also `result_r` exactly as stored, same as Raw
    Strategy.

HONESTY NOTE (do not skip this when reading the comparison output): Raw
Strategy and Observed Performance are numerically IDENTICAL today,
because `trades.json`'s `result_r` has never had any execution cost
subtracted from it — there is no live broker connection (Day 13's job),
so nothing has ever actually been "observed" through a real fill. The
gap this comparison surfaces between Realistic Execution and the other
three layers measures "how much execution cost was invisible until this
Day," not a live strategy-vs-reality gap for historical trades — those
trades were never actually routed through this simulator in real time.
Once Day 13 ships a real (or realistic paper) broker connection, Observed
Performance will diverge from Raw Strategy for the first time, and this
module's job will become genuinely comparing four DIFFERENT numbers
instead of three identical ones and one new one.
"""
from __future__ import annotations

from engine import research_stats as rs

from . import replay as rp

VERSION = "1.0.0"


def compare_layers(rows: list | None = None, symbol: str | None = None,
                   profile: str = "typical", seed: int = 42) -> dict:
    """Builds the four-layer comparison for a set of historical trades.
    Never raises — any internal failure degrades to empty layer reports
    with an `error` field, never fabricated statistics."""
    try:
        replay_out = rp.run_replay(rows=rows, symbol=symbol, profile=profile, seed=seed)
        reports = replay_out.get("reports", [])

        raw_r = [_stored_r(r) for r in reports]
        raw_r = [v for v in raw_r if v is not None]

        realistic_r = []
        for r in reports:
            stored = _stored_r(r)
            if stored is None:
                continue
            cost_r = r.get("cost_r")
            realistic_r.append(stored - cost_r if cost_r is not None else stored)

        raw_report = rs.full_report(raw_r)
        ideal_report = rs.full_report(raw_r)  # identical by definition — see module docstring
        realistic_report = rs.full_report(realistic_r)
        observed_report = rs.full_report(raw_r)  # identical today — see module docstring

        return {
            "profile": profile, "seed": seed, "symbol_filter": symbol,
            "n_trades": len(reports),
            "raw_strategy": raw_report,
            "ideal_execution": ideal_report,
            "realistic_execution": realistic_report,
            "observed_performance": observed_report,
            "execution_drag": {
                "expectancy_delta": _delta(raw_report, realistic_report, "expectancy"),
                "note": ("raw_strategy.expectancy minus realistic_execution.expectancy — "
                        "the average per-trade R this Day's modeled execution cost would "
                        "have consumed, had it been applied historically."),
            },
            "note": ("Raw Strategy and Observed Performance are numerically identical today "
                    "— see this module's docstring (Honesty Note) for why, and what changes "
                    "once Day 13's broker layer exists."),
            "is_estimate": True, "source": "engine.execution.comparison",
        }
    except Exception as exc:  # noqa: BLE001
        empty = rs.full_report([])
        return {
            "profile": profile, "seed": seed, "n_trades": 0,
            "raw_strategy": empty, "ideal_execution": empty,
            "realistic_execution": empty, "observed_performance": empty,
            "error": f"compare_layers error: {exc}",
            "is_estimate": True, "source": "engine.execution.comparison",
        }


def _delta(a: dict, b: dict, metric: str):
    """`a[metric].value - b[metric].value`, or None if either side is
    unavailable. Never raises."""
    try:
        av = a.get(metric, {}).get("value")
        bv = b.get(metric, {}).get("value")
        if av is None or bv is None:
            return None
        return round(av - bv, 4)
    except Exception:  # noqa: BLE001
        return None


def _stored_r(report: dict):
    """Reads the trade's original stored `result_r`, carried through
    verbatim on every `replay.run_replay()` report entry (not re-derived
    from the reconstructed exit price, which isn't cleanly invertible)."""
    return report.get("stored_result_r")
