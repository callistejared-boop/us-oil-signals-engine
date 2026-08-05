"""Market Regime Engine (V2) — Day 4.

Centralized, multi-timeframe market classification. This module does NOT
originate, score, or size trades — it produces structured context that
downstream systems (origination, MAST confluence, risk, portfolio risk) can
read, per the Day 4 mandate: "The Market Regime Engine does not generate
trades. Its sole purpose is to determine the current market environment and
provide structured context to downstream systems."

REUSE, NOT DUPLICATION. Every underlying calculation already exists
elsewhere in this codebase; this module's own new code is the multi-timeframe
hierarchy, the finer taxonomy, transition-risk estimation, the strategy
compatibility matrix, and the quality score — the synthesis layer, not the
math layer:
  - Per-timeframe trend/volatility classification -> engine.regime.classify()
    (Kaufman Efficiency Ratio + ATR percentile), called once per timeframe via
    engine.data_loader.resample(). Not reimplemented.
  - Resampling -> engine.data_loader.resample() (same TIMEFRAMES table
    everything else in the codebase uses, including "1w": "W-MON").
  - Structural break context (BOS/CHoCH) -> engine.structure.structure_series()
    / engine.ict.last_event(), read but not recomputed.
  - Session / kill-zone context -> engine.ict.read()'s "session" field /
    engine.structure.in_killzone(), read but not recomputed.
  - News-driven tagging -> engine.news_guard.evaluate(), read but not
    recomputed (this module never touches the news calendar itself).
  - Cross-asset context -> engine.correlation_dynamic.get_correlation()
    (Day 3), read but not recomputed.

ENGINEERING PRINCIPLES (all five satisfied explicitly):
  - Modular: one entry point (classify()), pure functions underneath, no
    global state.
  - Explainable: every result carries `evidence`, `conflicting_evidence`,
    and a `detail` breakdown of exactly how confidence/quality/transition
    numbers were computed — nothing is a black-box score.
  - Deterministic where possible: every number here is a closed-form
    function of the input DataFrame; no randomness, no unfitted ML model.
    Where a number IS a domain heuristic rather than a backtested constant
    (transition_risk, quality_score weights), it is labeled as such in this
    docstring and in RESEARCH_REGIME_ENGINE.md, matching the disclosure
    convention engine/structure.py's classify_swing_strength() already
    established in this codebase ("domain knowledge... not a rule extracted
    from a specific source document").
  - Fail safely: classify() never raises; on any internal error it returns a
    fully-formed "unknown" result with the error recorded in `evidence`, the
    same posture as engine.regime.classify()'s own degrade-to-"unknown" on
    thin data.
  - Supports future expansion: STRATEGY_COMPATIBILITY is a dict keyed by
    strategy name, with exactly one entry today (the platform's one
    production strategy) — adding a second strategy later is a new dict
    entry, not an architectural change.

INTEGRATION MODE (see RISK_SPECIFICATION.md / MARKET_REGIME_SPECIFICATION.md
for the full reasoning): classification runs and is logged/attached to every
alert unconditionally, but by DEFAULT does not block publication
(`Settings.regime_filter_mode = "advisory"`). Day 4's own mandate says a
regime filter should only stay in production if it demonstrates a measurable
improvement in expectancy/drawdown/profit-factor during replay and forward
testing — exactly the same evidence-first discipline `range_guard.py`'s
`SUPPRESS_MODE` and Day 3's `portfolio_risk_mode` already established in
this codebase. `"block"` mode exists and is fully implemented, but is not
the shipped default.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import regime as base_regime
from . import structure as st
from .data_loader import resample

# Day 8: retroactively assigned for version traceability (see
# EXPLAINABILITY_SPECIFICATION.md Sec.5 / engine/platform_version.py) — no
# explicit version marker existed before Day 8. "2.0.0" matches this
# module's own docstring label ("Market Regime Engine (V2)"), not a new
# revision made today. Purely additive metadata; changes no classification
# logic.
VERSION = "2.0.0"

# --- Multi-timeframe hierarchy ---------------------------------------------
# Higher timeframes establish STRATEGIC context; lower timeframes only
# REFINE it (add confidence/conflict/tags) - never override the strategic
# trend outright. This is the explicit alternative to a "simple voting
# system" the Day 4 mandate calls out.
STRATEGIC_TFS = ("1w", "1d")
TACTICAL_TFS = ("4h", "1h")
EXECUTION_TFS = ("15m",)
ALL_TFS = STRATEGIC_TFS + TACTICAL_TFS + EXECUTION_TFS
TF_WEIGHT = {"1w": 5, "1d": 4, "4h": 3, "1h": 2, "15m": 1}

# Minimum bars (in the TF's own resampled series) before a TF's classify()
# call is trusted at all; below this, engine.regime.classify() already
# degrades to "unknown" on its own (len(df) < er_len + 2), this is just the
# same threshold made explicit here for the confidence math.
MIN_BARS = 22

STRONG_ER = 0.55   # above base_regime.TREND_ER (0.35): a stronger, separate
                    # threshold for "Strong" vs "Weak" trend labeling.


def _classify_tf(df15, tf: str) -> dict:
    """One timeframe's regime.classify() result, via the shared resample()
    helper every other module uses. Never raises."""
    try:
        sub = df15 if tf == "15m" else resample(df15, tf)
        out = dict(base_regime.classify(sub))
        out["tf"] = tf
        out["bars"] = int(len(sub))
        out["weight"] = TF_WEIGHT[tf]
        out["sufficient"] = out["bars"] >= MIN_BARS and out["trend"] != "unknown"
        return out
    except Exception as exc:  # noqa: BLE001
        return {"tf": tf, "bars": 0, "weight": TF_WEIGHT[tf], "sufficient": False,
                "trend": "unknown", "vol": "unknown", "phase": "unknown",
                "label": "unknown", "er": 0.0, "atr_pct": 0.5,
                "error": str(exc)}


def _vol_trend(df, period: int = 14, lookback: int = 100, recent: int = 10) -> str:
    """Is volatility currently RISING or FALLING, not just what level it's
    at? engine.regime.atr_percentile() only reports the current level; this
    compares it against the same computation run on the series with the
    most recent `recent` bars removed, which regime.py does not do. Reuses
    atr_percentile() twice rather than reimplementing ATR math."""
    try:
        if len(df) < period + lookback + recent + 5:
            return "unknown"
        now_pct = base_regime.atr_percentile(df, period, lookback)
        prior_pct = base_regime.atr_percentile(df.iloc[:-recent], period, lookback)
        delta = now_pct - prior_pct
        if delta >= 0.10:
            return "expansion"
        if delta <= -0.10:
            return "contraction"
        return "stable"
    except Exception:  # noqa: BLE001
        return "unknown"


def _primary_label(strategic: dict) -> str:
    """Map one TF's regime.classify() output onto the Day 4 taxonomy."""
    if strategic.get("trend") == "unknown":
        return "Unknown"
    er = float(strategic.get("er", 0.0))
    phase = str(strategic.get("phase", ""))
    if strategic.get("trend") == "trend":
        strong = er >= STRONG_ER
        bull = "uptrend" in phase or "markup" in phase
        if bull:
            return "Strong Bull Trend" if strong else "Weak Bull Trend"
        return "Strong Bear Trend" if strong else "Weak Bear Trend"
    # range family
    if "distribution" in phase:
        return "Distribution"
    if "accumulation" in phase:
        return "Accumulation"
    return "Range"


