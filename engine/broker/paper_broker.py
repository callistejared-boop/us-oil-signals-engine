"""Day 13 — Paper Broker: the platform's first true execution provider.

Implements `contract.BrokerInterface` on top of Day 12's execution
simulator (`engine.execution.fill_model`) — this module does NOT
reimplement spread/slippage/latency modeling; it consumes
`fill_model.simulate_fill()` exactly as `execution_report.py` does, and
adds everything a broker needs on top: order lifecycle, positions,
account balances, idempotency, and graceful failure handling.

Order-type resolution policy (a disclosed design choice, not a fill_model
change):
  - MARKET / STOP: resolve IMMEDIATELY on submission (this platform's own
    alert semantics mean the trigger condition is already met at signal
    time — see `engine/execution/fill_model.py`'s own docstring for why
    this is true upstream too). Outcome is FILLED, PARTIALLY_FILLED, or
    REJECTED — never left WORKING.
  - LIMIT with a supplied `price_path`: also resolves immediately,
    deterministically (did price actually reach the limit level).
  - LIMIT with NO `price_path`: rests as a genuine WORKING order — this
    is what makes `cancel_order()`/`modify_order()` meaningful rather
    than trivial no-ops. A later call to `check_working_orders()`
    resolves it once a real price crossing is known.

Units note (read before touching P&L math): `engine.execution.fill_model`
reports execution cost in PRICE units (the same units as `entry`/`stop`).
Everything in `position_engine.py`/`account.py` is in DOLLAR units
(realized/unrealized P&L, balance, margin). This module is the ONE place
that converts between them — `_dollar_cost()` below — so the conversion
happens exactly once, not scattered across the package.

Concurrency note ("concurrent order scenarios" in the mandate): this
platform's execution model is a single-threaded 15-minute scan loop, the
same model every prior Day 1-12 subsystem already assumes. "Concurrent"
here means MULTIPLE ORDERS ACROSS DIFFERENT SYMBOLS submitted within the
same scan (e.g. XAUUSD and WTIUSD both trigger entries in the same
15-minute tick) — verified in testing to be correctly isolated (no
cross-symbol state bleed, no shared-account race), not true
multi-threaded concurrency, which this codebase has never claimed to
support anywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import account as acct_mod
from . import broker_history as bh
from . import events
from . import order_state as ost
from . import position_engine as pos_mod
from .contract import BrokerInterface, Fill, OrderRequest, TimeInForce, now_iso
from .order_state import OrderStatus
from .position_engine import _mult

VERSION = "1.0.0"

DEFAULT_ACCOUNT_ID = "paper-default"


def _direction_for_entry(side: str) -> str:
    return "long" if side == "buy" else "short"


def _closing_side(direction: str) -> str:
    return "sell" if direction == "long" else "buy"


def _dollar_cost(cost_price_units: "float | None", quantity: float, symbol: str) -> float:
    if not cost_price_units:
        return 0.0
    return round(abs(cost_price_units) * abs(quantity) * _mult(symbol), 6)


def _failure_reason(sf: "dict | None") -> "str | None":
    """Maps a `simulate_failure` dict's BROKER-INFRASTRUCTURE flags
    (never the market-condition ones, which pass through to
    `fill_model` instead — see `submit_order()`) to a disclosed
    rejection reason. Only ever set by tests/replay — NEVER by the live
    `alert_signals.py` call site. Documented recovery behavior for each:
      - broker_unavailable / network_interruption / timeout: transient —
        SAFE TO RETRY with the identical `client_order_id`; the
        idempotency check in `submit_order()` means a retry that
        eventually succeeds will not double-open a position, and a retry
        that hits the same simulated failure again is itself harmless
        (still no position opened).
      - stale_quote: the caller should refresh its price before retrying
        with a NEW `client_order_id` (retrying with the same intended
        price under the same stale condition will just reject again)."""
    sf = sf or {}
    if sf.get("broker_unavailable"):
        return "broker unavailable — simulated outage; safe to retry with the same client_order_id"
    if sf.get("network_interruption"):
        return "network interruption — simulated; safe to retry with the same client_order_id"
    if sf.get("timeout"):
        return "request timeout — simulated; safe to retry with the same client_order_id"
    if sf.get("stale_quote"):
        return "stale quote — simulated; refresh price before retrying with a new client_order_id"
    return None


class PaperBroker(BrokerInterface):
    """One `PaperBroker` instance is bound to one account for its
    lifetime (pass a different `account_id` to trade a different virtual
    account — see `account.AccountRegistry` for the "multiple independent
    accounts" support). `__init__` REBUILDS this account's position and
    balance state from `broker_history.jsonl` immediately — see
    `position_engine.PositionEngine.rebuild_from_history()`'s docstring
    for why this is required given this platform's fresh-process-per-scan
    execution model."""

    def __init__(self, account_id: str = DEFAULT_ACCOUNT_ID,
                starting_capital: "float | None" = None,
                leverage: "float | None" = None, risk_pct: "float | None" = None,
                rng=None):
        self.account_id = account_id
        acct_mod.REGISTRY.get_or_create(account_id, starting_capital, leverage, risk_pct)
        pos_mod.ENGINE.rebuild_from_history(account_id)
        acct_mod.REGISTRY.rebuild_from_history(account_id)
        self._rng = rng
        self._working: dict = {}          # order_id -> Order (resting limit orders)
        self._client_id_cache: dict = {}   # client_order_id -> order_id (this-process fast path)

    # ---- BrokerInterface -------------------------------------------------

    def submit_order(self, request: OrderRequest):
        try:
            existing = self._find_existing(request.account_id, request.client_order_id)
            if existing is not None:
                return existing

            sf = request.simulate_failure or {}
            broker_reason = _failure_reason(sf)
            order = ost.new_order(
                request.client_order_id, request.account_id, request.symbol, request.side,
                request.order_type, request.intended_price, request.quantity or 0.0,
                stop_price=request.stop_price, limit_price=request.limit_price,
                time_in_force=request.time_in_force, ref=request.ref)
            bh.record_order_transition(order, reason="order created")
            events.emit(events.EventType.ORDER_SUBMITTED, request.account_id, request.symbol,
                       {"order_id": order.order_id, "order_type": request.order_type,
                        "intended_price": request.intended_price}, ref=request.ref)

            if broker_reason:
                order = ost.transition(order, OrderStatus.REJECTED, reason=broker_reason,
                                       reject_reason=broker_reason)
                bh.record_order_transition(order, reason=broker_reason)
                events.emit(events.EventType.REJECTION, request.account_id, request.symbol,
                           {"order_id": order.order_id, "reason": broker_reason}, ref=request.ref)
                return order

            order = ost.transition(order, OrderStatus.ACCEPTED, reason="broker accepted order")
            bh.record_order_transition(order)
            events.emit(events.EventType.ORDER_ACCEPTED, request.account_id, request.symbol,
                       {"order_id": order.order_id}, ref=request.ref)
            order = ost.transition(order, OrderStatus.WORKING, reason="order is working")
            bh.record_order_transition(order)

            quantity = request.quantity
            if quantity is None:
                if request.stop_price is None:
                    order = ost.transition(order, OrderStatus.REJECTED,
                                           reason="cannot auto-size: no stop_price given",
                                           reject_reason="cannot auto-size: no stop_price given")
                    bh.record_order_transition(order)
                    events.emit(events.EventType.REJECTION, request.account_id, request.symbol,
                               {"order_id": order.order_id, "reason": order.reject_reason}, ref=request.ref)
                    return order
                quantity = acct_mod.REGISTRY.position_size(
                    request.account_id, request.intended_price, request.stop_price, request.symbol)
            if quantity <= 0:
                order = ost.transition(order, OrderStatus.REJECTED,
                                       reason="cannot size order (zero risk distance or zero equity)",
                                       reject_reason="cannot size order (zero risk distance or zero equity)")
                bh.record_order_transition(order)
                events.emit(events.EventType.REJECTION, request.account_id, request.symbol,
                           {"order_id": order.order_id, "reason": order.reject_reason}, ref=request.ref)
                return order
            import dataclasses
            order = dataclasses.replace(order, quantity=quantity)

            acct = acct_mod.REGISTRY.get_or_create(request.account_id)
            margin_needed = pos_mod.ENGINE.margin_required(
                request.symbol, request.intended_price, quantity, acct.leverage)
            snap = acct_mod.REGISTRY.snapshot(request.account_id)
            if margin_needed > snap.buying_power:
                reason = (f"insufficient buying power (need ~${margin_needed:,.2f}, "
                         f"have ~${snap.buying_power:,.2f})")
                order = ost.transition(order, OrderStatus.REJECTED, reason=reason, reject_reason=reason)
                bh.record_order_transition(order)
                events.emit(events.EventType.REJECTION, request.account_id, request.symbol,
                           {"order_id": order.order_id, "reason": reason}, ref=request.ref)
                return order

            # Resting limit order (no deterministic price path supplied) —
            # stays WORKING, no fill attempt yet.
            if request.order_type == "limit" and request.limit_price is not None \
                    and request.price_path is None:
                self._working[order.order_id] = order
                self._client_id_cache[request.client_order_id] = order.order_id
                return order

            return self._attempt_fill(order, request, quantity, sf)
        except Exception as exc:  # noqa: BLE001
            return self._rejected_stub(request, f"submit_order error: {exc}")

    def _attempt_fill(self, order, request: OrderRequest, quantity: float, sf: dict):
        from engine.execution import fill_model as fm
        direction = _direction_for_entry(request.side)
        fill_out = fm.simulate_fill(
            request.symbol, direction, request.order_type, request.intended_price,
            signal_ts=request.signal_ts, leg="entry", atr_pct=request.atr_pct,
            news_blackout=request.news_blackout, session=request.session,
            zero_liquidity=bool(sf.get("zero_liquidity")), missing_data=bool(sf.get("missing_data")),
            stale_price=bool(sf.get("stale_price")), price_path=request.price_path,
            limit_price=request.limit_price, rng=self._rng)

        if not fill_out.get("filled"):
            reason = fill_out.get("reason", "not filled")
            order = ost.transition(order, OrderStatus.REJECTED, reason=reason, reject_reason=reason)
            bh.record_order_transition(order)
            events.emit(events.EventType.REJECTION, request.account_id, request.symbol,
                       {"order_id": order.order_id, "reason": reason, "detail": fill_out},
                       ref=request.ref)
            return order

        fill_fraction = fill_out.get("fill_fraction", 1.0) or 1.0
        quantity_filled = round(quantity * fill_fraction, 6)
        is_partial = bool(fill_out.get("partial_fill")) or fill_fraction < 1.0
        cost_price = fill_out.get("execution_cost", 0.0) or 0.0
        cost_dollars = _dollar_cost(cost_price, quantity_filled, request.symbol)
        fill = Fill(fill_id=f"fill-{uuid.uuid4().hex[:16]}", order_id=order.order_id,
                   account_id=request.account_id, symbol=request.symbol, side=request.side,
                   leg="entry", price=fill_out["actual_price"], quantity=quantity_filled,
                   fee=0.0, execution_cost=cost_price, is_partial=is_partial, ts=now_iso())
        bh.record_fill(fill)

        acct = acct_mod.REGISTRY.get_or_create(request.account_id)
        margin_needed = pos_mod.ENGINE.margin_required(
            request.symbol, fill_out["actual_price"], quantity_filled, acct.leverage)
        acct_mod.REGISTRY.reserve_margin(request.account_id, margin_needed)

        result = pos_mod.ENGINE.on_fill(
            request.account_id, request.symbol, request.side, "entry", fill_out["actual_price"],
            quantity_filled, 0.0, cost_dollars, ref=request.ref, ts=fill.ts)
        # An "entry" fill can still realize P&L if it happens to be
        # opposite-direction to an already-open position on this symbol
        # (reduces/closes/flips it) — see position_engine.on_fill()'s
        # own branching. Applied here for the same reason as the
        # identical line in close_position() below.
        if result.get("realized_pnl_delta"):
            acct_mod.REGISTRY.apply_realized_pnl(request.account_id, result["realized_pnl_delta"])

        new_status = OrderStatus.PARTIALLY_FILLED if is_partial else OrderStatus.FILLED
        import dataclasses
        order = ost.transition(order, new_status,
                               reason=("partially filled" if is_partial else "filled"),
                               filled_quantity=quantity_filled, avg_fill_price=fill_out["actual_price"],
                               fills=order.fills + (fill,))
        bh.record_order_transition(order)
        events.emit(events.EventType.PARTIAL_FILL if is_partial else events.EventType.FILL,
                   request.account_id, request.symbol,
                   {"order_id": order.order_id, "price": fill_out["actual_price"],
                    "quantity": quantity_filled, "execution_cost_dollars": cost_dollars},
                   ref=request.ref)
        if result.get("action") == "opened":
            events.emit(events.EventType.POSITION_OPENED, request.account_id, request.symbol,
                       {"direction": result.get("direction"), "quantity": result.get("quantity")},
                       ref=request.ref)

        self._record_equity(request.account_id)
        self._client_id_cache[request.client_order_id] = order.order_id
        return order

    def cancel_order(self, account_id: str, order_id: str, reason: str = ""):
        try:
            order = self._working.get(order_id) or self._reconstruct(account_id, order_id)
            if order is None:
                return None
            if ost.is_terminal(order.status):
                return order
            new_order = ost.transition(order, OrderStatus.CANCELLED,
                                       reason=reason or "cancelled by caller")
            bh.record_order_transition(new_order)
            events.emit(events.EventType.CANCELLATION, account_id, order.symbol,
                       {"order_id": order_id, "reason": reason}, ref=order.ref)
            self._working.pop(order_id, None)
            return new_order
        except Exception as exc:  # noqa: BLE001
            return self._reconstruct(account_id, order_id) or None

    def modify_order(self, account_id: str, order_id: str, **changes):
        try:
            order = self._working.get(order_id)
            if order is None or order.status not in (OrderStatus.ACCEPTED, OrderStatus.WORKING):
                return self._reconstruct(account_id, order_id)
            allowed = {k: v for k, v in changes.items()
                      if k in ("limit_price", "quantity", "stop_price") and v is not None}
            if not allowed:
                return order
            import dataclasses
            ts = now_iso()
            new_hist = order.history + ({"status": order.status, "ts": ts,
                                        "reason": f"modified: {allowed}"},)
            new_order = dataclasses.replace(order, history=new_hist, updated_ts=ts, **allowed)
            self._working[order_id] = new_order
            bh.record_order_transition(new_order, reason=f"modified: {allowed}")
            return new_order
        except Exception:  # noqa: BLE001
            return self._working.get(order_id)

    def get_order_status(self, account_id: str, order_id: str):
        if order_id in self._working:
            return self._working[order_id]
        return self._reconstruct(account_id, order_id)

    def get_positions(self, account_id: str) -> list:
        return pos_mod.ENGINE.open_positions(account_id)

    def get_balances(self, account_id: str):
        positions = pos_mod.ENGINE.open_positions(account_id)
        unrealized_total = sum((p.unrealized_pnl or 0.0) for p in positions)
        return acct_mod.REGISTRY.snapshot(account_id, unrealized_pnl_total=unrealized_total,
                                         open_position_count=len(positions))

    def get_execution_reports(self, account_id: str, n: int = 20) -> list:
        return bh.execution_reports(account_id, n=n)

    # ---- Resting limit-order resolution (not part of the ABC contract —
    # a Paper-Broker-specific extension for the WORKING-limit lifecycle) --

    def check_working_orders(self, symbol: str, price_path, ts=None) -> list:
        """Resolves any resting WORKING limit orders for `symbol` against
        real subsequent bars (`price_path`, a DataFrame with High/Low —
        the exact shape `fill_model._limit_reached()` already expects).
        Never raises; returns the list of orders that changed state."""
        changed = []
        try:
            from engine.execution import fill_model as fm
            for order_id, order in list(self._working.items()):
                if order.symbol != symbol or order.status != OrderStatus.WORKING:
                    continue
                direction = _direction_for_entry(order.side)
                reached = fm._limit_reached(direction, order.limit_price, price_path)
                if reached is None:
                    continue
                if not reached:
                    continue
                request = OrderRequest(
                    client_order_id=order.client_order_id, account_id=order.account_id,
                    symbol=order.symbol, side=order.side, order_type=order.order_type,
                    intended_price=order.intended_price, quantity=order.quantity,
                    stop_price=order.stop_price, limit_price=order.limit_price,
                    signal_ts=ts, ref=order.ref, price_path=price_path)
                self._working.pop(order_id, None)
                resolved = self._attempt_fill(order, request, order.quantity, {})
                changed.append(resolved)
        except Exception:  # noqa: BLE001
            pass
        return changed

    def expire_working_orders(self, symbol: str, reason: str = "expired — resting limit never filled") -> list:
        changed = []
        for order_id, order in list(self._working.items()):
            if order.symbol != symbol:
                continue
            try:
                new_order = ost.transition(order, OrderStatus.EXPIRED, reason=reason)
                bh.record_order_transition(new_order)
                events.emit(events.EventType.CANCELLATION, order.account_id, symbol,
                           {"order_id": order_id, "reason": reason}, ref=order.ref)
                self._working.pop(order_id, None)
                changed.append(new_order)
            except Exception:  # noqa: BLE001
                continue
        return changed

    # ---- Closing (exit-leg) fills — see module docstring "Units note" ---

    def close_position(self, symbol: str, ref: str, exit_price: float, exit_ts=None,
                       reason: str = "position closed", atr_pct=None,
                       news_blackout: bool = False, session=None, stale_price: bool = False) -> dict:
        """Submits the EXIT leg for this account's current position in
        `symbol`. Not part of `BrokerInterface` (the mandate's 7 core
        broker operations are entry/lifecycle-focused; closing is this
        platform's own trade-management concept, layered on top — same
        relationship `journal.settle()`'s partial-banking logic has to
        the underlying signal). Never raises."""
        try:
            from engine.execution import fill_model as fm
            account_id = self.account_id
            snap = pos_mod.ENGINE.snapshot(account_id, symbol)
            if snap.direction == "flat":
                return {"closed": False, "reason": "no open position for this symbol"}
            direction = snap.direction
            side = _closing_side(direction)

            order = ost.new_order(f"close-{ref or uuid.uuid4().hex[:8]}", account_id, symbol,
                                  side, "market", exit_price, snap.quantity, ref=ref)
            bh.record_order_transition(order, reason="closing order created")
            order = ost.transition(order, OrderStatus.ACCEPTED, reason="broker accepted closing order")
            bh.record_order_transition(order)
            order = ost.transition(order, OrderStatus.WORKING, reason="closing order is working")
            bh.record_order_transition(order)

            fill_out = fm.simulate_fill(symbol, direction, "market", exit_price, signal_ts=exit_ts,
                                        leg="exit", atr_pct=atr_pct, news_blackout=news_blackout,
                                        session=session, stale_price=stale_price, rng=self._rng)
            if not fill_out.get("filled"):
                order = ost.transition(order, OrderStatus.REJECTED, reason=fill_out.get("reason", ""),
                                       reject_reason=fill_out.get("reason", ""))
                bh.record_order_transition(order)
                return {"closed": False, "reason": fill_out.get("reason"), "order_id": order.order_id}

            quantity = snap.quantity
            cost_price = fill_out.get("execution_cost", 0.0) or 0.0
            cost_dollars = _dollar_cost(cost_price, quantity, symbol)
            fill = Fill(fill_id=f"fill-{uuid.uuid4().hex[:16]}", order_id=order.order_id,
                       account_id=account_id, symbol=symbol, side=side, leg="exit",
                       price=fill_out["actual_price"], quantity=quantity, fee=0.0,
                       execution_cost=cost_price, is_partial=False, ts=now_iso())
            bh.record_fill(fill)

            result = pos_mod.ENGINE.on_fill(account_id, symbol, side, "exit", fill_out["actual_price"],
                                            quantity, 0.0, cost_dollars, ref=ref, ts=fill.ts)
            acct = acct_mod.REGISTRY.get_or_create(account_id)
            released = pos_mod.ENGINE.margin_required(symbol, snap.avg_entry, quantity, acct.leverage)
            acct_mod.REGISTRY.release_margin(account_id, released)
            # Realized P&L must be applied to THIS in-memory account object
            # immediately — `rebuild_from_history()` would also derive it
            # correctly, but only runs at `PaperBroker.__init__()`, so
            # without this line `get_balances()` would show a stale
            # balance for the rest of THIS process's lifetime after a
            # close. Found during Day 13's own smoke testing.
            acct_mod.REGISTRY.apply_realized_pnl(account_id, result.get("realized_pnl_delta", 0.0) or 0.0)

            order = ost.transition(order, OrderStatus.FILLED, reason=reason,
                                   filled_quantity=quantity, avg_fill_price=fill_out["actual_price"],
                                   fills=order.fills + (fill,))
            bh.record_order_transition(order)
            events.emit(events.EventType.FILL, account_id, symbol,
                       {"order_id": order.order_id, "price": fill_out["actual_price"],
                        "quantity": quantity, "leg": "exit"}, ref=ref)
            if result.get("action") == "closed":
                events.emit(events.EventType.POSITION_CLOSED, account_id, symbol,
                           {"realized_pnl_delta": result.get("realized_pnl_delta")}, ref=ref)

            self._record_equity(account_id)
            return {"closed": True, "order_id": order.order_id, "fill": fill,
                   "realized_pnl_delta": result.get("realized_pnl_delta")}
        except Exception as exc:  # noqa: BLE001
            return {"closed": False, "error": f"close_position error: {exc}"}

    def sync_closures(self, symbol: str, rows: "list | None" = None) -> list:
        """Scans closed trades for `symbol` (from `trades.json` unless
        `rows` is given for offline testing) and closes any that have a
        `broker_ref` but no recorded exit fill yet — this is what
        `alert_signals.py` calls right after `journal.settle()` each
        scan. Reconstructs the exit price the exact same way
        `engine.execution.replay.approx_exit_price()` does (imported,
        never duplicated — see that module's Day 13 addition). Never
        raises; skips a row on individual error rather than aborting the
        whole scan."""
        out = []
        try:
            from engine.execution.replay import approx_exit_price
            source_rows = rows if rows is not None else _load_trades()
            already = bh.exit_fill_refs_for_symbol(symbol, account_id=self.account_id)
            for row in source_rows:
                try:
                    if row.get("symbol") != symbol:
                        continue
                    if row.get("status") not in ("win", "loss", "scratch", "expired"):
                        continue
                    ref = row.get("broker_ref") or row.get("id") or ""
                    if not ref or ref in already:
                        continue
                    entry, stop = row.get("entry"), row.get("stop")
                    if entry is None or stop is None:
                        continue
                    exit_price = approx_exit_price(entry, stop, row.get("direction", "long"),
                                                   row.get("result_r", 0.0))
                    result = self.close_position(symbol, ref, exit_price,
                                                 exit_ts=row.get("closed") or row.get("opened"))
                    out.append({"ref": ref, **result})
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return out

    # ---- internals ---------------------------------------------------

    def _find_existing(self, account_id: str, client_order_id: str):
        if not client_order_id:
            return None
        order_id = self._client_id_cache.get(client_order_id)
        if order_id:
            return self._working.get(order_id) or self._reconstruct(account_id, order_id)
        row = bh.find_order_by_client_id(account_id, client_order_id)
        if row is None:
            return None
        return self._reconstruct(account_id, row["order_id"])

    def _reconstruct(self, account_id: str, order_id: str):
        """Builds a lightweight `Order` view from the latest persisted
        transition row for status-query purposes. This is NOT the full
        in-memory object (fills are approximated as empty; `history`
        holds only this one reconstructed entry) — a disclosed
        limitation of querying by `order_id` alone after the in-memory
        `_working` cache no longer has it. Never raises."""
        row = bh.latest_order_row(order_id)
        if row is None:
            return None
        from .contract import Order
        return Order(
            order_id=row["order_id"], client_order_id=row.get("client_order_id", ""),
            account_id=row["account_id"], symbol=row["symbol"], side=row["side"],
            order_type=row["order_type"], intended_price=row["intended_price"],
            quantity=row["quantity"], status=row["status"],
            filled_quantity=row.get("filled_quantity", 0.0),
            avg_fill_price=row.get("avg_fill_price"), ref=row.get("ref", ""),
            reject_reason=row.get("reject_reason", ""),
            history=({"status": row["status"], "ts": row["ts"], "reason": row.get("reason", "")},),
            created_ts=row["ts"], updated_ts=row["ts"])

    def _rejected_stub(self, request: OrderRequest, reason: str):
        order = ost.new_order(request.client_order_id, request.account_id, request.symbol,
                              request.side, request.order_type, request.intended_price,
                              request.quantity or 0.0, ref=request.ref)
        try:
            order = ost.transition(order, OrderStatus.REJECTED, reason=reason, reject_reason=reason)
        except Exception:  # noqa: BLE001
            pass
        return order

    def _record_equity(self, account_id: str) -> None:
        try:
            positions = pos_mod.ENGINE.open_positions(account_id)
            unrealized_total = sum((p.unrealized_pnl or 0.0) for p in positions)
            acct_mod.REGISTRY.record_equity_point(account_id, unrealized_total, len(positions))
        except Exception:  # noqa: BLE001
            pass


def _load_trades() -> list:
    """Same reuse pattern as `engine.execution.replay._load_trades()` —
    reads `journal.STORE` via `store.load_array()` rather than adding a
    second read path. Never raises."""
    try:
        from engine import journal, store
        return store.load_array(journal.STORE)
    except Exception:  # noqa: BLE001
        return []


def dashboard_snapshot(account_id: str = DEFAULT_ACCOUNT_ID, n_events: int = 10) -> dict:
    """One-call, PLAIN-DICT summary for `dashboard_publish.py` (and any
    other reporting consumer): account balances, open positions, pending
    (resting) orders, and the most recent execution activity. Returns
    plain dicts/lists (`dataclasses.asdict()`), not the frozen dataclass
    objects `BrokerInterface` methods return directly, so this is safe to
    drop straight into a JSON-published dashboard payload the same way
    `execution_history.last_for()`/`macro_engine.last_assessment()`
    already are.

    Constructs a fresh `PaperBroker` (which rebuilds from
    `broker_history.jsonl`) on every call — acceptable for a dashboard/
    reporting cadence, not a hot path; `alert_signals.py`'s own scan loop
    uses the cached `_broker()` accessor instead, precisely to avoid this
    cost on its own hot path. Never raises."""
    try:
        import dataclasses
        broker = PaperBroker(account_id=account_id)
        balances = dataclasses.asdict(broker.get_balances(account_id))
        positions = [dataclasses.asdict(p) for p in broker.get_positions(account_id)]
        pending_orders = [dataclasses.asdict(o) for o in broker._working.values()
                          if o.account_id == account_id]
        recent_activity = broker.get_execution_reports(account_id, n=n_events)
        return {
            "account_id": account_id, "balances": balances, "open_positions": positions,
            "pending_orders": pending_orders, "recent_activity": recent_activity,
            "is_estimate": True, "source": "engine.broker.paper_broker",
        }
    except Exception as exc:  # noqa: BLE001
        return {"account_id": account_id, "error": f"dashboard_snapshot error: {exc}",
               "is_estimate": True, "source": "engine.broker.paper_broker"}
