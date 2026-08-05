"""Day 13 — Order lifecycle state machine.

Owns the only two things that are allowed to create or change an
`Order`: `new_order()` and `transition()`. Both are pure functions —
`transition()` returns a brand-new `Order` (via `dataclasses.replace`)
with the new status appended to `history`; it never mutates the `Order`
passed in. This is the concrete mechanism behind the package's
"Immutable execution records" principle: nothing downstream can hold a
reference to an `Order` and have it change out from under it.

State diagram (mandate's own example states):

    CREATED --> ACCEPTED --> WORKING --> FILLED            (terminal)
                   |            |  \
                   |            |   --> PARTIALLY_FILLED --> FILLED   (terminal)
                   |            |                        \-> CANCELLED (terminal)
                   |            |                        \-> EXPIRED   (terminal)
                   |            +--> CANCELLED             (terminal)
                   |            +--> EXPIRED               (terminal)
                   +--> REJECTED                            (terminal)

Every transition is validated against `VALID_TRANSITIONS` before being
applied — `transition()` raises `InvalidTransition` for anything not in
that graph (a programming-error signal, not a runtime condition
`paper_broker.py` should ever hit in normal operation; it is caught
there defensively anyway, per this codebase's "never raises past a
public boundary" discipline)."""
from __future__ import annotations

import uuid

from .contract import Order, now_iso

VERSION = "1.0.0"


class OrderStatus:
    CREATED = "created"
    ACCEPTED = "accepted"
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"

    TERMINAL = (FILLED, CANCELLED, EXPIRED, REJECTED)
    ALL = (CREATED, ACCEPTED, WORKING, PARTIALLY_FILLED, FILLED,
           CANCELLED, EXPIRED, REJECTED)


VALID_TRANSITIONS = {
    OrderStatus.CREATED: {OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.WORKING, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.WORKING: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
                          OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.REJECTED: set(),
}


class InvalidTransition(Exception):
    pass


def new_order(client_order_id: str, account_id: str, symbol: str, side: str,
             order_type: str, intended_price: float, quantity: float,
             stop_price: float | None = None, limit_price: float | None = None,
             time_in_force: str = "gtc", ref: str = "") -> Order:
    """Constructs a brand-new `Order` in `CREATED` status with a fresh
    `order_id` and a one-entry transition history. Never raises (invalid
    inputs are the caller's responsibility to validate — this is a pure
    constructor)."""
    ts = now_iso()
    order_id = f"ord-{uuid.uuid4().hex[:16]}"
    return Order(
        order_id=order_id, client_order_id=client_order_id, account_id=account_id,
        symbol=symbol, side=side, order_type=order_type, intended_price=intended_price,
        quantity=quantity, status=OrderStatus.CREATED, stop_price=stop_price,
        limit_price=limit_price, time_in_force=time_in_force, ref=ref,
        filled_quantity=0.0, avg_fill_price=None, fills=(),
        history=({"status": OrderStatus.CREATED, "ts": ts, "reason": "order created"},),
        reject_reason="", created_ts=ts, updated_ts=ts,
    )


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in VALID_TRANSITIONS.get(from_status, set())


def transition(order: Order, to_status: str, reason: str = "", **changes) -> Order:
    """Returns a NEW `Order` moved to `to_status`, with the transition
    appended to `history`. `**changes` may set any other `Order` field
    at the same time (e.g. `filled_quantity=`, `fills=`, `reject_reason=`)
    so a fill and its status change land in one atomic replacement rather
    than two. Raises `InvalidTransition` if the move isn't in
    `VALID_TRANSITIONS` — callers in this codebase always catch this
    defensively (see `paper_broker.py`)."""
    if not can_transition(order.status, to_status):
        raise InvalidTransition(
            f"cannot move order {order.order_id} from {order.status!r} to {to_status!r}")
    ts = now_iso()
    new_history = order.history + ({"status": to_status, "ts": ts, "reason": reason},)
    import dataclasses
    return dataclasses.replace(order, status=to_status, history=new_history,
                               updated_ts=ts, **changes)


def is_terminal(status: str) -> bool:
    return status in OrderStatus.TERMINAL