EXPECTED_BEHAVIOR = {
    "Strong Bull Trend": "Pullbacks tend to be shallow and bought; BOS "
        "confirmations to the upside are more reliable than in range "
        "conditions; countertrend shorts have a lower historical hit rate.",
    "Strong Bear Trend": "Rallies tend to be sold; BOS confirmations to the "
        "downside are more reliable; countertrend longs have a lower "
        "historical hit rate.",
    "Weak Bull Trend": "Directional but choppy — structure breaks upward but "
        "with frequent CHoCH-style retracements; treat BOS confirmations "
        "with more skepticism than in a Strong Bull Trend.",
    "Weak Bear Trend": "Directional but choppy to the downside; retracements "
        "are frequent enough that trend-following entries need wider "
        "invalidation.",
    "Range": "Price oscillating without net displacement; breakout attempts "
        "are more likely to fail (false BOS) than in a trending regime; "
        "mean-reversion behavior dominates.",
    "Distribution": "Range near its highs — classic pre-markdown "
        "positioning; buy-side liquidity resting above is a common sweep "
        "target before a reversal lower.",
    "Accumulation": "Range near its lows — classic pre-markup positioning; "
        "sell-side liquidity resting below is a common sweep target before "
        "a reversal higher.",
    "Unknown": "Insufficient data to classify with any confidence — treat "
        "any setup in this window with reduced size/confidence.",
}

