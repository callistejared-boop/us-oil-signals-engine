# Developer Guide: Broker Abstraction Layer (Day 13)

Scoped to `engine/broker/` — a practical, code-first guide for anyone
extending or consuming this package. For architecture rationale see
BROKER_ABSTRACTION_SPECIFICATION.md; for the full API reference see
EXECUTION_API_DOCUMENTATION.md.

## Quick start: submit an order and check the result

```python
from engine.broker.paper_broker import PaperBroker
from engine.broker.contract import OrderRequest

broker = PaperBroker(account_id="paper-default")

order = broker.submit_order(OrderRequest(
    client_order_id="XAUUSD-2026-08-04T12:00:00",   # use journal.make_ref() in real callers
    account_id="paper-default", symbol="XAUUSD", side="buy",
    order_type="market", intended_price=2000.0, stop_price=1990.0,
    ref="XAUUSD-2026-08-04T12:00:00"))

print(order.status, order.quantity, order.avg_fill_price)

balances = broker.get_balances("paper-default")
positions = broker.get_positions("paper-default")
```

`quantity` was omitted above — it auto-sizes from 1% of the account's
current balance and the `entry`/`stop` distance (see
`account.AccountRegistry.position_size()`).

## Quick start: close a position

```python
result = broker.close_position("XAUUSD", "XAUUSD-2026-08-04T12:00:00", exit_price=2015.0)
print(result["closed"], result["realized_pnl_delta"])
```

## Quick start: run a historical replay

```python
from engine.broker.replay_broker import run_broker_replay

out = run_broker_replay(profile="typical", seed=42)   # reads trades.json by default
print(out["n_trades"], out["final_balances"])
```

Pass `rows=[...]` to replay a specific, in-memory list of trade dicts
instead of reading `trades.json` — the same offline-testing convention
every Day 9-13 module uses.

## Resting limit orders

```python
import pandas as pd

order = broker.submit_order(OrderRequest(
    client_order_id="c1", account_id="paper-default", symbol="XAUUSD",
    side="buy", order_type="limit", intended_price=1995.0, limit_price=1995.0,
    stop_price=1985.0, ref="ref-limit-1"))
assert order.status == "working"

# Later, once you have real subsequent bars:
path = pd.DataFrame({"Low": [1994.0], "High": [2001.0]})
changed = broker.check_working_orders("XAUUSD", path)   # fills if the level was reached

# Or cancel it outright:
broker.cancel_order("paper-default", order.order_id, reason="setup invalidated")
```

## Writing a new broker adapter

See EXECUTION_API_DOCUMENTATION.md's "Writing a new adapter" section.
The short version: subclass `contract.BrokerInterface`, implement all
seven methods, never raise past your own method boundaries. Nothing in
`alert_signals.py` or `dashboard_publish.py` needs to change to swap in
your adapter — they're written against `PaperBroker` today only because
it's the only provider that exists; both call sites use `_broker()`
(`alert_signals.py`) / `pbroker.dashboard_snapshot()`
(`dashboard_publish.py`) as their single point of contact, so pointing
either at a different provider is a one-line change.

## Common gotchas

1. **Units.** `Fill.execution_cost` is in PRICE units (same as
   `entry`/`stop`), not dollars. `PositionSnapshot.realized_pnl` IS in
   dollars. See PAPER_BROKER_SPECIFICATION.md Sec.3 if you're writing
   new P&L code.
2. **Idempotency is keyed on `client_order_id`, scoped to
   `account_id`.** Two different accounts can reuse the same
   `client_order_id` without colliding.
3. **Fresh `PaperBroker()` instances reconstruct state from
   `broker_history.jsonl`.** If you're writing a script that calls
   `PaperBroker()` in a loop, construct it ONCE outside the loop — each
   construction re-scans the persisted history (see
   PAPER_BROKER_SPECIFICATION.md Sec.6).
4. **`dataclasses.replace()`, not mutation.** `Order`/`Fill`/
   `PositionSnapshot`/`AccountSnapshot` are frozen. If you need to
   "change" one, you're constructing a new object — this is
   intentional, not a bug you should work around.
5. **`simulate_failure` is test/replay-only.** Never set it from a live
   code path; there is no code in this package that prevents you from
   doing so, but it would silently make your "live" submissions behave
   like injected failures.

## Testing conventions

See TESTING_GUIDE.md.
