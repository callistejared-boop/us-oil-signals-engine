"""Institutional trade note generator - hedge-fund-style, explainable.

Multi-symbol (2026-07-28): originally hardcoded to WTIUSD only. build() now
takes a `symbol` argument and every previously-hardcoded "WTIUSD" reference
(signal analysis, confluence, bias/range guards, macro note, basis note,
title, channel routing, risks section) is scoped to it via engine.symbol_meta
(the shared display-name/basis-note/risk-note source of truth, also used by
engine/dashboard_publish.py). main() defaults to WTIUSD with the exact same
output filename (wti_note.txt) as before so the existing hourly automation
(wti_hourly.py, the .bat launchers, command_center.py) is untouched; passing
a different symbol writes to note_<symbol>.txt instead so nothing collides.

Fuses the engine's ICT/SMC read with multi-target levels (TP1/TP2/TP3),
day-vs-swing classification, expected hold, a weighted-confidence breakdown,
and the fundamental/geopolitical picture. The signal's confidence and GRADE are
nudged by the LIVE news bias (bounded, transparent) so the trade reflects news,
not just technicals.

Fundamentals are LIVE when engine.fundamentals_feed has written a fresh
fundamentals.json for that symbol; otherwise the note falls back to an
honest "no live feed yet" note (never a fabricated bias), and
engine.freshness guards the age so stale context never masquerades as current.
"""
import pathlib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import config, markets, ict, technicals, signals   # noqa: E402
from engine.data_loader import resample                        # noqa: E402
from engine.freshness import staleness                         # noqa: E402
from engine import fundamentals_feed as ff                     # noqa: E402
from engine import bias_adjust as ba                           # noqa: E402
from engine import regime as rg, risk as risk_mod, calibration as cal  # noqa: E402
from engine import correlation as co                            # noqa: E402
from engine import range_guard as rgd                           # noqa: E402
from engine import confluence as cf                              # noqa: E402
from engine import eia_feed                                     # noqa: E402
from engine import cot_feed, spread_feed, seasonality, risk_sentiment  # noqa: E402
from engine import grade as gr                                  # noqa: E402
from engine import symbol_meta as sm                             # noqa: E402

DEFAULT_EQUITY = 10000  # illustrative for sizing; edit for your account

# Fallback static context (used only when the live feed is missing/stale).
FUND_ASOF = "2026-07-13"
FUNDAMENTALS = [
    "Geopolitics (BULLISH): US-Iran strikes reignited Strait of Hormuz risk; "
    "Iran declared the waterway closed while Western navies say it stays open. "
    "Hormuz (~20% of world oil/gas) flow disrupted - a live supply-shock premium.",
    "Inventories (MIXED): EIA showed a US crude build (bearish), but global "
    "stocks remain tight into Q3 (bullish).",
    "OPEC (BEARISH lean): OPEC cut its 2026 demand-growth forecast to ~800k b/d; "
    "planned output adds cap upside if Hormuz de-escalates.",
    "Net read: geopolitics dominating; risk premium keeps crude bid, but it is "
    "TWO-WAY - a credible ceasefire/Hormuz reopening is the main downside risk.",
]
FUND_BIAS = "bullish"


def _fundamentals(symbol):
    """Bug fix (2026-07-28, same class of bug as dashboard_publish.py's
    _fundamentals()): this used to call ff.load_feed() with no symbol,
    defaulting to WTIUSD, so a gold/BTC note would silently show oil's
    feed. WTIUSD keeps its existing curated static fallback unchanged
    (preserving prior work); other symbols get an honest "no feed yet"
    line instead of a fabricated bias."""
    feed = ff.load_feed(symbol)
    if feed:
        return feed["asof"], feed["net_bias"], ff.render_lines(feed), True
    if symbol == "WTIUSD":
        return FUND_ASOF, FUND_BIAS, FUNDAMENTALS, False
    today = datetime.now(timezone.utc).date().isoformat()
    return today, "neutral", [f"No cached fundamentals feed yet for {symbol} — "
                              "showing technicals only until the next refresh."], False


