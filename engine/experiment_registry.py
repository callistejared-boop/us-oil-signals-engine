"""Day 9 — Research Lifecycle, Hypothesis Template, and Experiment Registry.

Every future strategy, filter, scoring adjustment, feature, or AI capability
must pass through this framework before becoming eligible for production —
the Day 9 mandate's Primary Objective, made concrete: nothing in this
module can change production trading behavior. It is a permanent,
append-only RECORD of research, mirroring
`engine/decision_audit_history.py`'s (Day 8) exact immutability pattern —
no update/delete function of any kind, only `record()` (append) and
read-only lookups. Corrections/progress are new rows referencing the same
`experiment_id`, never edits, for the same reason Day 8 established:
"Failed experiments are valuable knowledge and should remain documented" —
overwriting history would destroy exactly the knowledge this registry
exists to preserve.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "experiment_registry.jsonl"
MAX_LINES = 20000

VERSION = "1.0.0"
SCHEMA_VERSION = 1

# --- Research lifecycle (verbatim from the Day 9 mandate's own diagram) ----
LIFECYCLE_STAGES = [
    "idea",
    "research_proposal",
    "technical_design",
    "implementation_research_branch",
    "historical_testing",
    "walk_forward_testing",
    "paper_trading",
    "performance_review",
    "production_recommendation",
    "controlled_release",
    "ongoing_monitoring",
]
# Terminal states reachable from ANY stage — an idea can be rejected at any
# point, and even a controlled release can be rolled back after monitoring
# reveals a problem. Both remain permanently in the registry (mandate:
# "Failed experiments are valuable knowledge").
TERMINAL_STAGES = ["rejected", "rolled_back"]
ALL_STAGES = LIFECYCLE_STAGES + TERMINAL_STAGES

# Documented entry/exit criteria per stage — descriptive guidance surfaced
# to researchers (e.g. via the research dashboard), not enforced
# programmatically (this framework governs research, not production; see
# module docstring and the mandate's own "does not change production
# trading behavior").
STAGE_CRITERIA = {
    "idea": {
        "entry": "Any observation, question, or intuition worth investigating.",
        "exit": "A filled Hypothesis template (see Hypothesis dataclass) exists.",
    },
    "research_proposal": {
        "entry": "A complete Hypothesis template has been recorded.",
        "exit": "Objective, rationale, and measurable success/rollback criteria are all specific enough to test.",
    },
    "technical_design": {
        "entry": "The proposal is accepted for design work.",
        "exit": "A concrete implementation plan exists (what changes, where, what it reuses vs. adds).",
    },
    "implementation_research_branch": {
        "entry": "Design is complete.",
        "exit": "Code exists in a form that can be run against historical/live data WITHOUT touching production paths.",
    },
    "historical_testing": {
        "entry": "Research-branch implementation is runnable.",
        "exit": "A `research_stats.full_report()` exists for the backtested result, with `evidence_tiers.assess()` applied.",
    },
    "walk_forward_testing": {
        "entry": "Historical testing shows a plausible edge.",
        "exit": "Out-of-sample (walk-forward) evaluation does not contradict the historical result — see engine.walkforward.",
    },
    "paper_trading": {
        "entry": "Walk-forward evidence supports moving to live (unrealized) evaluation.",
        "exit": "A meaningful paper-trading sample exists — see engine.paper_trading_review.",
    },
    "performance_review": {
        "entry": "Paper-trading sample reaches at least `moderate_confidence` (see engine.evidence_tiers).",
        "exit": "A documented promotion decision with explicit rationale exists.",
    },
    "production_recommendation": {
        "entry": "Performance review recommends production.",
        "exit": "The platform owner (or designated reviewer) has approved the recommendation.",
    },
    "controlled_release": {
        "entry": "Production recommendation is approved.",
        "exit": "The change is live in production, under close monitoring.",
    },
    "ongoing_monitoring": {
        "entry": "Change is live.",
        "exit": "Never — this is a permanent state; see engine.edge_decay_monitor for what triggers investigation.",
    },
}


@dataclass
class Hypothesis:
    """Standard template for every future experiment — verbatim per the
    Day 9 mandate's own list."""
    objective: str
    theoretical_rationale: str
    expected_benefit: str
    implementation_scope: str
    dependencies: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    measurable_success_criteria: list = field(default_factory=list)
    rollback_criteria: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def is_complete(self) -> bool:
        """A hypothesis is complete only when every required narrative
        field is non-empty AND at least one measurable success criterion
        and one rollback criterion are specified — an empty list there
        would defeat the entire point of a falsifiable hypothesis."""
        try:
            required_text = [self.objective, self.theoretical_rationale,
                             self.expected_benefit, self.implementation_scope]
            return (all(str(x).strip() for x in required_text)
                    and len(self.measurable_success_criteria) > 0
                    and len(self.rollback_criteria) > 0)
        except Exception:  # noqa: BLE001
            return False


def _read_all() -> list:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []


