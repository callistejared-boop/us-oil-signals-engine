"""Day 13 — Broker History: append-only JSONL persistence for the
Broker Abstraction Layer.

Same self-rotating, append-only, immutable JSONL pattern as
`engine/execution/execution_history.py` (Day 12) /
`engine/macro_history.py` (Day 11) / `regime_history.py` /
`confluence_history.py` / `confidence_history.py` before it — now the
SIXTH generation of this exact pattern in this codebase. No update or
delete function exists for any of the four stores below, by design (see
MARKET_MEMORY_SPECIFICATION.md Sec.2 for the precedent establishing
"immutable execution records" as a codebase-wide convention, not a
Day-13-specific one).

Four separate stores, one per record kind, all sharing the same
read/rotate helpers below:
  - `broker_orders.jsonl`   — one row per order TRANSITION (not just the
                              final state) — "Persist all transitions"
                              from the mandate.
  - `broker_fills.jsonl`    — one row per individual fill.
  - `broker_events.jsonl`   — standardized execution events (see
                              `events.py` for the taxonomy).
  - `broker_accounts.jsonl` — account equity/balance snapshots (the
                              "daily equity curve / historical balances"
                              the mandate's Account Model section asks
                              for).
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ORDERS_PATH = ROOT / "broker_orders.jsonl"
FILLS_PATH = ROOT / "broker_fills.jsonl"
EVENTS_PATH = ROOT / "broker_events.jsonl"
ACCOUNTS_PATH = ROOT / "broker_accounts.jsonl"
MAX_LINES = 20000

VERSION = "1.0.0"
SCHEMA_VERSION = 1


def _read_all(path: pathlib.Path) -> list:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []


def _rotate(path: pathlib.Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            path.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _append(path: pathlib.Path, rec: dict) -> dict:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate(path)
    except Exception:  # noqa: BLE001
        pass
    return rec


# --------------------------------------------------------------------------
# Orders — one row per transition
# --------------------------------------------------------------------------

def record_order_transition(order, reason: str = "") -> dict:
    """Persists the order's CURRENT (post-transition) state as one row.
    Called once per `order_state.transition()` call, so the full history
    of an order is reconstructable by filtering `broker_orders.jsonl` on
    `order_id` and reading rows in file order. Never raises."""
    rec = {
        "ts": order.updated_ts, "order_id": order.order_id,
        "client_order_id": order.client_order_id, "account_id": order.account_id,
        "symbol": order.symbol, "side": order.side, "order_type": order.order_type,
        "status": order.status, "intended_price": order.intended_price,
        "quantity": order.quantity, "filled_quantity": order.filled_quantity,
        "avg_fill_price": order.avg_fill_price, "ref": order.ref,
        "reject_reason": order.reject_reason, "reason": reason,
        "version": {"broker_history": VERSION, "schema": SCHEMA_VERSION},
    }
    return _append(ORDERS_PATH, rec)


def orders_for(order_id: str) -> list:
    return [r for r in _read_all(ORDERS_PATH) if r.get("order_id") == order_id]


def latest_order_row(order_id: str) -> "dict | None":
    rows = orders_for(order_id)
    return rows[-1] if rows else None


def orders_tail(n: int = 20, account_id: "str | None" = None) -> list:
    rows = _read_all(ORDERS_PATH)
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    return rows[-n:]


def all_orders(account_id: "str | None" = None) -> list:
    """Every persisted order-transition row (no `n` limit) — used by
    `position_engine.rebuild_from_history()` to reconstruct in-memory
    state on a fresh process. Never raises."""
    rows = _read_all(ORDERS_PATH)
    return [r for r in rows if not account_id or r.get("account_id") == account_id]


def all_fills(account_id: "str | None" = None) -> list:
    """Every persisted fill row (no `n` limit), same rebuild use-case as
    `all_orders()`. Never raises."""
    rows = _read_all(FILLS_PATH)
    return [r for r in rows if not account_id or r.get("account_id") == account_id]


def find_order_by_client_id(account_id: str, client_order_id: str) -> "dict | None":
    """Cross-process idempotency lookup: has THIS account already
    submitted an order with this `client_order_id`? Scans the CREATED
    row specifically (every order has exactly one) so a duplicate
    submission is recognized even after a process restart, not only
    within one `PaperBroker` instance's in-memory cache. Never raises."""
    if not client_order_id:
        return None
    try:
        for r in _read_all(ORDERS_PATH):
            if (r.get("account_id") == account_id and
                    r.get("client_order_id") == client_order_id and
                    r.get("status") == "created"):
                return r
        return None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Fills