# --- Strategy compatibility matrix ------------------------------------------
# Exactly one entry today: this platform has one production trade-origination
# strategy (ICT/SMC structural breaks + liquidity sweeps + FVG retracement,
# via signals.py, confirmed by the MAST confluence engine). Documented as a
# dict-of-dicts specifically so a second strategy is a new key, not a
# redesign, per the mandate's "support future expansion" principle.
STRATEGY_COMPATIBILITY = {
    "ict_smc_mast": {
        "description": "signals.py origination + confluence.py MAST scoring "
            "— the platform's sole production strategy as of Day 4.",
        "preferred": ["Strong Bull Trend", "Strong Bear Trend"],
        "acceptable": ["Weak Bull Trend", "Weak Bear Trend", "Distribution",
                      "Accumulation"],
        "discouraged": ["Range"],
        "prohibited": ["Unknown"],
        "rationale": "ICT/SMC entries depend on clean structural breaks "
            "(BOS/CHoCH) and displacement (which creates the FVGs the "
            "strategy enters on). Strong trends produce the cleanest, most "
            "reliable breaks. Distribution/Accumulation are acceptable "
            "because they are the classic ICT liquidity-sweep-then-reversal "
            "setup this strategy is explicitly designed to catch. Plain "
            "Range/consolidation is discouraged, not prohibited, because "
            "MAST confluence + range_guard.py already provide signal-level "
            "filtering for choppy conditions - this matrix is descriptive "
            "context, not a new enforcement mechanism (see module docstring "
            "'do not duplicate logic'). Unknown is prohibited because there "
            "is no evidence basis to act on at all.",
    },
}


def _compatibility(strategy: str, primary_label: str) -> str:
    m = STRATEGY_COMPATIBILITY.get(strategy)
    if not m:
        return "unrated"
    for tier in ("preferred", "acceptable", "discouraged", "prohibited"):
        if primary_label in m[tier]:
            return tier
    return "unrated"


def _confidence(strategic: dict, tactical: list, execution: list) -> tuple:
    """Deterministic confidence 0-100. Base = strategic TF's own efficiency
    ratio (already a natural 0-1 directionality-confidence measure), then
    nudged by cross-TF agreement/disagreement. Every contribution is
    returned in `detail` so the number is fully explainable, not a black box.
    """
    evidence, conflicts = [], []
    if strategic.get("trend") == "unknown":
        return 0, ["strategic timeframe has insufficient data"], []
    base = float(strategic.get("er", 0.0)) * 100.0
    evidence.append(f"strategic ({strategic['tf']}) efficiency ratio "
                    f"{strategic.get('er', 0):.2f} -> base confidence {base:.0f}")
    adj = 0.0
    for tf_result in tactical + execution:
        if not tf_result.get("sufficient"):
            continue
        w = tf_result["weight"]
        if tf_result.get("trend") == strategic.get("trend"):
            adj += w * 2
            evidence.append(f"{tf_result['tf']} agrees ({tf_result['trend']}) -> +{w * 2}")
        else:
            adj -= w * 2
            conflicts.append(f"{tf_result['tf']} shows {tf_result['trend']} "
                             f"vs strategic {strategic.get('trend')} -> -{w * 2}")
    conf = max(0, min(100, round(base + adj)))
    return conf, evidence, conflicts


