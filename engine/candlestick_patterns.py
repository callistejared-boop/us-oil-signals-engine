"""Classical candlestick pattern recognition — another genuinely new
confirmation source, not a re-weighting of anything already in the engine.

Gap this closes: the ICT/SMC layer already reasons about FVGs and order
blocks, and Wyckoff reasons about absorption/SOS/SOW, but nothing in the
engine names the actual candle shape at the point of reaction. A hammer or
bullish engulfing candle printing exactly at an OTE/FVG/order-block/pivot
confluence zone is precisely the kind of "everything lines up" evidence
discretionary and institutional traders alike look for — this module gives
that observation a name and a score instead of leaving it implicit.

Patterns detected (single, two, and three-candle), anchored on the most
recent completed bar so a pattern is only "live" if it just printed:
  Single:  Hammer, Inverted Hammer / Shooting Star, Doji (standard,
           dragonfly, gravestone), Marubozu (momentum candle)
  Two:     Bullish/Bearish Engulfing, Piercing Line, Dark Cloud Cover,
           Tweezer Top/Bottom, Bullish/Bearish Harami (+ Harami Cross)
  Three:   Morning Star, Evening Star, Three White Soldiers, Three Black Crows

Tweezer and harami patterns added from a literature review pass (The
Candlestick Trading Bible) — both are commonly-cited reversal signals this
module didn't originally cover.

Inside Bar added from the same book's dedicated chapter (a full chapter
covering false-breakout and support/resistance combinations for it) --
a genuinely new, distinct setup: the current candle's full range sits
inside the prior candle's range, signalling compression/indecision rather
than a directional reversal, so it is tagged "neutral" and never forces a
bull/bear lean on its own.

Every classification uses body/range/wick ratios only (no lookahead — each
pattern is evaluated strictly from bars that have already closed). Fail-safe
throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

DOJI_BODY_RATIO = 0.10      # body <= 10% of range -> doji family
MARUBOZU_WICK_RATIO = 0.05  # wicks <= 5% of range each -> marubozu
PIN_WICK_RATIO = 0.60       # dominant wick >= 60% of range -> hammer/star family
PIN_BODY_RATIO = 0.30       # body <= 30% of range for the pin-bar family


def _bar(row):
    o, h, l, c = float(row.Open), float(row.High), float(row.Low), float(row.Close)
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {"o": o, "h": h, "l": l, "c": c, "rng": rng, "body": body,
            "body_pct": body / rng, "upper_pct": upper / rng, "lower_pct": lower / rng,
            "bull": c > o, "bear": c < o}


def _single_candle_patterns(b) -> list:
    out = []
    if b["body_pct"] <= DOJI_BODY_RATIO:
        if b["lower_pct"] >= 0.6:
            out.append(("dragonfly doji", "bull"))
        elif b["upper_pct"] >= 0.6:
            out.append(("gravestone doji", "bear"))
        else:
            out.append(("doji", "neutral"))
    if b["upper_pct"] <= MARUBOZU_WICK_RATIO and b["lower_pct"] <= MARUBOZU_WICK_RATIO \
            and b["body_pct"] >= 0.85:
        out.append(("marubozu", "bull" if b["bull"] else "bear"))
    if b["body_pct"] <= PIN_BODY_RATIO:
        if b["lower_pct"] >= PIN_WICK_RATIO and b["upper_pct"] <= 0.15:
            out.append(("hammer", "bull"))
        elif b["upper_pct"] >= PIN_WICK_RATIO and b["lower_pct"] <= 0.15:
            out.append(("shooting star / inverted hammer", "bear"))
    return out


def _two_candle_patterns(prev, cur) -> list:
    out = []
    # bullish/bearish engulfing: current body fully engulfs prior body, opposite colors
    if cur["bear"] is False and cur["bull"] and prev["bear"] and \
            cur["o"] <= prev["c"] and cur["c"] >= prev["o"]:
        out.append(("bullish engulfing", "bull"))
    if cur["bull"] is False and cur["bear"] and prev["bull"] and \
            cur["o"] >= prev["c"] and cur["c"] <= prev["o"]:
        out.append(("bearish engulfing", "bear"))
    # piercing line: prior bearish, current bullish opens below prior low-ish and
    # closes above the midpoint of the prior body
    prev_mid = (prev["o"] + prev["c"]) / 2.0
    if prev["bear"] and cur["bull"] and cur["o"] < prev["c"] and cur["c"] > prev_mid \
            and cur["c"] < prev["o"]:
        out.append(("piercing line", "bull"))
    # dark cloud cover: mirror of the above
    if prev["bull"] and cur["bear"] and cur["o"] > prev["c"] and cur["c"] < prev_mid \
            and cur["c"] > prev["o"]:
        out.append(("dark cloud cover", "bear"))
    # tweezer bottom: two candles with matching (near-identical) lows after a
    # down move -> shared rejection of the same level
    low_tol = 0.1 * max(prev["rng"], cur["rng"], 1e-9)
    if abs(prev["l"] - cur["l"]) <= low_tol and prev["bear"] and cur["bull"]:
        out.append(("tweezer bottom", "bull"))
    # tweezer top: mirror, matching highs after an up move
    high_tol = 0.1 * max(prev["rng"], cur["rng"], 1e-9)
    if abs(prev["h"] - cur["h"]) <= high_tol and prev["bull"] and cur["bear"]:
        out.append(("tweezer top", "bear"))
    # bullish harami: prior big bearish candle, current small candle fully
    # contained inside the prior body -> momentum stalling, possible reversal up
    if prev["bear"] and prev["body_pct"] >= 0.5 and \
            cur["o"] > prev["c"] and cur["c"] < prev["o"] and cur["body"] < prev["body"]:
        out.append(("bullish harami" + (" cross" if cur["body_pct"] <= DOJI_BODY_RATIO else ""), "bull"))
    # bearish harami: mirror
    if prev["bull"] and prev["body_pct"] >= 0.5 and \
            cur["o"] < prev["c"] and cur["c"] > prev["o"] and cur["body"] < prev["body"]:
        out.append(("bearish harami" + (" cross" if cur["body_pct"] <= DOJI_BODY_RATIO else ""), "bear"))
    # inside bar: current candle's full range contained within the prior
    # candle's range -> compression/indecision, not itself directional
    if cur["h"] <= prev["h"] and cur["l"] >= prev["l"]:
        out.append(("inside bar", "neutral"))
    return out


def _three_candle_patterns(b1, b2, b3) -> list:
    out = []
    # morning star: bearish, small-body/indecision, strong bullish closing into b1's body
    if b1["bear"] and b1["body_pct"] >= 0.4 and b2["body_pct"] <= 0.35 and \
            b3["bull"] and b3["body_pct"] >= 0.4 and b3["c"] >= (b1["o"] + b1["c"]) / 2.0:
        out.append(("morning star", "bull"))
    # evening star: mirror
    if b1["bull"] and b1["body_pct"] >= 0.4 and b2["body_pct"] <= 0.35 and \
            b3["bear"] and b3["body_pct"] >= 0.4 and b3["c"] <= (b1["o"] + b1["c"]) / 2.0:
        out.append(("evening star", "bear"))
    # three white soldiers: three consecutive strong bullish candles, each closing higher
    if b1["bull"] and b2["bull"] and b3["bull"] and \
            b1["body_pct"] >= 0.5 and b2["body_pct"] >= 0.5 and b3["body_pct"] >= 0.5 and \
            b2["c"] > b1["c"] and b3["c"] > b2["c"]:
        out.append(("three white soldiers", "bull"))
    # three black crows: mirror
    if b1["bear"] and b2["bear"] and b3["bear"] and \
            b1["body_pct"] >= 0.5 and b2["body_pct"] >= 0.5 and b3["body_pct"] >= 0.5 and \
            b2["c"] < b1["c"] and b3["c"] < b2["c"]:
        out.append(("three black crows", "bear"))
    return out


def detect(df: pd.DataFrame) -> dict:
    """Patterns live on the most recently completed bar. Returns
    {"patterns": [(name, lean), ...], "lean": "bull"/"bear"/"neutral"/None,
    "note": str}."""
    try:
        if len(df) < 3:
            return {"patterns": [], "lean": None, "note": "candlesticks: insufficient bars"}
        b3 = _bar(df.iloc[-1])
        b2 = _bar(df.iloc[-2])
        b1 = _bar(df.iloc[-3])

        found = []
        found += [(n, l) for n, l in _single_candle_patterns(b3) if l != "neutral"]
        found += _two_candle_patterns(b2, b3)
        found += _three_candle_patterns(b1, b2, b3)

        if not found:
            return {"patterns": [], "lean": None,
                    "note": "candlesticks: no textbook pattern on the last bar"}

        bulls = sum(1 for _, l in found if l == "bull")
        bears = sum(1 for _, l in found if l == "bear")
        lean = "bull" if bulls > bears else "bear" if bears > bulls else None
        names = ", ".join(sorted({n for n, _ in found}))
        return {"patterns": found, "lean": lean,
                "note": f"candlesticks: {names} ({lean or 'mixed'})"}
    except Exception:  # noqa: BLE001
        return {"patterns": [], "lean": None, "note": "candlesticks: unavailable"}


def alignment(df: pd.DataFrame, direction: str) -> dict:
    """Does the most recent candlestick pattern support or warn against
    `direction`? Soft signal -> {supports: True/False/None, note}."""
    d = detect(df)
    if d["lean"] is None:
        return {"supports": None, "note": d["note"]}
    supports = (d["lean"] == "bull") == (direction == "long")
    return {"supports": supports, "note": d["note"]}
