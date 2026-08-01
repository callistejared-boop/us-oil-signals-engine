"""Multi-market briefing -> Telegram (DM + public channel).

Loops every configured market (Gold, Forex, Crypto, Oil). For each: settle open
trades, run the two-tier analysis, and send a rich Smart-Money read. Watch
setups are shown, not traded; confirmed setups are reported. Published
confidence and GRADE are nudged by the live news bias (bounded +/-6) via
engine.bias_adjust, so the briefing reflects news, not just technicals.
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))

import pandas as pd                                                # noqa: E402
from engine import config, signals, technicals, journal           # noqa: E402
from engine import news_guard, ict, markets, bias_adjust           # noqa: E402
from engine.data_loader import resample                           # noqa: E402


def build_message(symbol, df15, sig=None, guard=None, held_note="") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    price = float(df15["Close"].iloc[-1])
    r = ict.read(df15)

    L = [f"{symbol} BRIEFING", now, f"price: {price}", ""]
    if guard is not None:
        L.append(news_guard.line(guard)); L.append("")

    if held_note:
        L.append(held_note)
    elif sig is not None:
        adj, delta, nwhy = bias_adjust.apply_context(symbol, sig.direction, sig.confidence)
        grade = bias_adjust.grade_from(adj, sig.tier)
        head = "*** CONFIRMED SIGNAL" if sig.tier == "confirmed" else ">>> SETUP FORMING (watch)"
        L.append(f"{head} — {sig.direction.upper()} · GRADE {grade} ***")
        L.append(f"confidence {sig.confidence}->{adj}/100 ({delta:+d} news) · est. probability ~{sig.prob}%")
        if delta:
            L.append(f"news: {nwhy}")
        L.append(f"entry {sig.entry} | stop {sig.stop} | target {sig.target} | RR {sig.rr}")
        L.append(f"invalidation: {sig.invalidation}")
        L.append("why:")
        for reason in sig.reasons:
            L.append(f"  - {reason}")
        if sig.tier == "confirmed":
            L.append("")
            L.extend(markets.sizing_lines(symbol, sig.entry, sig.stop))
        else:
            L.append("  (watch-only — not logged; confirms if bias strengthens "
                     "and price taps the zone)")
    else:
        L.append("No qualifying setup right now — full read below.")

    L.append("")
    L.append("SMART MONEY READ (ICT / SMC):")
    for line in r["lines"]:
        L.append("  " + line)
    L.append(f"  directional lean: {r['lean'].upper()}"
             + (f" · est. prob ~{r['prob']}%" if r.get("prob") else ""))

    L.append("")
    L.extend(journal.track_record_lines())

    L.append("")
    tech = technicals.compute(resample(df15, "1h"))
    L.append(f"TECHNICALS (1H) overall: {tech.bias.upper()}")
    for line in tech.lines:
        L.append("  - " + line)

    L.append("")
    L.append("Research/education only - not financial advice.")
    return "\n".join(L)


def _post(token, chat, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    return json.load(urllib.request.urlopen(url, data=data, timeout=25))


def send(settings, text, channel=None):
    ok = _post(settings.telegram_bot_token, settings.telegram_chat_id, text).get("ok", False)
    ch = None
    channel = channel if channel is not None else settings.telegram_channel
    if channel:
        try:
            ch = _post(settings.telegram_bot_token, channel, text).get("ok", False)
        except Exception as exc:  # noqa: BLE001
            ch = f"err:{exc}"
    return ok, ch


def main():
    s = config.load()
    guard = news_guard.evaluate()
    lines = []
    for sym in markets.symbols(s):
        try:
            df = markets.fetch(sym, s)
            journal.settle(df, symbol=sym)
            raw = signals.analyze(df.tail(12000),
                                  min_conf=signals.WATCH_THRESHOLD, symbol=sym)
            held, sig = "", raw
            if raw is not None and raw.tier == "confirmed" and guard.get("blackout"):
                sig = None
                held = ("HELD: a confirmed setup formed but is suppressed due to "
                        "imminent high-impact news. No trade logged.")
            dm, ch = send(s, build_message(sym, df, sig, guard, held),
                          channel=markets.channel_for(sym, s))
            lines.append(f"{sym}: dm={dm} ch={ch}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{sym}: ERROR {exc}")
    (ROOT / "last_briefing.txt").write_text(
        f"{datetime.now(timezone.utc)}\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(" | ".join(lines))


if __name__ == "__main__":
    main()
