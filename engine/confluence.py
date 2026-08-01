"""Unified institutional confluence engine (MAST).

Design contract, matching the spec directly:
  * ICT + SMC (engine.signals / engine.ict_confluence / engine.structure)
    remain Layer 1 — the only methodology allowed to ORIGINATE a setup.
    Nothing in this module can create a trade idea that Layer 1 didn't find.
  * Every other methodology (price action, trend, breakout, mean reversion,
    volume profile, Wyckoff, macro, news, session, volatility, RR, RSI
    momentum divergence, daily/weekly pivot confluence, candlestick
    patterns, breaker/mitigation blocks, Fibonacci retracement/extension
    confluence, multi-swing chart patterns) is a CONFIRMATION layer only.
    Each contributes points to a single 0-100
    weighted confidence score and a pass/fail line to the validation
    checklist; none of them can flip a rejected Layer-1 read into a trade.
  * A small set of items are HARD gates (fail => reject outright): no
    chasing an already-exhausted mean-reversion extension, no entering
    immediately after a false breakout at the level, no fighting a HIGH-
    strength opposing news signal, minimum R:R. Everything else is scored,
    not gated — making every single item a hard gate would choke the system
    to near-zero signals, which is quantity=0, not quality. That trade-off
    is intentional and documented for the user, not hidden.
  * The base ICT/SMC tier (confirmed vs watch) from signals.py is itself a
    prerequisite: confluence can only ever CONFIRM or DOWNGRADE, never
    promote a watch-tier read to confirmed on its own.

Nothing here promises a win-rate. It produces an auditable, explainable
0-100 confluence score plus the checklist and reasoning the AI-reasoning
requirement asks for. Whether higher scores actually win more often is a
question for the walk-forward/forward-test loop, not this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import signals, structure as st, regime as rg
from . import price_action as pa, trend_quality as tq, breakout as bo
from . import mean_reversion as mr, wyckoff as wy, volume_profile as vp
from . import correlation as co, bias_adjust as ba
from . import cot_feed as cot, spread_feed as sp, seasonality as sea
from . import risk_sentiment as rs
from . import momentum_divergence as md, pivots as pv
from . import candlestick_patterns as cs
from . import breaker_blocks as bb, fibonacci as fib
from . import chart_patterns as chp
from . import liquidity_strength as ls
from . import balanced_range as bpr
from . import session_model as sm
from . import elliott_wave as ew
from . import icc as icc_mod
from .data_loader import resample

NEWS_HARD_BLOCK_PTS = -6   # a HIGH-strength opposing news signal is a hard gate
DEFAULT_MIN_SCORE = 70


@dataclass
class ConfluenceRead:
    symbol: str
    direction: str
    base_tier: str            # "confirmed" | "watch" from Layer 1 (ICT/SMC)
    final_tier: str           # base_tier, or "rejected" if a hard gate failed
    score: int                # 0-100 weighted confluence score
    checklist: list = field(default_factory=list)   # [(name, passed, note)]
    agree: list = field(default_factory=list)
    disagree: list = field(default_factory=list)
    reasoning: list = field(default_factory=list)
    layers: dict = field(default_factory=dict)
    sig: object = None

    @property
    def tradeable(self) -> bool:
        return self.final_tier == "confirmed"


def _htf(df15):
    try:
        return resample(df15, "4h")
    except Exception:  # noqa: BLE001
        return df15


def analyze(df15, symbol="WTIUSD", min_score=DEFAULT_MIN_SCORE):
    """Full MAST confluence read. Returns ConfluenceRead or None if Layer 1
    (ICT/SMC) found nothing at all — confirmation layers never originate."""
    sig = signals.analyze(df15, min_conf=signals.WATCH_THRESHOLD, symbol=symbol)
    if sig is None:
        return None

    direction = sig.direction
    df_htf = _htf(df15)
    atr_val = float(st.atr(df15).iloc[-1])
    swing_hi = float(st.structure_series(df15.tail(400))["swing_high"].iloc[-1] or sig.entry)
    swing_lo = float(st.structure_series(df15.tail(400))["swing_low"].iloc[-1] or sig.entry)

    pa_read = pa.read(df15, direction, key_level=sig.entry, atr_val=atr_val)
    tq_read = tq.read(df15, df_htf, direction)
    bo_read = bo.read(df15, direction)
    mr_read = mr.read(df15, direction, swing_high=swing_hi, swing_low=swing_lo)
    wy_read = wy.read(df15, direction, atr_val, htf_df=df_htf)
    vp_read = vp.read(df15, atr_val)
    reg = rg.classify(df_htf)

    dxy = co.read_macro()
    macro = co.macro_alignment(symbol, direction, dxy.get("trend") if dxy else None)
    news = ba.news_view(symbol)
    in_kz = st.in_killzone(df15.index[-1])

    # ---- weighted score -----------------------------------------------
    score = 0.0
    agree, disagree, reasoning = [], [], []

    ict_pts = sig.confidence * 0.45
    score += ict_pts
    reasoning.append(f"Layer 1 ICT/SMC confidence {sig.confidence}/100 -> "
                     f"{ict_pts:.1f} pts (45% weight)")

    if pa_read["agrees"] is True:
        score += 8; agree.append("price action")
    elif pa_read["agrees"] is False:
        score -= 5; disagree.append("price action")

    if tq_read["continuation_ok"]:
        score += 10; agree.append("trend (HTF stack + ADX)")
    elif tq_read["htf_agrees"]:
        score += 4; agree.append("trend (HTF direction only)")
    else:
        score -= 6; disagree.append("trend (HTF stack disagrees)")

    if bo_read["break_verdict"] == "real":
        score += 6; agree.append("breakout quality")
    elif bo_read["break_verdict"] == "false":
        score -= 6; disagree.append("breakout quality (recent false break)")

    mr_conflict = mr_read["conflict"]
    if mr_conflict:
        score -= 10; disagree.append("mean reversion (overextended)")

    vp_loc = vp_read.get("location")
    vp_weight = 0.5 if vp_read.get("approx") else 1.0
    if vp_loc in ("below_va", "at_poc") and direction == "long":
        score += 5 * vp_weight; agree.append("volume profile (fair value)")
    elif vp_loc in ("above_va", "at_poc") and direction == "short":
        score += 5 * vp_weight; agree.append("volume profile (fair value)")
    elif vp_loc == "above_va" and direction == "long":
        score -= 3 * vp_weight; disagree.append("volume profile (buying above value)")
    elif vp_loc == "below_va" and direction == "short":
        score -= 3 * vp_weight; disagree.append("volume profile (selling below value)")

    wy_pts = 0
    if wy_read["event"]:
        wy_pts += 8; agree.append(f"Wyckoff ({wy_read['event']['event']})")
    if wy_read["sos_sow"]:
        wy_pts += 4; agree.append(f"Wyckoff ({wy_read['sos_sow']})")
    if wy_read["absorption"] and not wy_read["event"]:
        wy_pts -= 5; disagree.append("Wyckoff (absorption / composite-operator warning)")
    score += max(-5, min(10, wy_pts))

    if macro["aligned"] is True:
        score += 6; agree.append("macro (USD)")
    elif macro["aligned"] is False:
        score -= 6; disagree.append("macro (USD headwind)")

    news_delta, news_why = ba.adjustment(symbol, direction)
    score += news_delta
    if news_delta > 0:
        agree.append("news")
    elif news_delta < 0:
        disagree.append("news")

    if in_kz:
        score += 4; agree.append("session/kill-zone timing")

    if reg.get("vol") == "expansion":
        score += 3
    elif reg.get("vol") == "normal":
        score += 2

    # ---- the four additional confirmation sources (all soft, modest weight) --
    # Bug fix (2026-07-28): these three used to call .alignment(direction)
    # with no symbol, which every one of them defaults to WTIUSD — so gold
    # and Bitcoin signals were silently being scored against OIL's COT
    # positioning, oil's Brent-WTI/crack spreads, and oil's seasonality
    # table, just mislabeled with generic chip names. risk_sentiment below
    # was already passing symbol correctly; these three were not.
    cot_align = cot.alignment(direction, symbol=symbol)
    if cot_align["supports"] is True:
        score += 5; agree.append("COT positioning")
    elif cot_align["supports"] is False:
        score -= 5; disagree.append("COT positioning")

    spread_align = sp.alignment(direction, symbol=symbol)
    if spread_align["supports"] is True:
        score += 4; agree.append(sp.label(symbol))
    elif spread_align["supports"] is False:
        score -= 4; disagree.append(sp.label(symbol))

    season_align = sea.alignment(direction, symbol=symbol)
    if season_align["supports"] is True:
        score += 3; agree.append("seasonality")
    elif season_align["supports"] is False:
        score -= 2; disagree.append("seasonality")

    risk_align = rs.alignment(direction, symbol=symbol)
    if risk_align["supports"] is True:
        score += 4; agree.append("cross-asset risk sentiment")
    elif risk_align["supports"] is False:
        score -= 4; disagree.append("cross-asset risk sentiment")

    # ---- two newer confirmation sources: RSI divergence + pivot levels ----
    div_align = md.alignment(df15, direction)
    if div_align["supports"] is True:
        score += 5; agree.append("RSI divergence")
    elif div_align["supports"] is False:
        score -= 6; disagree.append("RSI divergence (active divergence warns against this)")

    pivot_align = pv.alignment(df15, direction, sig.entry, atr_val)
    if pivot_align["supports"] is True:
        score += 4; agree.append("pivot level confluence")
    elif pivot_align["supports"] is False:
        score -= 3; disagree.append("pivot level confluence")

    candle_align = cs.alignment(df15, direction)
    if candle_align["supports"] is True:
        score += 4; agree.append("candlestick pattern")
    elif candle_align["supports"] is False:
        score -= 4; disagree.append("candlestick pattern (opposing pattern just printed)")

    breaker_align = bb.alignment(df15, direction, sig.entry, atr_val)
    if breaker_align["supports"] is True:
        score += 5; agree.append("breaker/mitigation block")
    elif breaker_align["supports"] is False:
        score -= 4; disagree.append("breaker/mitigation block (zone works against this)")

    fib_align = fib.alignment(swing_hi, swing_lo, direction, sig.entry, sig.target, atr_val)
    if fib_align["supports"] is True:
        score += 4; agree.append("Fibonacci confluence")

    chart_align = chp.alignment(df15, direction)
    if chart_align["supports"] is True:
        score += 5; agree.append("chart pattern")
    elif chart_align["supports"] is False:
        score -= 4; disagree.append("chart pattern (opposing formation just confirmed)")

    liq_str_align = ls.alignment(df15, direction, sig.entry)
    if liq_str_align["supports"] is True:
        score += 4; agree.append("liquidity strength (weak level ahead)")
    elif liq_str_align["supports"] is False:
        score -= 3; disagree.append("liquidity strength (strong level may hold)")

    bpr_align = bpr.alignment(df15, direction, sig.entry, atr_val)
    if bpr_align["supports"] is True:
        score += 3; agree.append("balanced price range / consequent encroachment")

    abc_align = fib.alignment_abc(df15, direction, sig.entry, atr_val)
    if abc_align["supports"] is True:
        score += 3; agree.append("Fibonacci ABC expansion")

    session_align = sm.alignment(df15, direction)
    if session_align["supports"] is True:
        score += 4; agree.append("session model (Judas Swing -> NY continuation)")
    elif session_align["supports"] is False:
        score -= 4; disagree.append("session model (Judas Swing implies the opposite direction)")

    ew_align = ew.alignment(df15, direction)
    if ew_align["supports"] is True:
        score += 3; agree.append("Elliott Wave (rule-valid impulse -> expected correction)")
    elif ew_align["supports"] is False:
        score -= 3; disagree.append("Elliott Wave (rule-valid impulse expects the opposite direction)")

    icc_align = icc_mod.alignment(df15, direction)
    if icc_align["supports"] is True:
        score += 3; agree.append("ICC (indication/correction/continuation)")
    elif icc_align["supports"] is False:
        score -= 3; disagree.append("ICC (continuation confirmed the opposite direction)")

    score = max(0, min(100, round(score)))

    # ---- validation checklist (spec order) -----------------------------
    checklist = [
        ("Higher timeframe trend", tq_read["htf_agrees"], tq_read["lines"][0]),
        ("Market structure", True, "Layer 1 structure trend already confirmed direction"),
        ("Liquidity objective", sig.target is not None, f"target {sig.target}"),
        ("Institutional order flow", True, "structure-trend gate passed in Layer 1"),
        ("Order Block quality", "order block" in " ".join(sig.reasons).lower()
         or wy_read["event"] is not None, "OB/ sweep confluence"),
        ("Fair Value Gap validity", True, "entry FVG required by Layer 1"),
        ("Price Action confirmation", pa_read["agrees"] is not False, pa_read["lines"]),
        ("Trend confirmation", tq_read["htf_agrees"], tq_read["lines"][0]),
        ("Volume Profile agreement", vp_loc not in ("unknown",), vp_read["lines"]),
        ("Wyckoff agreement", bool(wy_read["event"] or wy_read["sos_sow"]), wy_read["lines"]),
        ("Breakout confirmation", bo_read["break_verdict"] != "false", bo_read["lines"]),
        ("Mean Reversion context", not mr_conflict, mr_read["lines"]),
        ("Macroeconomic alignment", macro["aligned"] is not False, macro["note"]),
        ("News risk acceptable", news_delta > NEWS_HARD_BLOCK_PTS, news_why),
        ("Minimum Risk:Reward met", sig.rr >= signals.MIN_RR, f"RR {sig.rr}"),
        ("COT positioning", cot_align["supports"] is not False, cot_align["note"]),
        ("Brent-WTI/crack spreads", spread_align["supports"] is not False, spread_align["note"]),
        ("Seasonality", season_align["supports"] is not False, season_align["note"]),
        ("Cross-asset risk sentiment", risk_align["supports"] is not False, risk_align["note"]),
        ("RSI divergence", div_align["supports"] is not False, div_align["note"]),
        ("Pivot level confluence", pivot_align["supports"] is not False, pivot_align["note"]),
        ("Candlestick pattern", candle_align["supports"] is not False, candle_align["note"]),
        ("Breaker/mitigation block", breaker_align["supports"] is not False, breaker_align["note"]),
        ("Fibonacci confluence", True, fib_align["note"]),
        ("Chart pattern", chart_align["supports"] is not False, chart_align["note"]),
        ("Liquidity strength", liq_str_align["supports"] is not False, liq_str_align["note"]),
        ("BPR / consequent encroachment", True, bpr_align["note"]),
        ("Fibonacci ABC expansion", True, abc_align["note"]),
        ("Session model (AMD/Judas Swing)", session_align["supports"] is not False, session_align["note"]),
        ("Elliott Wave", ew_align["supports"] is not False, ew_align["note"]),
        ("ICC (Indication/Correction/Continuation)", icc_align["supports"] is not False, icc_align["note"]),
    ]

    hard_gate_names = {"Breakout confirmation", "Mean Reversion context",
                       "News risk acceptable", "Minimum Risk:Reward met",
                       "Liquidity objective"}
    hard_fail = [name for name, passed, _ in checklist
                if name in hard_gate_names and not passed]

    final_tier = sig.tier
    if hard_fail:
        final_tier = "rejected"
        reasoning.append("REJECTED — hard gate(s) failed: " + ", ".join(hard_fail))
    elif sig.tier == "confirmed" and score < min_score:
        final_tier = "watch"
        reasoning.append(f"downgraded confirmed->watch: confluence {score} < {min_score}")

    reasoning.append(f"final confluence score {score}/100 "
                     f"({len(agree)} confirmations agree, {len(disagree)} disagree)")

    return ConfluenceRead(
        symbol=symbol, direction=direction, base_tier=sig.tier,
        final_tier=final_tier, score=score, checklist=checklist,
        agree=agree, disagree=disagree, reasoning=reasoning,
        layers={"price_action": pa_read, "trend": tq_read, "breakout": bo_read,
                "mean_reversion": mr_read, "wyckoff": wy_read,
                "volume_profile": vp_read, "regime": reg, "macro": macro,
                "news": news, "cot": cot_align, "spreads": spread_align,
                "seasonality": season_align, "risk_sentiment": risk_align,
                "momentum_divergence": div_align, "pivots": pivot_align,
                "candlestick": candle_align, "breaker_mitigation": breaker_align,
                "fibonacci": fib_align, "chart_pattern": chart_align,
                "liquidity_strength": liq_str_align, "bpr_ce": bpr_align,
                "fibonacci_abc": abc_align, "session_model": session_align,
                "elliott_wave": ew_align, "icc": icc_align},
        sig=sig,
    )
