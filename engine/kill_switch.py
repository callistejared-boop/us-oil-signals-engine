"""V2.2 Priority 2 — Kill-Switch Status Reporter.

`PHASE0_FORENSIC_AUDIT.md` Section P flagged that the platform's three
protective stand-downs (risk_guard's per-symbol daily loss lock,
portfolio_risk's drawdown/day-stop protection, news_guard's blackout
window) "each exist independently... each is bespoke, not a shared
abstraction" and recommended "generalize into one shared abstraction."

Investigating what that abstraction should actually look like surfaced
something worth disclosing before the design, not after: all three
stand-downs are ALREADY deliberately stateless. None of them persist an
"engaged since <timestamp>" flag anywhere. Each is recomputed fresh, every
single call, from data that's already available (recent trade rows, the
current news calendar) — see RISK_RULES.md's explicit instruction "Do not
manually clear the stand-down" for the drawdown protection specifically:
there is nothing TO manually clear, because there is no stored state, only
a live recomputation that naturally stops matching its trigger condition
once enough time passes or enough new (better) trades close. That
statelessness is a real, positive property: it self-heals across process
restarts (this platform's scan loop is a fresh process every ~15 minutes,
see position_engine.py's own docstring on the same point) with zero risk
of a stale "still engaged" flag surviving past its actual trigger
condition clearing.

A traditional kill-switch object (activation timestamp, persisted state,
manual-reset recovery criteria) would ADD state where the current design
intentionally has none — that would be a regression, not hardening, and
exactly the kind of "rewrite a working system" this platform's own
standing rule warns against.

So this module is deliberately NOT a state machine. It is a read-only
STATUS REPORTER: `current_stand_downs()` queries all three existing,
unmodified functions (`news_guard.evaluate()`, `risk_guard.evaluate()`,
the same `today_realized_r()`/`portfolio_drawdown_r()` calls
`portfolio_risk.evaluate()` itself makes internally) and returns their
CURRENT state in one common, named shape — for a future dashboard panel,
Opportunity Ranking view, or Why-Not Engine to consume without each
needing to know three separate modules' return schemas. It changes
nothing about how or when any stand-down engages or clears.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import news_guard
from . import risk_guard
from . import portfolio_risk as pr


@dataclass
class StandDownStatus:
    """One stand-down's current, freshly-recomputed state. Never
    persisted -- constructing this object doesn't store anything, it's
    just a snapshot of what the underlying (unmodified) gate function
    returned just now."""
    name: str
    engaged: bool
    scope: str            # "symbol" | "portfolio" | "platform"
    reason: str = ""
    category: "str | None" = None
    source: str = ""      # which existing module/function this wraps
    detail: dict = field(default_factory=dict)


def news_blackout_status(now=None) -> StandDownStatus:
    """Wraps news_guard.evaluate() verbatim -- platform-wide, applies to
    every symbol simultaneously, no symbol parameter exists on the
    underlying function."""
    d = news_guard.evaluate(now=now)
    active = d.get("active")
    reason = ""
    if d.get("blackout") and active:
        title, mins = active
        reason = f"high-impact {title} ({mins:+d} min)"
    elif not d.get("ok"):
        reason = d.get("note", "")
    return StandDownStatus(
        name="news_blackout", engaged=bool(d.get("blackout", False)), scope="platform",
        reason=reason, category="news_blackout" if d.get("blackout") else None,
        source="engine.news_guard.evaluate", detail=d)


def risk_guard_status(symbol: str) -> StandDownStatus:
    """Wraps risk_guard.evaluate() verbatim -- scoped to one symbol
    (see risk_guard.py's own cross-symbol-contamination fix: a lock on
    one symbol must never imply anything about another)."""
    d = risk_guard.evaluate(symbol)
    return StandDownStatus(
        name="risk_guard_day_stop", engaged=bool(d.get("locked", False)), scope="symbol",
        reason=d.get("reason", ""), category="risk_lock" if d.get("locked") else None,
        source="engine.risk_guard.evaluate", detail=d)


def drawdown_status(settings=None, rows=None) -> StandDownStatus:
    """Reuses the EXACT two functions portfolio_risk.evaluate() itself
    calls for its checks #4 (portfolio-wide day-stop) and #5 (trailing
    30-trade drawdown cap) -- today_realized_r() and
    portfolio_drawdown_r() -- rather than re-deriving the threshold
    logic. Portfolio-wide: independent of any specific symbol/candidate,
    matching why decision_gate.py classifies portfolio_risk's
    DRAWDOWN_PROTECTION category as STAND_DOWN rather than REJECT (see
    DECISION_GATE_SPECIFICATION.md Section 3)."""
    if settings is None:
        from . import config
        settings = config.load()
    if rows is None:
        rows = pr._rows()  # same reader risk_guard.py/portfolio_risk.py both use
    day_stop_r = float(getattr(settings, "portfolio_day_stop_r", 2.0) or 2.0)
    max_dd_r = float(getattr(settings, "portfolio_max_drawdown_r", 6.0) or 6.0)
    dd_max_age_days = float(getattr(settings, "portfolio_drawdown_max_age_days", 30.0) or 30.0)

    portfolio_day_r = risk_guard.today_realized_r(rows, symbol=None)
    closed_rows = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]
    dd = pr.portfolio_drawdown_r(closed_rows, window=30, max_age_days=dd_max_age_days)

    detail = {"portfolio_day_r": portfolio_day_r, "day_stop_r": day_stop_r,
             "portfolio_drawdown_r_30": dd, "max_drawdown_r": max_dd_r,
             "drawdown_max_age_days": dd_max_age_days}

    if portfolio_day_r <= -abs(day_stop_r):
        return StandDownStatus(
            name="drawdown_protection", engaged=True, scope="portfolio",
            reason=f"PORTFOLIO DAY STOP: {portfolio_day_r:+.2f}R today (limit "
                  f"-{abs(day_stop_r):.1f}R)",
            category=pr.DRAWDOWN_PROTECTION,
            source="engine.risk_guard.today_realized_r", detail=detail)
    if dd >= max_dd_r:
        return StandDownStatus(
            name="drawdown_protection", engaged=True, scope="portfolio",
            reason=f"Trailing 30-trade drawdown is {dd:.2f}R (cap {max_dd_r:.1f}R)",
            category=pr.DRAWDOWN_PROTECTION,
            source="engine.portfolio_risk.portfolio_drawdown_r", detail=detail)
    return StandDownStatus(
        name="drawdown_protection", engaged=False, scope="portfolio",
        reason="", category=None,
        source="engine.portfolio_risk.portfolio_drawdown_r", detail=detail)


def current_stand_downs(symbol: "str | None" = None, settings=None, rows=None,
                        now=None) -> list:
    """Every stand-down's CURRENT status in one call. `symbol` given:
    includes that symbol's risk_guard status; omitted: only the
    symbol-agnostic ones (news blackout, portfolio drawdown). Never
    raises -- each wrapped function already fails safe on its own
    (risk_guard/portfolio_risk's disclosed fail-open behavior, news_guard's
    fail-open-with-disclosure); this adds no new failure surface."""
    out = [news_blackout_status(now=now), drawdown_status(settings=settings, rows=rows)]
    if symbol is not None:
        out.append(risk_guard_status(symbol))
    return out


def any_engaged(symbol: "str | None" = None, settings=None, rows=None, now=None) -> bool:
    """Convenience: True if ANY stand-down is currently engaged for this
    symbol (or platform/portfolio-wide, if symbol is omitted)."""
    return any(s.engaged for s in
              current_stand_downs(symbol=symbol, settings=settings, rows=rows, now=now))
