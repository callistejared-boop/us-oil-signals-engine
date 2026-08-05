"""Day 13 — Standardized Execution Events.

Defines the fixed event-type vocabulary the mandate asks for ("Publish
standardized execution events for: order submitted, order accepted,
fill, partial fill, cancellation, rejection, position opened, position
closed") and one `emit()` function every part of `paper_broker.py` calls
through — so there is exactly one place that decides what an event
record looks like, and every consumer (dashboards, journals, research,
replay) reads the same shape from `broker_history.events_tail()` /
`events_for_ref()`.

"Nothing should rely on opaque logs" (mandate, Observability section):
every event's `payload` dict is built from the SAME `Order`/`Fill`/
`AccountSnapshot` objects already returned to the caller — never a
separate, harder-to-trust summary computed independently.
"""
from __future__ import annotations

from . import broker_history as bh

VERSION = "1.0.0"


class EventType:
    ORDER_SUBMITTED = "order_submitted"
    ORDER_ACCEPTED = "order_accepted"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    CANCELLATION = "cancellation"
    REJECTION = "rejection"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    ALL = (ORDER_SUBMITTED, ORDER_ACCEPTED, FILL, PARTIAL_FILL, CANCELLATION,
           REJECTION, POSITION_OPENED, POSITION_CLOSED)


def emit(event_type: str, account_id: str, symbol: str, payload: dict,
        ref: str = "", ts: "str | None" = None) -> dict:
    """Publishes one standardized event. Never raises — a failure to
    persist degrades to a returned-but-unpersisted record rather than
    blocking the caller (same fail-safe posture as every other Day 4-12
    logging call in this codebase)."""
    if event_type not in EventType.ALL:
        event_type = f"unknown:{event_type}"
    try:
        return bh.record_event(event_type, account_id, symbol, payload, ref=ref, ts=ts)
    except Exception as exc:  # noqa: BLE001
        return {"event_type": event_type, "account_id": account_id, "symbol": symbol,
                "ref": ref, "payload": payload, "error": f"emit error: {exc}"}


def tail(n: int = 20, account_id: "str | None" = None, event_type: "str | None" = None) -> list:
    return bh.events_tail(n=n, account_id=account_id, event_type=event_type)


def for_ref(ref: str) -> list:
    return bh.events_for_ref(ref)
