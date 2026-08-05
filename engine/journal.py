"""Live trade journal - symbol-aware, with professional trade management.

Each entry is settled against real price using the same rules as the
backtester: stop to break-even after +1R, bank 50% at +2R, runner to target
(pessimistic, stop wins ties). So the live track record matches the tested
methodology.

Storage is hardened: writes are atomic (temp file + os.replace) with a rolling
.bak, and reads that hit a truncated/corrupt file are SALVAGED to the last
complete record instead of silently returning an empty list.

Learning loop: every entry is STAMPED with the live news context at the moment
it was logged (news signal / strength / confidence delta), so the self-review
can later measure whether news-agreeing trades actually win more. Stamping is
fail-safe and live-only - it never blocks a trade and never touches backtests.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict, dataclass

import pandas as pd

STORE = pathlib.Path(__file__).resolve().parent.parent / "trades.json"
BAK = STORE.with_suffix(".json.bak")
TMP = STORE.with_suffix(".json.tmp")
ENTRY_TOL = 0.0015
MAX_OPEN_BARS = 96 * 5


@dataclass
class Trade:
    id: str
    opened: str
    direction: str
    entry: float
    stop: float
    target: float
    rr: float
    confidence: int
    symbol: str = "XAUUSD"
    status: str = "open"      # open | win | loss | scratch | expired
    closed: str = ""
    result_r: float = 0.0
    news_signal: str = ""     # BUY | SELL | NEUTRAL | "" (none/unknown at entry)
    news_strength: str = ""   # HIGH | MED | LOW | ""
    news_delta: int = 0       # confidence points news added (+) or removed (-)
    regime_trend: str = ""    # trend | range | "" (unknown at entry)
    regime_vol: str = ""      # expansion | contraction | normal | ""
    guard_action: str = ""    # allow | downgrade | suppress | "" (range-guard verdict)
    guard_penalty: int = 0    # confidence pts the guard removed at entry (<=0)
    guard_headwind: str = ""  # "yes" | "no" | "" (was the trade fighting the dollar)
    confluence_score: int = -1   # 0-100 MAST score at entry, -1 = not computed
    confluence_agree: int = 0    # count of confirmation layers that agreed
    # --- Day 6: direct stable references (see CONFIDENCE_ENGINE_SPECIFICATION.md
    # Sec.5 "Trade Journal Integration"). Both are constructed with the exact
    # same f"{symbol}-{timestamp}" format as this row's own `id` (by design —
    # alert_signals.py computes the id ONCE and passes it through to
    # confluence_history.record()/confidence_history.record() as `ref` before
    # calling log_signal(), so `id == confluence_ref == confidence_ref` for
    # every trade logged from Day 6 onward). "" means either the trade
    # predates Day 6 (no ref was ever computed) or the corresponding engine
    # read failed for this trade — callers must fall back to the
    # nearest-timestamp join (confidence_calibration.join_trades_with_confidence)
    # exactly as Day 4/5 already do, never assume a non-empty value.
    confluence_ref: str = ""     # -> confluence_history.jsonl row (via find-by-ref)
    confidence_ref: str = ""     # -> confidence_history.jsonl row (via confidence_history.find_by_ref)
    # --- Day 7: completes the unified trade ID (see
    # MARKET_MEMORY_SPECIFICATION.md Sec.2 "Reference Architecture"). Same
    # equality-by-construction guarantee as confluence_ref/confidence_ref:
    # id == regime_ref == confluence_ref == confidence_ref for every trade
    # logged from Day 7 onward.
    regime_ref: str = ""         # -> regime_history.jsonl row (via regime_history.find_by_ref)
    # --- Day 11: completes the unified trade ID for the Macro Intelligence
    # Engine (see MACRO_ENGINE_SPECIFICATION.md Sec.5 "Trade Journal
    # Integration"). Same equality-by-construction guarantee as every ref
    # above: id == regime_ref == confluence_ref == confidence_ref ==
    # macro_ref for every trade logged from Day 11 onward. Advisory-only —
    # this ref exists so a past macro assessment can be looked up for a
    # specific trade during review; it is never read by any gating/sizing
    # path.
    macro_ref: str = ""          # -> macro_history.jsonl row (via macro_history.find_by_ref)
    # --- Day 12: completes the unified trade ID for the Execution
    # Simulator (see EXECUTION_SIMULATOR_SPECIFICATION.md Sec.6 "Trade
    # Journal Integration"). Same equality-by-construction guarantee as
    # every ref above: id == regime_ref == confluence_ref ==
    # confidence_ref == macro_ref == execution_ref for every trade logged
    # from Day 12 onward. Advisory-only — this ref exists so a trade's
    # simulated fill-quality report can be looked up during review; it is
    # never read by any gating/sizing path, and it never determines this
    # row's own entry/stop/target (those remain the strategy's INTENDED
    # levels, exactly as before Day 12 — see the spec's explicit note on
    # why `Trade.entry` is never overwritten with a simulated fill price).
    execution_ref: str = ""      # -> execution_history.jsonl row (via execution_history.find_by_ref)
    # --- Day 13: completes the unified trade ID for the Broker
    # Abstraction Layer (see PAPER_BROKER_SPECIFICATION.md Sec.6 "Trade
    # Journal Integration"). Same equality-by-construction guarantee as
    # every ref above: id == regime_ref == confluence_ref ==
    # confidence_ref == macro_ref == execution_ref == broker_ref for
    # every trade logged from Day 13 onward. Advisory-only — this ref is
    # the same string passed as `OrderRequest.ref`/`client_order_id` to
    # `PaperBroker.submit_order()`, so a trade's full paper-broker order/
    # fill/event history can be looked up during review via
    # `broker_history.py`'s `ref`-keyed queries. It is never read by any
    # gating/sizing path, and — same as `execution_ref` before it — it
    # never determines this row's own entry/stop/target.
    broker_ref: str = ""         # -> broker_orders.jsonl / broker_fills.jsonl rows (via ref)


def _news_stamp(symbol, direction):
    """Live news context at log time. Fail-safe: any error -> neutral/no-effect."""
    try:
        from engine import bias_adjust as ba
        view = ba.news_view(symbol) or {}
        delta, _ = ba.adjustment(symbol, direction)
        return (view.get("signal", "") or "", view.get("strength", "") or "", int(delta))
    except Exception:  # noqa: BLE001
        return "", "", 0


def _salvage(text: str) -> list:
    depth = in_str = esc = 0
    last_close = -1
    for i, ch in enumerate(text):
        if esc:
            esc = 0
            continue
        if in_str:
            if ch == "\\":
                esc = 1
            elif ch == '"':
                in_str = 0
            continue
        if ch == '"':
            in_str = 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_close = i
    if last_close < 0:
        return []
    candidate = text[:last_close + 1].rstrip()
    if not candidate.endswith("]"):
        candidate += "]"
    try:
        rows = json.loads(candidate)
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def _read(path: pathlib.Path) -> list:
    try:
        text = path.read_text()
    except Exception:  # noqa: BLE001
        return []
    try:
        rows = json.loads(text)
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return _salvage(text)


def _load() -> list:
    if STORE.exists():
        rows = _read(STORE)
        if rows:
            return rows
        if BAK.exists():
            return _read(BAK)
        return []
    return []


def _save(rows: list) -> None:
    """Atomic write with a rolling backup. Never truncates the live file."""
    try:
        if STORE.exists():
            cur = _read(STORE)
            if cur:
                BAK.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    TMP.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    os.replace(TMP, STORE)


def is_open(symbol: str, direction: str, entry: float) -> bool:
    for r in _load():
        if r["status"] == "open" and r.get("symbol", "XAUUSD") == symbol \
           and r["direction"] == direction \
           and abs(r["entry"] - entry) <= max(abs(entry) * ENTRY_TOL, 1e-9):
            return True
    return False


def make_ref(symbol: str, when: pd.Timestamp) -> str:
    """The single, canonical stable-reference format used across the trade
    journal, confluence_history.jsonl, and confidence_history.jsonl (Day 6).
    Extracted as its own function so every caller constructs the identical
    string this row's own `id` will use — see Trade.confluence_ref /
    Trade.confidence_ref's docstring for why that equality matters."""
    return f"{symbol}-{str(when).replace(' ', 'T')}"


