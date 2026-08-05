"""Day 13 — Paper Account Model.

`PaperAccount` is one virtual trading account. `AccountRegistry` holds
any number of INDEPENDENT named accounts (the mandate: "Support multiple
independent accounts for future testing") — e.g. a live `"paper-live"`
account fed by `alert_signals.py`'s real scan loop, and a separate
`"paper-research-<experiment>"` account a research script can spin up
without touching the live one's balances or equity curve.

Disclosed, illustrative defaults (never fitted, never presented as a
recommendation — same posture as every constant in
`engine/execution/*.py`, Day 12):
  - `DEFAULT_STARTING_CAPITAL = 10_000.0` — a round, illustrative
    account size. `markets.sizing_lines()` already shows 1%-risk sizing
    for 1000/5000/10000 accounts; 10,000 was picked as the middle of
    that existing, already-user-facing set, not a new number invented
    for this Day.
  - `DEFAULT_LEVERAGE = 30.0` — a common retail forex/CFD leverage
    figure. Real leverage varies enormously by broker/jurisdiction/
    instrument; this is a placeholder assumption, explicitly NOT a
    recommendation, and fully overridable per account.
  - `DEFAULT_RISK_PCT = 0.01` — 1% of current equity risked per trade,
    the exact convention `markets.sizing_lines()` already uses
    (`risk = acct * 0.01`) — reused verbatim here for auto-sizing rather
    than inventing a second convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import broker_history as bh
from .contract import AccountSnapshot, now_iso

VERSION = "1.0.0"

DEFAULT_STARTING_CAPITAL = 10_000.0
DEFAULT_LEVERAGE = 30.0
DEFAULT_RISK_PCT = 0.01
CURRENCY = "USD"


@dataclass
class PaperAccount:
    account_id: str
    currency: str = CURRENCY
    starting_capital: float = DEFAULT_STARTING_CAPITAL
    balance: float = 0.0             # realized cash — set to starting_capital on creation
    leverage: float = DEFAULT_LEVERAGE
    risk_pct: float = DEFAULT_RISK_PCT
    margin_used: float = 0.0
    created_ts: str = ""
    equity_curve: list = field(default_factory=list)   # in-memory cache; source of truth is broker_history

    def __post_init__(self):
        if not self.created_ts:
            self.created_ts = now_iso()
        if self.balance == 0.0:
            self.balance = self.starting_capital


class AccountRegistry:
    """Process-local registry of `PaperAccount`s, keyed by `account_id`.
    Not persisted itself as a mutable checkpoint — `PaperAccount.balance`/
    `margin_used` are DERIVED, via `rebuild_from_history()` below, from
    `broker_history.jsonl`'s immutable fill trail every time a fresh
    process starts (this platform's own scan loop is a new process each
    ~15-minute invocation — see `PAPER_BROKER_SPECIFICATION.md` Sec.6
    "Persistence Model"). `starting_capital`/`leverage`/`risk_pct` remain
    plain configuration, identical each process start."""

    def __init__(self):
        self._accounts: dict = {}

    def get_or_create(self, account_id: str, starting_capital: "float | None" = None,
                      leverage: "float | None" = None, risk_pct: "float | None" = None) -> PaperAccount:
        if account_id not in self._accounts:
            self._accounts[account_id] = PaperAccount(
                account_id=account_id,
                starting_capital=starting_capital if starting_capital is not None else DEFAULT_STARTING_CAPITAL,
                balance=starting_capital if starting_capital is not None else DEFAULT_STARTING_CAPITAL,
                leverage=leverage if leverage is not None else DEFAULT_LEVERAGE,
                risk_pct=risk_pct if risk_pct is not None else DEFAULT_RISK_PCT)
        return self._accounts[account_id]

    def get(self, account_id: str) -> "PaperAccount | None":
        return self._accounts.get(account_id)

    def apply_realized_pnl(self, account_id: str, delta: float, fee: float = 0.0) -> PaperAccount:
        acct = self.get_or_create(account_id)
        acct.balance = round(acct.balance + delta - fee, 6)
        return acct

    def reserve_margin(self, account_id: str, amount: float) -> None:
        acct = self.get_or_create(account_id)
        acct.margin_used = round(acct.margin_used + amount, 6)

    def release_margin(self, account_id: str, amount: float) -> None:
        acct = self.get_or_create(account_id)
        acct.margin_used = round(max(0.0, acct.margin_used - amount), 6)

    def snapshot(self, account_id: str, unrealized_pnl_total: float = 0.0,
                open_position_count: int = 0) -> AccountSnapshot:
        acct = self.get_or_create(account_id)
        equity = round(acct.balance + unrealized_pnl_total, 6)
        buying_power = round(max(0.0, equity * acct.leverage - acct.margin_used), 6)
        return AccountSnapshot(
            account_id=account_id, currency=acct.currency, starting_capital=acct.starting_capital,
            balance=acct.balance, equity=equity, margin_used=acct.margin_used,
            buying_power=buying_power, leverage=acct.leverage,
            open_position_count=open_position_count, as_of=now_iso())

    def record_equity_point(self, account_id: str, unrealized_pnl_total: float = 0.0,
                            open_position_count: int = 0) -> dict:
        """Persists one equity-curve point to `broker_accounts.jsonl` —
        called once per Stage-2 entry/close by `paper_broker.py`, giving
        the mandate's "daily equity curve / historical balances" a real,
        replayable time series rather than a snapshot computed on demand
        only when asked. Never raises."""
        snap = self.snapshot(account_id, unrealized_pnl_total, open_position_count)
        acct = self.get_or_create(account_id)
        acct.equity_curve.append({"ts": snap.as_of, "equity": snap.equity, "balance": snap.balance})
        try:
            return bh.record_account_snapshot(snap)
        except Exception:  # noqa: BLE001
            return {"ts": snap.as_of, "equity": snap.equity, "balance": snap.balance, "error": True}

    def position_size(self, account_id: str, entry: float, stop: float, symbol: str) -> float:
        """Auto-sizes a new order's quantity (lots) from
        `risk_pct` of CURRENT equity — the exact
        `markets.sizing_lines()` convention (`risk = acct * 0.01; lots =
        risk / (dist * mult)`), reused verbatim rather than reinvented,
        now applied against this account's actual live equity instead of
        the three illustrative fixed account sizes that Telegram message
        shows. Returns 0.0 (never raises, never a negative/undefined
        size) if `entry == stop` (zero risk distance — cannot size)."""
        try:
            from engine.markets import MARKETS
            mult = float(MARKETS.get(symbol, {}).get("mult", 100.0))
            dist = abs(float(entry) - float(stop))
            if dist <= 0:
                return 0.0
            acct = self.get_or_create(account_id)
            risk_dollars = acct.balance * acct.risk_pct
            return round(risk_dollars / (dist * mult), 6)
        except Exception:  # noqa: BLE001
            return 0.0

    def reset(self, account_id: "str | None" = None) -> None:
        """Testing-only: drops in-memory account state (does not touch
        `broker_accounts.jsonl`'s persisted history)."""
        if account_id is None:
            self._accounts.clear()
        else:
            self._accounts.pop(account_id, None)

    def rebuild_from_history(self, account_id: str) -> PaperAccount:
        """Recomputes `balance`/`margin_used` from
        `position_engine.ENGINE`'s own rebuilt state — call
        `position_engine.ENGINE.rebuild_from_history(account_id)` FIRST
        (`PaperBroker.__init__()` always does both, in that order).
        `balance = starting_capital + sum(realized_pnl) - sum(fees)`
        across every symbol this account has ever traded;
        `margin_used = sum(margin_required(...))` over currently-open
        positions, priced at each position's own average entry (the
        margin a real broker would have reserved at trade time, not a
        continuously repriced figure — a disclosed simplification, see
        PAPER_BROKER_SPECIFICATION.md Sec.5). Never raises."""
        try:
            from .position_engine import ENGINE as pos_engine
            acct = self.get_or_create(account_id)
            total_realized = 0.0
            total_fees = 0.0
            margin = 0.0
            for (acct_id, symbol), pos in pos_engine._positions.items():
                if acct_id != account_id:
                    continue
                total_realized += pos.realized_pnl
                total_fees += pos.fees_paid
                if pos.direction != "flat" and pos.avg_entry is not None:
                    margin += pos_engine.margin_required(symbol, pos.avg_entry, pos.quantity, acct.leverage)
            acct.balance = round(acct.starting_capital + total_realized - total_fees, 6)
            acct.margin_used = round(margin, 6)
            return acct
        except Exception:  # noqa: BLE001
            return self.get_or_create(account_id)


# Module-level singleton — see `position_engine.ENGINE`'s docstring for
# the same "one shared instance per process" reasoning.
REGISTRY = AccountRegistry()
