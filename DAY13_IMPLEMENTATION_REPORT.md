# Day 13 Implementation Report — Broker Abstraction Layer (Paper Trading First)

Full specifications: `BROKER_ABSTRACTION_SPECIFICATION.md`,
`PAPER_BROKER_SPECIFICATION.md`, `EXECUTION_API_DOCUMENTATION.md`,
`DEVELOPER_GUIDE.md`, `TESTING_GUIDE.md`.

## New files

- `engine/broker/__init__.py` — package docstring, governing principle
  (decision engine never talks to a broker directly), naming
  disambiguation against `config.paper_mode` and
  `paper_trading_review.py`.
- `engine/broker/contract.py` — Execution API v1: `BrokerInterface` ABC
  (`submit_order`/`cancel_order`/`modify_order`/`get_order_status`/
  `get_positions`/`get_balances`/`get_execution_reports`) + frozen
  dataclasses (`OrderRequest`/`Order`/`Fill`/`PositionSnapshot`/
  `AccountSnapshot`) + enums (`OrderSide`/`OrderType`/`TimeInForce`).
- `engine/broker/order_state.py` — `OrderStatus` enum, `VALID_TRANSITIONS`
  graph, `new_order()`/`transition()` (the only two functions that
  construct or change an `Order`; `transition()` returns a new object via
  `dataclasses.replace()`), `InvalidTransition` exception.
- `engine/broker/events.py` — `EventType` taxonomy (the mandate's eight
  named events), `emit()`/`tail()`/`for_ref()`.
- `engine/broker/broker_history.py` — four append-only JSONL stores
  (`broker_orders.jsonl`/`broker_fills.jsonl`/`broker_events.jsonl`/
  `broker_accounts.jsonl`), each with the established self-rotating
  read/write pattern; `execution_reports()` merges orders+fills into one
  time-ordered feed.
- `engine/broker/position_engine.py` — `PositionEngine` class:
  symbol-aggregate position tracking (`on_fill()`, `unrealized_pnl()`,
  `margin_required()`, `snapshot()`, `open_positions()`,
  `rebuild_from_history()`), module-level `ENGINE` singleton.
- `engine/broker/account.py` — `PaperAccount` dataclass +
  `AccountRegistry` class (`get_or_create()`, `apply_realized_pnl()`,
  `reserve_margin()`/`release_margin()`, `snapshot()`,
  `record_equity_point()`, `position_size()`, `rebuild_from_history()`),
  module-level `REGISTRY` singleton.
- `engine/broker/paper_broker.py` — `PaperBroker` class, the platform's
  first `BrokerInterface` implementation (586 lines — order submission,
  resting-limit-order lifecycle, closing, `sync_closures()`,
  `dashboard_snapshot()`).
- `engine/broker/replay_broker.py` — `run_broker_replay()`: drives
  `PaperBroker` from historical trades via the same calls the live scan
  loop makes.
- `engine/broker/research_bridge.py` — `compare_evidence_sources()`:
  simulated (Day 12) vs. paper (Day 13) evidence, kept separately
  labeled, never merged.
- `tests/conftest.py` — the first shared pytest fixture file in this
  codebase (`broker_paths`), justified by `broker_history.py`'s four
  JSONL paths.
- `BROKER_ABSTRACTION_SPECIFICATION.md`, `PAPER_BROKER_SPECIFICATION.md`,
  `EXECUTION_API_DOCUMENTATION.md`, `DEVELOPER_GUIDE.md`,
  `TESTING_GUIDE.md` — full documentation set.
- 11 new test files + 3 tests appended to an existing file (155 tests
  total — see Testing section below).

## Modified files