def confidence_breakdown(sig, biases, fund_bias, fund_asof, ndelta):
    aligned = sum(1 for v in biases.values() if v == ("bull" if sig.direction == "long" else "bear"))
    stale = staleness(fund_asof)[1] == "stale"
    if stale:
        fund_val, geo_val = "STALE - discounted", "STALE - discounted"
    elif fund_bias == "mixed":
        fund_val, geo_val = "mixed - neutral weight", "mixed - neutral weight"
    else:
        agrees = (fund_bias == "bullish") == (sig.direction == "long")
        fund_val = fund_bias + (" (agrees)" if agrees else " (conflicts - caution)")
        geo_val = "supply-risk premium " + ("supports" if sig.direction == "long" else "opposes")
    return [
        ("Technical alignment (20%)", "strong" if aligned >= 3 else "partial"),
        ("Higher-timeframe bias (15%)", biases.get("1d", "n/a")),
        ("ICT confirmation (15%)", "FVG entry + structure"),
        ("SMC confirmation (10%)", "order block / liquidity"),
        ("Liquidity quality (10%)", "targeting opposing liquidity"),
        ("Fundamental alignment (10%)", fund_val),
        ("Geopolitical alignment (5%)", geo_val),
        ("Risk-reward quality (5%)", f"RR {sig.rr}"),
        ("Live context nudge (news+killzone)", f"{ndelta:+d} pts (bounded +/-8)"),
    ]