# --------------------------------------------------------------------------

def record_fill(fill) -> dict:
    rec = {
        "ts": fill.ts, "fill_id": fill.fill_id, "order_id": fill.order_id,
        "account_id": fill.account_id, "symbol": fill.symbol, "side": fill.side,
        "leg": fill.leg, "price": fill.price, "quantity": fill.quantity,
        "fee": fill.fee, "execution_cost": fill.execution_cost,
        "is_partial": fill.is_partial,
        "version": {"broker_history": VERSION, "schema": SCHEMA_VERSION},
    }
    return _append(FILLS_PATH, rec)


def fills_for_order(order_id: str) -> list:
    return [r for r in _read_all(FILLS_PATH) if r.get("order_id") == order_id]


def fills_tail(n: int = 20, account_id: "str | None" = None, symbol: "str | None" = None) -> list:
    rows = _read_all(FILLS_PATH)
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def exit_fill_refs_for_symbol(symbol: str, account_id: "str | None" = None) -> set:
    """Set of trade `ref`s that already have a recorded EXIT-leg fill for
    this symbol — used by `paper_broker.sync_closures()` to avoid
    double-closing the same trade's position on a later scan. A fill row
    itself has no `ref` field (fills are order-scoped, not trade-scoped),
    so this joins through `broker_orders.jsonl` via `order_id`. Never
    raises."""
    try:
        order_ref_by_id = {}
        for r in _read_all(ORDERS_PATH):
            if r.get("symbol") == symbol and (not account_id or r.get("account_id") == account_id):
                order_ref_by_id[r["order_id"]] = r.get("ref", "")
        refs = set()
        for r in _read_all(FILLS_PATH):
            if r.get("symbol") != symbol or r.get("leg") != "exit":
                continue
            ref = order_ref_by_id.get(r.get("order_id"), "")
            if ref:
                refs.add(ref)
        return refs
    except Exception:  # noqa: BLE001
        return set()


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def record_event(event_type: str, account_id: str, symbol: str, payload: dict,
                 ref: str = "", ts: "str | None" = None) -> dict:
    from .contract import now_iso
    rec = {
        "ts": ts or now_iso(), "event_type": event_type, "account_id": account_id,
        "symbol": symbol, "ref": ref, "payload": payload or {},
        "version": {"broker_history": VERSION, "schema": SCHEMA_VERSION},
    }
    return _append(EVENTS_PATH, rec)


def events_tail(n: int = 20, account_id: "str | None" = None,
                event_type: "str | None" = None) -> list:
    rows = _read_all(EVENTS_PATH)
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    if event_type:
        rows = [r for r in rows if r.get("event_type") == event_type]
    return rows[-n:]


def events_for_ref(ref: str) -> list:
    if not ref:
        return []
    return [r for r in _read_all(EVENTS_PATH) if r.get("ref") == ref]


# --------------------------------------------------------------------------
# Account equity/balance snapshots
# --------------------------------------------------------------------------

def record_account_snapshot(snapshot) -> dict:
    rec = {
        "ts": snapshot.as_of, "account_id": snapshot.account_id, "currency": snapshot.currency,
        "starting_capital": snapshot.starting_capital, "balance": snapshot.balance,
        "equity": snapshot.equity, "margin_used": snapshot.margin_used,
        "buying_power": snapshot.buying_power, "leverage": snapshot.leverage,
        "open_position_count": snapshot.open_position_count,
        "version": {"broker_history": VERSION, "schema": SCHEMA_VERSION},
    }
    return _append(ACCOUNTS_PATH, rec)


def account_equity_curve(account_id: str, n: int = 500) -> list:
    rows = [r for r in _read_all(ACCOUNTS_PATH) if r.get("account_id") == account_id]
    return rows[-n:]


# --------------------------------------------------------------------------
# Combined view — backs `BrokerInterface.get_execution_reports()`
# --------------------------------------------------------------------------

def execution_reports(account_id: str, n: int = 20) -> list:
    """Merges the last `n` order-transition and fill rows for one
    account into one time-ordered feed — the "query execution reports"
    operation. Never raises."""
    try:
        orders = [{**r, "kind": "order"} for r in orders_tail(n, account_id=account_id)]
        fills = [{**r, "kind": "fill"} for r in _read_all(FILLS_PATH)
                if r.get("account_id") == account_id][-n:]
        merged = sorted(orders + fills, key=lambda r: r.get("ts", ""))
        return merged[-n:]
    except Exception:  # noqa: BLE001
        return []
