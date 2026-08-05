"""Adaptive Confluence Analysis Layer — Day 5.

This module does NOT change how engine/confluence.py scores a trade. MAST's
27-source weighted score, its hard gates, and its checklist are untouched —
per the Day 5 mandate, "the goal is not to replace MAST." This module reads
a `ConfluenceRead` AFTER `confluence.analyze()` has already produced it and
adds four things confluence.py itself doesn't provide:

  1. SOURCE_REGISTRY (Phase 1/2): a documented inventory of all 27 inputs —
     purpose, nominal point weights, informational-independence category,
     and named overlaps — built directly from reading confluence.py's own
     scoring code and every confirmation module's own docstring (see
     CONFLUENCE_SPECIFICATION.md for the full narrative version of this
     table with reasoning).
  2. explain() (Phase 5): a structured, human-readable breakdown of which
     sources helped, which hurt, which were silent, and which two rank
     highest/lowest by impact for one specific trade read.
  3. quality_score() (Phase 6): a score separate from confluence.py's own
     confidence score, that specifically rewards INDEPENDENT agreement
     (down-weighting sources this registry documents as Duplicate/Derived
     of something already counted) over raw confirmation count.
  4. contribution stats + adaptive-weight RECOMMENDATIONS (Phase 3/4/9):
     functions that measure each source's real historical contribution
     from closed, confluence-tagged trades — and recommend (never apply)
     weight changes once there is enough data to trust the measurement.

IMPORTANT — reconstructed, not authoritative, point values: `ConfluenceRead`
(confluence.py) stores each source's NAME in `agree`/`disagree` when it
contributes, but not its exact point value (several sources have
conditional sub-weights — trend quality's three-way split, Wyckoff's
capped sum, volume profile's approx-data discount — and confluence.py adds
straight to `score` inline rather than storing a per-source ledger). Rather
than modify confluence.py to expose exact deltas (out of scope — "reuse as
much existing code as possible," not restructure it), this module
reconstructs an approximate point value for each named source from
SOURCE_REGISTRY's documented NOMINAL weight (the value used in the most
common case, taken directly from confluence.py's source). This is
sufficient for explainability/education (Phase 5) and quality scoring
(Phase 6), which need relative ranking and category weighting, not
bit-exact backtestable point accounting. Every function that uses this
says so in its own docstring; `RESEARCH_CONFLUENCE_ENGINE.md` documents the
known-imprecise sources by name.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Phase 1/2: Source inventory --------------------------------------------
# category values (five-tier, per the Day 5 mandate):
#   "primary"   - Primary Evidence:   genuinely independent data/mechanism,
#                 not derived from Layer 1 or any other confluence source.
#   "supporting"- Supporting Evidence: different mechanism/data than Layer 1,
#                 but measures a correlated underlying phenomenon.
#   "derived"   - Derived Evidence:   built substantially from Layer 1's own
#                 primitives (structure.py/ict_confluence.py), repackaged
#                 with real but partial incremental value.
#   "duplicate" - Duplicate Evidence: scores the literal same underlying
#                 computation/boolean something else already scored.
#   "legacy"    - Legacy Evidence:    present for completeness; documented,
#                 weak provenance and/or the smallest incremental value
#                 among a cluster of siblings measuring the same thing.
#
# `nominal_pos`/`nominal_neg`: the point value confluence.py's source code
# uses in its most common branch (see module docstring on reconstruction).
# `shares_with`: other SOURCE_REGISTRY keys this source's underlying
# mechanism/data measurably overlaps with (informs quality_score's
# independence discount and CONFLUENCE_SPECIFICATION.md's dependency map).
# `note`: the specific, code-grounded reasoning for the category assigned.

SOURCE_REGISTRY = {
    "layer1_ict": {
        "label": "Layer 1 ICT/SMC confidence (45% weight)",
        "category": "primary",   # the anchor everything else is measured against - not itself an echo
        "nominal_pos": 42.75, "nominal_neg": 0,   # sig.confidence(<=95) * 0.45
        "shares_with": [],
        "note": "The origination read itself (signals.py). Not a confirmation "
                "source in the five-tier sense - it IS Layer 1. Flagged "
                "separately because every 'echo' finding below is measured "
                "against this anchor.",
    },
    "price_action": {
        "label": "price action", "category": "primary",
        "nominal_pos": 8, "nominal_neg": -5, "shares_with": ["candlestick"],
        "note": "Pin bar / engulfing / inside-outside bar geometry - a "
                "mechanism (candle body/wick ratios) nothing in Layer 1 or "
                "elsewhere in MAST computes. Overlaps candlestick_patterns.py "
                "(sibling redundancy, not a Layer-1 echo - both read candle "
                "shape, see 'candlestick' entry).",
    },
    "trend": {
        "label": "trend (HTF stack + ADX)", "category": "derived",
        "nominal_pos": 10, "nominal_neg": -6, "shares_with": ["layer1_ict"],
        "note": "EMA(20/50/100/200) stack + ADX on the 4H timeframe. Layer 1's "
                "own bias score (signals.structure_trend) ALSO falls back to "
                "an EMA(21/55) slope read when structure is range-bound, on "
                "overlapping timeframes. Genuinely new piece: ADX/MACD "
                "maturity. Core EMA-direction signal is substantially "
                "correlated with Layer 1's own bias input.",
    },
    "breakout": {
        "label": "breakout quality", "category": "supporting",
        "nominal_pos": 6, "nominal_neg": -6, "shares_with": ["layer1_ict"],
        "note": "Compression + session/day/week high-low break quality - a "
                "different specific level set than Layer 1's swing-fractal "
                "levels, but the same underlying question ('was a level "
                "broken with real follow-through?') Layer 1's sweep/OTE "
                "logic also answers. Correlated phenomenon, distinct levels.",
    },
    "mean_reversion": {
        "label": "mean reversion (overextended)", "category": "primary",
        "nominal_pos": 0, "nominal_neg": -10, "shares_with": [],
        "note": "RSI/Bollinger/VWAP/Stochastic extension - a genuinely new "
                "oscillator-based axis, not used anywhere in Layer 1. "
                "One-sided by design (penalty-only, documented as "
                "deliberately defensive in its own module docstring).",
    },
    "wyckoff": {
        "label": "Wyckoff", "category": "duplicate",
        "nominal_pos": 8, "nominal_neg": -5, "shares_with": ["layer1_ict"],
        "note": "Its own module docstring: 'mostly a translation + "
                "confirmation layer rather than new detection logic.' Spring/"
                "Upthrust are computed by calling the EXACT SAME "
                "ict_confluence.liquidity_sweep() function Layer 1 already "
                "used for its own +12 sweep bonus. The dominant scoring "
                "component (the 'event' field) is a near-direct echo.",
    },
    "volume_profile": {
        "label": "volume profile (fair value)", "category": "primary",
        "nominal_pos": 5, "nominal_neg": -3, "shares_with": [],
        "note": "POC/Value Area from volume-weighted price bins - genuinely "
                "different data axis. Its own module flags CFD tick-volume "
                "as an approximation (data-quality caveat, not an "
                "independence one) via the `approx` flag, already reflected "
                "in confluence.py's own vp_weight discount.",
    },
    "macro": {
        "label": "macro (USD)", "category": "primary",
        "nominal_pos": 6, "nominal_neg": -6, "shares_with": [],
        "note": "DXY trend alignment - external market data, orthogonal to "
                "price/structure entirely.",
    },
    "news": {
        "label": "news", "category": "primary",
        "nominal_pos": 6, "nominal_neg": -6, "shares_with": [],
        "note": "Live news feed direction - external data, orthogonal. Exact "
                "point delta is NOT stored on ConfluenceRead (bias_adjust."
                "adjustment()'s return value isn't persisted to `layers`) - "
                "a real architecture gap, flagged in "
                "RESEARCH_CONFLUENCE_ENGINE.md, worked around here via the "
                "nominal HIGH-strength value.",
    },
    "session_timing": {
        "label": "session/kill-zone timing", "category": "duplicate",
        "nominal_pos": 4, "nominal_neg": 0, "shares_with": ["layer1_ict", "session_model"],
        "note": "Calls structure.in_killzone() - the EXACT SAME function "
                "Layer 1 already used for its own +8 kill-zone bonus. This "
                "is the clearest, most literal duplicate in the entire "
                "engine: one boolean, from one function, scored twice under "
                "two names. session_model.py (see below) uses the identical "
                "session-hour boundaries a third time under a third name.",
    },
    "regime_vol": {
        "label": "regime volatility", "category": "supporting",
        "nominal_pos": 3, "nominal_neg": 0, "shares_with": [],
        "note": "ATR-percentile volatility level (engine.regime.classify, "
                "vol field) - measures volatility, not direction, a "
                "genuinely different axis from every directional source "
                "above. Weakly/asymmetrically scored (no penalty for "
                "contraction) - flagged for Phase 3 review, not an "
                "independence problem.",
    },
    "cot": {
        "label": "COT positioning", "category": "primary",
        "nominal_pos": 5, "nominal_neg": -5, "shares_with": [],
        "note": "CFTC weekly futures positioning - external capital-flow "
                "data, orthogonal to price/structure.",
    },
    "spreads": {
        "label": "spread/basis", "category": "primary",
        "nominal_pos": 4, "nominal_neg": -4, "shares_with": [],
        "note": "Brent-WTI / gold-silver ratio / BTC futures basis - "
                "external cross-instrument data, orthogonal.",
    },
    "seasonality": {
        "label": "seasonality", "category": "primary",
        "nominal_pos": 3, "nominal_neg": -2, "shares_with": [],
        "note": "Calendar-driven structural prior - orthogonal to price "
                "action entirely. Its own module is explicit that this is a "
                "documented structural pattern, not a statistically fitted "
                "edge - a Phase 3 validation question, not an independence one.",
    },
    "risk_sentiment": {
        "label": "cross-asset risk sentiment", "category": "primary",
        "nominal_pos": 4, "nominal_neg": -4, "shares_with": [],
        "note": "VIX/SPX regime, asset-specific interpretation - external, "
                "market-wide data, orthogonal to the traded instrument.",
    },
    "momentum_divergence": {
        "label": "RSI divergence", "category": "primary",
        "nominal_pos": 5, "nominal_neg": -6, "shares_with": [],
        "note": "RSI SHAPE (regular divergence at swing pivots), distinct "
                "from mean_reversion's use of RSI LEVEL - its own module "
                "docstring explicitly argues this independence and this "
                "analysis independently confirms the two use different "
                "properties of the same underlying oscillator.",
    },
    "pivots": {
        "label": "pivot level confluence", "category": "supporting",
        "nominal_pos": 4, "nominal_neg": -3, "shares_with": ["layer1_ict"],
        "note": "Floor-trader pivots from prior-period OHLC - a different "
                "level SET than Layer 1's swing/FVG/OTE levels, but the same "
                "'does price react to level X' concept.",
    },
    "candlestick": {
        "label": "candlestick pattern", "category": "supporting",
        "nominal_pos": 4, "nominal_neg": -4, "shares_with": ["price_action"],
        "note": "Broader single/two/three-candle pattern library. "
                "Independent of Layer 1, but overlaps price_action.py (both "
                "read candle geometry) - a sibling redundancy worth "
                "measuring in Phase 3/9, not a Layer-1 echo.",
    },
    "breaker_mitigation": {
        "label": "breaker/mitigation block", "category": "derived",
        "nominal_pos": 5, "nominal_neg": -4, "shares_with": ["layer1_ict"],
        "note": "Its own module docstring: genuinely new information "
                "(tracks what happens to order blocks/FVGs AFTER they fail, "
                "which ict.order_block() never does) built on the same "
                "underlying structure.py primitives Layer 1 also reads.",
    },
    "fibonacci": {
        "label": "Fibonacci confluence", "category": "derived",
        "nominal_pos": 4, "nominal_neg": 0, "shares_with": ["layer1_ict"],
        "note": "Its own module docstring: the ICT OTE zone Layer 1 already "
                "scores IS the 62-79% Fibonacci retracement band 'under a "
                "different name.' The retracement-confluence component "
                "substantially echoes Layer 1's OTE bonus; the extension-"
                "level (target confluence) component is genuinely new. "
                "One-sided scorer (no negative case).",
    },
    "chart_pattern": {
        "label": "chart pattern", "category": "primary",
        "nominal_pos": 5, "nominal_neg": -4, "shares_with": [],
        "note": "Multi-swing geometry (H&S, triangles, etc.) - Layer 1 only "
                "ever reasons about the single most recent swing/FVG; this "
                "is the only source in MAST that names multi-swing shape at "
                "all. Shares the low-level structure.find_swings() utility "
                "but the pattern-recognition layer itself is new information.",
    },
    "liquidity_strength": {
        "label": "liquidity strength", "category": "supporting",
        "nominal_pos": 4, "nominal_neg": -3, "shares_with": [],
        "note": "Strong-vs-weak swing labeling (structure.classify_swing_"
                "strength). Layer 1's own confidence score does NOT call "
                "this function (only ict.py's display-only liquidity() map "
                "does, which isn't part of sig.confidence) - reasonably "
                "independent within the actual scoring pipeline.",
    },
    "bpr_ce": {
        "label": "balanced price range / consequent encroachment",
        "category": "derived",
        "nominal_pos": 3, "nominal_neg": 0, "shares_with": ["layer1_ict"],
        "note": "Two overlapping opposite-kind FVGs - built on the same "
                "structure.find_fvgs() Layer 1 uses for its own single-FVG "
                "entry logic, but checks a specific TWO-FVG overlap "
                "condition Layer 1 never evaluates. One-sided scorer.",
    },
    "fibonacci_abc": {
        "label": "Fibonacci ABC expansion", "category": "primary",
        "nominal_pos": 3, "nominal_neg": 0, "shares_with": ["fibonacci"],
        "note": "Three-point A-B-C zigzag projection - distinct math from "
                "the two-point extension in the 'fibonacci' entry above, "
                "per that module's own explicit distinction. One-sided scorer.",
    },
    "session_model": {
        "label": "session model (Judas Swing)", "category": "supporting",
        "nominal_pos": 4, "nominal_neg": -4,
        "shares_with": ["layer1_ict", "session_timing"],
        "note": "Uses the IDENTICAL session-hour convention (Asian/London-KZ/"
                "NY-KZ) as structure.in_killzone - already scored once "
                "inside Layer 1's confidence and a SECOND time by this "
                "engine's own 'session_timing' entry. This is the third "
                "scoring event keyed off the same 6-hour daily window "
                "definition. Its incremental value is the directional Judas-"
                "swing NARRATIVE, not the timing fact itself, which by this "
                "point has already been counted twice under other names.",
    },
    "elliott_wave": {
        "label": "Elliott Wave", "category": "primary",
        "nominal_pos": 3, "nominal_neg": -3, "shares_with": ["icc", "chart_pattern"],
        "note": "3-rule impulse validation (wave2/3/4 relationships) on "
                "swing sequences - a genuinely distinct, falsifiable test "
                "Layer 1 never runs. Shares the swing-finding utility with "
                "icc.py and chart_pattern.py (see icc entry for the sibling-"
                "overlap finding).",
    },
    "icc": {
        "label": "ICC (indication/correction/continuation)", "category": "legacy",
        "nominal_pos": 3, "nominal_neg": -3, "shares_with": ["elliott_wave", "chart_pattern"],
        "note": "A simplified 3-point swing-geometry check - its own module "
                "docstring positions it as 'closer to just wave 1-2-3' of "
                "Elliott Wave's full 5-wave test. Of the three multi-swing-"
                "geometry checkers in MAST (elliott_wave, chart_pattern, "
                "icc), this is the least rigorous and most likely to be "
                "fully subsumed by the other two. Also one of three modules "
                "whose own docstring discloses weak documentary provenance "
                "(the source document was templated boilerplate).",
    },
}

# Cross-cutting Phase-2 finding, not tied to one entry: three modules
# (bpr_ce/balanced_range.py, session_model.py, icc.py) independently
# disclose in their own docstrings that their named provenance document
# ("Smart Money 200-Page Master Guide") turned out to be templated
# boilerplate with no unique operational rule - each was reimplemented from
# general domain knowledge instead. Their mechanism-independence category
# above was assessed on the actual code, not the provenance, but this
# pattern is worth surfacing on its own — see CONFLUENCE_SPECIFICATION.md.
WEAK_PROVENANCE_SOURCES = ["bpr_ce", "session_model", "icc"]

# The session-timing triple-count is the single most concrete, most
# actionable overlap finding in the whole inventory - three independently
# named sources all keyed off the same six-hour daily window.
SESSION_TIMING_TRIPLICATE = ["layer1_ict", "session_timing", "session_model"]


def registry_summary() -> dict:
    """Counts by category — the headline numbers for Phase 1/2 reporting."""
    out = {"primary": 0, "supporting": 0, "derived": 0, "duplicate": 0, "legacy": 0}
    for k, v in SOURCE_REGISTRY.items():
        if k == "layer1_ict":
            continue
        out[v["category"]] += 1
    return out


# --- Label matching: confluence.py's agree/disagree strings -> registry key ---
# confluence.py records the source's LABEL, not a stable key, and several
# labels are dynamic (Wyckoff's event name, spread's per-symbol label). This
# is a prefix/substring match against the exact strings confluence.py's
# source code appends, kept as data (not scattered logic) so it's auditable
# in one place and easy to extend if a source's label text changes.
LABEL_PATTERNS = {
    "price_action": ["price action"],
    "trend": ["trend ("],
    "breakout": ["breakout quality"],
    "mean_reversion": ["mean reversion"],
    "wyckoff": ["Wyckoff"],
    "volume_profile": ["volume profile"],
    "macro": ["macro ("],
    "news": ["news"],
    "session_timing": ["session/kill-zone timing"],
    "cot": ["COT positioning"],
    "spreads": ["Brent-WTI", "gold/silver ratio", "BTC futures basis",
               "cross-instrument spread"],
    "seasonality": ["seasonality"],
    "risk_sentiment": ["cross-asset risk sentiment"],
    "momentum_divergence": ["RSI divergence"],
    "pivots": ["pivot level confluence"],
    "candlestick": ["candlestick pattern"],
    "breaker_mitigation": ["breaker/mitigation block"],
    "fibonacci": ["Fibonacci confluence"],
    "chart_pattern": ["chart pattern"],
    "liquidity_strength": ["liquidity strength"],
    "bpr_ce": ["balanced price range"],
    "fibonacci_abc": ["Fibonacci ABC expansion"],
    "session_model": ["session model"],
    "elliott_wave": ["Elliott Wave"],
    "icc": ["ICC ("],
    # Day 6 observability fix (resolved 2026-08-03): regime_vol used to be
    # deliberately absent from this map — confluence.py added its +3/+2
    # points directly with no agree.append() call at all, making it
    # invisible to cr.agree/cr.disagree (a Phase 5/Day 5 finding, see
    # RESEARCH_CONFLUENCE_ENGINE.md Sec.2.3). confluence.py now labels it
    # ("regime volatility (expansion)" / "(normal)"), so it is matched here
    # like every other source.
    "regime_vol": ["regime volatility ("],
}


def _match_source(label: str):
    for key, patterns in LABEL_PATTERNS.items():
        for p in patterns:
            if p in label:
                return key
    return None


@dataclass
class SourceContribution:
    key: str
    label: str
    direction: str    # "agree" | "disagree"
    points: float      # reconstructed, nominal (see module docstring)
    category: str


def _source_points(cr) -> list:
    """Reconstruct a SourceContribution for every name in cr.agree/cr.disagree,
    using SOURCE_REGISTRY's nominal weights (see module docstring — this is
    an approximation for sources with conditional sub-weights, not a
    bit-exact replay of confluence.py's internal arithmetic). Unmatched
    labels (should not normally occur — see the regression test that checks
    every current confluence.py label matches) are returned with
    key=None, points=0.0 rather than dropped, so nothing is silently lost.

    Day 6 exception: "news" no longer uses a nominal approximation —
    confluence.py now persists the exact computed delta as `cr.news_delta`
    (see RESEARCH_CONFLUENCE_ENGINE.md Sec.2.3, resolved 2026-08-03), so
    this uses that real value whenever the label is present."""
    news_delta = int(getattr(cr, "news_delta", 0) or 0)
    out = []
    for label in getattr(cr, "agree", []) or []:
        key = _match_source(label)
        reg = SOURCE_REGISTRY.get(key)
        pts = float(news_delta) if key == "news" and news_delta else (reg["nominal_pos"] if reg else 0.0)
        out.append(SourceContribution(key, label, "agree", pts,
                                      reg["category"] if reg else "unclassified"))
    for label in getattr(cr, "disagree", []) or []:
        key = _match_source(label)
        reg = SOURCE_REGISTRY.get(key)
        pts = float(news_delta) if key == "news" and news_delta else (reg["nominal_neg"] if reg else 0.0)
        out.append(SourceContribution(key, label, "disagree", pts,
                                      reg["category"] if reg else "unclassified"))
    return out


# --- Phase 5: Explainable Confluence ----------------------------------------

def explain(cr) -> dict:
    """Structured explanation for one ConfluenceRead. Never raises — degrades
    to an empty-but-valid structure on unexpected input, consistent with
    every other fail-safe module in this codebase.

    Returns:
        {positive, negative, neutral, highest_impact, lowest_impact,
         conflicting_evidence, missing_evidence, unlabeled_sources,
         rationale}
    """
    try:
        contribs = _source_points(cr)
        positive = sorted([c for c in contribs if c.direction == "agree"],
                          key=lambda c: -c.points)
        negative = sorted([c for c in contribs if c.direction == "disagree"],
                          key=lambda c: c.points)
        touched = {c.key for c in contribs if c.key}
        neutral = [k for k in SOURCE_REGISTRY if k != "layer1_ict" and k not in touched]

        by_abs = sorted(contribs, key=lambda c: -abs(c.points))
        highest = by_abs[0] if by_abs else None
        lowest = by_abs[-1] if by_abs else None

        # conflicting evidence: sources that share an underlying mechanism
        # (SOURCE_REGISTRY's shares_with) but landed on opposite sides
        agree_keys = {c.key for c in positive if c.key}
        disagree_keys = {c.key for c in negative if c.key}
        conflicts = []
        for key in agree_keys:
            for other in SOURCE_REGISTRY.get(key, {}).get("shares_with", []):
                if other in disagree_keys:
                    conflicts.append(f"{SOURCE_REGISTRY[key]['label']} agrees "
                                     f"while {SOURCE_REGISTRY[other]['label']} "
                                     f"disagrees — both measure related "
                                     f"underlying evidence")

        rationale_bits = [
            f"{len(positive)} source(s) support this trade, {len(negative)} "
            f"oppose it, {len(neutral)} produced no signal either way.",
        ]
        if highest:
            rationale_bits.append(f"Highest-impact evidence: {highest.label} "
                                  f"({highest.direction}, ~{highest.points:+.1f} pts, "
                                  f"category={highest.category}).")
        if conflicts:
            rationale_bits.append(f"{len(conflicts)} conflicting evidence pair(s) "
                                  "detected between sources that share an "
                                  "underlying mechanism.")

        return {
            "positive": [c.__dict__ for c in positive],
            "negative": [c.__dict__ for c in negative],
            "neutral": neutral,
            "highest_impact": highest.__dict__ if highest else None,
            "lowest_impact": lowest.__dict__ if lowest and lowest is not highest else None,
            "conflicting_evidence": conflicts,
            "missing_evidence": neutral,   # alias, mandate uses both terms
            # Day 6 observability fix (resolved 2026-08-03): confluence.py
            # now labels regime_vol's contribution (see confluence.py's
            # "Day 6 observability fix" comment), so it is no longer
            # structurally invisible — kept as an empty list, not removed,
            # so any historical caller checking this key still gets a valid
            # (now-always-empty) result rather than a KeyError.
            "unlabeled_sources": [],
            "rationale": " ".join(rationale_bits),
        }
    except Exception as exc:  # noqa: BLE001
        return {"positive": [], "negative": [], "neutral": [], "highest_impact": None,
                "lowest_impact": None, "conflicting_evidence": [], "missing_evidence": [],
                "unlabeled_sources": [], "rationale": f"explain() error: {exc}"}


# --- Phase 6: Confluence Quality Score --------------------------------------

def quality_score(cr) -> dict:
    """A score SEPARATE from confluence.py's own confidence score
    (cr.score), specifically measuring evidence QUALITY rather than
    quantity: how many genuinely INDEPENDENT sources agree, not how many
    sources agree in total. Duplicate/Derived sources are down-weighted so
    that (for example) Layer 1 + Wyckoff + session_timing all agreeing is
    NOT scored as three independent confirmations — they substantially
    share the same underlying evidence (see SOURCE_REGISTRY).

    Returns {score (0-100), diversity, independent_agreement, conflict_penalty, detail}.
    Never raises."""
    try:
        contribs = _source_points(cr)
        matched = [c for c in contribs if c.key]
        agree = [c for c in matched if c.direction == "agree"]
        disagree = [c for c in matched if c.direction == "disagree"]

        # Diversity: how many distinct CATEGORIES contributed (not sources).
        # Five agreeing "supporting" sources is less diverse evidence than
        # one primary + one supporting + one derived agreeing.
        categories_present = {c.category for c in agree}
        diversity = len(categories_present) / 4.0   # 4 non-primary-anchor categories possible among confirmations
        diversity = min(1.0, diversity)

        # Independent agreement: agreeing sources weighted DOWN if
        # duplicate/derived (they're not adding much beyond what's already
        # counted), weighted fully if primary/supporting.
        indep_weight = {"primary": 1.0, "supporting": 0.8, "derived": 0.4,
                        "duplicate": 0.1, "legacy": 0.3}
        weighted_agree = sum(indep_weight.get(c.category, 0.5) for c in agree)
        raw_agree = len(agree)
        independent_agreement = (weighted_agree / raw_agree) if raw_agree else 0.0

        # Conflict penalty: fraction of touched sources that disagree
        touched_n = len(agree) + len(disagree)
        conflict_penalty = (len(disagree) / touched_n) if touched_n else 0.0

        # Cross-timeframe consistency proxy: reuses confluence.py's own
        # trend_quality read (already computed, not recomputed) rather than
        # inventing a new timeframe check.
        tq = (cr.layers or {}).get("trend", {}) if hasattr(cr, "layers") else {}
        cross_tf_consistent = 1.0 if tq.get("continuation_ok") else \
            0.5 if tq.get("htf_agrees") else 0.0

        score = round(100 * (
            0.35 * diversity +
            0.35 * independent_agreement +
            0.15 * cross_tf_consistent +
            0.15 * (1.0 - conflict_penalty)
        ))
        score = max(0, min(100, score))

        return {
            "score": score,
            "diversity": round(diversity, 3),
            "independent_agreement": round(independent_agreement, 3),
            "conflict_penalty": round(conflict_penalty, 3),
            "cross_tf_consistency": cross_tf_consistent,
            "detail": {
                "categories_present": sorted(categories_present),
                "n_agree": raw_agree, "n_disagree": len(disagree),
                "weighted_agree": round(weighted_agree, 2),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"score": 0, "diversity": 0, "independent_agreement": 0,
                "conflict_penalty": 0, "cross_tf_consistency": 0,
                "detail": {"error": str(exc)}}


# --- Phase 7: Conflict resolution -------------------------------------------
# Named patterns from the Day 5 mandate's own examples, detected from
# already-computed cr.layers data (no new calculations).

def conflict_resolution(cr) -> list:
    """Detect named disagreement patterns the mandate calls out explicitly.
    Returns a list of {pattern, description, recommendation} dicts. Purely
    descriptive/logged — does not change cr.score or final_tier (that would
    be altering MAST itself, out of scope for Day 5). Never raises."""
    out = []
    try:
        layers = cr.layers or {}
        macro = layers.get("macro", {})
        news = layers.get("news", {})
        vp = layers.get("volume_profile", {})

        if cr.score >= 80 and macro.get("aligned") is False:
            out.append({
                "pattern": "strong_ict_weak_macro",
                "description": f"High confluence score ({cr.score}) but macro "
                               f"(USD) context disagrees: {macro.get('note', '')}",
                "recommendation": "Treat as a lower-conviction version of a "
                                  "high-score setup — technical/structural "
                                  "evidence is strong, but a real external "
                                  "headwind exists. Not a hard gate (macro "
                                  "is Primary Evidence but only one of many); "
                                  "surfaced for trader awareness.",
            })

        strong_liq = "liquidity strength" in " ".join(cr.disagree)
        if cr.base_tier == "confirmed" and strong_liq:
            out.append({
                "pattern": "strong_structure_poor_liquidity",
                "description": "Layer 1 confirmed a structural setup, but "
                               "the nearest liquidity pool in this "
                               "direction is labeled STRONG (may hold as "
                               "real support/resistance rather than get "
                               "swept).",
                "recommendation": "The structural read is real; the "
                                  "liquidity context suggests the move may "
                                  "stall before the original target. "
                                  "Consider this a caution on target "
                                  "distance, not on direction.",
            })

        if news and news.get("strength") == "HIGH" and cr.score >= 70:
            out.append({
                "pattern": "bullish_technicals_high_impact_news",
                "description": "Strong technical confluence coinciding with "
                               "a HIGH-strength news signal in play.",
                "recommendation": "news_guard.py's blackout logic already "
                                  "hard-gates the highest-risk windows "
                                  "(unchanged by Day 5) — this pattern is "
                                  "surfaced for the remaining case where "
                                  "strong news exists but hasn't triggered "
                                  "a blackout. Treat the technical score as "
                                  "provisional until the news resolves.",
            })

        vp_loc = vp.get("location")
        if vp_loc == "above_va" and cr.direction == "long" and cr.score >= 70:
            out.append({
                "pattern": "buying_above_value",
                "description": "High confluence score for a long entry "
                               "priced above the volume-profile value area "
                               "(paying a premium relative to recent fair "
                               "value).",
                "recommendation": "Not a rejection — volume profile is one "
                                  "of many Primary Evidence sources — but "
                                  "worth flagging distinctly since it's a "
                                  "genuinely independent data source "
                                  "disagreeing with an otherwise strong read.",
            })
    except Exception:  # noqa: BLE001
        pass
    return out


# --- Phase 3/9: Information contribution measurement ------------------------
# Mirrors RISK_RULES.md's own 30-closed-trade validation bar and
# calibration.py's min_n=8 precedent: do not trust a per-source contribution
# estimate below MIN_N_FOR_CONTRIBUTION closed, source-tagged trades.
MIN_N_FOR_CONTRIBUTION = 30


def join_trades_with_confluence(trades_rows, history_rows) -> list:
    """Join closed trades.json rows to their confluence_history.jsonl
    record. Day 6 update: prefers the direct stable `ref` match (Trade.
    confluence_ref, set for every trade logged from Day 6 onward — see
    journal.make_ref()) and falls back to the nearest-preceding-timestamp
    join (the original Day 5 strategy, unchanged) for trades logged before
    that field existed or where the ref lookup misses. Same reasoning as
    RESEARCH_REGIME_ENGINE.md documented for regime data (Day 4): an exact
    reference beats a timestamp heuristic whenever one is available.

    Returns a list of {result_r, agree, disagree, quality_score} dicts —
    the shape measure_contribution()/recommend_weight_adjustments() expect.
    """
    def _norm(ts: str) -> str:
        """Normalize to a directly-comparable form: trades.json uses a
        space separator ("2026-08-01 10:00:00") while history stores
        already use ISO "T" separators ("2026-08-01T10:00:00") — naive
        string comparison across the two is wrong (space sorts before "T"
        in ASCII, silently reversing the comparison). Normalizing both to
        the same separator makes lexicographic comparison correct again
        without a full datetime parse (all timestamps here are already
        zero-padded ISO-ish "YYYY-MM-DD HH:MM:SS")."""
        return str(ts or "").replace("T", " ")

    out = []
    by_ref = {h.get("ref"): h for h in (history_rows or []) if h.get("ref")}
    by_symbol = {}
    for h in history_rows or []:
        by_symbol.setdefault(h.get("symbol"), []).append(h)
    for sym, rows in by_symbol.items():
        by_symbol[sym] = sorted(rows, key=lambda r: _norm(r.get("ts", "")))

    for t in trades_rows or []:
        if t.get("status") not in ("win", "loss", "scratch"):
            continue
        nearest = by_ref.get(t.get("confluence_ref")) if t.get("confluence_ref") else None
        if nearest is None:
            sym = t.get("symbol", "XAUUSD")
            opened = _norm(t.get("opened", ""))
            candidates = [h for h in by_symbol.get(sym, []) if _norm(h.get("ts", "")) <= opened]
            if not candidates:
                continue
            nearest = candidates[-1]
        out.append({
            "result_r": float(t.get("result_r", 0) or 0),
            "agree": nearest.get("agree", []),
            "disagree": nearest.get("disagree", []),
            "quality_score": nearest.get("quality_score"),
        })
    return out


def measure_contribution(source_key: str, labeled_trades: list,
                         min_n: int = MIN_N_FOR_CONTRIBUTION) -> dict:
    """For one source, split labeled_trades into agree/disagree/silent
    buckets (by whether SOURCE_REGISTRY label-matched contents of that
    trade's confluence read appear in agree/disagree) and compute
    expectancy per bucket. Returns `sufficient=False` and no directional
    claim when any bucket has fewer than `min_n` trades — do not draw
    conclusions from an underpowered sample. Never raises."""
    try:
        reg = SOURCE_REGISTRY.get(source_key)
        if not reg:
            return {"source": source_key, "sufficient": False,
                    "reason": "unknown source key"}
        patterns = LABEL_PATTERNS.get(source_key, [])

        def _bucket_r(trades, field):
            rs = []
            for t in trades:
                labels = t.get(field, []) or []
                if any(any(p in lbl for p in patterns) for lbl in labels):
                    rs.append(t["result_r"])
            return rs

        agree_r = _bucket_r(labeled_trades, "agree")
        disagree_r = _bucket_r(labeled_trades, "disagree")

        def _exp(rs):
            return (sum(rs) / len(rs)) if rs else None

        n_agree, n_disagree = len(agree_r), len(disagree_r)
        sufficient = n_agree >= min_n and n_disagree >= min_n
        return {
            "source": source_key, "label": reg["label"], "category": reg["category"],
            "n_agree": n_agree, "n_disagree": n_disagree,
            "expectancy_when_agree": round(_exp(agree_r), 3) if agree_r else None,
            "expectancy_when_disagree": round(_exp(disagree_r), 3) if disagree_r else None,
            "sufficient": sufficient,
            "reason": None if sufficient else
                f"n_agree={n_agree}, n_disagree={n_disagree}, both need >= {min_n}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"source": source_key, "sufficient": False, "reason": f"error: {exc}"}


def recommend_weight_adjustments(labeled_trades: list,
                                 min_n: int = MIN_N_FOR_CONTRIBUTION) -> list:
    """Phase 4: Adaptive Weighting Framework. For every source in
    SOURCE_REGISTRY (except the Layer 1 anchor), measure contribution and
    RECOMMEND (never apply) increase/decrease/retire/retain. This function
    has no write access to confluence.py — it cannot and does not change
    any live weight. A recommendation is only ever "increase"/"decrease"/
    "retire" when `sufficient=True`; otherwise it is always
    "insufficient_data — no recommendation", satisfying the mandate's "no
    source receives permanent authority... but no hard-coded rankings based
    on opinion" by construction: an opinion-based recommendation without
    data is refused, not guessed. Every recommendation is explainable
    (carries the measured expectancy numbers) and reversible (advisory
    text only, not a code change)."""
    out = []
    for key in SOURCE_REGISTRY:
        if key == "layer1_ict":
            continue
        m = measure_contribution(key, labeled_trades, min_n)
        if not m.get("sufficient"):
            out.append({**m, "recommendation": "insufficient_data",
                       "rationale": m.get("reason", "not enough tagged trades yet")})
            continue
        agree_exp = m["expectancy_when_agree"]
        disagree_exp = m["expectancy_when_disagree"]
        gap = agree_exp - disagree_exp
        if gap > 0.3:
            rec = "increase"
            rationale = (f"Trades where this source agreed averaged "
                        f"{agree_exp:+.2f}R vs {disagree_exp:+.2f}R when it "
                        f"disagreed (gap {gap:+.2f}R, n>={min_n} each side) "
                        f"— the source is discriminating real outcomes.")
        elif gap < -0.1:
            rec = "decrease_or_retire"
            rationale = (f"Trades where this source agreed averaged "
                        f"{agree_exp:+.2f}R, WORSE than {disagree_exp:+.2f}R "
                        f"when it disagreed (gap {gap:+.2f}R) — its current "
                        f"weight sign may be backwards or it is not "
                        f"adding value.")
        else:
            rec = "retain"
            rationale = (f"Gap between agree ({agree_exp:+.2f}R) and disagree "
                        f"({disagree_exp:+.2f}R) is small ({gap:+.2f}R) — no "
                        f"strong evidence to change the current weight.")
        out.append({**m, "recommendation": rec, "rationale": rationale})
    return out
