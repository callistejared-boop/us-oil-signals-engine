# Execution API v1 Documentation (Day 13)

Version: 1.0.0 (`engine.broker.contract.CONTRACT_VERSION`) | Date: 2026-08-04

Full reference for `engine/broker/contract.py`. This is the versioned,
broker-neutral contract every execution provider — `PaperBroker` today,
a live adapter later — implements.

## Enums

### `OrderSide`
| Value | Meaning |
|---|---|
| `BUY` = `"buy"` | Opens/adds to a long, or closes/reduces a short |
| `SELL` = `"sell"` | Opens/adds to a short, or closes/reduces a long |

### `OrderType`
| Value | Meaning |
|---|---|
| `MARKET` = `"market"` | Resolves immediately |
| `LIMIT` = `"limit"` | Rests until the limit price is reached (or resolves immediately if `price_path` is supplied) |
| `STOP` = `"stop"` | Resolves immediately, modeled as already-triggered |

### `TimeInForce`
| Value | Meaning |
|---|---|
| `GTC` = `"gtc"` | Good-till-cancelled — the Paper Broker's default resting behavior |
| `IOC` = `"ioc"` | Immediate-or-cancel — accepted by the contract; not yet enforced by `PaperBroker` (disclosed limitation, see PAPER_BROKER_SPECIFICATION.md Sec.7) |
| `DAY` = `"day"` | Treated as GTC by the Paper Broker (no session-close sweep yet) |

## `OrderRequest` (what a caller submits)

| Field | Type | Required | Notes |
|---|---|---|---|
| `client_order_id` | `str` | yes | Idempotency key. This platform always passes the unified trade `ref` |
| `account_id` | `str` | yes | |
| `symbol` | `str` | yes | |
| `side` | `str` | yes | `OrderSide.BUY`/`.SELL` |
| `order_type` | `str` | yes | `OrderType.MARKET`/`.LIMIT`/`.STOP` |
| `intended_price` | `float` | yes | |
| `quantity` | `float \| None` | no | `None` = auto-size from account risk |
| `stop_price` | `float \| None` | no | Required if `quantity` is `None` (used for auto-sizing) |
| `limit_price` | `float \| None` | no | Required for LIMIT orders |
| `time_in_force` | `str` | no | Default `GTC` |
| `signal_ts` | `datetime \| None` | no | |
| `ref` | `str` | no | Unified trade ID, also used for research joins |
| `atr_pct` | `float \| None` | no | Passthrough to `fill_model` |
| `news_blackout` | `bool` | no | Passthrough to `fill_model` |
| `session` | `str \| None` | no | Passthrough to `fill_model` |
| `price_path` | object | no | Optional real subsequent bars for deterministic limit fills |
| `simulate_failure` | `dict \| None` | no | TEST/REPLAY ONLY — never set by the live call site |

`simulate_failure` recognized keys: `broker_unavailable`,
`network_interruption`, `timeout`, `stale_quote` (broker-infrastructure,
rejected before any fill attempt); `zero_liquidity`, `missing_data`,
`stale_price` (market-condition, passed through to `fill_model`).

## `Order` (what every method returns)

| Field | Type |
|---|---|
| `order_id` | `str` (`ord-<16 hex>`) |
| `client_order_id`, `account_id`, `symbol`, `side`, `order_type` | `str` |
| `intended_price`, `quantity` | `float` |
| `status` | `str` — one of `order_state.OrderStatus.ALL` |
| `stop_price`, `limit_price` | `float \| None` |
| `time_in_force`, `ref` | `str` |
| `filled_quantity` | `float` |
| `avg_fill_price` | `float \| None` |
| `fills` | `tuple[Fill, ...]` |
| `history` | `tuple[dict, ...]` — one entry per transition |
| `reject_reason` | `str` |
| `created_ts`, `updated_ts` | ISO `str` |
| `is_estimate` | always `True` |

## `Fill`

| Field | Type |
|---|---|
| `fill_id`, `order_id`, `account_id`, `symbol`, `side`, `leg` (`"entry"`/`"exit"`) | `str` |
| `price`, `quantity`, `fee`, `execution_cost` | `float` — `execution_cost` is in PRICE units, see PAPER_BROKER_SPECIFICATION.md Sec.3 |
| `is_partial` | `bool` |
| `ts` | ISO `str` |

## `PositionSnapshot`

| Field | Type |
|---|---|
| `account_id`, `symbol` | `str` |
| `direction` | `"long"` / `"short"` / `"flat"` |
| `quantity` | `float` |
| `avg_entry` | `float \| None` |
| `realized_pnl`, `fees_paid`, `execution_costs` | `float` (dollars) |
| `unrealized_pnl` | `float \| None` — `None` if no mark price was supplied |
| `risk_utilization` | `float \| None` — reserved, not yet populated |
| `opened_ts`, `updated_ts` | ISO `str` |
| `open_refs` | `tuple[str, ...]` — trade refs contributing to this net position |

## `AccountSnapshot`

| Field | Type |
|---|---|
| `account_id`, `currency` | `str` |
| `starting_capital`, `balance`, `equity`, `margin_used`, `buying_power`, `leverage` | `float` |
| `open_position_count` | `int` |
| `as_of` | ISO `str` |

## `BrokerInterface` methods

| Method | Signature | Never raises — degrades to |
|---|---|---|
| `submit_order` | `(request: OrderRequest) -> Order` | `Order(status=REJECTED, reject_reason=...)` |
| `cancel_order` | `(account_id, order_id, reason="") -> Order \| None` | Unchanged order if already terminal; `None` if unknown |
| `modify_order` | `(account_id, order_id, **changes) -> Order \| None` | Unchanged order if not WORKING/ACCEPTED |
| `get_order_status` | `(account_id, order_id) -> Order \| None` | `None` if unknown |
| `get_positions` | `(account_id) -> list[PositionSnapshot]` | `[]` |
| `get_balances` | `(account_id) -> AccountSnapshot` | Zeroed/default snapshot |
| `get_execution_reports` | `(account_id, n=20) -> list[dict]` | `[]` |

## Writing a new adapter

1. Subclass `contract.BrokerInterface`.
2. Implement all seven abstract methods with the exact signatures above.
3. Set `contract_version = contract.CONTRACT_VERSION` (or declare which
   version your adapter targets if the contract has moved on).
4. Reuse `order_state.py`'s `new_order()`/`transition()` if your adapter
   wants the identical lifecycle semantics — not required, but
   recommended for consistency with `PaperBroker`'s behavior.
5. Never let your adapter's `submit_order()` (or any other method) raise
   past its own boundary — every method in this contract is documented
   as never-raising, and every caller in this codebase (`alert_signals.py`,
   `dashboard_publish.py`) relies on that guarantee.
