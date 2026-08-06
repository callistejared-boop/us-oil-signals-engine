"""Strategy Registry (V2.2 — metadata layer, before Trade.strategy schema).

The platform has ONE production origination path today: ICT/SMC signal
generation (`signals.py`) confirmed by MAST confluence (`confluence.py`),
identified elsewhere in this codebase by the string `"ict_smc_mast"` —
the same value `config.regime_strategy` already uses to select an entry
in `engine.regime_engine.STRATEGY_COMPATIBILITY`. This module gives that
one strategy (and any future ones) a small metadata record — today just
a trading `style` used to look up an `engine.execution.execution_profile`
tolerance profile — instead of the flat, single global `config.
execution_style` setting that stood in for it (see that field's own
docstring: "Superseded per-strategy once the Strategy Registry ... exists").

SCOPE, DELIBERATELY NARROW. This is the metadata-only precursor slice
described in STRATEGY_FRAMEWORK_SPECIFICATION.md Sec.2 ("should NOT be
done piecemeal ... deserves its own dedicated implementation Day") —
it is NOT that full `StrategyProfile` dataclass (20+ fields: regime
compatibility, position sizing, confluence weighting, etc.), and it
does NOT add a `strategy` column/field to `Trade`, the journal, or any
history file. Both of those remain a separate, later, dedicated roadmap
item (VERSION_2.2_ROADMAP.md Priority 2 Item 4, sequenced together with
the `origination_method` rename so the two ship in the same Day).

NOT THE SAME "STRATEGY" AS `regime_strategy`. `config.regime_strategy`
and this registry happen to share a key (`"ict_smc_mast"`) today because
there is only one strategy, but they answer different questions:
`regime_strategy` says which regime-compatibility table entry to score
market conditions against (engine.regime_engine); this registry says
which execution-quality tolerance style a strategy's fills are held to
(engine.execution.execution_profile). Do not merge the two concepts —
a future strategy could reuse one `regime_strategy` entry under two
different execution styles, or vice versa.

Fail-safe posture matches every other subsystem here: `strategy_for()`
and `execution_style_for()` never raise and always resolve to a usable
default (config.execution_style, then the hardcoded "day" default),
mirroring `execution_profile.profile_for()`'s own unknown-key fallback.
"""
from __future__ import annotations

VERSION = "1.0.0"

DEFAULT_STRATEGY_ID = "ict_smc_mast"

# One entry today, matching the platform's single production origination
# path. `style` names an engine.execution.execution_profile.PROFILES key
# ("swing" | "day" | "scalping") — see that module for what each style
# tolerates. Adding a second strategy is a dict entry, not a code change,
# matching regime_strategy's own "config value, not code branch" posture.
STRATEGIES = {
    "ict_smc_mast": {
        "strategy_id": "ict_smc_mast",
        "name": "ICT/SMC signal origination + MAST confluence",
        # This platform is Telegram-alert + human-manual-execution, not
        # auto-trading (see EXECUTION_SIMULATOR_SPECIFICATION.md Sec.5) —
        # "day" is the closest existing execution_profile style to that
        # reality's typical tens-of-seconds fill latency; "scalping"'s
        # 3s tolerance would fail nearly every real fill (see the Item 3
        # research finding logged in VERSION_2.2_ROADMAP.md).
        "style": "day",
        "notes": ("The platform's sole production strategy as of V2.2. "
                 "See STRATEGY_FRAMEWORK_SPECIFICATION.md Sec.9 step 2 for "
                 "how a second, differently-styled strategy would be added "
                 "here first, before any StrategyProfile/Trade.strategy work."),
    },
}


def strategy_for(strategy_id: str | None = None) -> dict:
    """Look up a strategy's registry entry. Falls back to
    DEFAULT_STRATEGY_ID when `strategy_id` is None or not found — never
    raises, matching execution_profile.profile_for()'s own fallback
    posture. The returned dict always carries `strategy_id_requested` so
    callers/tests can distinguish an exact hit from a fallback."""
    try:
        key = strategy_id or DEFAULT_STRATEGY_ID
        entry = STRATEGIES.get(key) or STRATEGIES[DEFAULT_STRATEGY_ID]
        out = dict(entry)
        out["strategy_id_requested"] = strategy_id
        return out
    except Exception:  # noqa: BLE001
        return {"strategy_id": DEFAULT_STRATEGY_ID, "name": "", "style": "day",
                "notes": "", "strategy_id_requested": strategy_id}


def execution_style_for(strategy_id: str | None = None, settings=None) -> str:
    """Resolve the execution_profile style to evaluate a trade's fill
    against, for the given strategy. Resolution order: (1) the
    registry entry's own `style`, if `strategy_id` names a KNOWN
    strategy; (2) `settings.execution_style`, the pre-Registry global
    interim value, if `strategy_id` is unset/unknown; (3) the hardcoded
    "day" default. This lets an operator's existing .env EXECUTION_STYLE
    override keep working unchanged for the single strategy that exists
    today, while giving a future second strategy its own registry-driven
    value without touching config.py again. Never raises."""
    try:
        if strategy_id and strategy_id in STRATEGIES:
            return STRATEGIES[strategy_id]["style"]
        if settings is not None:
            style = getattr(settings, "execution_style", None)
            if style:
                return str(style)
        return "day"
    except Exception:  # noqa: BLE001
        return "day"
