"""Execution Profile (V2.2 Priority 1 Item 3) — strategy-dependent
execution-quality tolerances.

Not to be confused with `engine.execution.replay.PROFILES` ("typical" /
"tight" / "wide" / "stressed" / ...), which is a DIFFERENT, older concept
this module deliberately does not reuse the name of: `replay.PROFILES`
describes what MARKET CONDITIONS to simulate (an input to the fill
simulator). This module describes what execution quality is ACCEPTABLE
for a given trading style (an evaluator of the simulator's output).
Going forward, refer to `replay.PROFILES` as a "replay profile" and this
module's profiles as an "execution profile" to keep the two distinct —
see VERSION_2.2_ROADMAP.md Priority 1 Item 3 and
STRATEGY_FRAMEWORK_SPECIFICATION.md Sec.3 for the full disambiguation.

Before this module, `execution_report.py`'s `score_execution()` applied
ONE global cost-vs-risk band table (`SCORE_BANDS_R`) to every trade
regardless of strategy — reasonable for a single scalping-oriented
strategy, wrong once Swing/Day/Scalping styles coexist: a cost that
barely dents a 40-pip swing target could meaningfully erode a tight
scalp target (see SCALPING_ENGINE_DESIGN.md Sec.6). This module adds an
ADDITIONAL, per-style evaluation layer on top of `execution_report.py`'s
existing output — it does not replace `score_execution()` (which stays
as the strategy-agnostic descriptive score every existing caller/test
already depends on) — this is purely additive, exactly like every other
advisory subsystem in this codebase: never gates, never resizes, never
touches confidence/confluence/the trade's own entry/stop/target.

DISCLOSED ASSUMPTION MODEL. Every threshold below is an illustrative,
non-fitted engineering judgment (not calibrated against this platform's
own trade history or any broker's real fill data) — same disclosure
posture as `spread_model.BASE_SPREAD` / `slippage_model.BASE_ADVERSE_PROB`
/ `execution_report.SCORE_BANDS_R`. An operator with real evidence should
override via the `overrides=` parameter on `evaluate()`, not by editing
this table, so the substitution stays visible at the call site.

`maximum_trade_duration_minutes` is carried on the profile for
completeness (matches `StrategyProfile.max_holding_minutes` in
STRATEGY_FRAMEWORK_SPECIFICATION.md Sec.3) but is NOT evaluated by
`evaluate()` below — trade duration is a position-management concern
(journal.py's `_manage()` rule vocabulary), not a fill-quality concern,
so enforcing/observing it belongs there, not in this execution-simulator
package. It is returned unevaluated (informational only) so a caller
building a full per-trade report has it in one place.
"""
from __future__ import annotations

VERSION = "1.0.0"

DEFAULT_STYLE = "day"

# Named, disclosed execution-quality tolerances per trading style.
#   acceptable_latency_ms          — max tolerable total simulated latency
#                                     (engine.execution.latency_model's
#                                     total_latency_ms).
#   acceptable_spread_multiplier   — max tolerable estimated spread,
#                                     expressed as a multiple of the
#                                     symbol's own BASE_SPREAD (spread_
#                                     model.py) rather than an absolute
#                                     price unit, so one profile works
#                                     across symbols whose spreads differ
#                                     by orders of magnitude (XAUUSD vs
#                                     EURUSD vs BTCUSD).
#   acceptable_slippage_r          — max tolerable total execution cost,
#                                     expressed as a fraction of the
#                                     trade's own planned risk (cost_r) —
#                                     reuses execution_report.py's existing
#                                     normalized unit rather than inventing
#                                     a new one.
#   acceptable_partial_fill        — whether a partial fill is tolerable
#                                     at all for this style, plus the
#                                     minimum tolerable fill_fraction when
#                                     it is.
#   acceptable_liquidity_shock     — whether a simulated liquidity-shock
#                                     event (slippage_model.py's
#                                     `liquidity_shock`) is tolerable at
#                                     all for this style.
#   maximum_trade_duration_minutes — informational only, see module
#                                     docstring.
PROFILES = {
    "swing": {
        "display_name": "Swing",
        "acceptable_latency_ms": 60000.0,
        "acceptable_spread_multiplier": 3.0,
        "acceptable_slippage_r": 0.15,
        "acceptable_partial_fill": True,
        "min_fill_fraction": 0.5,
        "acceptable_liquidity_shock": True,
        "maximum_trade_duration_minutes": None,
    },
    "day": {
        "display_name": "Day Trading",
        "acceptable_latency_ms": 15000.0,
        "acceptable_spread_multiplier": 1.8,
        "acceptable_slippage_r": 0.08,
        "acceptable_partial_fill": True,
        "min_fill_fraction": 0.75,
        "acceptable_liquidity_shock": False,
        "maximum_trade_duration_minutes": 480,
    },
    "scalping": {
        "display_name": "Scalping",
        "acceptable_latency_ms": 3000.0,
        "acceptable_spread_multiplier": 1.2,
        "acceptable_slippage_r": 0.03,
        "acceptable_partial_fill": False,
        "min_fill_fraction": 1.0,
        "acceptable_liquidity_shock": False,
        "maximum_trade_duration_minutes": 30,
    },
}


