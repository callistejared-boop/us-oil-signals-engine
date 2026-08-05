"""Day 13 — Execution API v1: the versioned, broker-neutral contract.

Per the mandate's own recommendation: "Before writing any broker-specific
adapter (MetaTrader, Interactive Brokers, OANDA, etc.), define a
versioned execution contract... Every broker adapter should conform to
that contract." `CONTRACT_VERSION` below is that version marker — any
future breaking change to this contract bumps it, and every provider
(`paper_broker.py` today, a live adapter tomorrow) declares which
version it implements via `BrokerInterface.contract_version`.

This module defines the SHAPE of every request/response in the system —
enums and plain dataclasses only, no execution logic. `paper_broker.py`
is the first (and, as of Day 13, only) implementation of
`BrokerInterface`. A live adapter written against this exact interface
can be swapped in later with zero changes required above this layer
(`alert_signals.py` would only need to construct a different broker
instance).

Design note on immutability: every dataclass here is intended to be
treated as a value object. `Order`/`Fill`/`PositionSnapshot`/
`AccountSnapshot` are never mutated in place by this codebase —
`order_state.transition()` returns a NEW `Order` (via
`dataclasses.replace`) rather than mutating the one passed in. This is
what the mandate's "Immutable execution records" principle means in
practice here.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone

CONTRACT_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Enums (plain str subclasses — JSON-serializable without a custom encoder,
# consistent with every other Day 4-12 module's disclosed-constant style)
# --------------------------------------------------------------------------

class OrderSide:
    BUY = "buy"
    SELL = "sell"
    ALL = (BUY, SELL)


class OrderType:
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    ALL = (MARKET, LIMIT, STOP)


class TimeInForce:
    """Included for contract completeness (a live adapter will need it);
    the Paper Broker's own synchronous fill model (Day 12) means GTC/DAY
    are effectively equivalent to "resolve now or rest as WORKING" — see
    PAPER_BROKER_SPECIFICATION.md Sec.4 for the disclosed simplification."""
    GTC = "gtc"      # good-till-cancelled — rests as WORKING if not filled
    IOC = "ioc"       # immediate-or-cancel — never rests; unfilled -> CANCELLED
    DAY = "day"       # treated as GTC by the Paper Broker (no session-close sweep yet)
    ALL = (GTC, IOC, DAY)


# --------------------------------------------------------------------------
# Request / response value objects
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderRequest:
    """What a caller (today: `alert_signals.py`; tomorrow: possibly a
    live-adapter caller) submits to `BrokerInterface.submit_order()`.
    `client_order_id` is the idempotency key — this platform always
    passes the unified trade `ref` (`journal.make_ref()`) so a retried
    submission for the same trade is guaranteed to be recognized as a
    duplicate rather than opening a second position. See
    `paper_broker.py`'s docstring for the recovery behavior this enables."""
    client_order_id: str
    account_id: str
    symbol: str
    side: str                       # OrderSide.BUY / .SELL
    order_type: str                 # OrderType.MARKET / .LIMIT / .STOP
    intended_price: float
    quantity: float | None = None   # lots; None = auto-size from account risk (see account.py)
    stop_price: float | None = None   # this trade's protective stop (for auto-sizing + cost_r)
    limit_price: float | None = None  # required for order_type == LIMIT
    time_in_force: str = TimeInForce.GTC
    signal_ts: "datetime | None" = None
    ref: str = ""                    # unified trade ID (journal.make_ref()) — "" if none available
    # Passthrough to engine.execution.fill_model — reused verbatim, never
    # recomputed (see PAPER_BROKER_SPECIFICATION.md Sec.3 "Reuse, not
    # Reimplementation").
    atr_pct: float | None = None
    news_blackout: bool = False
    session: str | None = None
    price_path: "object" = None      # optional real subsequent bars for deterministic limit fills
    # Test/replay-only failure injection — NEVER set by the live
    # alert_signals.py call site. See paper_broker.py "Failure Handling".
    simulate_failure: dict | None = None


@dataclass(frozen=True)
class Fill:
    """One immutable execution fill (entry or exit leg of one order)."""
    fill_id: str
    order_id: str
    account_id: str
    symbol: str
    side: str
    leg: str                # "entry" | "exit"
    price: float
    quantity: float          # lots actually filled (<= requested on a partial fill)
    fee: float
    execution_cost: float    # from engine.execution.fill_model — spread+slippage cost, reused verbatim
    is_partial: bool
    ts: str                  # ISO timestamp
    is_estimate: bool = True
    source: str = "engine.broker.paper_broker"


