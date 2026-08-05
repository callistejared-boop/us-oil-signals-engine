"""Multi-market briefing -> Telegram (DM + public channel).

Loops every configured market (Gold, Forex, Crypto, Oil). For each: settle open
trades, run the two-tier analysis, and send a rich Smart-Money read. Watch
setups are shown, not traded; confirmed setups are reported. Published
confidence and GRADE are nudged by the live news bias (bounded +/-6) via
engine.bias_adjust, so the briefing reflects news, not just technicals.

Day 3 (Phase 8) classification decision — RESEARCH/INFORMATIONAL, not a
production trade-execution path: this script never calls
`journal.log_signal()`, so a "confirmed" setup shown here is never written
to trades.json/journal.jsonl and can never itself become an "open position"
the rest of the platform (risk_guard, portfolio_risk) has to track. It is
kept available for manual, on-demand market reads (`4_SEND_SIGNAL_NOW.bat`,
`START_HERE.bat` option 3) rather than retired, because it serves a real,
distinct purpose the production alerter doesn't: a full always-on-demand
Smart-Money/technicals READ for every symbol, not just symbols that just
triggered a two-stage alert.

However, because it CAN still publish a "*** CONFIRMED SIGNAL ***" line to
Telegram that a human could act on manually, it is not exempt from risk
governance just because it doesn't touch the journal. As defense-in-depth
(so that no future launcher or scheduled task — see A_SCHEDULE_90MIN.bat —
can ever surface a confirmed signal the centralized engine would have
rejected), `main()` below now runs the SAME risk_guard + portfolio_risk
checks alert_signals.py runs, and suppresses the confirmed-signal section
exactly like the pre-existing news-blackout suppression does, with a
structured HELD reason. See RISK_SPECIFICATION.md Sec.6.
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
from engine import risk_guard, portfolio_risk as pr, ledger        # noqa: E402
from engine import regime_engine as rgeng, regime_history as rhist  # noqa: E402
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


def apply_risk_gate(sym, raw, s, guard):
    """Day 3 (Phase 8) defense-in-depth suppression, extracted as its own
    function so it is independently unit-testable (tests/test_hourly_briefing_risk_gate.py)
    without needing to drive all of main() (live fetch, Telegram, disk I/O).

    Mirrors alert_signals.py's production gates: news blackout (pre-existing,
    unchanged) -> risk_guard (per-symbol day-stop/position cap) -> centralized
    portfolio_risk. Returns (sig_or_None, held_note, ledger_event_or_None).
    This never logs a trade (hourly_briefing.py has no journal.log_signal
    call, by design — see module docstring) — it only decides whether the
    "*** CONFIRMED SIGNAL ***" section is shown or replaced with a HELD note.
    """
    if raw is None or raw.tier != "confirmed":
        return raw, "", None
    if guard.get("blackout"):
        return None, ("HELD: a confirmed setup formed but is suppressed due to "
                      "imminent high-impact news. No trade logged."), None
    rk = risk_guard.evaluate(sym)
    if rk["locked"]:
        held = (f"HELD: a confirmed setup formed but risk_guard is locked "
                f"for {sym} ({rk['reason']}). No trade logged.")
        return None, held, {"event": "briefing_held", "symbol": sym,
                            "category": "risk_guard", "reason": rk["reason"]}
    pr_v = pr.evaluate(sym, raw.direction, raw.entry, raw.stop, settings=s)
    if not pr_v["allow"]:
        held = (f"HELD: a confirmed setup formed but the centralized portfolio "
                f"risk engine would reject it ({pr_v['reason']}). No trade logged.")
        return None, held, {"event": "briefing_held", "symbol": sym,
                            "category": pr_v["category"], "reason": pr_v["reason"]}
    if pr_v.get("would_block"):
        return raw, "", {"event": "briefing_warn", "symbol": sym,
                         "category": pr_v["category"], "reason": pr_v["reason"]}
    return raw, "", None


def main():
    s = config.load()
    guard = news_guard.evaluate()
    lines = []
    for sym in markets.symbols(s):
        try:
            df = markets.fetch(sym, s)
            journal.settle(df, symbol=sym)
            # Day 4: log regime context here too, for a complete history
            # regardless of which entry point ran — informational only,
            # matches this script's existing research-only classification
            # (see module docstring); never gates the briefing.
            try:
                strategy = str(getattr(s, "regime_strategy", "ict_smc_mast") or "ict_smc_mast")
                mkt_regime = rgeng.classify(df, sym, strategy=strategy, news_state=guard)
                rhist.record(sym, "strategic", mkt_regime)
            except Exception:  # noqa: BLE001
                pass
            raw = signals.analyze(df.tail(12000),
                                  min_conf=signals.WATCH_THRESHOLD, symbol=sym)
            sig, held, ev = apply_risk_gate(sym, raw, s, guard)
            if ev:
                ledger.log(ev)
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
