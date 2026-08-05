"""Assembles every other module's output into one Health Report — the
single object the dashboard and any future consumer should read, rather
than each caller re-deriving its own view from the individual checks.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import registry as reg
from .provider_status import OPERATIONAL, DEGRADED, PARTIAL, UNAVAILABLE, affected_subsystems


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_report(statuses: dict, registry_validation: dict, heartbeat_record: dict = None,
                  recent_history: list = None) -> dict:
    """`statuses` is {feed_id: status_dict} — the output of
    provider_status.classify() + apply_dependency_cascade(), one entry per
    registered feed. Never raises: any per-feed formatting problem is
    isolated to that feed's own entry."""
    try:
        counts = {OPERATIONAL: 0, DEGRADED: 0, PARTIAL: 0, UNAVAILABLE: 0}
        providers = []
        dependency_map = {}
        degraded_or_worse = []

        for feed_id, status_dict in statuses.items():
            try:
                spec = reg.get(feed_id)
                status = status_dict.get("status", UNAVAILABLE)
                counts[status] = counts.get(status, 0) + 1
                entry = {
                    "feed_id": feed_id,
                    "provider": spec.provider if spec else None,
                    "category": spec.category if spec else None,
                    "status": status,
                    "confidence": status_dict.get("confidence"),
                    "reasons": status_dict.get("reasons", []),
                    "recommended_action": status_dict.get("recommended_action"),
                    "affected_subsystems": list(affected_subsystems(feed_id)),
                }
                providers.append(entry)
                dependency_map[feed_id] = {
                    "depends_on": list(spec.dependency_ids) if spec else [],
                    "dependents": list(affected_subsystems(feed_id)),
                }
                if status != OPERATIONAL:
                    degraded_or_worse.append(entry)
            except Exception as exc:  # noqa: BLE001
                providers.append({"feed_id": feed_id, "status": UNAVAILABLE,
                                    "reasons": [f"health_report formatting error: {exc}"]})

        total = sum(counts.values())
        if total == 0:
            overall = "unavailable"
        elif counts[UNAVAILABLE] > 0:
            overall = "degraded" if counts[OPERATIONAL] + counts[DEGRADED] >= total / 2 else "unavailable"
        elif counts[PARTIAL] > 0:
            overall = "degraded"
        elif counts[DEGRADED] > 0:
            overall = "degraded"
        else:
            overall = "operational"

        return {
            "generated_at": _now_iso(),
            "overall_status": overall,
            "counts": counts,
            "total_feeds": total,
            "providers": providers,
            "dependency_map": dependency_map,
            "degraded_or_worse": degraded_or_worse,
            "registry_validation": registry_validation,
            "heartbeat": heartbeat_record,
            "recent_history": recent_history or [],
            "note": (
                "Advisory only. No trade-gating decision reads this report. "
                "See DATA_HEALTH_SPECIFICATION.md for the structural proof."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "generated_at": _now_iso(),
            "overall_status": UNAVAILABLE,
            "counts": {},
            "total_feeds": 0,
            "providers": [],
            "dependency_map": {},
            "degraded_or_worse": [],
            "registry_validation": registry_validation,
            "heartbeat": heartbeat_record,
            "recent_history": [],
            "note": f"health_report.build_report internal error: {exc}",
        }
