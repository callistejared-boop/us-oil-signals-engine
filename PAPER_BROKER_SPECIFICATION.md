# Paper Broker Specification (Day 13)

Version: 1.0.0 | Date: 2026-08-04

Companion to `BROKER_ABSTRACTION_SPECIFICATION.md` (the interface-level
design) and `EXECUTION_SIMULATOR_SPECIFICATION.md` (Day 12, the fill
model this Paper Broker consumes). This document is specific to
`engine/broker/paper_broker.py`'s own behavior.

## 1. What the Paper Broker is, precisely

`PaperBroker` is `contract.BrokerInterface`'s first implementation. It
is a REALISTIC SIMULATION of a broker, built entirely on Day 12's
disclosed spread/slippage/latency assumption models
(`engine.execution.fill_model`) — it is not connected to any real
account, and every price/cost/fill it produces is labeled
`is_estimate: True`. "Paper" here refers to the same "forward-test, no
real money" convention `config.paper_mode` has used since Day 1 — but
this is the first module that actually SIMULATES an account rather than
just tagging a Telegram message.

### Naming disambiguation (repeated from `engine/broker/__init__.py` — important enough to restate)

- `config.paper_mode` (Day 1-2): boolean flag, tags alerts "FORWARD TEST
  (paper)". No execution model.
- `engine.paper_trading_review.py` (Day 9): a decision-AUDIT synthesis
  layer over Day 8's DecisionSnapshot trail. No account, no fills.
- `engine.broker.paper_broker.PaperBroker` (Day 13, this): a full
  execution provider with order lifecycle, positions, and a virtual
  account.

These three never call each other and measure different things.

## 2. Reuse, not reimplementation

Every fill this broker produces comes from
`engine.execution.fill_model.simulate_fill()` — the exact function
`execution_report.py` (Day 12) already uses. No spread/slippage/latency
constant is duplicated or re-derived here. Contract size (`mult`) is
read from `engine.markets.MARKETS` — the same table
`markets.sizing_lines()` already uses for its own Telegram sizing lines.
Position-sizing risk convention (1% of equity / stop distance) is the
identical formula `markets.sizing_lines()` uses, now applied against a
LIVE account balance instead of three fixed illustrative account sizes.

## 3. Units (read before touching any P&L code)

`fill_model.simulate_fill()` reports `execution_cost` in PRICE units
(same units as `entry`/`stop` — e.g. dollars-per-ounce for gold).
Everything in `position_engine.py`/`account.py` is in DOLLAR units
(realized/unrealized P&L, balance, margin). `paper_broker.py`'s
`_dollar_cost()` is the ONE place this conversion happens:

```
dollar_cost = abs(price_units_cost) * quantity_filled * MARKETS[symbol]["mult"]
```

## 4. Order-type behavior

