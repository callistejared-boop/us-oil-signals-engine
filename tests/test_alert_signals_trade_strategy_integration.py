"""Integration test: alert_signals.py's Stage-2 entry journal.log_signal()
call site stamps Trade.strategy via engine.strategy_registry.strategy_for()
(V2.2 Priority 2 Item 4), resolved from the same `regime_strategy` value
already used for regime classification and execution-style resolution —
NOT a raw/unvalidated pass-through, so an unknown or malformed
regime_strategy value still resolves to a safe, known strategy_id rather
than persisting garbage into the journal.
"""
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine import strategy_registry as sr  # noqa: E402


def test_main_call_site_passes_strategy_registry_resolved_id():
    # Source-level guard: the journal.log_signal() call inside main()'s
    # Stage-2 entry branch must pass `strategy=` resolved through
    # strategy_registry.strategy_for(), not a raw regime_strategy string
    # and not omitted entirely. Prevents a future edit from silently
    # dropping the Trade.strategy wiring.
    src = pathlib.Path(als.__file__).read_text(encoding="utf-8")
    assert src.count(
        'strategy=strategy_registry.strategy_for(\n'
        '                                               regime_strategy)["strategy_id"])'
    ) == 1


def test_strategy_for_known_id_resolves_to_itself():
    # The platform's one production strategy today: regime_strategy's
    # default value round-trips through the registry unchanged.
    assert sr.strategy_for("ict_smc_mast")["strategy_id"] == "ict_smc_mast"


def test_strategy_for_unknown_regime_strategy_falls_back_safely():
    # If config.regime_strategy were ever misconfigured to an unregistered
    # value, strategy_for() must still resolve to a known, safe strategy_id
    # (never raise, never persist an arbitrary unvalidated string).
    entry = sr.strategy_for("some_unregistered_value")
    assert entry["strategy_id"] == sr.DEFAULT_STRATEGY_ID
    assert entry["strategy_id_requested"] == "some_unregistered_value"
