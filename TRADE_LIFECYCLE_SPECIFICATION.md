# Trade Lifecycle — Signal-to-Outcome Unified Schema (Priority 5 Item 3)

## Problem

Before this change, one opportunity's story was split across four systems that were each built for a different purpose and never designed to be read together:

| System | What it tracks | What it's missing |
|---|---|---|
| `decision_audit_history.py` | One immutable snapshot per decision (`decision_id`) | No link between a heads-up decision and the trade it eventually became, or didn't |
| `pending.py` | Two-stage watch-list (`entry`/`void` events) | Events are returned to the caller but never themselves persisted anywhere |
| `journal.py` | `Trade.status`, mutated in place by `settle()` | No history of *how* it got there, just the current flat string |
| `broker/order_state.py` | A clean validated state machine | Scoped to broker `Order` objects only, not signals |

No module could answer "what happened to this opportunity, from the moment it was detected to the moment it was learned from, in order." In particular, a "setup voided" event (a pending setup that aged out without ever tapping) was previously logged as a single plain-text line and nowhere else — it vanished from any queryable history.

## Design

`engine/trade_lifecycle.py` reuses `engine/broker/order_state.py`'s exact validated-transition pattern rather than inventing a new one: an immutable, frozen `LifecycleRecord` dataclass, a `VALID_TRANSITIONS` adjacency dict, a pure `transition()` function returning a new record via `dataclasses.replace()` with the move appended to an append-only `history` tuple, and an `InvalidTransition` exception for any move not in the graph.

On top of that state machine sits a persistence layer mirroring `decision_audit_history.py`'s own JSONL append/rotate/tail convention (`trade_lifecycle.jsonl`) — every `transition()` result is written as a fresh, full row, so the last row for a given `lifecycle_id` is always that chain's complete current state.

### Stage graph

```
DETECTED --> QUALIFIED --> PENDING --> ENTERED --> MANAGING --> CLOSED --> LEARNED
    |            |            |
    +-> REJECTED-+------------+
                               |
                               +-> VOIDED
```

REJECTED is reachable from DETECTED, QUALIFIED, or PENDING — this module does not encode *why* by stage name; the `reason=` string and the upstream `decision_audit_history` row carry that detail. VOIDED is reserved specifically for a pending setup aging out (`pending.MAX_WAIT_BARS`) without ever tapping, distinguishing a natural-expiry outcome from a gate rejection. MANAGING and LEARNED are defined in the state machine but not yet populated by any wiring — `journal.settle()` only observes a trade at its close, not at intermediate break-even/partial events, and no post-trade-review write exists yet to record LEARNED. Both slots exist so a later day's work can populate them without another schema change.

### The identity insight

`decision_audit_history`'s `decision_id`, `pending.Pending.id`, and `journal.Trade.id` were already, by construction, built from the identical `f"{symbol}-{timestamp}"` format (`journal.make_ref()`) at the same call sites with the same `when` value — they just had never been treated as the same key across modules. `trade_lifecycle.py` introduces no new ID scheme; `lifecycle_id` is simply whichever of those three was assigned first for a given opportunity, confirmed identical in `tests/test_alert_signals_lifecycle_integration.py::test_lifecycle_id_matches_pending_id_and_decision_id_construction`.

## Wiring (advisory-only, additive)

Twelve call sites in `alert_signals.py`, each wrapped in the same fail-safe posture as every other `log_*`/`sync_*` helper in this codebase (never raises past its own boundary):

1. `s1_lifecycle_id = journal.make_ref(sym, when)` computed once, right after a Stage-1 signal is confirmed and dedup-checked.
2. Regime-gate rejection -> `tl.seed_rejected()` (DETECTED -> REJECTED in one call).
3. Confluence rejection -> `tl.seed_rejected()`.
4. Confluence pass -> `tl.seed_qualified()` (DETECTED -> QUALIFIED).
5. Heads-up-stage portfolio risk rejection -> `tl.mark_rejected()`.
6. `pending.add()` -> `tl.mark_pending()` (QUALIFIED -> PENDING).
7. Pending-resolution risk-lock rejection -> `tl.mark_rejected(rec["id"], ...)`.
8. Pending-resolution portfolio risk rejection -> `tl.mark_rejected(rec["id"], ...)`.
9. Successful entry (`journal.log_signal()`) -> `tl.mark_entered(rec["id"], trade_ref, ...)` (PENDING -> ENTERED, `trade_ref` set atomically).
10. Void resolution -> `tl.mark_voided(rec["id"], ...)` (PENDING -> VOIDED) — this is the event that previously had zero persistence.
11. New `sync_lifecycle_closures(sym)` helper, called right after `journal.settle()` at the same call site as the existing `sync_paper_broker_closures(sym)` — scans closed `trades.json` rows for `sym` and closes any lifecycle chain with a matching `trade_ref` that isn't already CLOSED/LEARNED (idempotent, mirrors `PaperBroker.sync_closures()`'s exact "already done" check).
12. `research_dashboard.build_research_payload()` gained a `lifecycle_stage_summary` key (current stage counts across recent chains, via the new `tl.stage_summary()`).

None of `journal.py`, `pending.py`, or `decision_audit_history.py`'s own existing state was touched, replaced, or read from any gate — `trade_lifecycle.jsonl` is a new, independent, purely observational overlay.

## Known limitation (disclosed)

`decision_id` (built by `explainability_engine.build_decision_snapshot()`) and `Pending.id` share the same base format but the former does not apply `journal.make_ref()`'s `-dup2`/`-dup3` collision-disambiguation suffix. In the rare case of two distinct Stage-1 signals for the same symbol at the exact same candle timestamp, the two IDs could in principle diverge. This has not been observed in practice (confirmed identical across all 47 module tests and the dedicated construction-equality test), and the practical effect of a divergence would only be a chain seeding defensively (`mark_pending()`/`mark_entered()`'s documented fallback path) rather than a crash or data loss.

## Testing

`tests/test_trade_lifecycle.py` (47 tests): pure state-machine transitions and their validation, persistence round-trips, all seven high-level helper functions, `sync_closures()` idempotency and error handling, `stage_summary()` aggregation, and a full end-to-end DETECTED-through-CLOSED and DETECTED-through-VOIDED chain via the persistence layer.

`tests/test_alert_signals_lifecycle_integration.py` (4 tests): the `sync_lifecycle_closures()` wrapper's logging/error behavior, and the cross-module ID-construction equality this whole design depends on.

`tests/test_research_dashboard.py` (+2 tests): the new `lifecycle_stage_summary` payload key.

Full suite: 1654/1654 passing.
