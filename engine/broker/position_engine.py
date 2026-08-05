"""Day 13 — Position Engine.

Centralized, symbol-aggregate position tracking. "Centralized" means
there is exactly one `PositionEngine` instance per process
(`ENGINE` at module level, mirroring `account.REGISTRY`'s singleton
pattern below) — every `PaperBroker` instance reads/writes through it,
so two `PaperBroker`s sharing an account never see divergent position
state.

Aggregation model (a disclosed simplification — see
PAPER_BROKER_SPECIFICATION.md Sec.7 "Known Limitations"): positions are
tracked per `(account_id, symbol)`, NOT per individual trade. This
matches how real brokers/OMS net exposure — if this platform ever opens
two independently-managed trades on the same symbol at the same time,
their fills blend into one weighted-average position here rather than
being tracked as two separate lots. Each contributing trade's `ref` is
still recorded in `open_refs` for traceability, and every individual
FILL remains separately queryable via `broker_history.fills_for_order()`
— no information is lost, only the position VIEW is aggregated.

Reuse discipline (mandate: "Avoid duplicating calculations already
present elsewhere"):
  - Contract size per symbol reuses `engine.markets.MARKETS[...]["mult"]`
    verbatim — the exact same multiplier `markets.sizing_lines()` already
    uses for its own Telegram position-sizing lines. No second multiplier
    table is introduced.
  - Execution cost per fill is read directly from the `Fill` object
    (itself sourced from `engine.execution.fill_model`, Day 12) — never
    recomputed here.
  - R-multiple / expectancy statistics are NOT computed here at all —
    that remains `engine.research_stats.full_report()`'s job (see
    `research_bridge.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .contract import PositionSnapshot, now_iso

VERSION = "1.0.0"


def _mult(symbol: str) -> float:
    try:
        from engine.markets import MARKETS
        return float(MARKETS.get(symbol, {}).get("mult", 100.0))
    except Exception:  # noqa: BLE001
        return 100.0


@dataclass
class _PositionState:
    account_id: str
    symbol: str
    direction: str = "flat"      # "long" | "short" | "flat"
    quantity: float = 0.0        # lots, always >= 0 (direction carries the sign)
    avg_entry: "float | None" = None
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    execution_costs: float = 0.0
    opened_ts: str = ""
    updated_ts: str = ""
    open_refs: tuple = field(default_factory=tuple)


class PositionEngine:
    """Not thread-safe (this platform is a single-threaded 15-minute
    scan loop, same concurrency model as every other Day 1-12 module —
    see paper_broker.py's "Concurrency" note for what "concurrent order
    scenarios" means in that context)."""

    def __init__(self):
        self._positions: dict = {}   # (account_id, symbol) -> _PositionState

    def _get_or_create(self, account_id: str, symbol: str) -> _PositionState:
        key = (account_id, symbol)
        if key not in self._positions:
            self._positions[key] = _PositionState(account_id=account_id, symbol=symbol)
        return self._positions[key]

    def on_fill(self, account_id: str, symbol: str, side: str, leg: str,
               price: float, quantity: float, fee: float, execution_cost: float,
               ref: str = "", ts: "str | None" = None) -> dict:
        """Applies one fill to the aggregate position. `side` is
        "buy"/"sell" (already resolved by `fill_model._side()`-equivalent
        logic in `paper_broker.py`). Returns a small dict describing what
        happened (`opened`/`increased`/`reduced`/`closed`/`flipped`) so
        the caller can decide which events to emit. Never raises — any
        internal error degrades to `{"action": "error", ...}` rather than
        corrupting position state."""
        try:
            ts = ts or now_iso()
            pos = self._get_or_create(account_id, symbol)
            signed_qty = quantity if side == "buy" else -quantity
            cur_signed = pos.quantity if pos.direction == "long" else (
                -pos.quantity if pos.direction == "short" else 0.0)
            new_signed = cur_signed + signed_qty

            action = "opened" if pos.direction == "flat" else "increased"
            realized_delta = 0.0

            if pos.direction == "flat":
                pos.direction = "long" if signed_qty > 0 else "short"
                pos.avg_entry = price
                pos.quantity = abs(signed_qty)
                pos.opened_ts = ts
                pos.open_refs = (ref,) if ref else ()
            elif (pos.direction == "long" and signed_qty > 0) or \
                 (pos.direction == "short" and signed_qty < 0):
                # same-direction add -> weighted-average entry
                total_qty = pos.quantity + abs(signed_qty)
                pos.avg_entry = ((pos.avg_entry * pos.quantity) +
                                 (price * abs(signed_qty))) / total_qty
                pos.quantity = total_qty
                action = "increased"
                if ref and ref not in pos.open_refs:
                    pos.open_refs = pos.open_refs + (ref,)
            else:
                # opposite-direction fill -> reduces, closes, or flips
                closing_qty = min(abs(signed_qty), pos.quantity)
                sign = 1 if pos.direction == "long" else -1
                realized_delta = sign * (price - pos.avg_entry) * closing_qty * _mult(symbol)
                pos.realized_pnl += realized_delta
                pos.quantity -= closing_qty
                remainder = abs(signed_qty) - closing_qty
                if pos.quantity <= 1e-12 and remainder <= 1e-12:
                    action = "closed"
                    pos.direction = "flat"
                    pos.avg_entry = None
                    pos.open_refs = ()
                elif pos.quantity <= 1e-12 and remainder > 1e-12:
                    action = "flipped"
                    pos.direction = "short" if pos.direction == "long" else "long"
                    pos.avg_entry = price
                    pos.quantity = remainder
                    pos.open_refs = (ref,) if ref else ()
                else:
                    action = "reduced"
                    if ref and ref not in pos.open_refs:
                        pos.open_refs = pos.open_refs + (ref,)

            pos.fees_paid += fee
            pos.execution_costs += execution_cost
            pos.updated_ts = ts
            return {"action": action, "realized_pnl_delta": round(realized_delta, 6),
                    "direction": pos.direction, "quantity": pos.quantity}
        except Exception as exc:  # noqa: BLE001
            return {"action": "error", "error": str(exc)}

    def unrealized_pnl(self, account_id: str, symbol: str, mark_price: "float | None") -> "float | None":
        key = (account_id, symbol)
        pos = self._positions.get(key)
        if pos is None:
            return None
        if pos.direction == "flat":
            return 0.0
        if mark_price is None or pos.avg_entry is None:
            return None
        sign = 1 if pos.direction == "long" else -1
        return round(sign * (mark_price - pos.avg_entry) * pos.quantity * _mult(symbol), 6)

    def margin_required(self, symbol: str, price: float, quantity: float, leverage: float) -> float:
        """Disclosed, illustrative margin formula: (quantity * price *
        contract_multiplier) / leverage — standard retail CFD/forex
        margin convention. Never fitted to any broker's real margin
        schedule; see PAPER_BROKER_SPECIFICATION.md Sec.5."""
        if leverage <= 0:
            return float("inf")
        return abs(quantity) * abs(price) * _mult(symbol) / leverage

    def snapshot(self, account_id: str, symbol: str, mark_price: "float | None" = None) -> PositionSnapshot:
        pos = self._positions.get((account_id, symbol))
        if pos is None or pos.direction == "flat":
            return PositionSnapshot(
                account_id=account_id, symbol=symbol, direction="flat", quantity=0.0,
                avg_entry=None, realized_pnl=(pos.realized_pnl if pos else 0.0),
                unrealized_pnl=0.0, fees_paid=(pos.fees_paid if pos else 0.0),
                execution_costs=(pos.execution_costs if pos else 0.0),
                risk_utilization=None, opened_ts="", updated_ts=(pos.updated_ts if pos else ""))
        return PositionSnapshot(
            account_id=account_id, symbol=symbol, direction=pos.direction, quantity=pos.quantity,
            avg_entry=pos.avg_entry, realized_pnl=pos.realized_pnl,
            unrealized_pnl=self.unrealized_pnl(account_id, symbol, mark_price),
            fees_paid=pos.fees_paid, execution_costs=pos.execution_costs,
            risk_utilization=None, opened_ts=pos.opened_ts, updated_ts=pos.updated_ts,
            open_refs=pos.open_refs)

    def open_positions(self, account_id: str) -> list:
        out = []
        for (acct, symbol), pos in self._positions.items():
            if acct == account_id and pos.direction != "flat":
                out.append(self.snapshot(account_id, symbol))
        return out

    def reset(self, account_id: "str | None" = None) -> None:
        """Testing/replay-only: clears in-memory position state (never
        touches `broker_history.py`'s persisted records — those remain
        the immutable audit trail)."""
        if account_id is None:
            self._positions.clear()
        else:
            for key in [k for k in self._positions if k[0] == account_id]:
                del self._positions[key]

    def rebuild_from_history(self, account_id: str) -> None:
        """Reconstructs this account's in-memory position state by
        replaying every persisted fill for it, in timestamp order.

        Why this exists: this platform's own scan loop
        (`alert_signals.py`, cron/GitHub-Actions-scheduled) runs as a
        FRESH PROCESS roughly every 15 minutes — there is no long-lived
        daemon holding position state in memory between scans. Without
        this rebuild step, every new process would start every account
        `flat` and silently lose all prior open exposure and realized
        P&L. `PaperBroker.__init__()` calls this once per account before
        serving any request, making `broker_history.py`'s immutable JSONL
        trail the actual source of truth and this in-memory engine a
        (correct, deterministic) CACHE over it, not independent state.
        See PAPER_BROKER_SPECIFICATION.md Sec.6 "Persistence Model".

        Idempotent — safe to call more than once (clears this account's
        in-memory state first, then replays from scratch). Never raises."""
        try:
            from . import broker_history as bh
            self.reset(account_id)
            fills = bh.all_fills(account_id)
            fills.sort(key=lambda f: f.get("ts", ""))
            order_ref_by_id = {r["order_id"]: r.get("ref", "") for r in bh.all_orders(account_id)}
            for f in fills:
                self.on_fill(account_id, f["symbol"], f["side"], f["leg"], f["price"],
                            f["quantity"], f.get("fee", 0.0) or 0.0,
                            f.get("execution_cost", 0.0) or 0.0,
                            ref=order_ref_by_id.get(f.get("order_id"), ""), ts=f.get("ts"))
        except Exception:  # noqa: BLE001
            pass


# Module-level singleton — see class docstring for why one shared
# instance per process is the intended usage (mirrors `account.REGISTRY`).
ENGINE = PositionEngine()
