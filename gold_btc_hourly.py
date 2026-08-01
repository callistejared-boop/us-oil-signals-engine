"""Hourly Gold + Bitcoin pipeline - the gold/BTC twin of wti_hourly.py.

Added 2026-07-28 as part of turning gold (XAUUSD) and Bitcoin (BTCUSD) on
end-to-end alongside the existing WTI pipeline. Each hour it: (1) refreshes
the gold and BTC news slices (merged into fundamentals.json - the WTI slice
that wti_hourly.py owns is left untouched), then (2) generates the full
institutional trade note for each symbol and sends it to Telegram.

Channel routing (per user decision, 2026-07-28): Bitcoin has no dedicated
Telegram channel yet, so its notes fall back to TELEGRAM_CHANNEL (the same
channel gold uses) via engine.markets.channel_for()'s existing per-symbol
fallback - this is not a bug, it's the deliberate, agreed-upon interim
behavior. Once a dedicated Bitcoin channel exists, set TELEGRAM_CHANNEL_BTCUSD
in .env (or the repo's GitHub Actions secrets) and BTC notes will
automatically route there instead - no code change needed, channel_for()
already checks for it.

Fail-safe throughout: any refresh error is logged and the note still sends
using its fallback context, and a failure on one symbol never blocks the
other (matching wti_hourly.py's and dashboard_publish.py's philosophy).
"""
import json
import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SYMBOLS = ["XAUUSD", "BTCUSD"]


def refresh_news(symbol):
    """Build one symbol's news slice and merge it into fundamentals.json,
    leaving every other symbol's cached slice untouched."""
    try:
        from engine import fundamentals_feed as ff
        res = ff.build_symbol(ff.SYMBOLS[symbol])
        if res is None:
            print(f"{symbol} news: no data this run (note uses fallback context).")
            return
        data = ff.read_feed_raw() or {}
        syms = dict(data.get("symbols", {}))
        syms[symbol] = res
        out = {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof": date.today().isoformat(),
            "source": data.get("source",
                               "Google News RSS (negation-aware headline sentiment)"),
            "symbols": syms,
        }
        ff.FEED_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"{symbol} news: {res.get('signal')} {res.get('strength')} "
              f"({res.get('n_total')} headlines)")
    except Exception as exc:  # noqa: BLE001
        print(f"{symbol} news refresh error:", exc)


def main():
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
          "Gold+BTC hourly pipeline start")
    import wti_note
    for symbol in SYMBOLS:
        refresh_news(symbol)
        try:
            sys.argv = ["wti_note.py", "--send"]   # generate + push to Telegram
            wti_note.main(symbol)
        except Exception as exc:  # noqa: BLE001
            # One symbol's failure must never block the other.
            print(f"{symbol} note failed:", exc)
    print("Gold+BTC hourly pipeline done.")


if __name__ == "__main__":
    main()
