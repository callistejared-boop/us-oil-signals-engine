"""Missing ICT confluences — sweep, displacement, true OTE, order-block.

These four are the concepts a strict ICT read demands that the scorer did not
yet check. Each is a pure, testable function; signals.py folds them into the
confidence score and (for sweep/discount) the CONFIRMED gate.

  * liquidity_sweep: the "turtle soup" trigger. Price runs stops beyond a
    prior swing (sell-side below a low for longs, buy-side above a high for
    shorts) and CLOSES back inside. Smart money engineered liquidity — the
    highest-quality ICT entry context.
  * displacement: an FVG only matters if it was created by an impulse leg.
    A drifting 3-candle gap is noise; a displacement gap is intent.
  * in_ote: textbook Optimal Trade Entry — the 62–79% retracement of the
    dealing range measured FROM the origin of the move (for longs: down from
    the high; for shorts: up from the low).
  * ob_confluence: the entry FVG overlapping the last opposing-candle order
    block doubles the institutional footprint at that price.

All fail-safe: bad input -> (False, ...) so a data hiccup can never crash a
scan or inflate a score.
"""
from __future__ import annotations

from . import structure as st

SWEEP_LOOKBACK = 96      # bars of reference liquidity (24h of 15m)
SWEEP_RECENT = 16        # sweep must have happened in the last N bars (4h)
DISP_RANGE_ATR = 1.2     # impulse candle range >= 1.2 x ATR ...
DISP_BODY_FRAC = 0.55    # ... with a dominant body (not a wick-fest)


def liquidity_sweep(df15, direction, lookback=SWEEP_LOOKBACK,
                    recent=SWEEP_RECENT, k=2):
    """Detect a recent stop-hunt in the trade's favour.

    long : some bar in the last `recent` bars traded BELOW a prior swing low
           (sell-side liquidity) and closed back above it.
    short: mirror above a prior swing high (buy-side liquidity).
    Returns (ok, level, bars_ago).
    """
    try:
        sub = df15.tail(lookback)
        if len(sub) < recent + 10:
            return False, None, None
        ref = sub.iloc[:-recent]
        rec = sub.iloc[-recent:]
        swings = st.find_swings(ref["High"].values, ref["Low"].values, k)
        highs = [s.price for s in swings if s.kind == "H"]
        lows = [s.price for s in swings if s.kind == "L"]
        lo_v, hi_v = rec["Low"].values, rec["High"].values
        cl_v = rec["Close"].values
        n = len(rec)
        if direction == "long" and lows:
            for j in range(n - 1, -1, -1):
                for lvl in lows:
                    if lo_v[j] < lvl and cl_v[j] > lvl:
                        return True, round(float(lvl), 4), n - 1 - j
        if direction == "short" and highs:
            for j in range(n - 1, -1, -1):
                for lvl in highs:
                    if hi_v[j] > lvl and cl_v[j] < lvl:
                        return True, round(float(lvl), 4), n - 1 - j
        return False, None, None
    except Exception:  # noqa: BLE001
        return False, None, None


def displacement(tail_df, gap, atr15):
    """Was the chosen FVG created by a displacement (impulse) candle?

    The gap forms on candle i (gap.created_idx); the impulse is the middle
    candle i-1 of the 3-bar pattern. Requires range >= DISP_RANGE_ATR x ATR
    and a dominant body in the gap's direction.
    """
    try:
        i = int(gap.created_idx) - 1
        if i < 0 or i >= len(tail_df) or not atr15 or atr15 <= 0:
            return False
        bar = tail_df.iloc[i]
        rng = float(bar["High"] - bar["Low"])
        body = float(abs(bar["Close"] - bar["Open"]))
        if rng < DISP_RANGE_ATR * atr15 or rng <= 0:
            return False
        if body / rng < DISP_BODY_FRAC:
            return False
        up = bar["Close"] > bar["Open"]
        return up if gap.kind == "bull" else (not up)
    except Exception:  # noqa: BLE001
        return False


def in_ote(entry, range_hi, range_lo, direction):
    """Textbook OTE: 62–79% retracement measured from the move's origin.
    long : entry between hi - 0.79R and hi - 0.62R (deep discount).
    short: entry between lo + 0.62R and lo + 0.79R (deep premium).
    """
    try:
        r = float(range_hi) - float(range_lo)
        if r <= 0:
            return False
        if direction == "long":
            return (range_hi - 0.79 * r) <= float(entry) <= (range_hi - 0.62 * r)
        return (range_lo + 0.62 * r) <= float(entry) <= (range_lo + 0.79 * r)
    except Exception:  # noqa: BLE001
        return False


def ob_confluence(df15, direction, entry_top, entry_bottom):
    """Does the entry zone overlap the most recent order block?"""
    try:
        from . import ict
        ob = ict.order_block(df15, direction)
        if not ob:
            return False
        ob_lo, ob_hi = ob
        return not (entry_top < ob_lo or entry_bottom > ob_hi)
    except Exception:  # noqa: BLE001
        return False
