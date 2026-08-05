"""Research Sandbox — Day 5 Phase 8.

A governance registry for candidate confluence sources, tracking each one
through the mandate's required pipeline:

    Research -> Historical Testing -> Walk-Forward Testing -> Paper Trading
    -> Production Recommendation

CRITICAL PROPERTY: nothing in `engine/confluence.py` — or anywhere else in
the live alert path — reads from this module. That is not an oversight to
fix later; it is the entire point. "No experimental feature should
influence live decisions until validated" is satisfied by construction: a
candidate's stage can be advanced to "production_recommendation" and it
still has zero runtime effect. Promoting a candidate into
`confluence.py`'s actual scored source list is a deliberate, separate,
human-reviewed code change (adding a new scored block the same way every
existing source was added) — this registry's job ends at producing the
evidence and paper-trading record that change would be based on.

Persisted as a single JSON object (not a growing JSONL log like
ledger.py/regime_history.py/confluence_history.py) because a candidate's
current stage is mutable state to look up by name, not an append-only
event stream — closer to `pending.json`'s shape than `run_ledger.jsonl`'s.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "confluence_sandbox.json"

STAGES = ["research", "historical_testing", "walk_forward", "paper_trading",
         "production_recommendation"]


def _load() -> dict:
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict) -> None:
    try:
        REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def register_candidate(name: str, description: str, hypothesis: str = "") -> dict:
    """Add a new candidate at stage 0 ("research"). If it already exists,
    returns the existing record unchanged (idempotent — does not reset
    progress)."""
    data = _load()
    if name in data:
        return data[name]
    rec = {
        "name": name, "description": description, "hypothesis": hypothesis,
        "stage": STAGES[0], "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history": [{"stage": STAGES[0], "note": "registered",
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}],
    }
    data[name] = rec
    _save(data)
    return rec


def advance_stage(name: str, new_stage: str, evidence_note: str) -> dict:
    """Move a candidate to `new_stage`. Enforces that stages advance in
    order (no skipping — a candidate cannot jump from 'research' straight
    to 'production_recommendation' without the intermediate evidence
    stages) and that every advance carries a note explaining WHY, so the
    registry itself is the audit trail for "was this validated before it
    mattered." Raises ValueError on an invalid transition or unknown
    candidate — this is a deliberately strict, not fail-open, function:
    silently allowing a stage-skip would defeat the entire point of the
    sandbox."""
    data = _load()
    if name not in data:
        raise ValueError(f"unknown candidate: {name!r} — register_candidate() first")
    if new_stage not in STAGES:
        raise ValueError(f"unknown stage: {new_stage!r} — must be one of {STAGES}")
    cur_idx = STAGES.index(data[name]["stage"])
    new_idx = STAGES.index(new_stage)
    if new_idx not in (cur_idx, cur_idx + 1):
        raise ValueError(
            f"cannot advance {name!r} from {data[name]['stage']!r} to "
            f"{new_stage!r} — stages must advance one at a time "
            f"({STAGES}), no skipping")
    if not evidence_note:
        raise ValueError("advance_stage requires a non-empty evidence_note "
                         "— every transition must be justified")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data[name]["stage"] = new_stage
    data[name]["updated"] = now
    data[name]["history"].append({"stage": new_stage, "note": evidence_note, "ts": now})
    _save(data)
    return data[name]


def get_candidate(name: str):
    return _load().get(name)


def list_candidates(stage: str = None) -> list:
    data = _load()
    out = list(data.values())
    if stage:
        out = [c for c in out if c["stage"] == stage]
    return sorted(out, key=lambda c: c["name"])


def is_production_ready(name: str) -> bool:
    c = get_candidate(name)
    return bool(c and c["stage"] == "production_recommendation")
