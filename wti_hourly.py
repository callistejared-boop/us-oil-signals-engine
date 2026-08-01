"""Hourly WTI-only pipeline (runs on the laptop via Task Scheduler).

Each hour it: (1) refreshes the USD/DXY macro read, (2) refreshes ONLY the WTI
news slice (merged into fundamentals.json, so other pairs are untouched and no
extra Claude-analyst API credits are spent on them), then (3) generates the full
institutional WTI note — multi-timeframe ICT/SMC structure + regime + the
range-extension / dollar-headwind guard + live geopolitics — and sends it to
your Telegram (DM + WTI channel).

WTI-only by design, per the current focus. Fail-safe: any refresh error is
logged and the note still sends using its fallback context.
"""
import json
import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def refresh_macro():
    try:
        from engine import correlation as co
        d = co.refresh_macro()
        print("macro (DXY):", d.get("trend") if d else "unavailable")
    except Exception as exc:  # noqa: BLE001
        print("macro refresh skipped:", exc)


def refresh_wti_news():
    """Build only the WTI news slice and merge it into fundamentals.json."""
    try:
        from engine import fundamentals_feed as ff
        res = ff.build_symbol(ff.SYMBOLS["WTIUSD"])
        if res is None:
            print("WTI news: no data this run (note uses fallback context).")
            return
        data = ff.read_feed_raw() or {}
        syms = dict(data.get("symbols", {}))
        syms["WTIUSD"] = res
        out = {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof": date.today().isoformat(),
            "source": data.get("source",
                               "Google News RSS (negation-aware headline sentiment)"),
            "symbols": syms,
        }
        ff.FEED_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"WTI news: {res.get('signal')} {res.get('strength')} "
              f"({res.get('n_total')} headlines)")
    except Exception as exc:  # noqa: BLE001
        print("WTI news refresh error:", exc)


def main():
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
          "WTI hourly pipeline start")
    refresh_macro()
    refresh_wti_news()
    import wti_note
    sys.argv = ["wti_note.py", "--send"]   # generate + push to Telegram
    wti_note.main()
    try:
        import publisher
        publisher.main()                    # refresh the public track record
    except Exception as exc:  # noqa: BLE001
        print("track-record refresh skipped:", exc)
    try:
        from engine import dashboard_publish as dp
        dp.main()                           # push a fresh snapshot to the live mobile dashboard
    except Exception as exc:  # noqa: BLE001
        print("dashboard publish skipped:", exc)
    print("WTI hourly pipeline done.")


if __name__ == "__main__":
    main()