def build(df, s, symbol="WTIUSD"):
    r = ict.read(df)
    tech = technicals.compute(resample(df, "1h"))
    reg = rg.classify(resample(df, "4h"))
    sig = signals.analyze(df.tail(12000), min_conf=signals.WATCH_THRESHOLD, symbol=symbol)
    try:
        cr = cf.analyze(df.tail(12000), symbol=symbol, min_score=s.confluence_min_score)
    except Exception:  # noqa: BLE001
        cr = None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fund_asof, fund_bias, fund_lines, live = _fundamentals(symbol)
    lo, hi = r["range"]
    L = [
        "==============================================",
        f"  {sm.short_label(symbol)} - INSTITUTIONAL TRADE NOTE",
        f"  {now}   |   price {r['price']:.2f}",
        "==============================================",
        "",
        "1) DIRECTIONAL BIAS (multi-timeframe)",
        f"   D={r['biases']['1d']}  4H={r['biases']['4h']}  1H={r['biases']['1h']}  15m={r['biases']['15m']}",
        f"   Consolidated technical lean: {r['lean'].upper()} (est ~{r['prob']}%)",
        f"   Market regime (4H): {reg['label']}  |  ER {reg['er']}  ATR-pct {reg['atr_pct']}",
        "",
        "2) THE SETUP",
    ]
    ndelta = 0
    if sig:
        risk = abs(sig.entry - sig.stop)
        sgn = 1 if sig.direction == "long" else -1
        tp1 = round(sig.entry + sgn * 1.0 * risk, 2)
        tp2 = round(sig.entry + sgn * 2.0 * risk, 2)
        tp3 = round(sig.target, 2)
        atr = tech.atr
        span = abs(tp3 - sig.entry)
        ttype = "DAY TRADE (intraday)" if span <= 2.5 * atr else "SWING TRADE (multi-day)"
        hold = "a few hours to ~1 session" if "DAY" in ttype else "1-4 sessions"
        base_conf = sig.confidence
        adj_conf, ndelta, nwhy = ba.apply_context(symbol, sig.direction, base_conf)
        # display grade is MAST-based (confluence score/tier), not raw ICT
        # confidence — it reflects every confirmation layer, not just Layer 1
        g_score = cr.score if cr else 0
        g_tier = cr.final_tier if cr else sig.tier
        grade = gr.grade_for(g_score, g_tier).letter

        # --- range-extension / dollar-headwind guard ------------------------
        macro = co.read_macro()
        dxy = macro.get("trend") if macro else None
        guard = rgd.evaluate(symbol, sig.direction, r.get("pos"), dxy, reg)
        g_conf = max(0, adj_conf + guard["penalty"])
        g_grade = rgd.cap_grade(grade, guard["grade_cap"])
        grade_disp = g_grade + (f"  (guard-capped from {grade})"
                                if g_grade != grade else "")
        size_lines = list(risk_mod.sizing_lines(DEFAULT_EQUITY, sig.entry, sig.stop,
                                                vol_regime=reg["vol"]))
        if guard["action"] != "allow":
            size_lines.append(
                f"   Guard size adjustment: x{guard['size_factor']:.2f} of the above "
                f"(chase risk — take a partial or wait for a pullback)")

        L += [
            f"   {sig.tier.upper()} {sig.direction.upper()}  |  GRADE {grade_disp}  |  {ttype}",
            f"   Entry {sig.entry}   Stop {sig.stop}   (risk {risk:.2f})",
            f"   TP1 {tp1} (+1R, bank 50% / stop->BE)",
            f"   TP2 {tp2} (+2R)",
            f"   TP3 {tp3} (structure target, RR {sig.rr})",
            f"   Expected holding time: {hold}",
            f"   Confidence: {base_conf}/100 technical -> {adj_conf}/100 context "
            f"-> {g_conf}/100 guard-adjusted ({guard['penalty']:+d} guard)",
            f"   Context (news+killzone): {nwhy}",
            f"   {rgd.line(guard)}",
            f"   Est probability: {sig.prob}% model -> {int(cal.calibrated_probability(g_conf)*100)}% calibrated (from live history)",
            *size_lines,
            f"   Macro (USD): {co.macro_note(symbol, sig.direction)}",
            f"   Invalidation: {sig.invalidation}",
            f"   NOTE: {sm.basis_note(symbol)}",
            "",
            "3) CONFIDENCE BREAKDOWN (weighted factors)",
        ]
        for name, val in confidence_breakdown(sig, r["biases"], fund_bias, fund_asof, ndelta):
            L.append(f"   - {name}: {val}")
    else:
        L += ["   No A+ setup right now - engine standing aside. Levels to watch below.", "",
              "3) CONFIDENCE BREAKDOWN", "   - n/a (no qualifying setup)"]

    L += [
        "",
        "4) SMART-MONEY MAP (ICT / SMC)",
        f"   Dealing range {lo:.2f}-{hi:.2f} | equilibrium {(lo+hi)/2:.2f} | OTE {r['ote'][0]:.2f}-{r['ote'][1]:.2f}",
        f"   Buy-side liquidity: {r['liq']['buyside'] or '-'}   Sell-side: {r['liq']['sellside'] or '-'}",
        f"   Last structure event: {r['event']}",
        f"   Nearest unfilled FVG: {r.get('fvg') or '-'}   Order block: {r.get('ob') or '-'}",
        f"   Session: {r['session']}",
        "",
        "5) TECHNICALS (1H)  overall: " + tech.bias.upper(),
    ]
    for line in tech.lines:
        L.append("   - " + line)

    age, level, banner = staleness(fund_asof)
    tag = "LIVE feed" if live else "STATIC fallback"
    L += ["", f"6) FUNDAMENTAL & GEOPOLITICAL ({tag}, as of {fund_asof})", "   " + banner]
    for f in fund_lines:
        L.append("   - " + f)
    L += ["", "7) INSTITUTIONAL POSITIONING & CROSS-MARKET"]
    # Bug fix (2026-07-28): these four used to call .note() with no symbol,
    # which every one of them defaults to WTIUSD - so a gold/BTC note would
    # print oil's COT/spread/seasonality/risk-sentiment reads under generic
    # section headers. Now scoped to the symbol this note is actually for.
    try:
        L.append("   " + cot_feed.note(symbol))
    except Exception as exc:  # noqa: BLE001
        L.append(f"   COT: error ({exc})")
    try:
        L.append("   " + spread_feed.note(symbol))
    except Exception as exc:  # noqa: BLE001
        L.append(f"   Spreads: error ({exc})")
    try:
        L.append("   " + seasonality.note(symbol))
    except Exception as exc:  # noqa: BLE001
        L.append(f"   Seasonality: error ({exc})")
    try:
        L.append("   " + risk_sentiment.note(symbol))
    except Exception as exc:  # noqa: BLE001
        L.append(f"   Risk sentiment: error ({exc})")

    L += ["", "8) MAST CONFLUENCE ENGINE (price action / trend / breakout / "
          "mean reversion / volume profile / Wyckoff / macro / news / COT / "
          "spreads / seasonality / risk sentiment / RSI divergence / pivots / "
          "candlestick patterns / breaker-mitigation blocks / Fibonacci / "
          "chart patterns)"]
    if cr is None:
        L.append("   No Layer-1 (ICT/SMC) setup to confirm — nothing to score.")
    else:
        L += [
            f"   Score {cr.score}/100  |  base tier {cr.base_tier.upper()} -> "
            f"final {cr.final_tier.upper()}  (threshold {s.confluence_min_score})",
            f"   Agree ({len(cr.agree)}): " + (", ".join(cr.agree) or "-"),
            f"   Disagree ({len(cr.disagree)}): " + (", ".join(cr.disagree) or "-"),
            "   Validation checklist:",
        ]
        for name, passed, _ in cr.checklist:
            L.append(f"     {'PASS' if passed else 'FAIL'}  {name}")
        # EIA weekly crude inventory data is inherently oil-only (there is no
        # gold/BTC equivalent) - never printed on a gold/BTC note.
        if symbol == "WTIUSD":
            L.append("   " + eia_feed.note())
    L += [
        "",
        "9) RISKS / WHAT VOIDS THIS",
        *[f"   - {line}" for line in sm.risk_notes(symbol)],
        "",
        "Confluence score is an explainability tool, not a promised win rate — "
        "only the forward-test track record proves what any score is worth.",
        "Research/education only - not financial advice.",
    ]
    return "\n".join(L)


