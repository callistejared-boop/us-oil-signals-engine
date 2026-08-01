"""Read TradingView webhook confirmations (written by tv_webhook.py) and fold
them into the engine as a small extra confirmation. Fail-safe: if no fresh
TradingView signal exists (the common case - webhooks need a paid TV plan and a
tunnel), this contributes 0 and nothing changes.
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "tradingview_signals.json"
TV_PTS = 2


def _load():
    try:
        d = json.loads(STORE.read_text())
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def latest(symbol, max_age_min=60, now=None):
    """Most recent TradingView action ('buy'/'sell') for symbol within age, or None."""
    now = now or datetime.now(timezone.utc)
    best = None
    for r in _load():
        if str(r.get("symbol", "")).upper() != symbol.upper():
            continue
        try:
            ts = datetime.fromisoformat(r["ts"])
            if (now - ts).total_seconds() / 60.0 > max_age_min:
                continue
        except Exception:  # noqa: BLE001
            continue
        if best is None or r["ts"] > best["ts"]:
            best = r
    return (best.get("action", "").lower() or None) if best else None


def confirmation(symbol, direction, max_age_min=60, now=None):
    """Return (delta_points, rationale). +TV_PTS if TV agrees, - if conflicts, 0 none."""
    act = latest(symbol, max_age_min=max_age_min, now=now)
    if act not in ("buy", "sell"):
        return 0, ""
    tv_long = act == "buy"
    trade_long = direction == "long"
    if tv_long == trade_long:
        return TV_PTS, f"TradingView {act.upper()} agrees (+{TV_PTS})"
    return -TV_PTS, f"TradingView {act.upper()} conflicts (-{TV_PTS})"