@dataclass(frozen=True)
class Order:
    """The full order record, including its immutable transition
    history. `order_state.py` is the only module that constructs or
    transitions these — see that module's docstring."""
    order_id: str
    client_order_id: str
    account_id: str
    symbol: str
    side: str
    order_type: str
    intended_price: float
    quantity: float
    status: str               # order_state.OrderStatus.*
    stop_price: float | None = None
    limit_price: float | None = None
    time_in_force: str = TimeInForce.GTC
    ref: str = ""
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    fills: tuple = field(default_factory=tuple)         # tuple[Fill, ...] — immutable
    history: tuple = field(default_factory=tuple)        # tuple[dict, ...] — transition log
    reject_reason: str = ""
    created_ts: str = ""
    updated_ts: str = ""
    is_estimate: bool = True
    source: str = "engine.broker.paper_broker"


@dataclass(frozen=True)
class PositionSnapshot:
    """Read-only snapshot returned by `get_positions()` — the live
    mutable state lives in `position_engine.PositionEngine`, never
    exposed directly (same "expose a snapshot, not the mutable object"
    convention as `account.AccountSnapshot` below)."""
    account_id: str
    symbol: str
    direction: str            # "long" | "short" | "flat"
    quantity: float
    avg_entry: float | None
    realized_pnl: float
    unrealized_pnl: float | None
    fees_paid: float
    execution_costs: float
    risk_utilization: float | None   # margin_used / equity for this position, 0-1+
    opened_ts: str = ""
    updated_ts: str = ""
    open_refs: tuple = field(default_factory=tuple)   # trade_ref(s) contributing to this net position


@dataclass(frozen=True)
class AccountSnapshot:
    """Read-only snapshot returned by `get_balances()`."""
    account_id: str
    currency: str
    starting_capital: float
    balance: float             # realized cash
    equity: float               # balance + total unrealized P&L across positions
    margin_used: float
    buying_power: float
    leverage: float
    open_position_count: int
    as_of: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# The interface itself
# --------------------------------------------------------------------------

class BrokerInterface(abc.ABC):
    """Execution API v1. Every execution provider — Paper Broker today,
    a live adapter later, a pure Simulation/Replay broker for research —
    implements this exact surface. `alert_signals.py` (and any future
    caller) is written against THIS interface, never against
    `PaperBroker` directly, so swapping providers never requires a
    change above this layer."""

    contract_version: str = CONTRACT_VERSION

    @abc.abstractmethod
    def submit_order(self, request: OrderRequest) -> Order:
        """Submit a new order. Never raises — a broker-level failure
        (rejected, unavailable, stale quote, etc.) is represented as a
        returned `Order` with `status == OrderStatus.REJECTED` and a
        populated `reject_reason`, never an exception. Idempotent on
        `request.client_order_id`: a duplicate submission returns the
        ORIGINAL order unchanged."""
        raise NotImplementedError

    @abc.abstractmethod
    def cancel_order(self, account_id: str, order_id: str, reason: str = "") -> Order:
        """Cancel a resting (WORKING) order. A no-op (returns the order
        unchanged, with a note) if the order is already in a terminal
        state — never raises."""
        raise NotImplementedError

    @abc.abstractmethod
    def modify_order(self, account_id: str, order_id: str, **changes) -> Order:
        """Modify a resting order's price/quantity. Only valid while
        WORKING; a no-op with a note otherwise. Never raises."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_order_status(self, account_id: str, order_id: str) -> "Order | None":
        raise NotImplementedError

    @abc.abstractmethod
    def get_positions(self, account_id: str) -> list:
        """Returns `list[PositionSnapshot]` — open positions only."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_balances(self, account_id: str) -> AccountSnapshot:
        raise NotImplementedError

    @abc.abstractmethod
    def get_execution_reports(self, account_id: str, n: int = 20) -> list:
        """Returns the most recent `n` persisted order/fill/event records
        for this account — the "query execution reports" operation named
        in the Day 13 mandate. Backed by `broker_history.py`."""
        raise NotImplementedError
