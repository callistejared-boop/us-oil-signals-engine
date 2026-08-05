# Broker Abstraction Layer Specification (Day 13)

Version: 1.0.0 | Date: 2026-08-04

## 1. Purpose and scope

The Broker Abstraction Layer (BAL) separates trading decisions from
execution providers. Before this Day, this platform's decision engine
(regime -> confluence -> confidence -> risk -> portfolio) produced an
approved signal and handed it straight to Telegram/the trade journal.
There was no concept of "submitting an order to a broker" anywhere in
the codebase — Day 12's execution simulator estimated what a fill
*would* cost, but nothing modeled the actual lifecycle of an order, a
position, or an account.

This package (`engine/broker/`) introduces that missing layer:

```
Decision Engine
      |
      v  (an already-approved trade)
alert_signals.py
      |
      v
Broker Abstraction Layer  (engine/broker/contract.py — Execution API v1)
      |
      +-- Paper Broker        (engine/broker/paper_broker.py — Day 13, THIS)
      +-- Live Broker Adapter (future — conforms to the same contract)
      +-- Replay Broker       (engine/broker/replay_broker.py — drives
                                Paper Broker from historical trades)
```

Every execution provider implements the identical interface
(`contract.BrokerInterface`). The Paper Broker is the first, and today
the only, implementation — but nothing above this layer needs to change
when a live adapter is added later.

## 2. Core design principles, and how each is satisfied