def main(symbol=None):
    """Defaults to WTIUSD and writes wti_note.txt exactly as before, so the
    existing hourly automation (wti_hourly.py, the .bat launchers,
    command_center.py — all of which read wti_note.txt by that exact name)
    keeps working untouched. Pass a symbol (or run with --symbol=XAUUSD /
    --symbol=BTCUSD) to build a note for gold or Bitcoin instead; those are
    written to note_<symbol>.txt so they never collide with the oil file."""
    if symbol is None:
        symbol = "WTIUSD"
        for arg in sys.argv[1:]:
            if arg.startswith("--symbol="):
                symbol = arg.split("=", 1)[1].strip().upper()
    s = config.load()
    df = markets.fetch(symbol, s)
    note = build(df, s, symbol)
    out_name = "wti_note.txt" if symbol == "WTIUSD" else f"note_{symbol.lower()}.txt"
    (ROOT / out_name).write_text(note, encoding="utf-8")
    print(note[:400])
    if "--send" in sys.argv:
        import json as _json

        def _chunks(text, limit=3900):
            out, cur = [], ""
            for line in text.split("\n"):
                if len(cur) + len(line) + 1 > limit and cur:
                    out.append(cur)
                    cur = ""
                cur += line + "\n"
            if cur.strip():
                out.append(cur)
            return out or [text]

        ch = markets.channel_for(symbol, s)
        parts = _chunks(note)
        status = []
        for chat, label in ((s.telegram_chat_id, "DM"), (ch, sm.channel_label(symbol))):
            if not chat:
                status.append({"target": label, "ok": False, "error": "not configured"})
                continue
            ok_all, err = True, ""
            for idx, part in enumerate(parts, 1):
                tag = f"(part {idx}/{len(parts)})\n" if len(parts) > 1 else ""
                data = urllib.parse.urlencode({"chat_id": chat, "text": tag + part}).encode()
                try:
                    resp = _json.load(urllib.request.urlopen(
                        "https://api.telegram.org/bot" + s.telegram_bot_token + "/sendMessage",
                        data=data, timeout=25))
                    if not resp.get("ok"):
                        ok_all, err = False, resp.get("description", "")
                except Exception as exc:  # noqa: BLE001
                    ok_all, err = False, str(exc)[:200]
            status.append({"target": label, "chat": str(chat), "ok": ok_all,
                           "parts": len(parts), "error": err})
        status_name = "wti_send_status.txt" if symbol == "WTIUSD" else f"send_status_{symbol.lower()}.txt"
        (ROOT / status_name).write_text(_json.dumps(status, indent=2), encoding="utf-8")
        print("\n[send status] " + _json.dumps(status))


if __name__ == "__main__":
    main()
