"""Per-provider health classification + dependency-cascade logic.

Health Scoring, per the mandate: NOT a single number. Every provider is
classified into one of four states, plus a confidence-in-the-assessment
value, the list of affected downstream subsystems, and a recommended
action:

- Operational — fresh (or reference/computed data as-designed), no
  completeness/consistency/anomaly issues worse than minor.
- Degraded    — usable but imperfect: aging freshness, or minor/major
  isolated issues. Still safe to read, worth watching.
- Partial     — meaningfully compromised: stale freshness, or a major
  completeness/consistency finding. Usable with real caution.
- Unavailable — expired freshness, a critical finding, or a feed whose
  own `configured_check` reports it isn't configured at all.

Confidence in the assessment itself is separate from the status: a
feed with UNKNOWN freshness and no other signal gets LOW confidence
regardless of what status it's assigned, because "we can't tell" is a
different fact from "we can tell and it's bad."
"""
from __future__ import annotations

from . import registry as reg
from .freshness import FRESH, AGING, STALE, EXPIRED, UNKNOWN
from .completeness import NONE_, MINOR, MAJOR, CRITICAL

OPERATIONAL = "operational"
DEGRADED = "degraded"
PARTIAL = "partial"
UNAVAILABLE = "unavailable"

_STATUS_RANK = {OPERATIONAL: 0, DEGRADED: 1, PARTIAL: 2, UNAVAILABLE: 3}

_FRESHNESS_FLOOR = {
    FRESH: OPERATIONAL,
    AGING: DEGRADED,
    STALE: PARTIAL,
    EXPIRED: UNAVAILABLE,
    UNKNOWN: DEGRADED,  # unknown is a confidence problem, not automatically "bad"
}

_SEVERITY_FLOOR = {
    NONE_: OPERATIONAL,
    MINOR: DEGRADED,
    MAJOR: PARTIAL,
    CRITICAL: UNAVAILABLE,
}

RECOMMENDED_ACTION = {
    OPERATIONAL: "none — feed is healthy",
    DEGRADED: "monitor — no action required yet, revisit if it persists past the next cycle",
    PARTIAL: "investigate — data is usable but materially compromised; check the underlying provider/cache",
    UNAVAILABLE: "do not rely on this feed's current data; check provider connectivity/configuration",
}


def _worse(a: str, b: str) -> str:
    return a if _STATUS_RANK.get(a, 3) >= _STATUS_RANK.get(b, 3) else b


def classify(feed_id: str, freshness_state: str, completeness_severity: str = NONE_,
             consistency_severity: str = NONE_, anomaly_severity: str = NONE_,
             configured: object = None) -> dict:
    """Combines the four independent checks into one status for a single
    feed. `configured` is True/False/None (None = not applicable / unknown
    — most feeds have no configuration gate at all)."""
    try:
        status = OPERATIONAL
        reasons = []

        if configured is False:
            status = _worse(status, UNAVAILABLE)
            reasons.append("provider is not configured (missing required API key/setting)")

        f_status = _FRESHNESS_FLOOR.get(freshness_state, DEGRADED)
        if f_status != OPERATIONAL:
            reasons.append(f"freshness={freshness_state}")
        status = _worse(status, f_status)

        for label, sev in (("completeness", completeness_severity),
                            ("consistency", consistency_severity),
                            ("anomaly", anomaly_severity)):
            sev_status = _SEVERITY_FLOOR.get(sev, DEGRADED)
            if sev_status != OPERATIONAL:
                reasons.append(f"{label}={sev}")
            status = _worse(status, sev_status)

        # confidence in the assessment itself
        if freshness_state == UNKNOWN and not reasons[:-1]:
            confidence = "low"
        elif freshness_state == UNKNOWN:
            confidence = "medium"
        else:
            confidence = "high"

        return {
            "feed_id": feed_id,
            "status": status,
            "confidence": confidence,
            "reasons": reasons,
            "recommended_action": RECOMMENDED_ACTION.get(status, RECOMMENDED_ACTION[UNAVAILABLE]),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "feed_id": feed_id,
            "status": UNAVAILABLE,
            "confidence": "low",
            "reasons": [f"provider_status internal error: {exc}"],
            "recommended_action": RECOMMENDED_ACTION[UNAVAILABLE],
        }


def apply_dependency_cascade(statuses: dict) -> dict:
    """Given {feed_id: status_dict}, degrades any feed whose dependency is
    PARTIAL/UNAVAILABLE — cascading failure, per the mandate's own
    'Macro Engine -> Rates Feed -> Yahoo' example. A feed is never
    upgraded by this pass, only ever held at or pushed to a worse status
    than its own direct checks produced. Never raises: any lookup failure
    just leaves that feed's status unchanged."""
    try:
        out = {k: dict(v) for k, v in statuses.items()}
        for feed_id, status_dict in out.items():
            spec = reg.get(feed_id)
            if spec is None:
                continue
            for dep_id in spec.dependency_ids:
                dep_status = out.get(dep_id, {}).get("status")
                if dep_status in (PARTIAL, UNAVAILABLE):
                    if _STATUS_RANK.get(dep_status, 0) > _STATUS_RANK.get(status_dict["status"], 0):
                        status_dict["status"] = dep_status
                        status_dict.setdefault("reasons", []).append(
                            f"cascaded from dependency '{dep_id}' ({dep_status})"
                        )
                        status_dict["recommended_action"] = RECOMMENDED_ACTION.get(dep_status, "")
        return out
    except Exception:  # noqa: BLE001
        return statuses


def affected_subsystems(feed_id: str) -> tuple:
    """Every feed that transitively depends on feed_id — 'what breaks if
    this goes down,' read straight from the registry's dependency graph."""
    try:
        seen = set()
        frontier = [feed_id]
        result = []
        while frontier:
            current = frontier.pop()
            for dependent in reg.dependents_of(current):
                if dependent not in seen:
                    seen.add(dependent)
                    result.append(dependent)
                    frontier.append(dependent)
        return tuple(result)
    except Exception:  # noqa: BLE001
        return ()
