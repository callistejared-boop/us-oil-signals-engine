"""Two-stage multi-market entry alerter - run every 15 min.

Stage 1 - HEADS-UP: the moment a confirmed setup forms (entry is a limit at
an FVG level price hasn't reached), announce "watching for entry at X, and
why", and remember it.
Stage 2 - ENTRY: on a later scan, when price taps that level, fire the actual
entry and log it to the track record.

This is what removes the '15 minutes late' problem - you get the heads-up
first, the trigger second. Deduped and isolated per market; silent when
nothing changes; stands aside during high-impact news. Published confidence and
GRADE are nudged by the live news bias (bounded +/-6) via engine.bias_adjust.
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

import pandas as pd                                                        # noqa: E402
from engine.data_loader import resample                                    # noqa: E402
from engine import (config, signals, journal, pending, news_guard,        # noqa: E402
                    ict, ltf, markets, bias_adjust, calibration, regime, ledger,
                    range_guard as rgd, correlation as co, risk_guard,
                    confluence as cf, grade as gr, symbol_meta as sm)


def _paper(s=None):
    try:
        s = s or config.load()
        return bool(int(getattr(s, "paper_mode", 1)))
    except Exception:  # noqa: BLE001
        return True


def _post(token, chat, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    return json.load(urllib.request.urlopen(url, data=data, timeout=25))


def _send(s, text, channel=None):
    ok = _post(s.telegram_bot_token, s.telegram_chat_id, text).get("ok", False)
    channel = channel if channel is not None else s.telegram_channel
    if channel:
        try:
            _post(s.telegram_bot_token, channel, text)
        except Exception:  # noqa: BLE001
            pass
    return ok


def build_prealert(sig, r, guard=None, confluence=None) -> str:
    arrow = "SHORT" if sig.direction == "short" else "LONG"
    adj, delta, nwhy = bias_adjust.apply_context(sig.symbol, sig.direction, sig.confidence)
    guard = guard or {"action": "allow", "penalty": 0, "grade_cap": None}
    g_conf = max(0, adj + guard.get("penalty", 0))
    # display grade is MAST-based (confluence score/tier) — reflects every
    # confirmation layer, not just raw ICT confidence
    cscore = confluence.score if confluence else 0
    ctier = confluence.final_tier if confluence else getattr(sig, "tier", "confirmed")
    base_grade = gr.grade_for(cscore, ctier).letter
    g_grade = rgd.cap_grade(base_grade, guard.get("grade_cap"))
    L = [
        f"👀 {markets.name(sig.symbol)} — WATCHING FOR ENTRY ({arrow})  [GRADE {g_grade}]",
        ("📋 FORWARD TEST (paper) — track it, don't risk real size yet" if _paper() else None),
        f"Looking to {arrow} at {sig.entry} (limit at the {('bear' if sig.direction=='short' else 'bull')} FVG).",
        "why:",
        *[f"  - {x}" for x in sig.reasons],
        f"stop {sig.stop} | target {sig.target} | RR {sig.rr} | "
        f"conf {sig.confidence}->{g_conf}/100 ({delta:+d} news, {guard.get('penalty', 0):+d} guard)",
        (f"MAST confluence: {cscore}/100" if confluence else None),
        f"prob: ~{int(calibration.calibrated_probability(g_conf)*100)}% (calibrated on live history)",
        (f"news: {nwhy}" if delta else None),
        (f"⚠️ {rgd.line(guard)}" if guard.get("action") != "allow" else None),
        f"session: {r['session']} · bias D={r['biases']['1d']} 4H={r['biases']['4h']} 1H={r['biases']['1h']}",
        f"➡️ I'll send the ENTRY the moment price taps {sig.entry}.",
        "Research/education only - not financial advice.",
    ]
    return "\n".join(x for x in L if x)


def _guard_for(sym, direction, df):
    """Compute the range-guard verdict for a live signal. Fail-safe → allow."""
    try:
        r = ict.read(df)
        reg = regime.classify(resample(df, "4h"))
        macro = co.read_macro()
        dxy = macro.get("trend") if macro else None
        return rgd.evaluate(sym, direction, r.get("pos"), dxy, reg)
    except Exception:  # noqa: BLE001
        return {"action": "allow", "penalty": 0, "grade_cap": None,
                "size_factor": 1.0, "severity": 0.0, "macro_headwind": False}


def build_entry(rec, lt, confluence=None) -> str:
    arrow = "SHORT" if rec["direction"] == "short" else "LONG"
    risk = abs(rec["entry"] - rec["stop"])
    sgn = 1 if rec["direction"] == "long" else -1
    r1 = round(rec["entry"] + sgn * risk, 2)
    r2 = round(rec["entry"] + sgn * 2 * risk, 2)
    grade_tag = ""
    if confluence:
        g = gr.grade_for(confluence.score, confluence.final_tier)
        grade_tag = f"  [GRADE {g.letter}]"
    # Bug fix (2026-07-31): this used to quote a module-level BASIS_NOTE that
    # was hardcoded to "WTI futures (CL=F)" for every symbol, so a live gold
    # or Bitcoin ENTRY alert told the reader to check the wrong futures
    # contract's price. symbol_meta.py already carries the correct per-symbol
    # basis note (used by dashboard_publish.py and wti_note.py); this just
    # wires the live Telegram entry alert to the same source of truth.
    L = [
        f"✅ {markets.name(rec['symbol'])} — ENTRY TRIGGERED ({arrow}){grade_tag}",
        ("📋 FORWARD TEST (paper) — log it, don't risk real size yet" if _paper() else None),
        f"Price tapped {rec['entry']} — take {arrow} now.",
        f"({sm.basis_note(rec['symbol'])})",
        f"entry {rec['entry']} | stop {rec['stop']} | target {rec['target']} | RR {rec['rr']}",
        ltf.line(rec["direction"], lt) if lt else None,
        "MANAGE THE TRADE:",
        f"  • at +1R ({r1}) move stop to break-even",
        f"  • at +2R ({r2}) bank 50%, let the runner target {rec['target']}",
        *markets.sizing_lines(rec["symbol"], rec["entry"], rec["stop"]),
        f"invalidation: {rec.get('invalidation','')}",
        "Research/education only - not financial advice.",
    ]
    return "\n".join(x for x in L if x)


def main():
    s = config.load()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blackout = news_guard.evaluate().get("blackout", False)
    log = [now + (" [NEWS BLACKOUT]" if blackout else "")]

    for sym in markets.symbols(s):
        try:
            df = markets.fetch(sym, s)
            journal.settle(df, symbol=sym)

            for typ, rec in pending.update(sym, df):
                if typ == "entry" and not blackout:
                    erk = risk_guard.evaluate(sym)
                    if erk["locked"]:
                        log.append(f"{sym}: entry HELD — {erk['reason']}")
                        ledger.log({"event": "entry_held", "symbol": sym,
                                    "reason": erk["reason"]})
                        continue
                    lt = ltf.confirm(rec["direction"]) if sym == "XAUUSD" else {}
                    e_reg = regime.classify(resample(df, "4h"))
                    e_guard = _guard_for(sym, rec["direction"], df)
                    try:
                        e_cr = cf.analyze(df.tail(12000), symbol=sym,
                                          min_score=s.confluence_min_score)
                        e_conf = ({"score": e_cr.score, "agree": len(e_cr.agree)}
                                  if e_cr else {})
                    except Exception:  # noqa: BLE001
                        e_cr = None
                        e_conf = {}
                    _send(s, build_entry(rec, lt, confluence=e_cr), channel=markets.channel_for(sym, s))
                    journal.log_signal(pending.as_signal(rec),
                                       pd.Timestamp(df.index[-1]),
                                       regime=e_reg, guard=e_guard,
                                       confluence=e_conf)
                    log.append(f"{sym}: ENTRY {rec['direction']} @ {rec['entry']}")
                    ledger.log({"event": "entry", "symbol": sym, "dir": rec["direction"],
                                "entry": rec["entry"], "stop": rec["stop"], "rr": rec["rr"],
                                "guard": e_guard.get("action")})
                elif typ == "void":
                    log.append(f"{sym}: setup voided")

            if blackout:
                log.append(f"{sym}: held (news)")
                continue

            rk = risk_guard.evaluate(sym)
            if rk["locked"]:
                log.append(f"{sym}: RISK LOCK — {rk['reason']}")
                ledger.log({"event": "risk_lock", "symbol": sym,
                            "reason": rk["reason"], "day_r": rk["day_r"]})
                continue

            sig = signals.analyze(df.tail(12000),
                                  min_conf=signals.PUBLISH_THRESHOLD, symbol=sym)
            if sig is None:
                log.append(f"{sym}: no setup"); continue
            if pending.exists(sig) or journal.is_open(sym, sig.direction, sig.entry):
                log.append(f"{sym}: already tracked"); continue

            # MAST confluence engine — Layer 1 (ICT/SMC) found the setup,
            # Layer 2 confirmations must also clear before this ever reaches
            # a live channel. Confluence can only confirm or reject/downgrade
            # Layer 1's read, never originate a trade on its own.
            try:
                cr = cf.analyze(df.tail(12000), symbol=sym,
                                min_score=s.confluence_min_score)
            except Exception as exc:  # noqa: BLE001
                cr = None
                log.append(f"{sym}: confluence engine error {exc}")
            if cr is not None and cr.final_tier != "confirmed":
                log.append(f"{sym}: MAST held — {cr.final_tier} "
                           f"(score {cr.score}, disagree: {', '.join(cr.disagree) or '-'})")
                ledger.log({"event": "confluence_held", "symbol": sym,
                            "score": cr.score, "final_tier": cr.final_tier,
                            "disagree": cr.disagree})
                continue

            r = ict.read(df)
            guard = _guard_for(sym, sig.direction, df)
            grade = rgd.cap_grade(
                gr.grade_for(cr.score if cr else 0,
                            cr.final_tier if cr else getattr(sig, "tier", "confirmed")).letter,
                guard.get("grade_cap"))
            pending.add(sig, pd.Timestamp(df.index[-1]))
            _send(s, build_prealert(sig, r, guard, confluence=cr), channel=markets.channel_for(sym, s))
            log.append(f"{sym}: HEADS-UP {sig.direction} @ {sig.entry}"
                       + (f" [{guard['action']}]" if guard.get("action") != "allow" else ""))
            ledger.log({"event": "heads_up", "symbol": sym, "dir": sig.direction,
                        "entry": sig.entry, "conf": sig.confidence, "grade": grade,
                        "guard": guard.get("action"), "guard_pen": guard.get("penalty", 0),
                        "session": r.get("session")})
        except Exception as exc:  # noqa: BLE001
            log.append(f"{sym}: ERROR {exc}")

    (ROOT / "alert_heartbeat.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(" | ".join(log))

    try:
        from engine import dashboard_publish as dp
        dp.main()   # keep the live mobile dashboard fresh every scan, not just hourly
    except Exception as exc:  # noqa: BLE001
        print("dashboard publish skipped:", exc)


if __name__ == "__main__":
    main()
