"""Day 11 — Macro Regime: descriptive classification, deliberately NOT a
scoring engine.

The platform already has a weighted-scoring model (`engine.confluence`)
and a probability-style score (`engine.confidence_engine`). Per the Day 11
mandate's explicit prohibition, this module does not build a third one.
Instead it answers a narrower, purely descriptive question: "which of a
small set of textbook macro-environment labels currently apply?" Multiple
labels can apply simultaneously (an environment can be both Risk-Off AND
Tightening at once — these are not mutually exclusive dimensions), and
"Neutral"/"Mixed" are themselves valid, non-evasive answers when the
evidence doesn't clearly support anything sharper.

Reads ONLY `engine.macro_providers` (the Day 11 abstraction-layer rule —
this module never imports `risk_sentiment`, `rates_feed`, or any other
underlying feed module directly).

Two fields deliberately kept distinct, per the Day 11 mandate's own
explicit design recommendation:

  * `macro_confidence` — how INTERNALLY CONSISTENT this assessment is
    (do the independent pieces of evidence agree, or fight each other?).
    This is NOT the trading Confidence Engine's score and never feeds it.
  * `evidence_quality` — how RELIABLE the underlying inputs were this run
    (live and fresh vs. stale/missing/reference-only). A confident-sounding
    label built entirely on missing data should never look as trustworthy
    as the same label built on five fresh, live readings — this field is
    what keeps that distinction visible rather than hidden inside a single
    number.
"""
from __future__ import annotations

from datetime import datetime, timezone

VERSION = "1.0.0"

LABELS = ["Inflationary", "Disinflationary", "Tightening", "Easing",
         "Risk-On", "Risk-Off", "Neutral", "Mixed"]


def _evidence_quality(providers: dict) -> tuple[str, dict]:
    """Aggregates freshness/source_availability across every provider read
    into one qualitative tier — NOT a weighted score, a simple disclosed
    count-based rule: what fraction of providers actually had usable data
    this run. Never raises."""
    states = {name: p.get("freshness", {}).get("state") for name, p in providers.items()}
    availability = {name: p.get("source_availability") for name, p in providers.items()}
    usable = sum(1 for s in states.values() if s in ("fresh", "reference_data", "computed"))
    total = max(1, len(states))
    frac = usable / total
    tier = "high" if frac >= 0.7 else "medium" if frac >= 0.35 else "low"
    return tier, {"usable_providers": usable, "total_providers": total,
                 "states": states, "availability": availability}


def _label(name, basis, supporting, note, confidence_hint):
    return {"label": name, "basis": basis, "supporting_providers": supporting,
           "note": note, "confidence_hint": confidence_hint}


def _risk_labels(providers: dict) -> list:
    vol = providers.get("volatility", {})
    regime = (vol.get("facts") or {}).get("regime")
    if not regime or vol.get("source_availability") != "available":
        return []
    if regime == "risk-on":
        return [_label("Risk-On", "Rising equities + falling volatility (VIX/SPX regime).",
                       ["volatility"], vol.get("interpretation", ""), "high")]
    if regime == "risk-off":
        return [_label("Risk-Off", "Falling equities + rising volatility (VIX/SPX regime).",
                       ["volatility"], vol.get("interpretation", ""), "high")]
    return [_label("Mixed", "VIX/SPX regime read as mixed — no clean risk-on/risk-off signal.",
                   ["volatility"], vol.get("interpretation", ""), "low")]


