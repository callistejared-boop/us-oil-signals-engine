"""Day 12 — Latency Model.

Estimates the delay between a signal being generated and an order
actually reaching the market, broken into named stages, and produces a
separate "estimated execution timestamp" distinct from the signal's own
timestamp. This platform is Telegram-alert-based, not auto-trading (see
`alert_signals.py`) — a human reads `build_entry()`'s "Price tapped X —
take LONG now" message and manually places the order. That human-reaction
step is real, is almost always the dominant source of delay for a market-
style entry, and is disclosed here as its own named stage rather than
folded silently into "broker latency" the way a naive model might.

DISCLOSED ASSUMPTION MODEL — every range below is an illustrative,
documented benchmark (consistent with typical retail-platform component
latencies and typical human alert-reaction times), not measured from this
platform's own infrastructure or any specific broker. See
EXECUTION_SIMULATOR_SPECIFICATION.md Sec.11.

Reproducibility: every function accepts an optional `rng`
(`random.Random`); pass a seeded instance for reproducible replay runs.
"""
from __future__ import annotations

import random
from datetime import timedelta

VERSION = "1.0.0"

_LIVE_RNG = random.Random()

# (min_ms, max_ms) uniform-draw ranges per stage, illustrative and disclosed.
STAGE_RANGES_MS = {
    "signal_generation": (100, 400),     # engine compute time to produce the alert
    "telegram_delivery": (300, 1500),    # network delivery of the Telegram message
    "human_reaction": (3000, 45000),     # time for a human to read the alert and act —
                                          # the dominant, most variable component for any
                                          # order type requiring immediate manual action
    "broker_api": (50, 300),             # order submission to the broker's API/platform
    "order_execution": (20, 200),        # broker-side matching/execution latency
}

# Whether `human_reaction` applies by default, per order type. Market and
# stop orders in this platform's alert flow ("take LONG now") require
# immediate manual action upon receiving the alert. Limit orders are
# modeled as pre-positioned ahead of the trigger (the ICT/SMC convention
# of placing a limit at a level in advance), so no incremental human-
# reaction delay is assumed once the order is already resting — a caller
# can override this via `include_human_reaction=`.
DEFAULT_INCLUDE_HUMAN_REACTION = {"market": True, "stop": True, "limit": False}


def estimate_latency(order_type: str = "market", include_human_reaction: bool | None = None,
                     rng: "random.Random | None" = None) -> dict:
    """Draws one simulated latency breakdown. Never raises. Returns the
    per-stage draws (ms), whether human_reaction was included, and the
    total."""
    try:
        r = rng or _LIVE_RNG
        order_type = order_type if order_type in DEFAULT_INCLUDE_HUMAN_REACTION else "market"
        include_hr = (DEFAULT_INCLUDE_HUMAN_REACTION[order_type]
                     if include_human_reaction is None else bool(include_human_reaction))

        stages = {}
        for stage, (lo, hi) in STAGE_RANGES_MS.items():
            if stage == "human_reaction" and not include_hr:
                stages[stage] = 0.0
                continue
            stages[stage] = round(r.uniform(lo, hi), 1)

        total_ms = round(sum(stages.values()), 1)
        return {
            "order_type": order_type, "include_human_reaction": include_hr,
            "stages_ms": stages, "total_latency_ms": total_ms,
            "assumption": ("disclosed illustrative latency benchmarks, not measured from "
                          "live infrastructure — see STAGE_RANGES_MS in "
                          "engine/execution/latency_model.py"),
            "is_estimate": True, "source": "engine.execution.latency_model",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "order_type": order_type, "include_human_reaction": False,
            "stages_ms": {}, "total_latency_ms": 0.0,
            "assumption": f"estimate_latency error: {exc}",
            "is_estimate": True, "source": "engine.execution.latency_model",
        }


def estimated_execution_timestamp(signal_ts, total_latency_ms: float):
    """Signal timestamp + total latency, as a distinct timestamp from the
    signal's own — the mandate's explicit "record estimated execution
    timestamps separately from signal timestamps" requirement. Accepts
    any object supporting `+ timedelta` (datetime, pandas.Timestamp).
    Never raises — returns the original `signal_ts` unchanged on error
    (a visible no-op, not a silently wrong timestamp)."""
    try:
        return signal_ts + timedelta(milliseconds=float(total_latency_ms))
    except Exception:  # noqa: BLE001
        return signal_ts
