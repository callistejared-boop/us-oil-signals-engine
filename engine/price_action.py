"""Price-action layer — classical candlestick + S/R confirmation for ICT/SMC.

This never generates trades on its own. It answers one question for the
confluence engine: does raw price action AGREE or DISAGREE with the ICT/SMC
setup already found? A bullish FVG entry backed by a bullish engulfing candle
at support is a stronger signal than the same FVG with a doji.

Patterns: pin bar (rejection wick), engulfing, inside bar (compression),
outside bar (expansion), breakout-retest quality. All pure functions of
OHLC, fail-safe on short/garbage input.
"""
from __future__ import annotations

PIN_WICK_RATIO = 2.0     # wick >= 2x body to count as a pin bar
PIN_BODY_MAX = 0.35      # body <= 35% of full range


def _bar(df, i):
    r = df.iloc[i]
    o, h, l, c = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])
    rng = h - l
    body = abs(c - o)
    return o, h, l, c, rng, body


def pin_bar(df, i=-1):
    """Bullish pin (hammer): long lower wick, small body near the top.
    Bearish pin (shooting star): long upper wick, small body near the bottom.
    Returns "bull" | "bear" | None.
    """
    try:
        o, h, l, c, rng, body = _bar(df, i)
        if rng <= 0 or body / rng > PIN_BODY_MAX:
            return None
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        if lower_wick >= PIN_WICK_RATIO * max(body, 1e-9) and lower_wick > upper_wick:
            return "bull"
        if upper_wick >= PIN_WICK_RATIO * max(body, 1e-9) and upper_wick > lower_wick:
            return "bear"
        return None
    except Exception:  # noqa: BLE001
        return None


def engulfing(df, i=-1):
    """Current candle's body fully engulfs the prior candle's body."""
    try:
        o1, h1, l1, c1, _, b1 = _bar(df, i - 1)
        o2, h2, l2, c2, _, b2 = _bar(df, i)
        if b2 <= b1:
            return None
        if c2 > o2 and c1 < o1 and c2 >= max(o1, c1) and o2 <= min(o1, c1):
            return "bull"
        if c2 < o2 and c1 > o1 and o2 >= max(o1, c1) and c2 <= min(o1, c1):
            return "bear"
        return None
    except Exception:  # noqa: BLE001
        return None


def inside_bar(df, i=-1):
    """Current bar's range sits fully inside the prior bar's range (compression)."""
    try:
        _, h1, l1, _, _, _ = _bar(df, i - 1)
        _, h2, l2, _, _, _ = _bar(df, i)
        return bool(h2 <= h1 and l2 >= l1)
    except Exception:  # noqa: BLE001
        return False


def outside_bar(df, i=-1):
    """Current bar's range fully engulfs the prior bar's range (expansion)."""
    try:
        _, h1, l1, _, _, _ = _bar(df, i - 1)
        _, h2, l2, _, _, _ = _bar(df, i)
        return bool(h2 >= h1 and l2 <= l1)
    except Exception:  # noqa: BLE001
        return False


def momentum_candle(df, i=-1, atr_val=None):
    """Wide-range, dominant-body candle — displacement in classical terms."""
    try:
        o, h, l, c, rng, body = _bar(df, i)
        if rng <= 0:
            return None
        if atr_val and atr_val > 0 and rng < 1.1 * atr_val:
            return None
        if body / rng < 0.6:
            return None
        return "bull" if c > o else "bear"
    except Exception:  # noqa: BLE001
        return None


def near_level(price, level, atr_val, mult=0.5):
    """Is price within `mult` x ATR of a support/resistance level?"""
    try:
        if not atr_val or atr_val <= 0:
            return False
        return abs(float(price) - float(level)) <= mult * atr_val
    except Exception:  # noqa: BLE001
        return False


def breakout_retest_quality(df, level, direction, atr_val, lookback=8):
    """After a break of `level`, did the retest hold (good) or reclaim through
    it (bad — likely a false breakout / liquidity grab)?
    Returns "held" | "failed" | "untested".
    """
    try:
        sub = df.tail(lookback)
        touched = False
        for _, r in sub.iterrows():
            lo, hi, c = float(r["Low"]), float(r["High"]), float(r["Close"])
            if direction == "long":
                if lo <= level + 0.25 * (atr_val or 0):
                    touched = True
                    if c < level:
                        return "failed"
            else:
                if hi >= level - 0.25 * (atr_val or 0):
                    touched = True
                    if c > level:
                        return "failed"
        return "held" if touched else "untested"
    except Exception:  # noqa: BLE001
        return "untested"


def read(df, direction, key_level=None, atr_val=None):
    """One-call summary the confluence engine consumes.
    Returns dict: pattern, agrees(bool|None), retest, lines[].
    """
    try:
        pin = pin_bar(df)
        eng = engulfing(df)
        mom = momentum_candle(df, atr_val=atr_val)
        inside = inside_bar(df)
        outside = outside_bar(df)
        pattern = eng or pin or mom
        agrees = None
        if pattern is not None:
            agrees = (pattern == "bull") if direction == "long" else (pattern == "bear")
        lines = []
        if pattern:
            lines.append(f"price action: {pattern} pattern "
                         f"({'agrees' if agrees else 'disagrees'} with {direction})")
        if inside:
            lines.append("inside bar — compression, awaiting expansion")
        if outside:
            lines.append("outside bar — expansion / conviction candle")
        retest = "untested"
        if key_level is not None:
            retest = breakout_retest_quality(df, key_level, direction, atr_val)
            lines.append(f"breakout retest of {key_level}: {retest}")
        return {"pattern": pattern, "agrees": agrees, "retest": retest, "lines": lines}
    except Exception:  # noqa: BLE001
        return {"pattern": None, "agrees": None, "retest": "untested", "lines": []}