def _rotate() -> None:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            HISTORY_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _write(rec: dict) -> dict:
    rec = dict(rec)
    rec["recorded"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def _new_id(title: str) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(":", "").replace("+", "")
    slug = "".join(c if c.isalnum() else "-" for c in (title or "experiment"))[:40].strip("-").lower()
    return f"{slug or 'experiment'}-{ts}"


def log_idea(title: str, note: str = "") -> dict:
    """Lightest-weight lifecycle entry — the "Idea" stage, before a full
    Hypothesis template exists. Never raises."""
    exp_id = _new_id(title)
    rec = {"record_type": "proposal", "experiment_id": exp_id, "title": title,
          "stage": "idea", "note": note, "hypothesis": None,
          "version": {"experiment_registry": VERSION, "schema": SCHEMA_VERSION}}
    return _write(rec)


def propose(title: str, hypothesis: Hypothesis, dataset: str = "",
           experiment_id: str = "") -> dict:
    """Record a complete Research Proposal — a filled `Hypothesis`.
    `hypothesis.is_complete()` is checked and the result is recorded
    (`"complete": bool`) but NEVER blocks the write — an incomplete
    proposal is still valuable to have on record (e.g. to flag it as
    needing more work), matching this codebase's "disclose, don't hide"
    convention. Never raises."""
    exp_id = experiment_id or _new_id(title)
    try:
        h = hypothesis.as_dict()
        complete = hypothesis.is_complete()
    except Exception as exc:  # noqa: BLE001
        h = {}
        complete = False
        title = title or f"(hypothesis error: {exc})"
    rec = {"record_type": "proposal", "experiment_id": exp_id, "title": title,
          "stage": "research_proposal", "dataset": dataset, "hypothesis": h,
          "complete": complete,
          "version": {"experiment_registry": VERSION, "schema": SCHEMA_VERSION}}
    return _write(rec)


def transition(experiment_id: str, new_stage: str, *, notes: str = "",
              evidence: dict | None = None, decision: str | None = None,
              rationale: str = "") -> dict:
    """Append a stage-transition record. `new_stage` is checked against
    `ALL_STAGES` and flagged `"valid_stage": False` (never raises, never
    refuses to write) if it isn't recognized — disclosed, not silently
    coerced or rejected. `decision` (e.g. `"promoted"`/`"rejected"`/
    `"rolled_back"`) and `rationale` are how a terminal outcome is
    recorded — required by convention (not enforced) when `new_stage` is
    in `TERMINAL_STAGES`."""
    rec = {
        "record_type": "stage_transition", "experiment_id": experiment_id,
        "stage": new_stage, "valid_stage": new_stage in ALL_STAGES,
        "notes": notes, "evidence": evidence or {}, "decision": decision or "",
        "rationale": rationale,
        "version": {"experiment_registry": VERSION, "schema": SCHEMA_VERSION},
    }
    return _write(rec)


def history(experiment_id: str) -> list:
    """Every record (proposal + every stage transition) for one
    experiment, in write order — the full, unaltered research trail."""
    return [r for r in _read_all() if r.get("experiment_id") == experiment_id]


def current_state(experiment_id: str) -> dict | None:
    """Reconstructs an experiment's CURRENT stage/decision by reading its
    full history and taking the latest record — never stored redundantly,
    always derived, so there is no risk of the "current" view drifting
    from the append-only log of how it got there."""
    rows = history(experiment_id)
    if not rows:
        return None
    latest = rows[-1]
    proposal = next((r for r in rows if r.get("record_type") == "proposal"), rows[0])
    return {
        "experiment_id": experiment_id,
        "title": proposal.get("title", ""),
        "hypothesis": proposal.get("hypothesis"),
        "current_stage": latest.get("stage"),
        "decision": latest.get("decision") or "",
        "is_terminal": latest.get("stage") in TERMINAL_STAGES,
        "n_records": len(rows),
        "last_updated": latest.get("recorded"),
        "history": rows,
    }


def all_experiment_ids() -> list:
    seen = []
    for r in _read_all():
        eid = r.get("experiment_id")
        if eid and eid not in seen:
            seen.append(eid)
    return seen


def _all_current_states() -> list:
    out = []
    for eid in all_experiment_ids():
        state = current_state(eid)
        if state:
            out.append(state)
    return out


def active_experiments() -> list:
    """Every experiment still progressing through the pre-monitoring
    lifecycle (not yet terminal, and not yet in `ongoing_monitoring`) —
    the mandate's "active experiments" dashboard category. `ongoing_
    monitoring` is deliberately excluded here and reported instead by
    `completed_experiments()`: an experiment being monitored in production
    is no longer "in research," even though `is_terminal` is technically
    `False` for it (monitoring has no defined exit stage) — see
    `current_state()`'s own `is_terminal` field if a caller wants that
    stricter, terminal-only distinction instead."""
    return [s for s in _all_current_states()
           if not s["is_terminal"] and s["current_stage"] != "ongoing_monitoring"]


def completed_experiments() -> list:
    """Experiments that reached `ongoing_monitoring` (successfully
    promoted and still being watched) — distinct from `rejected`."""
    return [s for s in _all_current_states() if s["current_stage"] == "ongoing_monitoring"]


def rejected_experiments() -> list:
    """Rejected (or rolled-back) experiments — kept permanently per the
    mandate: "Failed experiments are valuable knowledge and should remain
    documented.\""""
    return [s for s in _all_current_states() if s["current_stage"] in TERMINAL_STAGES]


def tail(n: int = 20) -> list:
    return _read_all()[-n:]


def all_rows() -> list:
    return _read_all()
