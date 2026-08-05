"""Day 12 — Fill Model.

Combines `spread_model`, `latency_model`, and `slippage_model` into one
order-type-aware fill simulation. This is the module that answers "did
the order fill, and at what price?" — the other three only estimate one
ingredient each.

Order-type behavior, by design:
  - MARKET: attempts to fill immediately. Slippage skews adverse more
    often than favorable (`BASE_ADVERSE_PROB["market"]` in
    `slippage_model.py`), reflecting the cost of crossing the spread plus
    latency-induced adverse selection. Fails only under an explicit
    stress condition (zero liquidity / missing data / stale price).
  - STOP: this platform's own alert semantics mean the trigger condition
    is already met at signal time ("Price tapped X — take LONG now" is
    only sent once price has reached the level) — so a stop order here
    behaves like a market order that fires in a moving market: same
    fill-or-stress-fail logic, but a wider, more adverse-skewed slippage
    distribution (stop-run/gap risk).
  - LIMIT: fills only if price is assumed to reach the limit level.
    Given real subsequent price bars (`price_path`), the fill is
    determined deterministically from that data (did High/Low actually
    cross the limit price). Without price data, a disclosed default
    probability (`limit_fill_probability`) is used instead — clearly
    flagged as a probabilistic assumption, not observed. A filled limit
    order's slippage is favorable-skewed by construction (a limit order
    fills at its price or better) except during a liquidity shock, which
    can "gap through" a resting order — the one case a limit fill can
    still be adverse.

Fail-safe stress handling: `zero_liquidity` and `missing_data` both
produce an explicit `filled: False` with a disclosed `reason` — this
module never fabricates a fill price when the simulated conditions say
none should exist. `stale_price` does not block the fill but widens the
uncertainty (a documented penalty multiplier) and is flagged in the
output so a caller can discount the result.
"""
from __future__ import annotations

import random

from . import latency_model as lat
from . import slippage_model as slip
from . import spread_model as spr

VERSION = "1.0.0"

STALE_PRICE_PENALTY_MULT = 1.5   # widens the slippage magnitude when stale_price=True
DEFAULT_LIMIT_FILL_PROBABILITY = 0.65


def _side(direction: str, leg: str) -> str:
    """Derives the actual transaction side (buy/sell) from position
    direction + which leg of the trade this is. Long entry = buy; long
    exit = sell; short entry = sell; short exit = buy."""
    is_entry = leg == "entry"
    if direction == "long":
        return "buy" if is_entry else "sell"
    return "sell" if is_entry else "buy"


def _limit_reached(direction: str, limit_price: float, price_path) -> bool | None:
    """Deterministic check against real subsequent bars: did price ever
    reach `limit_price`? For a long limit (buying), the level is reached
    if any bar's Low <= limit_price. For a short limit (selling), if any
    bar's High >= limit_price. Returns None (unknown) if `price_path` is
    missing/malformed — caller falls back to the probabilistic
    assumption. Never raises."""
    try:
        if price_path is None or len(price_path) == 0:
            return None
        if direction == "long":
            return bool((price_path["Low"] <= limit_price).any())
        return bool((price_path["High"] >= limit_price).any())
    except Exception:  # noqa: BLE001
        return None