def log_signal(sig, when: pd.Timestamp, regime=None, guard=None,
              confluence=None, confluence_ref: str = "",
              confidence_ref: str = "", regime_ref: str = "",
              macro_ref: str = "", execution_ref: str = "",
              broker_ref: str = "") -> bool:
    sym = getattr(sig, "symbol", "XAUUSD")
    if is_open(sym, sig.direction, sig.entry):
        return False
    ns, nstr, nd = _news_stamp(sym, sig.direction)
    reg = regime or {}
    g = guard or {}
    cf = confluence or {}
    rows = _load()
    rows.append(asdict(Trade(
        id=make_ref(sym, when), opened=str(when),
        direction=sig.direction, entry=float(sig.entry), stop=float(sig.stop),
        target=float(sig.target), rr=float(sig.rr), confidence=int(sig.confidence),
        symbol=sym, news_signal=ns, news_strength=nstr, news_delta=nd,
        regime_trend=str(reg.get("trend", "")), regime_vol=str(reg.get("vol", "")),
        confluence_score=int(cf.get("score", -1)) if cf else -1,
        confluence_agree=int(cf.get("agree", 0)) if cf else 0,
        guard_action=str(g.get("action", "")),
        guard_penalty=int(g.get("penalty", 0) or 0),
        guard_headwind=("yes" if g.get("macro_headwind") else
                        "no" if g.get("action") else ""),
        confluence_ref=str(confluence_ref or ""),
        confidence_ref=str(confidence_ref or ""),
        regime_ref=str(regime_ref or ""),
        macro_ref=str(macro_ref or ""),
        execution_ref=str(execution_ref or ""),
        broker_ref=str(broker_ref or ""))))
    _save(rows)
    return True


