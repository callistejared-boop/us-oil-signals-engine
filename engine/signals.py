"""Multi-timeframe confluence scoring and signal generation (instrument-agnostic).

Tiers:
  * CONFIRMED (confidence >= PUBLISH_THRESHOLD and strong bias) -> tradeable, logged.
  * WATCH     (confidence >= WATCH_THRESHOLD)                    -> surfaced only.

Bias uses market structure with an EMA-slope fallback so the engine forms a
directional view often; the confidence score governs tradeability.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import structure as st
from . import ict_confluence as icf
from .data_loader import resample
from .technicals import ema

MIN_RR = 2.0
MAX_RR = 4.0
SPREAD_MULT = 0.0001   # min stop distance as a fraction of price (cost floor)
PUBLISH_THRESHOLD = 70
WATCH_THRESHOLD = 55
FVG_MAX_AGE_BARS = 96
ENTRY_MAX_DISTANCE_ATR = 3.0
BIAS_WEIGHTS = {"1d": 3, "4h": 2, "1h": 1}
BIAS_MIN = 2


@dataclass
class Signal:
    time: pd.Timestamp
    direction: str
    entry: float
    stop: float
    target: float
    rr: float
    confidence: int
    symbol: str = "XAUUSD"
    biases: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    invalidation: str = ""
    tier: str = "confirmed"
    prob: int = 0

    def as_text(self) -> str:
        arrow = "LONG" if self.direction == "long" else "SHORT"
        head = ("CONFIRMED SIGNAL" if self.tier == "confirmed"
                else "SETUP FORMING (watch)")
        return "\n".join([
            f"{head} — {self.symbol} {arrow}",
            f"confidence {self.confidence}/100 · est. probability ~{self.prob}%",
            f"entry {self.entry} | stop {self.stop} | target {self.target} (RR {self.rr})",
            f"invalidation: {self.invalidation}",
        ])


def _bias_score(biases: dict) -> tuple:
    score = 0
    for tf, b in biases.items():
        w = BIAS_WEIGHTS.get(tf, 1)
        if b == "bull":
            score += w
        elif b == "bear":
            score -= w
    if score >= BIAS_MIN:
        return "long", score
    if score <= -BIAS_MIN:
        return "short", -score
    return "none", abs(score)


def _prob(conf: int) -> int:
    return int(min(78, 45 + (conf - 50) * 0.7))


def analyze(df15: pd.DataFrame, min_conf: int = PUBLISH_THRESHOLD,
            symbol: str = "XAUUSD"):
    if len(df15) < 400:
        return None
    now = df15.index[-1]
    price = float(df15["Close"].iloc[-1])

    min_bars = {"1d": 15, "4h": 60, "1h": 100}
    biases = {}
    for tf in ("1d", "4h", "1h"):
        hdf = resample(df15, tf)
        if len(hdf) < min_bars[tf]:
            return None
        biases[tf] = structure_trend(hdf)

    direction, bias_pts = _bias_score(biases)
    if direction == "none":
        return None

    struct15 = st.structure_series(df15.tail(400))
    trend15 = str(struct15["trend"].iloc[-1])
    if (direction == "long" and trend15 == "bear") or \
       (direction == "short" and trend15 == "bull"):
        return None

    h1 = resample(df15, "1h")
    range_hi, range_lo = st.dealing_range(h1, lookback=200)
    pos = st.range_position(price, range_hi, range_lo)
    discount_ok = (direction == "long" and pos <= 0.5) or \
                  (direction == "short" and pos >= 0.5)

    tail = df15.tail(FVG_MAX_AGE_BARS + 4)
    fvgs = st.find_fvgs(tail)
    kind = "bull" if direction == "long" else "bear"
    live_gaps = st.unfilled_fvgs(fvgs, len(tail) - 1, kind)
    atr15 = float(st.atr(df15).iloc[-1])
    if not live_gaps or atr15 <= 0:
        return None

    def usable(g):
        if direction == "long":
            return g.top < price and (price - g.mid) <= ENTRY_MAX_DISTANCE_ATR * atr15
        return g.bottom > price and (g.mid - price) <= ENTRY_MAX_DISTANCE_ATR * atr15

    candidates = [g for g in live_gaps if usable(g)]
    if not candidates:
        return None
    gap = min(candidates, key=lambda g: abs(price - g.mid))

    entry = gap.mid
    pad = 0.25 * atr15
    stop = gap.bottom - pad if direction == "long" else gap.top + pad

    if direction == "long":
        tgt = struct15["swing_high"].iloc[-1]
        if pd.isna(tgt) or tgt <= entry:
            tgt = float(df15["High"].tail(200).max())
    else:
        tgt = struct15["swing_low"].iloc[-1]
        if pd.isna(tgt) or tgt >= entry:
            tgt = float(df15["Low"].tail(200).min())
    target = float(tgt)

    risk = abs(entry - stop)
    reward = abs(target - entry)
    # cost floor scales with volatility (ATR) so it works for gold, FX and
    # crypto alike, and adapts to each regime instead of a fixed dollar value
    if risk <= 0 or risk < 0.15 * atr15:
        return None
    rr = reward / risk
    if rr < MIN_RR:
        return None
    if rr > MAX_RR:
        target = entry + MAX_RR * risk if direction == "long" \
            else entry - MAX_RR * risk
        rr = MAX_RR

    # --- full ICT confluence read (sweep / displacement / OTE / OB) --------
    sweep_ok, sweep_lvl, sweep_ago = icf.liquidity_sweep(df15, direction)
    disp_ok = icf.displacement(tail, gap, atr15)
    ote_ok = icf.in_ote(entry, range_hi, range_lo, direction)
    ob_ok = icf.ob_confluence(df15, direction, gap.top, gap.bottom)

    reasons = []
    conf = 40 + bias_pts * 5
    reasons.append(f"HTF bias {biases} (weighted {bias_pts}) [+{bias_pts*5}]")
    if discount_ok:
        conf += 12
        zone = "discount" if direction == "long" else "premium"
        reasons.append(f"price in {zone} of 1H range ({pos:.0%}) [+12]")
    if sweep_ok:
        conf += 12
        side_l = "sell-side" if direction == "long" else "buy-side"
        reasons.append(f"{side_l} liquidity SWEPT at {sweep_lvl} "
                       f"({sweep_ago} bars ago) — stop-hunt reversal [+12]")
    if disp_ok:
        conf += 8
        reasons.append("entry FVG born of displacement (impulse leg) [+8]")
    if ote_ok:
        conf += 8
        reasons.append("entry inside true OTE (62-79% retracement) [+8]")
    if ob_ok:
        conf += 6
        reasons.append("entry FVG overlaps order block [+6]")
    if st.in_killzone(now):
        conf += 8
        reasons.append("inside London/NY kill zone [+8]")
    if rr >= 3:
        conf += 4
        reasons.append(f"RR {rr:.1f} >= 3 [+4]")
    conf = min(conf, 95)

    # CONFIRMED demands institutional context: never chase mid-range without
    # either a discount/premium location OR an engineered-liquidity sweep.
    location_ok = discount_ok or sweep_ok
    confirmed = conf >= PUBLISH_THRESHOLD and bias_pts >= 3 and location_ok
    if not location_ok:
        reasons.append("NO discount/sweep context — capped at watch tier")
    if confirmed:
        tier = "confirmed"
    elif conf >= WATCH_THRESHOLD:
        tier = "watch"
    else:
        return None
    if min_conf >= PUBLISH_THRESHOLD and tier != "confirmed":
        return None

    side = "below" if direction == "long" else "above"
    ndp = 5 if price < 10 else 2
    return Signal(
        time=now, direction=direction, entry=round(entry, ndp),
        stop=round(stop, ndp), target=round(target, ndp), rr=round(rr, 2),
        confidence=conf, symbol=symbol, biases=biases, reasons=reasons,
        tier=tier, prob=_prob(conf),
        invalidation=f"15m close {side} {round(stop, ndp)} voids it — {kind} FVG mitigated.",
    )


def structure_trend(df: pd.DataFrame) -> str:
    s = st.structure_series(df.tail(300))
    trend = str(s["trend"].iloc[-1])
    if trend != "range":
        return trend
    c = df["Close"]
    if len(c) < 55:
        return "range"
    ef, es, px = float(ema(c, 21).iloc[-1]), float(ema(c, 55).iloc[-1]), float(c.iloc[-1])
    if px > ef > es:
        return "bull"
    if px < ef < es:
        return "bear"
    return "range"