- `alert_signals.py` — added `from engine.broker.contract import
  OrderRequest` import and a lazily-constructed, process-cached
  `_broker()` accessor (`_BROKER_CACHE`). Added
  `log_paper_broker_submission()` (called at Stage-2 entry, immediately
  after `log_execution_context()`, reusing the same `atr_pct`/
  `news_blackout`/`session` values already computed) and
  `sync_paper_broker_closures()` (called immediately after
  `journal.settle(df, symbol=sym)` at the top of the per-symbol loop).
  `build_entry()` gained a `broker=None` parameter and a `paper broker:`
  message line. The Stage-2 entry flow now passes `broker=e_broker` to
  `build_entry()` and `broker_ref=trade_ref` to `journal.log_signal()`.
- `engine/journal.py` — added `Trade.broker_ref` (default `""`, after
  `execution_ref`) and a `broker_ref=""` parameter to `log_signal()`,
  extending the unified-ID invariant to `id == regime_ref ==
  confluence_ref == confidence_ref == macro_ref == execution_ref ==
  broker_ref`. `Trade.entry`/`.stop`/`.target` were NOT touched.
- `engine/dashboard_publish.py` — added `from engine.broker import
  paper_broker as pbroker` import and a `"paper_trading"` payload key
  reading `pbroker.dashboard_snapshot()` (which converts every frozen
  dataclass to a plain dict before it reaches the payload).
- `engine/execution/replay.py` — added a public `approx_exit_price()`
  wrapper around the existing private `_approx_exit_price()`, so
  `paper_broker.sync_closures()` reuses the EXACT Day 12 reconstruction
  formula rather than duplicating it. The private function and its
  existing Day 12 tests are unchanged.
- `ARCHITECTURE_SPECIFICATION.md` — new §23.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 13" section.
- `tests/test_dashboard_publish.py` — 3 new tests appended for the
  `paper_trading` payload key (existing 15 tests unchanged).

**No other file was touched.** `engine/confluence.py`,
`engine/confidence_engine.py`, `engine/bias_adjust.py`,
`engine/risk_guard.py`, `engine/signals.py`, `engine/portfolio_risk.py`,
`engine/regime_engine.py`, and every Day 1-12 gating or scoring module
are byte-for-byte unchanged from the end of Day 12 — grep-verified (see
Validation Report).

## Explicit decisions made (documented, not silently resolved)

1. **Interface written and versioned before any implementation**, per
   the mandate's own explicit recommendation — `contract.py`'s
   `CONTRACT_VERSION = "1.0.0"` existed before a single line of
   `paper_broker.py` was written.