| Principle | How it's satisfied |
|---|---|
| Broker-agnostic architecture | `alert_signals.py` only ever calls `contract.BrokerInterface` methods (via the `PaperBroker` instance it holds) — never a Paper-Broker-specific method for anything the interface itself covers. |
| Interface-first design | `contract.py` was written and versioned (`CONTRACT_VERSION = "1.0.0"`) BEFORE `paper_broker.py`'s implementation, per the mandate's own recommendation. |
| Dependency inversion | The decision engine (`signals.py`/`confluence.py`/`confidence_engine.py`/`risk_guard.py`/`portfolio_risk.py`/`bias_adjust.py`) has ZERO imports of `engine.broker` — grep-verified, see DAY13_VALIDATION_REPORT.md. |
| Immutable execution records | `Order`/`Fill`/`PositionSnapshot`/`AccountSnapshot` are frozen dataclasses; `order_state.transition()` returns a NEW `Order` via `dataclasses.replace()`, never mutates in place. |
| Advisory mode by default | The broker layer is invoked AFTER every gate (regime/confluence/risk/portfolio) has already approved a trade — a broker-level rejection (e.g. simulated insufficient buying power) is recorded for research, never fed back into the gating pipeline. |
| Replay compatibility | `replay_broker.run_broker_replay()` drives `PaperBroker.submit_order()`/`close_position()` — the SAME two calls the live Stage-2 flow makes — against historical trades. |
| Independent testing | 155 new offline tests, zero network dependency, zero shared mutable state leakage between tests (see `tests/conftest.py`'s `broker_paths` fixture). |

## 3. Package structure

10 files, 1,988 lines:

| File | Lines | Role |
|---|---|---|
| `__init__.py` | 86 | Package docstring, governing principle, naming disambiguation |
| `contract.py` | 245 | Execution API v1: `BrokerInterface` ABC + request/response dataclasses + enums |
| `order_state.py` | 113 | Order lifecycle state machine — the only place that constructs/transitions `Order`s |
| `events.py` | 58 | Standardized execution event taxonomy + `emit()` |
| `broker_history.py` | 262 | Append-only JSONL persistence (orders/fills/events/account snapshots) |
| `position_engine.py` | 240 | Centralized, symbol-aggregate position tracking |
| `account.py` | 190 | `PaperAccount` + `AccountRegistry` — capital, leverage, margin, equity curve |
| `paper_broker.py` | 586 | `PaperBroker` — the first execution provider |
| `replay_broker.py` | 125 | Drives `PaperBroker` from historical trades, reproducibly |
| `research_bridge.py` | 83 | Keeps simulated/paper/live evidence sources separate |

## 4. The Execution API v1 contract

See `EXECUTION_API_DOCUMENTATION.md` for the full method-by-method
reference. Summary of the seven operations the mandate named, all on
`BrokerInterface`:

`submit_order`, `cancel_order`, `modify_order`, `get_order_status`,
`get_positions`, `get_balances`, `get_execution_reports`.

`contract.py`'s own module docstring states the versioning policy: any
future BREAKING change to this contract bumps `CONTRACT_VERSION`; a live
adapter declares which version it implements via
`BrokerInterface.contract_version`.

## 5. Order lifecycle

```
CREATED --> ACCEPTED --> WORKING --> FILLED            (terminal)
               |            |  \
               |            |   --> PARTIALLY_FILLED --> FILLED   (terminal)
               |            |                        \-> CANCELLED (terminal)
               |            |                        \-> EXPIRED   (terminal)
               |            +--> CANCELLED             (terminal)
               |            +--> EXPIRED               (terminal)
               +--> REJECTED                            (terminal)
```

Every transition is validated against `order_state.VALID_TRANSITIONS`
and persisted as its own row in `broker_orders.jsonl` — "Persist all
transitions" from the mandate is satisfied by writing one row per
transition, not just the final state, so an order's full history is
reconstructable by filtering on `order_id`.

Order-type resolution policy (see `paper_broker.py`'s module docstring
for the full reasoning):
- MARKET / STOP: resolve immediately on submission (FILLED,
  PARTIALLY_FILLED, or REJECTED — never left WORKING).
- LIMIT with a supplied `price_path`: resolves immediately,
  deterministically.
- LIMIT with no `price_path`: rests as a genuine WORKING order —
  cancellable, modifiable, and resolvable later via
  `check_working_orders()` or `expire_working_orders()`.

## 6. Position Engine

Aggregates fills into ONE net position per `(account_id, symbol)` —
the standard institutional OMS convention. Tracks average entry
(weighted on same-direction adds), realized P&L (accumulated across the
symbol's entire lifetime, not reset on each close), unrealized P&L
(computed on demand from a supplied mark price), fees, execution costs,
and the set of trade `ref`s contributing to the current position
(`open_refs`).

Known limitation, disclosed: if this platform ever holds two
independently-managed trades on the same symbol concurrently, their
fills blend into one aggregate position here — each individual fill
remains separately queryable via `broker_history.fills_for_order()`, but
the position VIEW is aggregated. See PAPER_BROKER_SPECIFICATION.md
Sec.7.

## 7. Account Model

`PaperAccount`: starting capital (default $10,000, illustrative),
leverage (default 30x, illustrative), risk-per-trade percentage
(default 1%, same convention `markets.sizing_lines()` already uses),
margin used, and a persisted equity curve (`broker_accounts.jsonl`).
`AccountRegistry` supports any number of independent named accounts —
the live `"paper-default"` account and any number of isolated research/
replay accounts (`replay-<profile>-<seed>-<uuid>` by default) never
share state.

## 8. Execution Events

Eight standardized event types, exactly the mandate's list:
`order_submitted`, `order_accepted`, `fill`, `partial_fill`,
`cancellation`, `rejection`, `position_opened`, `position_closed`. Every
event's payload is built from the SAME `Order`/`Fill`/`AccountSnapshot`
objects already returned to the caller — never a separately-computed
summary, per the mandate's "nothing should rely on opaque logs"
observability requirement.

## 9. Failure Handling

| Condition | Behavior | Documented recovery |
|---|---|---|
| `broker_unavailable` | REJECTED before any fill attempt | Safe to retry with the same `client_order_id` |
| `network_interruption` | REJECTED before any fill attempt | Safe to retry with the same `client_order_id` |
| `timeout` | REJECTED before any fill attempt | Safe to retry with the same `client_order_id` |
| `stale_quote` | REJECTED before any fill attempt | Refresh price, retry with a NEW `client_order_id` |
| `duplicate` submission | Idempotency check returns the ORIGINAL order, no new position | No action needed — this is the intended behavior |
| `zero_liquidity` / `missing_data` (market-condition, from Day 12's `fill_model`) | REJECTED with a disclosed reason | Same as above — retry once conditions clear |
| `stale_price` (market-condition) | Fill proceeds with a widened cost penalty, not blocked | No action needed |

All seven conditions are covered by dedicated tests in
`tests/test_paper_broker.py`. None of them ever raises an exception past
`PaperBroker`'s public methods — every failure mode degrades to a
returned `Order`/`dict` with a disclosed reason.

## 10. Replay Compatibility

`replay_broker.run_broker_replay()` drives a fresh `PaperBroker` through
historical trades using the EXACT same two calls (`submit_order()` /
`close_position()`) the live `alert_signals.py` Stage-2 flow makes — "no
separate replay-only fill logic exists anywhere in this module" (see
that file's own docstring). Reproducibility follows Day 12's convention:
one shared, seeded `random.Random(seed)` passed through to every fill.

## 11. Research Integration

`research_bridge.compare_evidence_sources()` returns simulated (Day 12,
retrospective, per-trade) and paper (Day 13, sequential, account-aware)
evidence SIDE BY SIDE, each tagged with its own `evidence_source`,
never merged into one series. `live` is always `None` today — reserved
for a future adapter. See RESEARCH_EXECUTION_MODEL.md's Day 12 honesty
note for the parallel precedent this follows.

## 12. Dashboard Integration

`dashboard_publish.py`'s payload gained a `"paper_trading"` key
(`engine.broker.paper_broker.dashboard_snapshot()`): account balances,
open positions, pending (resting) orders, and recent execution activity.
Advisory only — this key is symbol-agnostic (one shared paper account
across every symbol) and never influences `signal_payload`.

## 13. Assumptions and limitations (disclosed, not hidden)

1. No live broker connection exists. Every fill is a Day-12-modeled
   estimate, not a real one.
2. Positions aggregate per symbol, not per trade (Sec.6).
3. Margin is computed at trade time from average entry, not
   continuously repriced (a real broker's margin call/liquidation
   mechanics are NOT modeled).
4. No commission/fee schedule exists yet — `fee` is always `0.0`;
   spread+slippage (Day 12) is the only modeled transaction cost.
5. Account state is derived from `broker_history.jsonl` on every
   `PaperBroker.__init__()` (`rebuild_from_history()`), because this
   platform's scan loop is a fresh process roughly every 15 minutes —
   there is no long-lived daemon holding state in memory between scans.

## 14. Testing summary

155 new tests across 12 files (11 new + 3 appended to
`tests/test_dashboard_publish.py`), zero network dependency, zero
regressions against the Day 12 baseline of 1,049. See
DAY13_VALIDATION_REPORT.md for the full breakdown.