def _manage(hi, lo, direction, entry, stop, target):
    """Break-even after +1R, bank 50% at +2R, runner to target."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None, 0
    finalR = abs(target - entry) / risk
    be = partial = False
    for j in range(len(hi)):
        cur_stop = entry if be else stop
        if direction == "long":
            if lo[j] <= cur_stop:
                if partial:
                    return 0.5 * 2.0 + 0.5 * (0.0 if be else -1.0), j
                return (0.0 if be else -1.0), j
            if hi[j] >= target:
                return 0.5 * 2.0 + 0.5 * finalR, j
            if not be and hi[j] >= entry + risk:
                be = True
            if not partial and hi[j] >= entry + 2 * risk:
                partial = True
        else:
            if hi[j] >= cur_stop:
                if partial:
                    return 0.5 * 2.0 + 0.5 * (0.0 if be else -1.0), j
                return (0.0 if be else -1.0), j
            if lo[j] <= target:
                return 0.5 * 2.0 + 0.5 * finalR, j
            if not be and lo[j] <= entry - risk:
                be = True
            if not partial and lo[j] <= entry - 2 * risk:
                partial = True
    return None, len(hi) - 1


def settle(df: pd.DataFrame, symbol: str | None = None) -> None:
    rows = _load()
    changed = False
    for r in rows:
        if r["status"] != "open":
            continue
        if symbol is not None and r.get("symbol", "XAUUSD") != symbol:
            continue
        seg = df.loc[df.index > pd.Timestamp(r["opened"])]
        if seg.empty:
            continue
        res, j = _manage(seg["High"].values, seg["Low"].values,
                         r["direction"], r["entry"], r["stop"], r["target"])
        if res is not None:
            r["result_r"] = round(float(res), 3)
            r["status"] = ("win" if res > 1e-9 else "loss" if res < -1e-9 else "scratch")
            r["closed"] = str(seg.index[j])
            changed = True
        elif len(seg) >= MAX_OPEN_BARS:
            r["status"] = "expired"
            r["closed"] = str(seg.index[-1])
            changed = True
    if changed:
        _save(rows)


def stats() -> dict:
    rows = _load()
    closed = [r for r in rows if r["status"] in ("win", "loss", "scratch")]
    wins = [r for r in closed if r["status"] == "win"]
    losses = [r for r in closed if r["status"] == "loss"]
    net_r = sum(r["result_r"] for r in closed)
    since = rows[0]["opened"][:10] if rows else "-"
    return {
        "total": len(rows), "closed": len(closed),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(closed), 3) if closed else None,
        "net_r": round(net_r, 2), "since": since,
    }


def track_record_lines() -> list:
    s = stats()
    if s["closed"] == 0:
        return [f"TRACK RECORD: {s['open']} open, none closed yet "
                f"(tracking since {s['since']})."]
    wr = f"{s['win_rate']*100:.0f}%"
    return [
        f"TRACK RECORD (live, all markets, since {s['since']}):",
        f"  closed {s['closed']} | wins {s['wins']} | losses {s['losses']} "
        f"| win-rate {wr} | net {s['net_r']:+.1f}R | {s['open']} open",
    ]
