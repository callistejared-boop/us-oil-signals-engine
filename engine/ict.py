"""Deep ICT / Smart Money Concepts read.

Produces the full institutional picture the briefing reports: multi-timeframe
bias (structure + EMA fallback), liquidity map (buy-side / sell-side),
last BOS/CHoCH event, nearest unfilled Fair Value Gaps with prices, the most
recent order block, premium/discount (with OTE zone), the trading session,
and a directional lean with an estimated probability.

Nothing here fabricates certainty — the probability is a transparent score
built from how many independent factors align, labelled as an estimate.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st
from .data_loader import resample
from .technicals import ema


def tf_trend(df: pd.DataFrame) -> str:
    """Structure trend, with an EMA-slope fallback when structure is 'range'.
    This is why the engine now forms a directional view far more often."""
    s = st.structure_series(df.tail(300))
    trend = str(s["trend"].iloc[-1])
    if trend != "range":
        return trend
    c = df["Close"]
    if len(c) < 50:
        return "range"
    e_fast = float(ema(c, 21).iloc[-1])
    e_slow = float(ema(c, 55).iloc[-1])
    price = float(c.iloc[-1])
    if price > e_fast > e_slow:
        return "bull"
    if price < e_fast < e_slow:
        return "bear"
    return "range"


def biases(df15: pd.DataFrame) -> dict:
    out = {}
    for tf in ("1d", "4h", "1h", "15m"):
        try:
            out[tf] = tf_trend(resample(df15, tf) if tf != "15m" else df15)
        except Exception:  # noqa: BLE001
            out[tf] = "n/a"
    return out


def liquidity(df: pd.DataFrame, price: float, lookback: int = 300) -> dict:
    """Nearest resting liquidity: buy-side above (swing highs), sell-side
    below (swing lows). Also returns strong/weak-labelled pools (see
    structure.classify_swing_strength) so the caller can tell a defended
    level apart from a high-probability sweep target -- this labelling is
    standard ICT/SMC domain knowledge, not sourced from a specific document."""
    sub = df.tail(lookback)
    sw = st.find_swings(sub["High"].values, sub["Low"].values, k=2)
    highs = sorted({round(float(s.price), 2) for s in sw if s.kind == "H" and s.price > price})
    lows = sorted({round(float(s.price), 2) for s in sw if s.kind == "L" and s.price < price}, reverse=True)

    try:
        atr_val = float(st.atr(sub).iloc[-1])
        sw_labelled = st.classify_swing_strength(sub.reset_index(drop=True), sw, atr_val)
        buy_labelled = sorted(
            ({"price": round(s.price, 2), "strength": s.strength}
             for s in sw_labelled if s.kind == "H" and s.price > price and s.strength),
            key=lambda x: x["price"])[:3]
        sell_labelled = sorted(
            ({"price": round(s.price, 2), "strength": s.strength}
             for s in sw_labelled if s.kind == "L" and s.price < price and s.strength),
            key=lambda x: -x["price"])[:3]
    except Exception:  # noqa: BLE001
        buy_labelled, sell_labelled = [], []

    return {"buyside": highs[:2], "sellside": lows[:2],
            "buyside_labeled": buy_labelled, "sellside_labeled": sell_labelled}


def last_event(df: pd.DataFrame) -> str:
    s = st.structure_series(df.tail(400))
    ev = s[s["event"] != ""]
    if ev.empty:
        return "none recent"
    row = ev.iloc[-1]
    bars_ago = len(s) - 1 - s.index.get_loc(ev.index[-1])
    return f"{row['event']} ({int(bars_ago)} bars ago)"


def nearest_fvg(df: pd.DataFrame, kind: str, price: float):
    tail = df.tail(120)
    gaps = st.unfilled_fvgs(st.find_fvgs(tail), len(tail) - 1, kind)
    if not gaps:
        return None
    g = min(gaps, key=lambda x: abs(price - x.mid))
    return (round(g.bottom, 2), round(g.top, 2))


def order_block(df: pd.DataFrame, direction: str):
    """Last opposite-colour candle before a displacement move — a simple,
    robust order-block proxy."""
    d = df.tail(60).reset_index(drop=True)
    o, c, h, l = d["Open"], d["Close"], d["High"], d["Low"]
    if direction == "long":
        for i in range(len(d) - 2, 1, -1):
            if c[i] > o[i] and (c[i] - o[i]) > 1.2 * (d["High"] - d["Low"]).tail(20).mean() \
               and c[i - 1] < o[i - 1]:
                return (round(float(l[i - 1]), 2), round(float(h[i - 1]), 2))
    else:
        for i in range(len(d) - 2, 1, -1):
            if c[i] < o[i] and (o[i] - c[i]) > 1.2 * (d["High"] - d["Low"]).tail(20).mean() \
               and c[i - 1] > o[i - 1]:
                return (round(float(l[i - 1]), 2), round(float(h[i - 1]), 2))
    return None


def read(df15: pd.DataFrame) -> dict:
    price = float(df15["Close"].iloc[-1])
    h1 = resample(df15, "1h")
    bs = biases(df15)
    rng_hi, rng_lo = st.dealing_range(h1, lookback=200)
    pos = st.range_position(price, rng_hi, rng_lo)
    eq = (rng_hi + rng_lo) / 2
    ote_lo, ote_hi = rng_lo + 0.62 * (rng_hi - rng_lo), rng_lo + 0.79 * (rng_hi - rng_lo)

    # directional lean: weighted vote across TFs
    score = 0
    for tf, w in (("1d", 3), ("4h", 2), ("1h", 2), ("15m", 1)):
        b = bs.get(tf)
        if b == "bull":
            score += w
        elif b == "bear":
            score -= w
    lean = "bullish" if score >= 2 else "bearish" if score <= -2 else "balanced"
    direction = "long" if lean == "bullish" else "short" if lean == "bearish" else None

    liq = liquidity(df15, price)
    kind = "bull" if direction == "long" else "bear" if direction == "short" else None
    fvg = nearest_fvg(df15, kind, price) if kind else None
    ob = order_block(df15, direction) if direction else None
    ev = last_event(h1)

    hour = df15.index[-1].hour
    session = ("London KZ" if 7 <= hour < 10 else "New York KZ" if 12 <= hour < 15
               else "Asian" if 0 <= hour < 6 else "off-session")

    # transparent probability estimate from aligned factors
    factors = 0
    total = 5
    if direction:
        factors += 1
        if (direction == "long" and pos <= 0.5) or (direction == "short" and pos >= 0.5):
            factors += 1
        if fvg:
            factors += 1
        if ob:
            factors += 1
        if 7 <= hour < 15:
            factors += 1
    prob = 40 + int(factors / total * 40) if direction else None   # 40–80 band

    zone = ("discount" if pos <= 0.4 else "premium" if pos >= 0.6 else "equilibrium")
    if pos > 1:
        zone = "above range (breakout)"
    elif pos < 0:
        zone = "below range (breakdown)"

    lines = [
        f"bias  D={bs['1d']}  4H={bs['4h']}  1H={bs['1h']}  15m={bs['15m']}",
        f"dealing range {rng_lo:.2f}-{rng_hi:.2f}  ->  {zone} "
        f"(eq {eq:.2f}, OTE {ote_lo:.2f}-{ote_hi:.2f})",
        f"buy-side liquidity: {liq['buyside'] or '—'}",
        f"sell-side liquidity: {liq['sellside'] or '—'}",
        f"last structure: {ev}",
        f"nearest unfilled FVG ({kind or 'n/a'}): "
        f"{(str(fvg[0])+'-'+str(fvg[1])) if fvg else '—'}",
        f"order block: {(str(ob[0])+'-'+str(ob[1])) if ob else '—'}",
        f"session: {session}",
    ]
    return {
        "price": price, "biases": bs, "lean": lean, "direction": direction,
        "prob": prob, "pos": pos, "zone": zone, "range": (rng_lo, rng_hi),
        "ote": (ote_lo, ote_hi), "liq": liq, "fvg": fvg, "ob": ob,
        "event": ev, "session": session, "lines": lines,
    }
