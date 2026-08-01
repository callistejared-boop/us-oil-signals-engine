#!/usr/bin/env python3
"""Gold Engine CLI.

Commands:
  scan            one-off analysis on the freshest data (live if configured,
                  otherwise the bundled historical CSV) — prints/alerts a
                  signal only if every rule passes
  run             continuous mode: scan every 15 minutes, alert on Telegram
  backtest        replay the engine over history and print statistics
  test-telegram   send a test message to verify bot credentials
"""
from __future__ import annotations

import argparse
import sys
import time

from engine import backtest as bt
from engine import config, data_loader, report, signals, telegram_alerts


def _load_data(settings, prefer_live: bool):
    if prefer_live:
        try:
            df = data_loader.fetch_live(settings)
            print(f"[data] live: {len(df)} bars up to {df.index[-1]}")
            return df
        except Exception as exc:  # noqa: BLE001
            print(f"[data] live fetch failed ({exc}); using historical CSV")
    df = data_loader.load_csv(settings.data_csv)
    print(f"[data] csv: {len(df)} bars up to {df.index[-1]}")
    return df


def cmd_scan(settings, live: bool) -> None:
    df = _load_data(settings, prefer_live=live)
    sig = signals.analyze(df.tail(12000))
    if sig is None:
        print("No qualifying setup right now. (This is normal — the engine "
              "rejects everything below the confluence threshold.)")
        return
    print(sig.as_text())
    telegram_alerts.send_signal(settings, sig)


def cmd_run(settings) -> None:
    print(f"Continuous mode: scanning every "
          f"{settings.scan_interval_seconds // 60} min. Ctrl+C to stop.")
    last_alert_time = None
    while True:
        try:
            df = _load_data(settings, prefer_live=True)
            sig = signals.analyze(df.tail(12000))
            if sig is not None and sig.time != last_alert_time:
                print(sig.as_text())
                telegram_alerts.send_signal(settings, sig)
                last_alert_time = sig.time
            else:
                print(f"[{time.strftime('%H:%M')}] no qualifying setup")
        except Exception as exc:  # noqa: BLE001
            print(f"[run] cycle error: {exc}")
        time.sleep(settings.scan_interval_seconds)


def cmd_backtest(settings, start: str | None, end: str | None,
                 verbose: bool) -> None:
    df = data_loader.load_csv(settings.data_csv)
    print(f"Backtesting {start or df.index[0]} -> {end or df.index[-1]} ...")
    stats = bt.run(df, start=start, end=end, verbose=verbose)
    trades = stats.pop("trade_list", [])
    print("\n=== RESULTS (R multiples, size-agnostic) ===")
    for k, v in stats.items():
        print(f"{k:>18}: {v}")
    if trades and not verbose:
        print("\nlast 5 trades:")
        for t in trades[-5:]:
            print(f"  {t.signal.time}  {t.signal.direction:5s} "
                  f"conf={t.signal.confidence}  {t.outcome} "
                  f"({t.result_r:+.2f}R)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan");  s.add_argument("--live", action="store_true")
    sub.add_parser("run")
    b = sub.add_parser("backtest")
    b.add_argument("--start"); b.add_argument("--end")
    b.add_argument("-v", "--verbose", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("--start"); r.add_argument("--end")
    r.add_argument("--out", default="report.html")
    sub.add_parser("test-telegram")

    args = p.parse_args()
    settings = config.load()

    if args.cmd == "scan":
        cmd_scan(settings, live=args.live)
    elif args.cmd == "run":
        cmd_run(settings)
    elif args.cmd == "backtest":
        cmd_backtest(settings, args.start, args.end, args.verbose)
    elif args.cmd == "report":
        df = data_loader.load_csv(settings.data_csv)
        stats = bt.run(df, start=args.start, end=args.end)
        period = f"{args.start or 'begin'} .. {args.end or 'end'}"
        out = report.generate(stats, args.out, period=period)
        print(f"report written: {out.resolve()}")
    elif args.cmd == "test-telegram":
        ok = telegram_alerts.send_message(settings, "Gold Engine: test OK")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