2. **Order-type resolution: MARKET/STOP resolve immediately; only LIMIT
   without a supplied price path rests as a genuine WORKING order.**
   This platform's own alert semantics mean market/stop trigger
   conditions are already met at signal time (the same reasoning Day
   12's `fill_model.py` used for the identical question). Making LIMIT
   orders genuinely restable (rather than resolving everything
   immediately) was a deliberate choice to give `cancel_order()`/
   `modify_order()` something real to operate on, not trivial no-ops.
3. **Positions aggregate per `(account_id, symbol)`, not per trade.**
   Standard institutional OMS convention. Disclosed as a known
   limitation (each fill's own `ref` is still individually traceable via
   `broker_history.fills_for_order()` — only the position VIEW is
   aggregated, not the underlying fill records).
4. **`rebuild_from_history()` added to both `PositionEngine` and
   `AccountRegistry`, called once per `PaperBroker.__init__()`.** This
   was NOT in the original design — it was added mid-Day after this
   Day's own smoke testing revealed that in-memory-only state would
   silently reset every account on each of this platform's ~15-minute
   fresh-process scan-loop invocations. See the Bug section below.
5. **Margin is reserved at fill time and released at close, using the
   position's own average entry — not continuously mark-to-market
   repriced.** A disclosed simplification; real brokers reprice margin
   continuously against current market value. No margin-call/
   liquidation mechanic exists as a consequence.
6. **No commission/fee schedule.** `Fill.fee` is always `0.0`.
   Spread+slippage (Day 12's `fill_model`) remains the only modeled
   transaction cost — adding a commission table was judged out of scope
   for this Day and left as an explicit backlog item.
7. **`research_bridge.compare_evidence_sources()` never merges simulated
   and paper evidence into one series**, per the mandate's explicit
   instruction — the two use different measurement methodologies
   (independent-per-trade vs. sequential account state) and combining
   them would produce a misleading number.
8. **The first `tests/conftest.py` in this codebase.** Justified
   explicitly: every prior file-backed history module had one JSONL path
   to monkeypatch; `broker_history.py` has four, needed identically by
   roughly a dozen new test files. This is additive — no existing test
   file's inline-patching convention was changed.

## Bug found and fixed during this Day's own work

**In-memory-only account/position state would have silently reset every
~15 minutes.** While smoke-testing `PaperBroker` end-to-end (submit an
order, close it, check the resulting balance), the FIRST draft of
`account.py`/`position_engine.py` held all state purely in Python
objects with no reconstruction step. A direct python -c test exposed
this immediately: submitting an order and closing it produced a correct
in-memory balance, but constructing a SECOND `PaperBroker` instance
against the same persisted `broker_history.jsonl` files (simulating a
fresh scan-loop process) showed the account back at its untouched
starting balance — the realized P&L from the close had not been applied
to the in-memory account object correctly, AND even where it had been,
nothing would have survived a real process restart.

Two related fixes were required: (1) `PositionEngine.rebuild_from_history()`
and `AccountRegistry.rebuild_from_history()` were added, called once at
`PaperBroker.__init__()`, replaying every persisted fill to reconstruct
correct position/balance state from the immutable JSONL trail; (2) a
narrower same-instance bug was also found and fixed — `close_position()`
was releasing margin correctly but never calling
`account.REGISTRY.apply_realized_pnl()`, so `get_balances()` showed a
stale balance for the REST of that same process's lifetime after a
close, even before the process-restart question came up. Both fixes were
verified via a dedicated smoke test comparing a same-instance balance
against a rebuilt-from-scratch one, and later formalized as
`tests/test_paper_broker.py::test_account_reconciliation_matches_after_process_restart`.

## Testing

155 new offline tests, zero live-network dependency:

| File | Tests |
|---|---|
| `tests/test_broker_contract.py` | 11 |
| `tests/test_broker_order_state.py` | 11 |
| `tests/test_broker_events.py` | 7 |
| `tests/test_broker_history.py` | 17 |
| `tests/test_broker_position_engine.py` | 18 |
| `tests/test_broker_account.py` | 15 |
| `tests/test_paper_broker.py` | 38 |
| `tests/test_replay_broker.py` | 12 |
| `tests/test_research_bridge.py` | 6 |
| `tests/test_journal_broker.py` | 5 |
| `tests/test_alert_signals_broker.py` | 12 |
| `tests/test_dashboard_publish.py` (+3 new) | 3 |
| **Total new** | **155** |

## What was explicitly NOT touched

- `engine/confluence.py`, `engine/confidence_engine.py`,
  `engine/bias_adjust.py`, `engine/risk_guard.py`, `engine/signals.py`,
  `engine/portfolio_risk.py`, `engine/regime_engine.py` — zero changes.
- Every Day 1-12 engine module besides the four integration touch points
  listed above — zero changes.
- `trades.json` — zero changes; no broker submission writes to the trade
  journal itself, only to the new `broker_orders.jsonl`/
  `broker_fills.jsonl`/`broker_events.jsonl`/`broker_accounts.jsonl`
  (none of which exist on disk at the end of this Day — same convention
  as `execution_history.jsonl`/`macro_history.jsonl` at prior Days' close).
- `Trade.entry`/`.stop`/`.target` — never overwritten with a simulated
  fill price on any trade, past or newly logged.
- `engine/execution/*.py`'s existing Day 12 behavior — only one public
  wrapper function (`approx_exit_price()`) was added; every existing
  Day 12 function, constant, and test is unchanged.
- No threshold, confidence score, confluence score, macro label, or
  gating decision changed as a result of this Day's work.
