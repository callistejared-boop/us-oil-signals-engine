"""Day 9 — Research Dashboard: read-only payload showing active/completed
experiments, statistical evidence, validation progress, promotion status,
and rejected ideas.

DELIBERATELY SEPARATE from `engine.dashboard_publish` — the mandate:
"Keep research clearly separated from production." This module is
symbol-agnostic (research spans the whole platform, not one instrument)
and is never called from `dashboard_publish.build_payload()`/`main()` or
from `alert_signals.py`'s live scan loop. It is a standalone data-layer
function a future research-only view (or a manual research review) can
call; consistent with this codebase's existing "dashboard = a JSON payload
function" precedent (`dashboard_publish.py` itself has never rendered
HTML directly — the webapp/ frontend, outside this repo, does that).
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import experiment_registry as er   # noqa: E402
from engine import edge_decay_monitor as edm   # noqa: E402
from engine import evidence_tiers as et        # noqa: E402
from engine import promotion_gate as pg        # noqa: E402
from engine import qualification_diagnostics as qd   # noqa: E402

VERSION = "1.0.0"


def _experiment_summary(state: dict) -> dict:
    hyp = state.get("hypothesis") or {}
    return {
        "experiment_id": state.get("experiment_id"),
        "title": state.get("title"),
        "objective": hyp.get("objective", ""),
        "current_stage": state.get("current_stage"),
        "decision": state.get("decision"),
        "n_records": state.get("n_records"),
        "last_updated": state.get("last_updated"),
    }


def build_research_payload() -> dict:
    """The research dashboard's data layer. Never raises — every section
    degrades independently so one failure doesn't blank the whole
    payload."""
    try:
        active = [_experiment_summary(s) for s in er.active_experiments()]
    except Exception as exc:  # noqa: BLE001
        active = []
        active_error = str(exc)
    else:
        active_error = None

    try:
        completed = [_experiment_summary(s) for s in er.completed_experiments()]
    except Exception as exc:  # noqa: BLE001
        completed = []
        completed_error = str(exc)
    else:
        completed_error = None

    try:
        rejected = [_experiment_summary(s) for s in er.rejected_experiments()]
    except Exception as exc:  # noqa: BLE001
        rejected = []
        rejected_error = str(exc)
    else:
        rejected_error = None

    try:
        decay = edm.check()
    except Exception as exc:  # noqa: BLE001
        decay = {"error": str(exc)}

    try:
        promotion_audit = pg.summary()
    except Exception as exc:  # noqa: BLE001
        promotion_audit = {"error": str(exc)}

    try:
        qualification_diagnostics = qd.summary()
    except Exception as exc:  # noqa: BLE001
        qualification_diagnostics = {"error": str(exc)}

    return {
        "advisory_only": True,
        "note": "Research and validation status — entirely separate from live trade "
               "recommendations. Nothing here influences production.",
        "version": VERSION,
        "lifecycle_stages": er.LIFECYCLE_STAGES,
        "terminal_stages": er.TERMINAL_STAGES,
        "stage_criteria": er.STAGE_CRITERIA,
        "active_experiments": active,
        "completed_experiments": completed,
        "rejected_experiments": rejected,
        "errors": {k: v for k, v in
                  {"active": active_error, "completed": completed_error,
                   "rejected": rejected_error}.items() if v},
        "edge_decay_check": decay,
        "promotion_pipeline_audit": promotion_audit,
        "qualification_diagnostics": qualification_diagnostics,
        "evidence_tier_reference": [
            {"tier": name, "min_n": floor, "description": desc}
            for name, floor, desc in et.TIERS
        ],
    }