def simulate_fill(symbol: str, direction: str, order_type: str, intended_price: float,
                  signal_ts=None, leg: str = "entry", atr_pct: float | None = None,
                  news_blackout: bool = False, session: str | None = None,
                  zero_liquidity: bool = False, missing_data: bool = False,
                  stale_price: bool = False, price_path=None, limit_price: float | None = None,
                  limit_fill_probability: float = DEFAULT_LIMIT_FILL_PROBABILITY,
                  spread_overrides: dict | None = None,
                  rng: "random.Random | None" = None) -> dict:
    """Simulates one order's execution. Returns a dict covering the
    intended price, whether it filled, the actual (simulated) price if
    so, the spread/slippage/latency inputs used, and disclosed
    assumption flags. Never raises — any internal error degrades to
    `filled: False` with the error recorded, never a fabricated fill."""
    try:
        order_type = order_type if order_type in ("market", "limit", "stop") else "market"
        side = _side(direction, leg)

        if missing_data:
            return {
                "symbol": symbol, "direction": direction, "order_type": order_type,
                "leg": leg, "side": side, "intended_price": intended_price,
                "filled": False, "actual_price": None,
                "reason": "missing market data — cannot simulate execution",
                "is_estimate": True, "source": "engine.execution.fill_model",
            }

        spread_est = spr.estimate(symbol, now=signal_ts, atr_pct=atr_pct,
                                  news_blackout=news_blackout, session=session,
                                  overrides=spread_overrides)
        latency_est = lat.estimate_latency(order_type, rng=rng)
        estimated_ts = (lat.estimated_execution_timestamp(signal_ts, latency_est["total_latency_ms"])
                        if signal_ts is not None else None)

        if zero_liquidity:
            return {
                "symbol": symbol, "direction": direction, "order_type": order_type,
                "leg": leg, "side": side, "intended_price": intended_price,
                "filled": False, "actual_price": None,
                "reason": "zero liquidity — no counterparty available to fill this order",
                "spread": spread_est, "latency": latency_est,
                "signal_timestamp": signal_ts, "estimated_execution_timestamp": estimated_ts,
                "is_estimate": True, "source": "engine.execution.fill_model",
            }

        filled = True
        fill_reason = "filled"
        limit_probability_used = None
        if order_type == "limit" and limit_price is not None:
            reached = _limit_reached(direction, limit_price, price_path)
            if reached is None:
                r = rng or slip._LIVE_RNG
                limit_probability_used = limit_fill_probability
                filled = r.random() < limit_fill_probability
                fill_reason = ("filled (probabilistic assumption — no price path supplied)"
                              if filled else
                              "not filled (probabilistic assumption — limit price assumed unreached)")
            else:
                filled = reached
                fill_reason = ("filled (limit price reached in supplied price path)" if filled
                              else "not filled (limit price never reached in supplied price path)")

        if not filled:
            return {
                "symbol": symbol, "direction": direction, "order_type": order_type,
                "leg": leg, "side": side, "intended_price": intended_price,
                "filled": False, "actual_price": None, "reason": fill_reason,
                "limit_fill_probability_used": limit_probability_used,
                "spread": spread_est, "latency": latency_est,
                "signal_timestamp": signal_ts, "estimated_execution_timestamp": estimated_ts,
                "is_estimate": True, "source": "engine.execution.fill_model",
            }

        spread_val = spread_est.get("estimated_spread") or 0.0
        fill_price_basis = limit_price if (order_type == "limit" and limit_price is not None) else intended_price

        slip_out = slip.draw_slippage(symbol, direction, order_type, spread_val,
                                      atr_pct=atr_pct, news_blackout=news_blackout,
                                      session=session, rng=rng)
        price_delta = slip_out["price_delta"]
        stale_caveat = False
        if stale_price:
            price_delta *= STALE_PRICE_PENALTY_MULT
            stale_caveat = True

        sign = 1 if side == "buy" else -1
        actual_price = round(fill_price_basis + sign * price_delta, 8)
        execution_cost = round(abs(actual_price - intended_price), 8)

        return {
            "symbol": symbol, "direction": direction, "order_type": order_type,
            "leg": leg, "side": side, "intended_price": intended_price,
            "filled": True, "actual_price": actual_price, "reason": fill_reason,
            "limit_fill_probability_used": limit_probability_used,
            "execution_cost": execution_cost,
            "spread": spread_est, "slippage": slip_out, "latency": latency_est,
            "stale_price_caveat": stale_caveat,
            "partial_fill": slip_out.get("partial_fill", False),
            "fill_fraction": slip_out.get("fill_fraction", 1.0),
            "signal_timestamp": signal_ts, "estimated_execution_timestamp": estimated_ts,
            "is_estimate": True, "source": "engine.execution.fill_model",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol, "direction": direction, "order_type": order_type,
            "leg": leg, "intended_price": intended_price, "filled": False,
            "actual_price": None, "reason": f"simulate_fill error: {exc}",
            "is_estimate": True, "source": "engine.execution.fill_model",
        }
