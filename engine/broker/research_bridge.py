"""Day 13 — Research Integration: keeping evidence sources separate.

Per the mandate: "Extend the research framework to distinguish clearly
between: simulated execution, paper execution, future live execution. Do
not merge these datasets. Each evidence source should remain
identifiable."

This module is deliberately thin — it does NOT introduce a new
statistics engine. It calls the two things that already exist and
returns them side by side, each labeled with its own `source`, rather
than blending their numbers into one series:

  - SIMULATED  — `engine.execution.comparison.compare_layers()` (Day 12):
    a purely RETROSPECTIVE fill simulation applied to each trade's
    already-stored `result_r`. No account, no position aggregation, no
    sequencing — every trade is evaluated independently.
  - PAPER      — `engine.broker.replay_broker.run_broker_replay()`
    (Day 13): actually drives a `PaperBroker` through the SAME trades in
    chronological order, with a real account (starting capital,
    leverage, margin) and a real AGGREGATE position per symbol. Realized
    P&L here reflects sequencing and position-netting effects the
    simulated layer cannot see (e.g. two same-symbol trades overlapping
    in time blend into one position — see `position_engine.py`'s
    docstring).
  - LIVE       — always `None` today. No live broker connection exists.
    Reserved so a future Day's live adapter has an obvious place to
    plug in without changing this function's shape.

WHY these are not merged into one number: the simulated layer's
per-trade R-multiples and the paper layer's account-level realized P&L
are not computed the same way (independent-per-trade vs. sequential
account state), so summing or averaging them together would silently mix
two different measurement methodologies into one misleading figure. Read
them side by side instead — where they roughly agree, that is itself a
useful research signal; where they diverge, the divergence is likely
telling you something about position-netting or sequencing effects, not
noise to be averaged away.
"""
from __future__ import annotations

from engine.execution import comparison as sim_comparison

from . import replay_broker as rb

VERSION = "1.0.0"

EVIDENCE_SOURCES = {
    "simulated": "engine.execution.comparison.compare_layers (Day 12) — retrospective, "
                "per-trade, no account/position state",
    "paper": "engine.broker.replay_broker.run_broker_replay (Day 13) — PaperBroker-driven, "
            "sequential, account/position-aware",
    "live": "not yet implemented — reserved for a future live broker adapter (see Version 2.1 roadmap)",
}


def compare_evidence_sources(rows: "list | None" = None, symbol: "str | None" = None,
                             profile: str = "typical", seed: int = 42,
                             account_id: "str | None" = None) -> dict:
    """Returns the simulated and paper evidence side by side, each
    clearly labeled and never combined into one series. Never raises —
    either half degrading independently is preferable to the whole
    comparison failing."""
    try:
        simulated = sim_comparison.compare_layers(rows=rows, symbol=symbol, profile=profile, seed=seed)
    except Exception as exc:  # noqa: BLE001
        simulated = {"error": f"simulated layer error: {exc}"}
    try:
        paper = rb.run_broker_replay(rows=rows, symbol=symbol, account_id=account_id,
                                     profile=profile, seed=seed)
    except Exception as exc:  # noqa: BLE001
        paper = {"error": f"paper layer error: {exc}"}

    return {
        "evidence_sources": EVIDENCE_SOURCES,
        "simulated": {**simulated, "evidence_source": "simulated"},
        "paper": {**paper, "evidence_source": "paper"},
        "live": None,
        "note": ("Simulated and paper evidence are DELIBERATELY NOT MERGED — see this module's "
                "docstring for why summing/averaging them would be misleading. Compare them side "
                "by side; treat agreement as corroboration and divergence as a prompt to "
                "investigate position-netting/sequencing effects, not as noise."),
        "is_estimate": True, "source": "engine.broker.research_bridge",
    }
