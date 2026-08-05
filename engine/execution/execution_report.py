"""Day 12 — Execution Report.

Builds a per-trade fill-quality report (intended entry, actual entry,
expected exit, actual exit, total execution cost) and a DESCRIPTIVE
execution score — Excellent / Good / Average / Poor / Failed. This
measures EXECUTION QUALITY, not strategy quality: a losing trade can
still have Excellent execution (the strategy was wrong, the fill was
clean), and a winning trade can still have Poor execution (the strategy
was right despite paying a lot to get in). The two questions are kept
structurally separate here, the same way Day 11 kept `macro_confidence`
separate from the trading Confidence Engine's score — this module never
feeds `engine.confidence_engine` or `engine.confluence`, and grep-
verifying that stays a permanent part of this Day's validation.

Scoring uses cost relative to the trade's own planned risk (R, this
platform's native unit — `|entry - stop|`) when a stop is available,
falling back to cost-in-basis-points-of-price when it isn't. Both
threshold tables are simple, disclosed, non-fitted bands — not fitted
against this platform's own trade history and not a probability.
"""
from __future__ import annotations

import random

from . import fill_model as fm

VERSION = "1.0.0"

# Disclosed, non-fitted score bands. Cost as a fraction of planned risk
# (R): a trade whose entry+exit execution cost consumed 5% of its planned
# risk is "Excellent" execution; one that consumed more than 35% is
# "Poor" even if the trade itself won.
SCORE_BANDS_R = [(0.05, "Excellent"), (0.15, "Good"), (0.35, "Average")]
# Fallback bands (basis points of price) when no stop is available to
# compute a risk-relative cost.
SCORE_BANDS_BPS = [(2.0, "Excellent"), (5.0, "Good"), (15.0, "Average")]


def score_execution(cost_r: float | None = None, cost_bps: float | None = None,
                    filled: bool = True) -> str:
    """Descriptive score from cost-relative-to-risk (preferred) or
    cost-in-bps (fallback). "Failed" means the order never filled at all
    — categorically worse than "Poor", which still means it filled.
    Never raises."""
    try:
        if not filled:
            return "Failed"
        bands = None
        value = None
        if cost_r is not None:
            bands, value = SCORE_BANDS_R, abs(float(cost_r))
        elif cost_bps is not None:
            bands, value = SCORE_BANDS_BPS, abs(float(cost_bps))
        if bands is None:
            return "Unknown"
        for threshold, label in bands:
            if value <= threshold:
                return label
        return "Poor"
    except Exception:  # noqa: BLE001
        return "Unknown"


def build_trade_execution_report(symbol: str, direction: str, entry_price: float,
                                 exit_price: float | None = None, stop_price: float | None = None,
                                 signal_ts=None, exit_ts=None,
                                 entry_order_type: str = "market", exit_order_type: str = "market",
                                 atr_pct: float | None = None, news_blackout: bool = False,
                                 session: str | None = None, zero_liquidity: bool = False,
                                 missing_data: bool = False, stale_price: bool = False,
                                 entry_limit_price: float | None = None, entry_price_path=None,
                                 rng: "random.Random | None" = None) -> dict:
    """Simulates entry (always) and exit (if `exit_price` given) fills and
    assembles the full fill-quality report + execution score. Never
    raises — any internal failure degrades to a report with `filled:
    False` legs and an `error` field, never a fabricated cost."""
    try:
        entry_fill = fm.simulate_fill(
            symbol, direction, entry_order_type, entry_price, signal_ts=signal_ts,
            leg="entry", atr_pct=atr_pct, news_blackout=news_blackout, session=session,
            zero_liquidity=zero_liquidity, missing_data=missing_data, stale_price=stale_price,
            price_path=entry_price_path, limit_price=entry_limit_price, rng=rng)

        exit_fill = None
        if exit_price is not None:
            exit_fill = fm.simulate_fill(
                symbol, direction, exit_order_type, exit_price, signal_ts=exit_ts or signal_ts,
                leg="exit", atr_pct=atr_pct, news_blackout=news_blackout, session=session,
                zero_liquidity=zero_liquidity, missing_data=missing_data, stale_price=stale_price,
                rng=rng)

        both_filled = entry_fill.get("filled") and (exit_fill is None or exit_fill.get("filled"))
        total_cost = 0.0
        if entry_fill.get("filled"):
            total_cost += entry_fill.get("execution_cost") or 0.0
        if exit_fill is not None and exit_fill.get("filled"):
            total_cost += exit_fill.get("execution_cost") or 0.0

        cost_r = None
        if stop_price is not None and entry_price is not None:
            risk = abs(entry_price - stop_price)
            if risk > 0:
                cost_r = round(total_cost / risk, 6)
        cost_bps = None
        if entry_price:
            cost_bps = round((total_cost / abs(entry_price)) * 10000, 4)

        score = score_execution(cost_r=cost_r, cost_bps=cost_bps, filled=bool(both_filled))

        return {
            "symbol": symbol, "direction": direction,
            "intended_entry": entry_price, "actual_entry": entry_fill.get("actual_price"),
            "entry_filled": entry_fill.get("filled"), "entry_fill_reason": entry_fill.get("reason"),
            "expected_exit": exit_price,
            "actual_exit": exit_fill.get("actual_price") if exit_fill else None,
            "exit_filled": exit_fill.get("filled") if exit_fill else None,
            "exit_fill_reason": exit_fill.get("reason") if exit_fill else None,
            "total_execution_cost": round(total_cost, 8),
            "cost_r": cost_r, "cost_bps": cost_bps,
            "execution_score": score,
            "both_legs_filled": bool(both_filled),
            "entry_detail": entry_fill, "exit_detail": exit_fill,
            "note": ("Execution score measures FILL QUALITY, not strategy quality — a losing "
                    "trade can score Excellent and a winning trade can score Poor. Every price "
                    "here is a MODELED ESTIMATE (no live broker connection exists yet); see "
                    "EXECUTION_SIMULATOR_SPECIFICATION.md."),
            "is_estimate": True, "source": "engine.execution.execution_report",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol, "direction": direction, "intended_entry": entry_price,
            "actual_entry": None, "entry_filled": False, "execution_score": "Unknown",
            "error": f"build_trade_execution_report error: {exc}",
            "is_estimate": True, "source": "engine.execution.execution_report",
        }