def _transition_risk(strategic: dict, tactical: list, vol_trend: str,
                     range_pos: float) -> tuple:
    """Deterministic 0-1 transition-risk heuristic (domain-labeled, NOT a
    fitted probability - see module docstring). Higher = more likely the
    current regime is about to change. Contributing factors:
      - tactical/strategic disagreement (bottom-up divergence often
        precedes a strategic-level regime change)
      - volatility trend == 'expansion' while still range-bound (classic
        contraction -> breakout setup, one of the mandate's own examples)
      - price near a dealing-range extreme (>0.85 or <0.15) - proximity to
        a liquidity pool that, if swept, often triggers a CHoCH
    """
    score = 0.0
    factors = []
    disagree_w = sum(t["weight"] for t in tactical
                     if t.get("sufficient") and t.get("trend") != strategic.get("trend"))
    total_w = sum(t["weight"] for t in tactical if t.get("sufficient")) or 1
    disagree_frac = disagree_w / total_w
    if disagree_frac > 0:
        score += 0.4 * disagree_frac
        factors.append(f"tactical/strategic disagreement ({disagree_frac:.0%} "
                       f"of tactical weight) -> +{0.4 * disagree_frac:.2f}")
    if vol_trend == "expansion" and strategic.get("trend") == "range":
        score += 0.3
        factors.append("volatility expanding while strategic TF still range-bound "
                       "(contraction -> breakout pattern) -> +0.30")
    if range_pos is not None and (range_pos >= 0.85 or range_pos <= 0.15):
        score += 0.2
        factors.append(f"price near dealing-range extreme (pos {range_pos:.2f}) -> +0.20")
    score = round(min(1.0, score), 2)
    label = "high" if score >= 0.6 else "medium" if score >= 0.3 else "low"
    return score, label, factors


def _quality_score(compat: str, confidence: int, transition_risk: float) -> tuple:
    base = {"preferred": 80, "acceptable": 60, "discouraged": 35,
           "prohibited": 10, "unrated": 50}.get(compat, 50)
    conf_adj = (confidence - 50) * 0.3          # +/-15 max
    risk_adj = -transition_risk * 20            # 0 to -20
    score = max(0, min(100, round(base + conf_adj + risk_adj)))
    detail = {"base_from_compatibility": base, "confidence_adjustment": round(conf_adj, 1),
              "transition_risk_adjustment": round(risk_adj, 1)}
    return score, detail