| Order type | Resolution | Notes |
|---|---|---|
| MARKET | Immediate | Trigger condition already met at signal time (this platform's own alert semantics) |
| STOP | Immediate | Modeled like MARKET but with wider, more adverse-skewed slippage (Day 12's `fill_model`) — represents an already-triggered stop, not a pending one |
| LIMIT + `price_path` supplied | Immediate, deterministic | Did price actually reach the limit level in the supplied bars |
| LIMIT, no `price_path` | Rests as WORKING | Resolved later via `check_working_orders()`, or terminated via `cancel_order()`/`expire_working_orders()` |

## 5. Margin formula (disclosed, illustrative)

```
margin_required = quantity_lots * price * MARKETS[symbol]["mult"] / leverage
```

Standard retail CFD/forex margin convention. NOT fitted to, or claimed
to match, any specific real broker's margin schedule. Margin is reserved
at fill time (using the fill price) and released in full at close
(using the position's average entry) — this is a simplification: real
brokers continuously reprice margin against current market value
(mark-to-market), which this Day does not model.

## 6. Persistence Model — why `rebuild_from_history()` exists

This platform's scan loop (`alert_signals.py`) is invoked as a FRESH
PROCESS roughly every 15 minutes (cron/GitHub-Actions-scheduled) — there
is no long-lived daemon holding position/account state in memory between
scans. Without a rebuild step, every new process would start every
account flat and silently lose all prior open exposure and realized P&L.

`PaperBroker.__init__()` therefore calls, in order:
1. `position_engine.ENGINE.rebuild_from_history(account_id)` — replays
   every persisted fill for this account, in timestamp order, to
   reconstruct current positions and lifetime realized P&L.
2. `account.REGISTRY.rebuild_from_history(account_id)` — derives
   `balance` (`starting_capital + realized_pnl - fees`) and
   `margin_used` (sum of `margin_required()` over currently-open
   positions) from the just-rebuilt position state.

This makes `broker_history.jsonl`'s immutable JSONL trail the actual
source of truth, and the in-memory `PositionEngine`/`AccountRegistry`
singletons a correct, deterministic CACHE over it — verified in
`tests/test_paper_broker.py::test_account_reconciliation_matches_after_process_restart`.

`alert_signals.py` caches one `PaperBroker` per `(account_id, process)`
(`_broker()`) so this rebuild only runs ONCE per scan, not once per
symbol.

## 7. Known limitations (disclosed)

1. **Symbol-aggregate positions, not per-trade.** Two independently-
   managed same-symbol trades open at the same time blend into one net
   position. Each fill's own `ref` is still recorded (`open_refs`), so
   no traceability is lost — only the position VIEW is aggregated. This
   matches how most real brokers/OMS net exposure by default.
2. **No commission schedule.** `fee` is always `0.0`. Spread+slippage
   (Day 12) is the only modeled transaction cost. A future Day could add
   a disclosed, illustrative commission table if useful.
3. **No margin call / liquidation logic.** A real broker would force-
   close a position if margin usage breaches a maintenance threshold;
   this Day's Paper Broker has no such mechanism (an order is simply
   rejected pre-trade if buying power is insufficient — nothing happens
   post-trade if unrealized losses erode equity below margin
   requirements).
4. **Resting limit orders never auto-expire on their own.** A WORKING
   limit order stays WORKING until explicitly cancelled, filled via
   `check_working_orders()`, or expired via `expire_working_orders()` —
   there is no time-based auto-expiry (`time_in_force` is accepted by
   the contract but not yet enforced by a clock).
5. **`_reconstruct()`'s status-query view is lossy.** Once an order
   leaves the in-memory `_working` cache, `get_order_status()` rebuilds
   a lightweight `Order` from the latest persisted transition row —
   `fills`/full `history` are not restored, only the current state. Full
   fill detail remains available via `broker_history.fills_for_order()`.

## 8. `alert_signals.py` Integration

Stage-2 entry flow, in order (same placement pattern as every prior
Day's advisory subsystem):

```
log_macro_context()          (Day 11)
log_execution_context()      (Day 12)
log_paper_broker_submission() (Day 13, NEW)  <- submits ENTRY only
log_confidence_assessment()  (Day 6)
log_decision_snapshot()      (Day 8)
_send() the Telegram alert (build_entry() now includes a "paper broker:" line)
journal.log_signal(..., broker_ref=trade_ref)
```

Separately, at the TOP of each symbol's scan iteration, immediately
after `journal.settle(df, symbol=sym)`:

```
sync_paper_broker_closures(sym)   -> PaperBroker.sync_closures(sym)
```

This closes the Paper Broker's aggregate position for any trade
`journal.settle()` just marked win/loss/scratch/expired, using the exact
same exit-price reconstruction (`engine.execution.replay.approx_exit_price()`)
Day 12's replay tooling uses.

## 9. Dashboard

`dashboard_publish.py`'s `"paper_trading"` payload key
(`pbroker.dashboard_snapshot()`): account balances, open positions,
pending orders, and the last 10 execution-report rows. Identical across
every symbol's payload (one shared account) — see that function's own
docstring for why.

## 10. Testing

38 dedicated `PaperBroker` tests in `tests/test_paper_broker.py`
covering: basic fills, idempotency (same-instance and cross-process),
auto-sizing, insufficient buying power, resting limit orders (submit /
check_working_orders / cancel / modify / expire), closing + realized
P&L, `sync_closures` (including double-close prevention), status
reconstruction, execution-report queries, multi-symbol and multi-account
concurrency isolation, partial fills, all seven documented failure
modes, and account reconciliation across a simulated process restart.
