"""Day 9 — Sample size / evidence-tier policy.

The Day 9 mandate is explicit: "Avoid rigid numerical thresholds where
statistical context matters; instead, document how confidence should
increase with larger, more representative samples." This module is
deliberately NOT a single hard cutoff table. `evidence_tier()` returns a
DEFAULT tier from sample size alone (useful as a quick, honest label), but
`assess()` — the function research code should actually call — also
considers REPRESENTATIVENESS (does the sample span multiple regimes/
sessions/market conditions, or is it clustered in one narrow period) and
CONSISTENCY (does `research_stats.stability_over_time()` show the effect
holding across sub-segments, or concentrated in one).

The five tiers below match the mandate's own list verbatim. They are
descriptive labels, not gates — nothing in this codebase blocks on a tier;
`experiment_registry.py`'s promotion recommendation READS a tier and
presents it, it does not enforce one, consistent with the Day 9 mandate's
governing principle that this framework governs RESEARCH, not production
behavior.

Reused, not re-declared: the platform's existing `MIN_N_FOR_TRUST=30`
(Day 5/6/7 precedent, also `research_stats.MIN_N_FOR_TRUST`) is the anchor
for the "moderate_confidence" default boundary — this module does not
invent a competing number.
"""
from __future__ import annotations

TIERS = [
    ("research_observation", 0, "A handful of observations — worth noting, not yet evidence of anything."),
    ("exploratory_evidence", 5, "Enough to form a testable hypothesis; far too few to trust a number."),
    ("preliminary_evidence", 15, "A pattern is visible; still easily explained by chance or a narrow period."),
    ("moderate_confidence", 30, "Matches this platform's established statistical-trust bar (Day 5/6/7) — "
                               "worth weighing seriously, still not production-ready alone."),
    ("production_ready_evidence", 100, "Large enough that a single unlucky/lucky stretch is unlikely to "
                                       "explain the result BY ITSELF — still requires representativeness "
                                       "and consistency checks below, not sample size alone."),
]


def evidence_tier(n: int) -> str:
    """Sample-size-only default tier. A starting point, not the whole
    policy — see `assess()` for the full, context-aware version."""
    label = TIERS[0][0]
    for name, floor, _ in TIERS:
        if n >= floor:
            label = name
    return label


def _tier_description(name: str) -> str:
    for tname, _, desc in TIERS:
        if tname == name:
            return desc
    return ""


def assess(n: int, *, representative: bool | None = None,
          consistent_sign: bool | None = None, notes: str = "") -> dict:
    """The full, non-rigid evidence assessment research code should
    actually call. Combines sample size with two qualitative signals:

    - `representative`: does the sample span multiple market regimes/
      sessions/time periods, or is it clustered in one narrow window? Pass
      `None` (default) when this hasn't been checked — the function will
      say so explicitly rather than assuming representativeness.
    - `consistent_sign`: from `research_stats.stability_over_time()`'s own
      `consistent_sign` field, or equivalent — does the effect hold across
      sub-segments of the sample, or is it concentrated in one?

    A sample can have a large `n` and still be downgraded a tier if it is
    NOT representative or NOT consistent — this is the mechanism that
    keeps the policy from being "just a number," per the mandate's
    explicit instruction. Never raises."""
    try:
        base_tier = evidence_tier(n)
        base_idx = [t[0] for t in TIERS].index(base_tier)
        caveats = []
        effective_idx = base_idx

        if representative is False:
            caveats.append("sample is NOT representative (clustered in a narrow period/condition) — "
                           "downgraded regardless of n")
            effective_idx = min(effective_idx, [t[0] for t in TIERS].index("preliminary_evidence"))
        elif representative is None:
            caveats.append("representativeness not assessed — treat this tier as provisional")

        if consistent_sign is False:
            caveats.append("effect is NOT consistent across sub-segments (see stability_over_time) — "
                           "downgraded regardless of n")
            effective_idx = min(effective_idx, [t[0] for t in TIERS].index("preliminary_evidence"))
        elif consistent_sign is None:
            caveats.append("within-sample stability not assessed — treat this tier as provisional")

        effective_tier = TIERS[effective_idx][0]
        return {
            "n": n,
            "size_only_tier": base_tier,
            "effective_tier": effective_tier,
            "description": _tier_description(effective_tier),
            "downgraded": effective_idx < base_idx,
            "caveats": caveats,
            "notes": notes,
        }
    except Exception as exc:  # noqa: BLE001
        return {"n": n, "size_only_tier": "research_observation",
               "effective_tier": "research_observation",
               "description": _tier_description("research_observation"),
               "downgraded": False, "caveats": [f"assessment error: {exc}"], "notes": notes}