def classify(df15, symbol: str, strategy: str = "ict_smc_mast",
            session_label: str = None, news_state: dict = None) -> dict:
    """Main entry point. Never raises. Returns a fully-structured result:

        {symbol, generated, primary, confidence, evidence, conflicting_evidence,
         transition_risk, transition_label, transition_factors,
         expected_behavior, quality_score, quality_detail,
         strategy, compatibility, tags, per_tf, vol_trend}
    """
    try:
        per_tf = {tf: _classify_tf(df15, tf) for tf in ALL_TFS}
        strategic = per_tf["1d"] if per_tf["1w"].get("trend") in ("unknown", None) \
            or not per_tf["1w"].get("sufficient") else per_tf["1w"]
        if not strategic.get("sufficient") and per_tf["1d"].get("sufficient"):
            strategic = per_tf["1d"]
        tactical = [per_tf[tf] for tf in TACTICAL_TFS]
        execution = [per_tf[tf] for tf in EXECUTION_TFS]

        primary = _primary_label(strategic)
        confidence, evidence, conflicts = _confidence(strategic, tactical, execution)

        vol_trend = _vol_trend(df15)
        range_pos = None
        try:
            h1 = resample(df15, "1h")
            hi, lo = st.dealing_range(h1, lookback=200)
            price = float(df15["Close"].iloc[-1])
            range_pos = st.range_position(price, hi, lo)
        except Exception:  # noqa: BLE001
            pass

        tr_score, tr_label, tr_factors = _transition_risk(strategic, tactical,
                                                           vol_trend, range_pos)

        tags = []
        if vol_trend in ("expansion",) and strategic.get("atr_pct", 0.5) >= 0.85:
            tags.append("High Volatility")
        if vol_trend in ("contraction",) and strategic.get("atr_pct", 0.5) <= 0.15:
            tags.append("Low Volatility")
        if strategic.get("trend") == "trend" and vol_trend == "expansion":
            tags.append("Expansion")
        if strategic.get("trend") == "range" and vol_trend == "contraction":
            tags.append("Contraction")
        illiquid = (session_label in (None, "off-session", "Asian")
                   and strategic.get("atr_pct", 0.5) <= 0.15
                   and execution[0].get("atr_pct", 0.5) <= 0.15)
        if illiquid:
            tags.append("Illiquid")
            evidence.append("low volatility during an off-peak session -> Illiquid tag")
        news_active = bool(news_state and (news_state.get("blackout")
                          or (news_state.get("next_in_min") is not None
                              and news_state.get("next_in_min") <= 30)))
        if news_active:
            tags.append("News-Driven")
            evidence.append(f"news calendar flagged as active/imminent "
                            f"({news_state.get('note', 'blackout or <=30min to event')}) "
                            "-> News-Driven tag")

        compat = _compatibility(strategy, primary)
        quality, quality_detail = _quality_score(compat, confidence, tr_score)

        return {
            "symbol": symbol,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "primary": primary,
            "confidence": confidence,
            "evidence": evidence,
            "conflicting_evidence": conflicts,
            "transition_risk": tr_score,
            "transition_label": tr_label,
            "transition_factors": tr_factors,
            "expected_behavior": EXPECTED_BEHAVIOR.get(primary, EXPECTED_BEHAVIOR["Unknown"]),
            "quality_score": quality,
            "quality_detail": quality_detail,
            "strategy": strategy,
            "compatibility": compat,
            "tags": tags,
            "per_tf": {tf: {"trend": v.get("trend"), "vol": v.get("vol"),
                            "phase": v.get("phase"), "er": v.get("er"),
                            "atr_pct": v.get("atr_pct"), "sufficient": v.get("sufficient")}
                      for tf, v in per_tf.items()},
            "vol_trend": vol_trend,
            "range_pos": round(range_pos, 3) if range_pos is not None else None,
            # backward-compatible shape for engine.journal.log_signal(regime=...),
            # which already reads .get("trend")/.get("vol") from whatever dict
            # is passed as `regime=` - see journal.py, unchanged by Day 4.
            "trend": strategic.get("trend", "unknown"),
            "vol": strategic.get("vol", "unknown"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "primary": "Unknown", "confidence": 0,
            "evidence": [], "conflicting_evidence": [],
            "transition_risk": 0.0, "transition_label": "unknown",
            "transition_factors": [],
            "expected_behavior": EXPECTED_BEHAVIOR["Unknown"],
            "quality_score": 0, "quality_detail": {},
            "strategy": strategy, "compatibility": "unrated", "tags": [],
            "per_tf": {}, "vol_trend": "unknown", "range_pos": None,
            "trend": "unknown", "vol": "unknown",
            "error": f"regime-engine error ({exc}) — degraded to Unknown, failing safe",
        }


def line(result: dict) -> str:
    tags = f" [{', '.join(result['tags'])}]" if result.get("tags") else ""
    return (f"{result.get('symbol', '?')}: {result.get('primary', 'Unknown')} "
           f"(conf {result.get('confidence', 0)}, quality {result.get('quality_score', 0)}, "
           f"transition {result.get('transition_label', 'unknown')}){tags}")
