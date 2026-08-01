"""Institutional risk layer — volatility-normalized sizing + portfolio exposure.

Capital preservation first: size every trade so it risks a FIXED fraction of
equity regardless of the stop distance, scale risk down when volatility is
expanding, and cap aggregate open risk across the portfolio. Pure math, no deps,
fully testable. Nothing here touches order execution — it advises size only.
"""
from __future__ import annotations

DEFAULT_RISK_PCT = 1.0        # risk per trade, % of equity
MAX_PORTFOLIO_RISK_PCT = 6.0  # aggregate open-risk cap
VOL_SCALE = {"expansion": 0.75, "normal": 1.0, "contraction": 1.0, "unknown": 1.0}


def vol_adjusted_risk(base_risk_pct: float, vol_regime: str) -> float:
    """Shrink per-trade risk when volatility is expanding (wider, wilder moves)."""
    return round(base_risk_pct * VOL_SCALE.get(vol_regime, 1.0), 3)


def position_size(equity: float, risk_pct: float, entry: float, stop: float,
                  value_per_point: float = 1.0) -> dict:
    """Units to trade so loss at stop == risk_pct of equity. Fail-safe on bad input."""
    per_unit = abs(entry - stop) * value_per_point
    risk_cash = equity * (risk_pct / 100.0)
    units = (risk_cash / per_unit) if per_unit > 0 else 0.0
    return {"units": round(units, 4), "risk_cash": round(risk_cash, 2),
            "per_unit_risk": round(per_unit, 4), "risk_pct": risk_pct}


def portfolio_exposure(open_positions, equity: float,
                       cap_pct: float = MAX_PORTFOLIO_RISK_PCT) -> dict:
    """open_positions: list of dicts with 'risk_cash' (and optional 'base' currency).
    Returns aggregate risk %, a cap breach flag, and a concentration note."""
    total = sum(float(p.get("risk_cash", 0)) for p in (open_positions or []))
    pct = (total / equity * 100.0) if equity > 0 else 0.0
    bases = {}
    for p in (open_positions or []):
        b = p.get("base", "?")
        bases[b] = bases.get(b, 0) + 1
    concentrated = [b for b, n in bases.items() if n >= 2 and b != "?"]
    return {"open_risk_pct": round(pct, 2), "cap_pct": cap_pct,
            "over_cap": pct > cap_pct, "n_positions": len(open_positions or []),
            "concentration": concentrated}


def sizing_lines(equity, entry, stop, vol_regime="normal", base_risk_pct=DEFAULT_RISK_PCT,
                 value_per_point=1.0) -> list:
    r = vol_adjusted_risk(base_risk_pct, vol_regime)
    ps = position_size(equity, r, entry, stop, value_per_point)
    note = "" if r == base_risk_pct else f" (scaled from {base_risk_pct}% for {vol_regime})"
    return [f"POSITION SIZING (equity {equity:g}, risk {r}%{note}):",
            f"  entry {entry} | stop {stop} | risk/unit {ps['per_unit_risk']}",
            f"  -> size {ps['units']} units  (risking {ps['risk_cash']:g})"]
