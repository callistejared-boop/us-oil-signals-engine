"""Day 11 — Macro Intelligence Engine: top-level orchestrator.

    Providers -> Macro Regime -> Cross-Asset Context -> Macro Assessment
    -> Explainability

Nothing more. This module performs NO calculations of its own — every
number/label here was already computed by `macro_providers.py` (facts) or
`macro_regime.py` (descriptive classification); this file's only job is to
call them in order, assemble the result, and produce the explainability
narrative. If a future change needs a NEW calculation, it belongs in
`macro_providers.py` (a new provider) or `macro_regime.py` (a new label
rule) — never inlined here.

GOVERNING PRINCIPLE (Day 11 mandate, verbatim): this engine answers "what
is the broader environment in which this trade is occurring?" It does not
answer "should this trade be taken?" `assess()` never returns a
score adjustment, never gates, and is never called anywhere that could
block or resize a trade — see MACRO_ENGINE_SPECIFICATION.md Sec.6 for the
structural proof (grep of alert_signals.py's gating functions).
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import macro_providers as mp
from . import macro_regime as mr
from . import macro_history as mh

VERSION = "1.0.0"


def assess(symbol: str, direction: str = "long") -> dict:
    """The one call downstream code needs: every provider's read for
    `symbol`, the descriptive regime classification built from them, and
    an explainability narrative — assembled, not computed, here. Never
    raises."""
    try:
        providers = mp.get_all(symbol, direction=direction)
        regime = mr.classify(providers, symbol=symbol)
        cross_asset = providers.get("cross_asset", {})
        seasonality = mp.seasonality(symbol)
        calendar = mp.calendar_summary()
        assessment = {
            "version": VERSION, "symbol": symbol, "direction": direction,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "providers": providers,
            "regime": regime,
            "cross_asset": cross_asset,
            "seasonality": seasonality,
            "calendar": calendar,
        }
        assessment["explainability"] = explain(assessment)
        return assessment
    except Exception as exc:  # noqa: BLE001
        return {"version": VERSION, "symbol": symbol, "direction": direction,
               "providers": {}, "regime": {"labels": ["Neutral"], "macro_confidence": "low",
                                           "evidence_quality": "low"},
               "cross_asset": {}, "error": f"assess error: {exc}"}


def explain(assessment: dict) -> dict:
    """Answers the five questions the Day 11 mandate names, from data
    already in `assessment` — never re-fetches, never re-derives. Avoids
    deterministic language throughout (labels are described as "read as"/
    "consistent with", never "will"/"is guaranteed to"). Never raises."""
    try:
        regime = assessment.get("regime", {}) or {}
        providers = assessment.get("providers", {}) or {}
        symbol = assessment.get("symbol")
        labels = regime.get("labels", [])

        what_happened = (
            f"The macro environment for {symbol} currently reads as: {', '.join(labels)} "
            f"(macro_confidence={regime.get('macro_confidence','unknown')}, "
            f"evidence_quality={regime.get('evidence_quality','unknown')})."
        )

        why_it_matters = (
            "Macro context does not originate or gate any trade — it is background "
            "evidence for the environment ICT/SMC setups are occurring in, useful for "
            "reviewing why a setup did or didn't work after the fact, and for future, "
            "separately-validated research into whether macro context correlates with "
            "outcomes (see RESEARCH_MACRO_ENGINE.md)."
        )

        assets_affected = sorted({
            asset for rel in (assessment.get("cross_asset", {}).get("facts", {})
                              .get("relationships", {}) or {}).values()
            for asset in ([symbol] if rel.get("supports") is not None else [])
        }) or [symbol]

        uncertainties = []
        for name, p in providers.items():
            state = (p.get("freshness") or {}).get("state")
            if state in ("missing", "stale") or p.get("source_availability") != "available":
                uncertainties.append(f"{name}: {state or p.get('source_availability')}")
        if regime.get("evidence_quality") == "low":
            uncertainties.append("overall evidence quality is LOW this run — treat labels as provisional")

        evidence = [
            {"label": lbl, "basis": ev.get("basis"), "supporting_providers": ev.get("supporting_providers"),
             "note": ev.get("note")}
            for lbl, ev in (regime.get("label_evidence") or {}).items()
        ]

        return {
            "what_happened": what_happened,
            "why_it_matters": why_it_matters,
            "assets_most_affected": assets_affected,
            "uncertainties_remaining": uncertainties or ["none flagged this run"],
            "evidence_supporting_assessment": evidence,
        }
    except Exception as exc:  # noqa: BLE001
        return {"what_happened": "unavailable", "why_it_matters": "unavailable",
               "assets_most_affected": [], "uncertainties_remaining": [f"error: {exc}"],
               "evidence_supporting_assessment": []}


def record_assessment(symbol: str, assessment: dict, ref: str = "") -> dict:
    """Persists one assessment via `macro_history.py`. A thin pass-through
    — kept here (not called directly by callers against macro_history)
    so `alert_signals.py` only ever needs to import `macro_engine`, never
    `macro_history` directly, matching the same "one stable interface"
    discipline `macro_providers.py` established for the feed layer."""
    return mh.record(symbol, assessment, ref=ref)


def last_assessment(symbol: str) -> dict | None:
    return mh.last_for(symbol)


def find_assessment_by_ref(ref: str) -> dict | None:
    return mh.find_by_ref(ref)