def profile_for(style: str, overrides: dict | None = None) -> dict:
    """Returns the named profile (falls back to DEFAULT_STYLE on an
    unknown style — never raises, never returns None). `overrides`
    shallow-merges onto the base profile without mutating PROFILES."""
    try:
        base = PROFILES.get(style, PROFILES[DEFAULT_STYLE])
        prof = dict(base)
        prof["style"] = style if style in PROFILES else DEFAULT_STYLE
        prof["style_requested"] = style
        if overrides:
            prof.update(overrides)
        return prof
    except Exception:  # noqa: BLE001
        return dict(PROFILES[DEFAULT_STYLE], style=DEFAULT_STYLE, style_requested=style)


def _check(label: str, actual, acceptable, within: bool) -> dict:
    return {"label": label, "actual": actual, "acceptable": acceptable, "within_tolerance": within}


def evaluate(report: dict, style: str = DEFAULT_STYLE, overrides: dict | None = None) -> dict:
    """Evaluates one `execution_report.build_trade_execution_report()`
    output against a named execution profile's tolerances. Purely
    observational — never gates, never resizes, never touches the
    trade's own entry/stop/target, never raises. Returns per-dimension
    checks (latency, spread, slippage, partial_fill, liquidity_shock)
    plus an overall `within_tolerance` verdict, so this can be logged and
    persisted alongside the existing execution report without changing
    what that report itself contains."""
    try:
        prof = profile_for(style, overrides=overrides)
        entry = (report or {}).get("entry_detail") or {}
        filled = bool((report or {}).get("entry_filled"))

        checks = {}

        latency_ms = ((entry.get("latency") or {}).get("total_latency_ms"))
        checks["latency"] = _check(
            "latency_ms", latency_ms, prof["acceptable_latency_ms"],
            (latency_ms is not None and latency_ms <= prof["acceptable_latency_ms"]))

        spread_detail = entry.get("spread") or {}
        est_spread = spread_detail.get("estimated_spread")
        base_spread = spread_detail.get("base_spread")
        spread_multiplier = (est_spread / base_spread
                             if est_spread is not None and base_spread else None)
        checks["spread"] = _check(
            "spread_multiplier", spread_multiplier, prof["acceptable_spread_multiplier"],
            (spread_multiplier is not None
             and spread_multiplier <= prof["acceptable_spread_multiplier"]))

        cost_r = (report or {}).get("cost_r")
        abs_cost_r = abs(cost_r) if cost_r is not None else None
        checks["slippage"] = _check(
            "cost_r", abs_cost_r, prof["acceptable_slippage_r"],
            (abs_cost_r is not None and abs_cost_r <= prof["acceptable_slippage_r"]))

        fill_fraction = entry.get("fill_fraction", 1.0 if filled else 0.0)
        partial = bool(entry.get("partial_fill"))
        partial_ok = (not partial) or (prof["acceptable_partial_fill"]
                                       and fill_fraction >= prof["min_fill_fraction"])
        checks["partial_fill"] = _check(
            "fill_fraction", fill_fraction, prof["min_fill_fraction"], partial_ok)

        shock = bool((entry.get("slippage") or {}).get("liquidity_shock"))
        checks["liquidity_shock"] = _check(
            "liquidity_shock_occurred", shock, prof["acceptable_liquidity_shock"],
            (not shock) or prof["acceptable_liquidity_shock"])

        all_within = filled and all(c["within_tolerance"] for c in checks.values())

        return {
            "style": prof["style"], "style_requested": prof["style_requested"],
            "profile": prof, "entry_filled": filled, "checks": checks,
            "all_within_tolerance": all_within,
            "maximum_trade_duration_minutes": prof["maximum_trade_duration_minutes"],
            "note": ("Advisory only - never gates, never resizes. "
                    "maximum_trade_duration_minutes is informational here; not evaluated "
                    "by this function (see module docstring). Disclosed, non-fitted "
                    "thresholds - see PROFILES in engine/execution/execution_profile.py."),
            "is_estimate": True, "source": "engine.execution.execution_profile",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "style": style, "style_requested": style, "profile": None,
            "entry_filled": False, "checks": {}, "all_within_tolerance": False,
            "maximum_trade_duration_minutes": None,
            "error": f"evaluate error: {exc}",
            "is_estimate": True, "source": "engine.execution.execution_profile",
        }
