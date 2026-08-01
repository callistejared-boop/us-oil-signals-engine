"""Fold live news bias into a signal's confidence - bounded and transparent.

Turns the news feed from a sidebar into a real input: if the live per-pair
news signal agrees with the trade direction it nudges confidence up; if it
conflicts it nudges down. The nudge is small and strength-scaled (max +/-6),
so news can refine but never overturn the technical read. When there is no
fresh/directional news the delta is 0 - so backtests and the core engine are
completely unaffected (this is only ever called on the LIVE path).
"""
from engine import fundamentals_feed as ff

STRENGTH_PTS = {"HIGH": 6, "MED": 3, "LOW": 1}


def news_view(symbol, load=ff.load_feed):
    """Fresh directional news for a symbol, or None."""
    feed = load(symbol)
    if not feed:
        return None
    return {"signal": feed.get("signal", "NEUTRAL"),
            "strength": feed.get("strength", "LOW"),
            "why": feed.get("why", ""),
            "asof": feed.get("asof")}


def adjustment(symbol, direction, load=ff.load_feed):
    """Return (delta_points, rationale) for a trade in `direction`."""
    v = news_view(symbol, load=load)
    if not v or v["signal"] not in ("BUY", "SELL"):
        return 0, "no fresh directional news - technical read unchanged"
    pts = STRENGTH_PTS.get(v["strength"], 1)
    news_long = v["signal"] == "BUY"
    trade_long = direction == "long"
    if news_long == trade_long:
        return pts, f"news {v['signal']} ({v['strength']}) agrees with {direction} (+{pts})"
    return -pts, f"news {v['signal']} ({v['strength']}) CONFLICTS with {direction} (-{pts})"


def apply(symbol, direction, base_conf, load=ff.load_feed):
    """Return (adjusted_conf, delta, rationale). Bounded to [0, 100]."""
    delta, why = adjustment(symbol, direction, load=load)
    adj = max(0, min(100, int(round(base_conf + delta))))
    return adj, delta, why


def grade_from(conf, tier):
    if tier != "confirmed":
        return "C (watch)"
    return "A+" if conf >= 88 else "A" if conf >= 78 else "B"


CONTEXT_CAP = 8


def apply_context(symbol, direction, base_conf, now=None, load=None):
    """Fold live-news bias + ICT kill-zone timing + any fresh TradingView
    confirmation into confidence, capped at +/-CONTEXT_CAP so context refines but
    never overturns technicals. Returns (adjusted_conf, total_delta, rationale)."""
    from engine import session_edge, tv_signals
    load = load or ff.load_feed
    nd, nwhy = adjustment(symbol, direction, load=load)
    sd, swhy = session_edge.adjustment(now)
    td, twhy = tv_signals.confirmation(symbol, direction, now=now)
    total = max(-CONTEXT_CAP, min(CONTEXT_CAP, nd + sd + td))
    adj = max(0, min(100, int(round(base_conf + total))))
    why = f"news {nwhy}; session {swhy}" + (f"; {twhy}" if td else "")
    return adj, total, why
