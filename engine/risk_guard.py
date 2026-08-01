"""Personal risk circuit breaker — the rules that protect the account.

Two hard rules, enforced automatically on the live alert path:

  1. DAILY LOSS LOCK: once TODAY's closed trades for a given SYMBOL sum to
     -MAX_DAILY_LOSS_R or worse, NO new signals are published for that symbol
     until tomorrow (UTC). Open trades are still managed/settled — the lock
     only stops adding risk. Scoped per-symbol so a bad day on gold can't
     silently lock out oil or Bitcoin signals too.
  2. POSITION CAP: at most MAX_OPEN_PER_SYMBOL open trades per symbol. No
     stacking three oil longs because three scans fired.

Both are configurable via .env (MAX_DAILY_LOSS_R, MAX_OPEN_PER_SYMBOL) and
default to the values in RISK_RULES.md (2R day-stop, 1 position). Fail-safe:
any error evaluating the rules returns "unlocked" so a bug can never silently
kill the pipeline — but errors are reported in the reason string.

Pure logic + a thin journal reader, so it is unit-testable offline.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_MAX_DAILY_LOSS_R = 2.0
DEFAULT_MAX_OPEN_PER_SYMBOL = 1


def _rows():
    try:
        from engine import store
        return store.load_array(ROOT / "trades.json")
    except Exception:  # noqa: BLE001
        return []


def today_realized_r(rows, today=None, symbol=None) -> float:
    """Sum of result_r for trades CLOSED today (UTC), scoped to `symbol`.

    Bug fix (2026-07-28): this used to sum every symbol's closed trades
    together, so a bad day on one instrument would lock out signals on all
    the others too. `open_count()` already filtered by symbol a few lines
    below — this brings the loss lock in line with that, using the same
    legacy-row fallback (untagged old rows are treated as XAUUSD, matching
    how the account originally started before multi-symbol support)."""
    today = today or datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for r in rows:
        if symbol is not None and r.get("symbol", "XAUUSD") != symbol:
            continue
        if r.get("status") in ("win", "loss", "scratch") \
           and str(r.get("closed", ""))[:10] == today:
            total += float(r.get("result_r", 0) or 0)
    return round(total, 3)


def open_count(rows, symbol=None) -> int:
    return sum(1 for r in rows if r.get("status") == "open"
               and (symbol is None or r.get("symbol", "XAUUSD") == symbol))


def evaluate(symbol, rows=None, max_daily_loss_r=None, max_open=None,
             today=None) -> dict:
    """Return {locked, reason, day_r, open_n}. locked=True means publish no
    NEW signal for `symbol` right now."""
    try:
        if rows is None:
            rows = _rows()
        if max_daily_loss_r is None or max_open is None:
            try:
                from engine import config
                s = config.load()
                if max_daily_loss_r is None:
                    max_daily_loss_r = float(getattr(s, "max_daily_loss_r", 0)
                                             or DEFAULT_MAX_DAILY_LOSS_R)
                if max_open is None:
                    max_open = int(getattr(s, "max_open_per_symbol", 0)
                                   or DEFAULT_MAX_OPEN_PER_SYMBOL)
            except Exception:  # noqa: BLE001
                max_daily_loss_r = max_daily_loss_r or DEFAULT_MAX_DAILY_LOSS_R
                max_open = max_open or DEFAULT_MAX_OPEN_PER_SYMBOL
        day_r = today_realized_r(rows, today=today, symbol=symbol)
        n_open = open_count(rows, symbol)
        if day_r <= -abs(max_daily_loss_r):
            return {"locked": True, "day_r": day_r, "open_n": n_open,
                    "reason": f"DAILY LOSS LOCK: {day_r:+.1f}R today (limit "
                              f"-{abs(max_daily_loss_r):.0f}R). No new signals until "
                              "tomorrow UTC — capital preservation first."}
        if n_open >= max_open:
            return {"locked": True, "day_r": day_r, "open_n": n_open,
                    "reason": f"POSITION CAP: {n_open} open {symbol} trade(s) "
                              f"(max {max_open}). Manage what's on before adding."}
        return {"locked": False, "day_r": day_r, "open_n": n_open,
                "reason": f"clear (day {day_r:+.1f}R, {n_open} open)"}
    except Exception as exc:  # noqa: BLE001
        return {"locked": False, "day_r": 0.0, "open_n": 0,
                "reason": f"risk-guard error ({exc}) — failing open"}
