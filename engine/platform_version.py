"""Day 8 — Platform/version traceability (see EXPLAINABILITY_SPECIFICATION.md
Sec.5 "Version Traceability").

Single source of truth for "what version of the platform produced this
decision." Before Day 8, only two modules (`confidence_engine.py`,
`market_memory.py`, both introduced Day 6/7) carried an explicit `VERSION`
constant — every other engine module was, honestly, unversioned. This
module does two things:

1. Declares `PLATFORM_VERSION` and `ARCHITECTURE_VERSION` — platform-wide
   version identifiers bumped by convention each Day a major capability
   lands (NOT strict SemVer against a public API — there isn't one; this is
   an internal traceability marker, documented as such rather than
   overclaiming a versioning discipline that doesn't exist yet).
2. `component_versions()` walks the small set of engine modules that matter
   to a trading decision and reads each one's own `VERSION` constant where
   it exists — reporting `"unversioned"` HONESTLY for modules that don't
   declare one, rather than fabricating a number. Four core decision-path
   modules (`signals.py`, `regime_engine.py`, `confluence.py`,
   `portfolio_risk.py`) had a `VERSION = "1.0.0"` (or, for regime_engine,
   `"2.0.0"` matching its own "V2" docstring label) added this Day
   specifically to close this gap — see DAY8_IMPLEMENTATION_REPORT.md
   decision log for why these four and not every module in the codebase.

Reused, not duplicated: `confidence_engine.VERSION`/`market_memory.VERSION`
are read directly from those modules' own already-declared constants, never
re-declared here.
"""
from __future__ import annotations

import importlib

# Bumped by convention on each Day a major capability lands. "0.8.0" reflects
# eight Day-numbered capability milestones (Day 1-2 baseline through Day 8
# Explainability & Decision Audit) — see PROJECT_SUMMARY_AND_ROADMAP.md and
# ARCHITECTURE_SPECIFICATION.md's own §-per-Day structure, which this number
# deliberately mirrors so the two stay easy to cross-reference.
PLATFORM_VERSION = "0.8.0"

# Tracks ARCHITECTURE_SPECIFICATION.md's own section count for the "core
# decision architecture" (§13-§18, Day 3-8) — bumped alongside that document,
# not independently.
ARCHITECTURE_VERSION = "0.8.0"

# Modules whose own declared (or, honestly, undeclared) VERSION constant is
# meaningful to a trading decision's explainability — deliberately NOT every
# module in engine/ (most are low-level math/IO helpers with no independent
# versioning story; see EXPLAINABILITY_SPECIFICATION.md Sec.5 for the scoping
# rationale, matching every prior day's "smallest evidence set" discipline).
COMPONENT_MODULES = [
    "engine.signals",            # Layer 1 ICT/SMC origination ("strategy version")
    "engine.regime_engine",      # Day 4 Market Regime Engine
    "engine.confluence",         # Day 5 MAST confluence scoring
    "engine.portfolio_risk",     # Day 3 Portfolio Risk Engine
    "engine.confidence_engine",  # Day 6 Confidence Engine
    "engine.market_memory",      # Day 7 Market Memory Engine
]


def component_versions() -> dict:
    """{module_name: version_string | "unversioned"}. Never raises — an
    import failure for any one module reports "unavailable" for that module
    only, never blocks the others."""
    out = {}
    for mod_name in COMPONENT_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            out[mod_name] = getattr(mod, "VERSION", "unversioned")
        except Exception as exc:  # noqa: BLE001
            out[mod_name] = f"unavailable ({exc})"
    return out


def snapshot() -> dict:
    """The full version-traceability record attached to every
    DecisionSnapshot (see engine/explainability_engine.py). Never raises."""
    return {
        "platform_version": PLATFORM_VERSION,
        "architecture_version": ARCHITECTURE_VERSION,
        "components": component_versions(),
    }
