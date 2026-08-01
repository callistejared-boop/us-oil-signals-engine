"""Macro correlation gate — is the trade fighting the US dollar?

Gold, EUR/USD and Bitcoin are all inversely correlated with the US Dollar Index
(DXY); WTI is mildly inverse. Trading long gold into a rising dollar is a classic
macro headwind. This fetches the DXY trend on the laptop, caches it to macro.json
(refreshed with the 5-minute job), and reports whether a given trade is ALIGNED
with or FIGHTS the dollar. Fail-safe: no data -> None, everything degrades cleanly.

It is DISPLAYED and (later) stamped on trades so the walk-forward loop can prove
whether macro-alignment predicts wins BEFORE it is ever allowed to change a score.
"""
import json
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
MACRO_PATH = ROOT / "macro.json"

# sign of each instrument's correlation with the US dollar (-1 = inverse)
USD_SENSITIVITY = {"XAUUSD": -1, "EURUSD": -1, "BTCUSD": -1, "WTIUSD": -0.5}


def dollar_trend(timeout: int = 20):
    """Short-term DXY trend via EMA stack. Returns {'trend','price'} or None."""
    try:
        import yfinance as yf
        df = yf.download("DX-Y.NYB", period="1mo", interval="1h", progress=False)
        if df is None or df.empty:
            df = yf.download("DX=F", period="1mo", interval="1h", progress=False)
        c = df["Close"].dropna()
        if hasattr(c, "columns"):
            c = c.iloc[:, 0]
        if len(c) < 50:
            return None
        ef = float(c.ewm(span=20).mean().iloc[-1])
        es = float(c.ewm(span=50).mean().iloc[-1])
        px = float(c.iloc[-1])
        trend = "up" if px > ef > es else "down" if px < ef < es else "flat"
        return {"trend": trend, "price": round(px, 3)}
    except Exception:  # noqa: BLE001
        return None


def refresh_macro():
    d = dollar_trend()
    if not d:
        return None
    d.update({"asof": date.today().isoformat(),
              "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    try:
        MACRO_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return d


def read_macro(max_age_days: int = 2):
    try:
        d = json.loads(MACRO_PATH.read_text())
        if (date.today() - date.fromisoformat(d["asof"])).days > max_age_days:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


def macro_alignment(symbol, direction, dxy_trend):
    """Return {aligned: True/False/None, note}. None when no clean read."""
    sens = USD_SENSITIVITY.get(symbol, 0)
    if not dxy_trend or dxy_trend == "flat" or sens == 0:
        return {"aligned": None, "note": "no strong USD trend / not USD-sensitive"}
    usd_up = dxy_trend == "up"
    # instrument's expected drift given the dollar and its sensitivity sign
    instrument_up = (usd_up and sens > 0) or ((not usd_up) and sens < 0)
    trade_up = direction == "long"
    aligned = (instrument_up == trade_up)
    verdict = "ALIGNED with the dollar" if aligned else "FIGHTS the dollar (caution)"
    return {"aligned": aligned,
            "note": f"USD {dxy_trend} -> {symbol} macro drift {'up' if instrument_up else 'down'}; "
                    f"{direction} {verdict}"}


def macro_note(symbol, direction):
    m = read_macro()
    if not m:
        return "n/a (no fresh DXY read)"
    return macro_alignment(symbol, direction, m.get("trend"))["note"]


if __name__ == "__main__":
    d = refresh_macro()
    print("macro.json updated:", d if d else "DXY fetch failed - macro gate will show n/a.")