def _tightening_easing_labels(providers: dict) -> list:
    rates = providers.get("interest_rates", {})
    bonds = providers.get("sovereign_bonds", {})
    cb = providers.get("central_bank_policy", {})
    out = []
    signals = []  # list of ("tightening"|"easing", provider_name)
    rf = rates.get("facts") or {}
    if rates.get("source_availability") == "available":
        if rf.get("ten_year_trend") == "rising":
            signals.append(("tightening", "interest_rates"))
        elif rf.get("ten_year_trend") == "falling":
            signals.append(("easing", "interest_rates"))
    bf = bonds.get("facts") or {}
    if bonds.get("source_availability") == "available":
        if bf.get("trend") == "falling":  # bond price down -> yields up
            signals.append(("tightening", "sovereign_bonds"))
        elif bf.get("trend") == "rising":
            signals.append(("easing", "sovereign_bonds"))
    if cb.get("source_availability") == "available":
        for bank, stance in (cb.get("facts") or {}).items():
            direction = str(stance.get("expected_direction", "")).lower()
            if "hike" in direction or "tighten" in direction:
                signals.append(("tightening", f"central_bank_policy:{bank}"))
            elif "cut" in direction or "ease" in direction:
                signals.append(("easing", f"central_bank_policy:{bank}"))
    tight_support = [p for d, p in signals if d == "tightening"]
    ease_support = [p for d, p in signals if d == "easing"]
    if tight_support and not ease_support:
        out.append(_label("Tightening", "Rising yields / falling bond prices / hawkish central-bank stance.",
                          tight_support, f"{len(tight_support)} independent signal(s) agree", "high"))
    elif ease_support and not tight_support:
        out.append(_label("Easing", "Falling yields / rising bond prices / dovish central-bank stance.",
                          ease_support, f"{len(ease_support)} independent signal(s) agree", "high"))
    elif tight_support and ease_support:
        out.append(_label("Mixed", "Tightening and easing signals both present — rates/bonds/central-bank "
                          "evidence does not agree.", tight_support + ease_support,
                          f"{len(tight_support)} tightening vs {len(ease_support)} easing signal(s)", "low"))
    return out


def _inflation_labels(providers: dict) -> list:
    infl = providers.get("inflation", {})
    if infl.get("source_availability") not in ("available",):
        return []
    proxy = (infl.get("facts") or {}).get("market_implied_proxy") or {}
    trend = proxy.get("trend")
    if trend == "rising":
        return [_label("Inflationary", "Market-implied inflation-expectations proxy (TIP/IEF) rising.",
                       ["inflation"], proxy.get("interpretation", ""), "medium")]
    if trend == "falling":
        return [_label("Disinflationary", "Market-implied inflation-expectations proxy (TIP/IEF) falling.",
                       ["inflation"], proxy.get("interpretation", ""), "medium")]
    return []


def classify(providers: dict, symbol: str = None) -> dict:
    """Builds the full descriptive regime assessment from an already-
    fetched `macro_providers.get_all(symbol)` payload (passed in, not
    re-fetched here — the caller, `macro_engine.py`, owns fetching).
    Never raises."""
    try:
        candidates = []
        candidates += _risk_labels(providers)
        candidates += _tightening_easing_labels(providers)
        candidates += _inflation_labels(providers)

        labels = [c["label"] for c in candidates]
        if not labels:
            labels = ["Neutral"]
            candidates = [_label("Neutral", "No provider cleared a minimal evidence bar this run.",
                                 [], "insufficient/unavailable data across providers", "low")]

        # Internal consistency: any candidate itself flagged "Mixed"
        # (conflicting signals within one dimension), or a genuinely
        # low confidence_hint anywhere, pulls overall macro_confidence
        # down — this is a simple disclosed rule, not a weighted score.
        any_mixed = "Mixed" in labels
        hints = [c["confidence_hint"] for c in candidates]
        if any_mixed or hints.count("low") > hints.count("high"):
            macro_confidence = "low"
        elif all(h == "high" for h in hints):
            macro_confidence = "high"
        else:
            macro_confidence = "medium"

        evidence_quality, eq_detail = _evidence_quality(providers)

        return {
            "version": VERSION, "symbol": symbol,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "labels": sorted(set(labels)),
            "label_evidence": {c["label"]: c for c in candidates},
            "macro_confidence": macro_confidence,
            "evidence_quality": evidence_quality,
            "evidence_quality_detail": eq_detail,
            "note": ("Descriptive classification only — not a weighted score and never fed "
                    "into engine.confluence or engine.confidence_engine. Labels are not "
                    "mutually exclusive; multiple can apply at once."),
        }
    except Exception as exc:  # noqa: BLE001
        return {"version": VERSION, "symbol": symbol, "labels": ["Neutral"],
               "label_evidence": {}, "macro_confidence": "low", "evidence_quality": "low",
               "evidence_quality_detail": {}, "error": f"classify error: {exc}"}
