"""Day 12 — Slippage Model.

Models the gap between a quoted price and a realistically-fillable price,
beyond the spread itself: normal execution friction, adverse slippage
(the price moves against the order before it fills), favorable slippage
(the price moves in the order's favor — real, if less discussed), rare
liquidity shocks, and partial fills. This platform never assumes every
order executes at the requested price — that assumption is exactly what
this module exists to remove from any future research conclusion.

DISCLOSED ASSUMPTION MODEL, not a fitted or observed distribution. Every
probability and magnitude constant below is a documented, illustrative
retail-execution assumption (consistent with commonly discussed retail
CFD/futures execution behavior), not calibrated against this platform's
own trade history or any broker's real fill data. See
EXECUTION_SIMULATOR_SPECIFICATION.md Sec.11 for the full disclosure and
the plan for replacing these with observed data once Day 13's broker
layer exists.

Reproducibility: every function accepts an optional `rng` (a
`random.Random` instance). Pass a seeded `random.Random(seed)` for
reproducible research/replay runs (see `replay.py`); omit it for live use
(falls back to an unseeded, module-shared `random.Random()`).
"""
from __future__ import annotations

import random

VERSION = "1.0.0"

_LIVE_RNG = random.Random()  # unseeded, live-use fallback — not used by any test

# Probability an order's slippage lands "adverse" (worse than quoted) vs
# "favorable" (better than quoted), under NORMAL (no shock) conditions,
# by order type. Market/stop orders pay a documented adverse skew (latency
# + adverse selection); limit orders that DO fill rarely do so adversely
# by construction (a limit order fills at its price or better) — the
# small residual here models minor same-tick execution noise, not the
# "didn't fill at all" case (that belongs to fill_model.py).
BASE_ADVERSE_PROB = {"market": 0.55, "stop": 0.70, "limit": 0.10}

# Normal-condition slippage magnitude, as a (min, max) fraction of the
# estimated spread, drawn uniformly. Stops draw wider because a triggered
# stop order chases price in a moving market by definition.
NORMAL_SLIPPAGE_FRACTION = {
    "market": (0.00, 0.50),
    "stop": (0.10, 0.80),
    "limit": (0.00, 0.15),
}

# Liquidity-shock probability model: a rare, large adverse-slippage event
# (a "gap" or momentary liquidity vacuum). Base probability compounds
# multiplicatively with disclosed risk factors, capped at SHOCK_MAX_PROB
# so no combination of factors implies a near-certain shock.
SHOCK_BASE_PROB = 0.01
SHOCK_NEWS_MULT = 5.0
SHOCK_OFFSESSION_MULT = 3.0
SHOCK_HIGH_VOL_MULT = 4.0       # applied when atr_pct >= HIGH_VOL_THRESHOLD
HIGH_VOL_THRESHOLD = 0.90
SHOCK_MAX_PROB = 0.40
SHOCK_MAGNITUDE_MULT = (3.0, 8.0)   # multiplies the normal slippage draw
SHOCK_PARTIAL_FILL_PROB = 0.35
PARTIAL_FILL_FRACTION_RANGE = (0.25, 0.85)


def shock_probability(atr_pct: float | None = None, news_blackout: bool = False,
                      session: str | None = None) -> float:
    """Combined, capped probability of a liquidity shock this order.
    Never raises — bad input degrades to the base probability."""
    try:
        p = SHOCK_BASE_PROB
        if news_blackout:
            p *= SHOCK_NEWS_MULT
        if session in ("Asian", "off-session"):
            p *= SHOCK_OFFSESSION_MULT
        if atr_pct is not None and float(atr_pct) >= HIGH_VOL_THRESHOLD:
            p *= SHOCK_HIGH_VOL_MULT
        return min(p, SHOCK_MAX_PROB)
    except Exception:  # noqa: BLE001
        return SHOCK_BASE_PROB


def draw_slippage(symbol: str, direction: str, order_type: str, spread: float,
                  atr_pct: float | None = None, news_blackout: bool = False,
                  session: str | None = None, rng: "random.Random | None" = None,
                  force_shock: bool = False) -> dict:
    """Draws one simulated slippage outcome for an order that DOES fill
    (whether it fills at all is fill_model.py's concern). Returns a dict
    with a signed `price_delta` (positive = cost/adverse, negative =
    benefit/favorable, in the same price units as `spread`), the
    `outcome` label, whether a `liquidity_shock` occurred, and whether a
    `partial_fill` resulted. `force_shock=True` bypasses the probabilistic
    draw and guarantees a shock outcome — used by `fill_model.py` to
    simulate an explicit zero-liquidity stress scenario deterministically
    rather than relying on a low-probability random draw to exercise that
    path. Never raises."""
    try:
        r = rng or _LIVE_RNG
        order_type = order_type if order_type in BASE_ADVERSE_PROB else "market"
        spread = float(spread) if spread else 0.0

        shock_p = shock_probability(atr_pct, news_blackout, session)
        is_shock = True if force_shock else r.random() < shock_p

        lo, hi = NORMAL_SLIPPAGE_FRACTION[order_type]
        base_fraction = r.uniform(lo, hi)

        if is_shock:
            mult_lo, mult_hi = SHOCK_MAGNITUDE_MULT
            magnitude = spread * base_fraction * r.uniform(mult_lo, mult_hi)
            outcome = "adverse"  # shocks are modeled as adverse by construction —
                                  # a "favorable shock" is not a coherent liquidity event
            price_delta = magnitude
            partial_fill = r.random() < SHOCK_PARTIAL_FILL_PROB
            fill_fraction = (round(r.uniform(*PARTIAL_FILL_FRACTION_RANGE), 4)
                             if partial_fill else 1.0)
        else:
            magnitude = spread * base_fraction
            adverse_prob = BASE_ADVERSE_PROB[order_type]
            is_adverse = r.random() < adverse_prob
            outcome = "adverse" if is_adverse else "favorable" if magnitude > 0 else "neutral"
            price_delta = magnitude if is_adverse else -magnitude
            partial_fill = False
            fill_fraction = 1.0

        return {
            "symbol": symbol, "direction": direction, "order_type": order_type,
            "outcome": outcome, "price_delta": round(price_delta, 8),
            "liquidity_shock": is_shock, "shock_probability_used": round(shock_p, 6),
            "partial_fill": partial_fill, "fill_fraction": fill_fraction,
            "is_estimate": True, "source": "engine.execution.slippage_model",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol, "direction": direction, "order_type": order_type,
            "outcome": "neutral", "price_delta": 0.0, "liquidity_shock": False,
            "shock_probability_used": SHOCK_BASE_PROB, "partial_fill": False,
            "fill_fraction": 1.0, "is_estimate": True, "error": f"draw_slippage error: {exc}",
            "source": "engine.execution.slippage_model",
        }
