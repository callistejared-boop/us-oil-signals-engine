"""Day 13 — Replay Broker: drives `PaperBroker` from historical trades
exactly as live signals would.

Per the mandate: "The replay engine should be able to drive the Paper
Broker exactly as live signals would. Historical research and paper
trading should share the same execution path wherever practical." This
module is that bridge — `run_broker_replay()` submits each historical
trade's ENTRY through `PaperBroker.submit_order()` and its CLOSE through
`PaperBroker.close_position()`, the identical two calls
`alert_signals.py`'s live Stage-2 flow makes (see
`ALERT_SIGNALS_INTEGRATION` note in PAPER_BROKER_SPECIFICATION.md
Sec.8). No separate "replay-only" fill logic exists anywhere in this
module — reproducing history through the SAME code path a live signal
would take is the entire point.

Reuses Day 12's `engine.execution.replay.PROFILES` (named, disclosed
assumption profiles) and `spread_model.session_for()` verbatim — no
second profile table, no second session-detection function.

Reproducibility: identical to Day 12's convention — ONE shared, seeded
`random.Random(seed)` passed into the `PaperBroker` and advanced
sequentially across every trade. Given the same `rows`/`symbol`/
`profile`/`seed`, two runs produce byte-identical fills (verified by
`tests/test_replay_broker.py::test_run_broker_replay_reproducible_same_seed`).

Isolation: unless the caller passes an explicit `account_id`, each call
gets a FRESH, uniquely-suffixed account id
(`replay-{profile}-{seed}-{uuid}`) so two replay runs — or a replay run
and the live `"paper-default"` account — never share position/balance
state. This is what "Replay compatibility" means here: same CODE PATH,
never shared STATE, unless explicitly requested.
"""
from __future__ import annotations

import random
import uuid

from engine.execution import replay as rp
from engine.execution import spread_model as spr

from .contract import OrderRequest
from .paper_broker import PaperBroker, _load_trades

VERSION = "1.0.0"


def run_broker_replay(rows: "list | None" = None, symbol: "str | None" = None,
                      account_id: "str | None" = None, starting_capital: "float | None" = None,
                      leverage: "float | None" = None, profile: str = "typical",
                      seed: int = 42, include_exit: bool = True) -> dict:
    """Runs historical trades through a fresh `PaperBroker` under one
    named assumption profile. Never raises — degrades to an empty-but-
    valid report on failure, exactly like `engine.execution.replay.
    run_replay()`."""
    try:
        import pandas as pd

        prof = rp.PROFILES.get(profile, rp.PROFILES["typical"])
        acct_id = account_id or f"replay-{profile}-{seed}-{uuid.uuid4().hex[:8]}"
        rng = random.Random(seed)
        broker = PaperBroker(account_id=acct_id, starting_capital=starting_capital,
                             leverage=leverage, rng=rng)

        source_rows = rows if rows is not None else _load_trades()
        if symbol:
            source_rows = [r for r in source_rows if r.get("symbol") == symbol]
        source_rows = sorted(source_rows, key=lambda r: r.get("opened", ""))

        trades = []
        for row in source_rows:
            try:
                entry, stop = row.get("entry"), row.get("stop")
                direction = row.get("direction", "long")
                if entry is None or stop is None:
                    continue
                sym = row.get("symbol", symbol or "XAUUSD")
                signal_ts = pd.Timestamp(row.get("opened")) if row.get("opened") else None
                sess = spr.session_for(signal_ts)
                side = "buy" if direction == "long" else "sell"
                stress = dict(prof.get("stress") or {})

                request = OrderRequest(
                    client_order_id=row.get("id", "") or f"replay-{uuid.uuid4().hex[:12]}",
                    account_id=acct_id, symbol=sym, side=side, order_type="market",
                    intended_price=entry, stop_price=stop, signal_ts=signal_ts, ref=row.get("id", ""),
                    atr_pct=prof["atr_pct"], news_blackout=prof["news_blackout"], session=sess,
                    simulate_failure=stress or None)
                order = broker.submit_order(request)

                close_result = None
                status = row.get("status", "")
                if include_exit and status in ("win", "loss", "scratch", "expired"):
                    exit_price = rp.approx_exit_price(entry, stop, direction, row.get("result_r", 0.0))
                    close_result = broker.close_position(
                        sym, row.get("id", ""), exit_price,
                        exit_ts=row.get("closed") or row.get("opened"),
                        atr_pct=prof["atr_pct"], news_blackout=prof["news_blackout"], session=sess)

                trades.append({"trade_id": row.get("id", ""), "symbol": sym,
                              "order_status": order.status if order else None,
                              "order_id": order.order_id if order else None,
                              "avg_fill_price": order.avg_fill_price if order else None,
                              "closed": bool(close_result and close_result.get("closed")),
                              "realized_pnl_delta": (close_result or {}).get("realized_pnl_delta")})
            except Exception:  # noqa: BLE001
                continue

        balances = broker.get_balances(acct_id)
        positions = broker.get_positions(acct_id)
        return {
            "account_id": acct_id, "profile": profile, "profile_assumptions": prof, "seed": seed,
            "symbol_filter": symbol, "n_trades": len(trades), "trades": trades,
            "final_balances": balances, "open_positions": positions,
            "reproducible": True,
            "note": ("Drives PaperBroker.submit_order()/close_position() — the SAME calls the "
                    "live alert_signals.py Stage-2 flow makes — against historical trades under "
                    "one named, disclosed assumption profile. Same rows+symbol+profile+seed "
                    "always reproduces identical fills. Account is isolated per replay run unless "
                    "an explicit account_id is supplied."),
            "is_estimate": True, "source": "engine.broker.replay_broker",
        }
    except Exception as exc:  # noqa: BLE001
        return {"profile": profile, "seed": seed, "n_trades": 0, "trades": [],
               "reproducible": True, "error": f"run_broker_replay error: {exc}",
               "is_estimate": True, "source": "engine.broker.replay_broker"}
