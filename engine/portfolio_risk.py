"""Centralized production Portfolio Risk Engine — Day 3.

This is the module the Day 1 audit's Finding F01 was written about:
`engine/risk.py` already implements institutional-grade position sizing and
an aggregate-exposure cap, fully unit-tested (`tests/test_risk.py`), but was
never called from the live path. This module does NOT reimplement that
math — it IMPORTS `engine.risk` and adds exactly the layer that was
missing: reading the CURRENT open book, aggregating it across every symbol,
checking it against the candidate trade, and returning one structured
verdict the live alert path can act on before publication.

Design principles (see DAY3_PHASE1_EXECUTION_PATH.md and RISK_SPECIFICATION.md):
  - Reuse, don't duplicate. Position sizing math -> engine.risk. Drawdown
    math -> forward_report.drawdown_r. Trade-row reading -> engine.store
    (same salvage-on-corruption reader risk_guard.py already uses). Today's
    realized R -> engine.risk_guard.today_realized_r (symbol=None sums
    across the whole book "for free" — no new aggregation code needed).
    Correlation -> engine.correlation_dynamic.
  - Fail-open on internal error (consistent with risk_guard.py /
    range_guard.py): a bug here must never silently kill the alert
    pipeline. A caught exception returns allow=True with the error message
    in `reason`, exactly like risk_guard.evaluate()'s own failure mode.
  - Fail-CLOSED on a genuine, computed constraint breach when
    `portfolio_risk_mode == "block"` (the default — see engine/config.py):
    those are not bugs, they are the check doing its job, per the explicit
    Day 3 mandate ("the trade must be rejected before publication").
    `portfolio_risk_mode == "warn"` is a shadow-mode escape hatch for an
    operator who wants to gather evidence before trusting a new check —
    the violation is still computed, logged, and returned, just not
    allowed to block.
  - Scope discipline: this module owns the categories that are genuinely
    PORTFOLIO-scoped (span more than one symbol / trade). Categories that
    are already owned by an existing, tested per-signal gate are NOT
    reimplemented here:
      - SESSION_RESTRICTION / market hours   -> existing session logic in ict.py
      - MARKET_REGIME_UNSUITABLE             -> engine/regime.py + range_guard.py
      - CONFIDENCE_BELOW_THRESHOLD           -> signals.py / confluence.py thresholds
      - LIQUIDITY_CONDITIONS                 -> range_guard.py's chase/extreme checks
      - DUPLICATE_OPPORTUNITY (same symbol)  -> risk_guard.py's per-symbol position cap
    Reproducing any of those here would be exactly the "parallel
    implementation" the Day 3 mandate explicitly says to avoid.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from . import risk
from . import risk_guard
from . import correlation_dynamic as corr_dyn
from . import store

# Day 8: retroactively assigned for version traceability (see
# EXPLAINABILITY_SPECIFICATION.md Sec.5 / engine/platform_version.py) — no
# explicit version marker existed before Day 8. Purely additive metadata;
# changes no risk logic.
VERSION = "1.0.0"

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRADES_PATH = ROOT / "trades.json"

# --- Phase 7: canonical trade-rejection category vocabulary ----------------
# All ten categories from the Day 3 mandate are named here so every layer of
# the pipeline logs rejections under the same vocabulary. This module only
# ever RETURNS the five it owns (see module docstring); the other five are
# listed for completeness / for ledger-logging consistency when other
# modules' existing reasons are recorded.
RISK_BUDGET_EXCEEDED = "risk_budget_exceeded"
CORRELATION_TOO_HIGH = "correlation_too_high"
PORTFOLIO_EXPOSURE_EXCEEDED = "portfolio_exposure_exceeded"
MARKET_REGIME_UNSUITABLE = "market_regime_unsuitable"          # owned by regime.py/range_guard.py
CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"       # owned by signals.py/confluence.py
SESSION_RESTRICTION = "session_restriction"                     # owned by ict.py session logic
DRAWDOWN_PROTECTION = "drawdown_protection"
LIQUIDITY_CONDITIONS = "liquidity_conditions"                   # owned by range_guard.py
TRADE_FREQUENCY_CONTROL = "trade_frequency_control"
DUPLICATE_OPPORTUNITY = "duplicate_opportunity"                 # owned by risk_guard.py (per-symbol cap)

PORTFOLIO_OWNED_CATEGORIES = (
    RISK_BUDGET_EXCEEDED, CORRELATION_TOO_HIGH, PORTFOLIO_EXPOSURE_EXCEEDED,
    DRAWDOWN_PROTECTION, TRADE_FREQUENCY_CONTROL,
)


def _rows():
    """Same reader risk_guard.py uses: salvage-on-corruption, never raises."""
    try:
        return store.load_array(TRADES_PATH)
    except Exception:  # noqa: BLE001
        return []


def open_positions_snapshot(open_rows, equity: float, base_risk_pct: float = None) -> list:
    """Turn raw open journal rows into the shape engine.risk.portfolio_exposure
    expects ({'risk_cash', 'base', 'symbol', 'direction'}).

    IMPORTANT DOCUMENTED LIMITATION: engine/journal.py's Trade dataclass does
    not persist the actual risk_cash/units a position was sized at (verified
    by direct read, 2026-08-03 — no such field exists). Until that field is
    added (flagged as a Day 4+ backlog item in DAY3_NEXT_DAY_READINESS_REPORT.md),
    every open position is conservatively treated as sized at the platform's
    own stated default risk (RISK_RULES.md: 0.5-1%, engine.risk.DEFAULT_RISK_PCT)
    for the purposes of THIS aggregation. This is a documented approximation,
    not a measurement, and is called out again in RISK_SPECIFICATION.md."""
    base_risk_pct = risk.DEFAULT_RISK_PCT if base_risk_pct is None else base_risk_pct
    out = []
    for p in open_rows:
        entry = p.get("entry")
        stop = p.get("stop")
        sym = p.get("symbol", "XAUUSD")
        if entry is None or stop is None:
            continue
        sized = risk.position_size(equity, base_risk_pct, entry, stop)
        out.append({"risk_cash": sized["risk_cash"], "base": sym, "symbol": sym,
                    "direction": p.get("direction"), "opened": p.get("opened")})
    return out


def directional_exposure(open_rows) -> dict:
    """Count of open positions per direction, across ALL symbols — this is
    the 'maximum simultaneous directional exposure' input from Phase 3."""
    out = {"long": 0, "short": 0}
    for p in open_rows:
        d = p.get("direction")
        if d in out:
            out[d] += 1
    return out


def portfolio_drawdown_r(closed_rows, window: int = 30) -> float:
    """Trailing peak-to-trough drawdown across the last `window` CLOSED
    trades, pooled across every symbol. Reuses forward_report.drawdown_r
    rather than reimplementing drawdown math."""
    try:
        import forward_report as fr
    except Exception:  # noqa: BLE001
        return 0.0
    closed = sorted((r for r in closed_rows if r.get("status") in ("win", "loss", "scratch")),
                    key=lambda r: str(r.get("closed", "")))[-window:]
    rs = [float(r.get("result_r", 0) or 0) for r in closed]
    return fr.drawdown_r(rs)


def portfolio_heat(open_risk_pct: float, cap_pct: float) -> float:
    """Fraction of the portfolio risk cap already in use (0.0-1.0+)."""
    if cap_pct <= 0:
        return 0.0
    return round(open_risk_pct / cap_pct, 4)


def risk_budget_remaining_pct(open_risk_pct: float, cap_pct: float) -> float:
    return round(cap_pct - open_risk_pct, 4)


def session_overlap_factor(session_label: str) -> float:
    """Informational only (not a blocking gate — Day 3 mandate lists session
    overlap as something to EVALUATE, not something explicitly required to
    reject on; per the Additional Instruction, new blocking behavior needs
    forward-test evidence first, matching range_guard.py's SUPPRESS_MODE
    precedent). Returns a heat multiplier used only for the explainability
    payload and ledger logging today."""
    if not session_label:
        return 1.0
    label = str(session_label).lower()
    if "overlap" in label or ("london" in label and "ny" in label):
        return 1.25   # higher liquidity + higher volatility window
    return 1.0


def _verdict(allow, mode, category, reason, **detail) -> dict:
    enforced = allow or mode != "block"
    return {
        "allow": enforced,
        "would_block": (not allow),
        "mode": mode,
        "category": category,
        "reason": reason,
        "detail": detail,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def evaluate(symbol: str, direction: str, entry: float, stop: float,
            settings=None, rows=None, session_label=None) -> dict:
    """Main entry point — call this immediately before publication, after
    all per-symbol gates (risk_guard, range_guard, MAST confluence) have
    already passed. Returns a structured verdict:

        {allow, would_block, mode, category, reason, detail, generated}

    `allow` already accounts for portfolio_risk_mode ("warn" mode always
    returns allow=True even on a genuine violation — check `would_block` to
    see if it WOULD have rejected under "block" mode, for shadow-mode
    evidence gathering). Never raises."""
    try:
        if settings is None:
            from . import config
            settings = config.load()
        equity = float(getattr(settings, "portfolio_equity", 10000.0) or 10000.0)
        mode = str(getattr(settings, "portfolio_risk_mode", "block") or "block").lower()
        cap_pct = float(getattr(settings, "portfolio_max_risk_pct", risk.MAX_PORTFOLIO_RISK_PCT)
                        or risk.MAX_PORTFOLIO_RISK_PCT)
        day_stop_r = float(getattr(settings, "portfolio_day_stop_r", 2.0) or 2.0)
        max_dd_r = float(getattr(settings, "portfolio_max_drawdown_r", 6.0) or 6.0)
        max_dir = int(getattr(settings, "portfolio_max_directional", 2) or 2)
        corr_hi = float(getattr(settings, "correlation_high_threshold", 0.6) or 0.6)

        if rows is None:
            rows = _rows()
        open_rows = [r for r in rows if r.get("status") == "open"]
        closed_rows = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]

        snapshot = open_positions_snapshot(open_rows, equity)
        dirs = directional_exposure(open_rows)
        candidate_sized = risk.position_size(equity, risk.DEFAULT_RISK_PCT, entry, stop)
        exposure_now = risk.portfolio_exposure(snapshot, equity, cap_pct=cap_pct)
        heat = portfolio_heat(exposure_now["open_risk_pct"], cap_pct)
        budget_left = risk_budget_remaining_pct(exposure_now["open_risk_pct"], cap_pct)
        sess_factor = session_overlap_factor(session_label)

        explain = {
            "equity": equity, "cap_pct": cap_pct, "open_risk_pct": exposure_now["open_risk_pct"],
            "n_open": exposure_now["n_positions"], "portfolio_heat": heat,
            "risk_budget_remaining_pct": budget_left, "directional_exposure": dirs,
            "candidate_risk_cash": candidate_sized["risk_cash"],
            "session_overlap_factor": sess_factor,
        }

        # --- 1. Portfolio exposure cap (Phase 3: "aggregate exposure") -----
        projected = snapshot + [{"risk_cash": candidate_sized["risk_cash"], "base": symbol,
                                 "symbol": symbol, "direction": direction}]
        exposure_after = risk.portfolio_exposure(projected, equity, cap_pct=cap_pct)
        explain["open_risk_pct_after"] = exposure_after["open_risk_pct"]
        if exposure_after["over_cap"]:
            return _verdict(False, mode, PORTFOLIO_EXPOSURE_EXCEEDED,
                f"Portfolio exposure would reach {exposure_after['open_risk_pct']}% "
                f"of equity (cap {cap_pct}%) — {exposure_after['n_positions']} positions "
                f"including this one.", **explain)

        # --- 2. Simultaneous directional exposure (Phase 3) ---------------
        if direction in dirs and dirs[direction] + 1 > max_dir:
            return _verdict(False, mode, TRADE_FREQUENCY_CONTROL,
                f"{dirs[direction] + 1} simultaneous {direction} positions across the "
                f"portfolio would exceed the configured max of {max_dir}.", **explain)

        # --- 3. Correlation concentration (Phase 3 + Phase 4) --------------
        worst = None
        for p in open_rows:
            other_sym = p.get("symbol", "XAUUSD")
            if other_sym == symbol or p.get("direction") != direction:
                continue
            c = corr_dyn.get_correlation(symbol, other_sym, settings=settings)
            if abs(c["corr"]) >= corr_hi and (worst is None or abs(c["corr"]) > abs(worst["corr"])):
                worst = dict(c, against=other_sym)
        if worst:
            explain["correlation"] = worst
            return _verdict(False, mode, CORRELATION_TOO_HIGH,
                f"New {direction} {symbol} is correlated {worst['corr']:+.2f} with an "
                f"existing open {direction} {worst['against']} position (threshold "
                f"{corr_hi}) — same-direction correlated risk, not diversified exposure.",
                **explain)

        # --- 4. Portfolio-wide daily loss stop (Phase 3 + RISK_RULES.md) ---
        # risk_guard.today_realized_r(rows, symbol=None) sums across every
        # symbol "for free" — reused as-is, no new aggregation logic added.
        # This reconciles RISK_RULES.md rule #2 (an account-wide -2R rule)
        # with risk_guard.py's deliberate per-symbol-only implementation —
        # see RISK_SPECIFICATION.md Sec.5 for the full reasoning.
        portfolio_day_r = risk_guard.today_realized_r(rows, symbol=None)
        explain["portfolio_day_r"] = portfolio_day_r
        if portfolio_day_r <= -abs(day_stop_r):
            return _verdict(False, mode, DRAWDOWN_PROTECTION,
                f"PORTFOLIO DAY STOP: {portfolio_day_r:+.2f}R today across all symbols "
                f"(limit -{abs(day_stop_r):.1f}R) — no new signals until tomorrow UTC.",
                **explain)

        # --- 5. Trailing portfolio drawdown cap (RISK_RULES.md: <6R/30-trade) --
        dd = portfolio_drawdown_r(closed_rows, window=30)
        explain["portfolio_drawdown_r_30"] = dd
        if dd >= max_dd_r:
            return _verdict(False, mode, DRAWDOWN_PROTECTION,
                f"Trailing 30-trade portfolio drawdown is {dd:.2f}R (cap {max_dd_r:.1f}R) "
                f"— capital-preservation stand-down until the drawdown recovers.",
                **explain)

        return _verdict(True, mode, None, "portfolio checks clear", **explain)
    except Exception as exc:  # noqa: BLE001
        return {"allow": True, "would_block": False, "mode": "fail-open", "category": None,
                "reason": f"portfolio-risk error ({exc}) — failing open", "detail": {},
                "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def line(verdict: dict) -> str:
    if verdict.get("category") is None:
        return "portfolio: clear"
    tag = "REJECTED" if verdict.get("would_block") and not verdict.get("allow") else \
          "WOULD REJECT (warn mode)" if verdict.get("would_block") else "flagged"
    return f"portfolio {tag} [{verdict['category']}]: {verdict['reason']}"
