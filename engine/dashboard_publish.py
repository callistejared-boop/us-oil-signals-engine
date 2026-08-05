"""Publishes a JSON snapshot per symbol to Supabase for the live mobile/web
dashboard (see webapp/). This is a read-only reporting module — it computes
nothing new, it re-derives the same numbers wti_note.py and alert_signals.py
already show (same functions, same guard/grade logic) and ships them as
structured JSON instead of text, so the web dashboard always agrees with the
Telegram messages and the note.

Multi-symbol (2026-07-28): `dashboard_snapshot` used to be a single fixed
row (id=1, oil only). It's now one row per symbol (unique on `symbol`),
migrated so the pre-existing oil row was preserved untouched at
symbol='WTIUSD'. Each symbol in config.symbols publishes/updates its own
row independently — a failure building one symbol's payload must never
block the others.

Write path is deliberately narrow: the frontend only ever holds the Supabase
ANON key (public, read-only via RLS). This script holds the one write
credential — DASHBOARD_PUBLISH_SECRET — and calls a single Postgres RPC
(publish_snapshot) that upserts one row per symbol. No table-level write
grant exists for anon, so leaking the anon key (it's already embedded in
the public frontend by design) cannot let anyone alter the dashboard.

Fail-safe throughout: any error publishing must never break the hourly/alert
pipeline that calls this — always log and return, never raise.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import config, markets, ict, signals, store          # noqa: E402
from engine import bias_adjust as ba, regime as rg, correlation as co  # noqa: E402
from engine import range_guard as rgd, confluence as cf, grade as gr   # noqa: E402
from engine import risk_guard, eia_feed                            # noqa: E402
from engine import (regime_engine as rgeng, portfolio_risk as pr,  # noqa: E402
                    confidence_engine as confeng, news_guard, market_memory as mm,
                    decision_audit_history as dah, explainability_engine as expl)
from engine import cot_feed, spread_feed, seasonality, risk_sentiment  # noqa: E402
from engine.data_loader import resample                            # noqa: E402
from engine.freshness import staleness                             # noqa: E402
from engine import fundamentals_feed as ff                         # noqa: E402
from engine import technicals as tc                                # noqa: E402
from engine import symbol_meta as sm                                # noqa: E402
from engine import macro_engine as macro                            # noqa: E402
from engine.execution import execution_history as exhist            # noqa: E402
from engine.broker import paper_broker as pbroker                   # noqa: E402
from engine.data_health import feed_monitor as dhfm                 # noqa: E402

CHART_BARS = 120   # ~5 days of 1H candles — enough context without a huge payload

SUPABASE_URL = "https://ftgihtwznkuyyhhnxafx.supabase.co"
SUPABASE_ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
                     "ImZ0Z2lodHd6bmt1eXloaG54YWZ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ0NjU5"
                     "MjAsImV4cCI6MjEwMDA0MTkyMH0.ka4GywiOh98PQT8hem2wNoT8HJTHx2TBde3L6WwsYiQ")
FWD_START = "2026-07-17"

# Kept as aliases for backward compatibility (tests + any external caller
# that reached into the old module-level dicts) — canonical source is now
# engine/symbol_meta.py, shared with wti_note.py.
_DISPLAY_NAMES = sm.DISPLAY_NAMES
_BASIS_NOTES = sm.BASIS_NOTES


def _max_drawdown_r(rs_in_order):
    peak = cum = dd = 0.0
    for x in rs_in_order:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return round(dd, 2)


def _stats_and_trades(symbol):
    rows = store.load_array(ROOT / "trades.json")
    rows = [r for r in rows if r.get("symbol") == symbol]
    rows = sorted(rows, key=lambda r: str(r.get("opened", "")))
    closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]
    rs = [float(r.get("result_r", 0) or 0) for r in closed]
    n = len(rs)
    wins = sum(1 for x in rs if x > 1e-9)
    exp = (sum(rs) / n) if n else 0.0
    gross_w = sum(x for x in rs if x > 0)
    gross_l = abs(sum(x for x in rs if x < 0))
    pf = None if not gross_l else round(gross_w / gross_l, 2) if gross_w else 0.0
    open_rows = [r for r in rows if r.get("status") == "open"]
    stats = {
        "closed": n, "wins": wins,
        "win_rate": round(wins / n, 3) if n else None,
        "expectancy_r": round(exp, 3), "net_r": round(sum(rs), 2),
        "profit_factor": pf, "max_drawdown_r": _max_drawdown_r(rs),
        "open_now": len(open_rows),
        "forward_test_start": FWD_START,
    }
    recent = []
    for r in reversed(rows[-25:]):
        status = r.get("status", "?")
        cscore = r.get("confluence_score", -1)
        letter = None
        if cscore is not None and cscore >= 0:
            # journal only ever logs trades that passed the "confirmed" gate
            # (alert_signals holds anything that isn't), so the letter here
            # always reflects a tradeable-grade entry at the time it fired.
            letter = gr.grade_for(cscore, "confirmed").letter
        recent.append({
            "opened": r.get("opened", ""), "closed": r.get("closed", ""),
            "direction": r.get("direction", ""), "entry": r.get("entry"),
            "stop": r.get("stop"), "target": r.get("target"),
            "status": status, "result_r": r.get("result_r", 0),
            "confluence_score": cscore, "grade_letter": letter,
        })
    return stats, recent


def _fundamentals(symbol):
    """Bug fix (2026-07-28): this used to call ff.load_feed() with no symbol,
    which defaults to WTIUSD — so gold/BTC payloads were silently showing
    oil's fundamentals feed. Now scoped per symbol, with an honest (not
    fabricated) fallback when that symbol has no cached feed yet."""
    feed = ff.load_feed(symbol)
    if feed:
        return feed["asof"], feed["net_bias"], ff.render_lines(feed), True
    today = datetime.now(timezone.utc).date().isoformat()
    return today, "neutral", [f"No cached fundamentals feed yet for {symbol} — "
                              "showing technicals only until the next refresh."], False


def _safe_note(fn, label):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return f"{label}: unavailable ({exc})"


def _chart_data(df):
    """Recent 1H candles + EMA20/50/100/200, for the dashboard's own markup
    chart (drawn client-side). This exists because the public embeddable
    TradingView widget has no scripting API for custom price-line drawings —
    that requires TradingView's licensed Charting Library, not the free
    widget this site uses. Rendering our own small chart is the honest way
    to actually put the engine's indicators and levels on a chart, rather
    than claiming the TradingView embed does something it can't."""
    try:
        h1 = resample(df, "1h").tail(CHART_BARS + 210)  # pad for EMA warmup
        if h1.empty:
            return None
        e20 = tc.ema(h1["Close"], 20)
        e50 = tc.ema(h1["Close"], 50)
        e100 = tc.ema(h1["Close"], 100)
        e200 = tc.ema(h1["Close"], 200) if len(h1) >= 200 else None

        h1 = h1.tail(CHART_BARS)
        candles = [
            {"t": str(idx), "o": round(float(row.Open), 2), "h": round(float(row.High), 2),
             "l": round(float(row.Low), 2), "c": round(float(row.Close), 2)}
            for idx, row in h1.iterrows()
        ]

        def _series(e):
            if e is None:
                return []
            e = e.tail(CHART_BARS)
            return [round(float(v), 2) for v in e.values]

        return {
            "candles": candles,
            "ema20": _series(e20), "ema50": _series(e50),
            "ema100": _series(e100), "ema200": _series(e200),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"dashboard_publish: chart data build failed ({exc})")
        return None


def build_payload(symbol, df=None, s=None):
    s = s or config.load()
    # Dashboard is read-only/display — use the cache-backed resilient fetch
    # so a live-feed outage shows the last known snapshot with a stale
    # banner instead of the whole publish step just skipping silently.
    df = df if df is not None else markets.fetch_resilient(symbol, s)
    data_stale = bool(df.attrs.get("stale", False))
    data_stale_since_s = df.attrs.get("stale_since", 0)
    r = ict.read(df)
    reg = rg.classify(resample(df, "4h"))
    # Never present an actionable setup computed from stale (cached) data —
    # the dashboard can still show price/structure/track-record from the
    # cache, but a "has_setup" call must always come from a live fetch.
    sig = (signals.analyze(df.tail(12000), min_conf=signals.WATCH_THRESHOLD, symbol=symbol)
           if not data_stale else None)

    signal_payload = {"has_setup": False}
    memory_payload = None   # Day 7 — only computed when a setup exists (see below)
    if sig:
        risk = abs(sig.entry - sig.stop)
        sgn = 1 if sig.direction == "long" else -1
        tp1 = round(sig.entry + sgn * 1.0 * risk, 2)
        tp2 = round(sig.entry + sgn * 2.0 * risk, 2)
        tp3 = round(sig.target, 2)
        base_conf = sig.confidence
        adj_conf, ndelta, nwhy = ba.apply_context(symbol, sig.direction, base_conf)

        # NOTE: named dxy_macro, not "macro" — this function also references
        # the module-level `macro` (engine.macro_engine, imported above) via
        # the macro_advisory lambda near the end of this function. A local
        # variable named `macro` here would shadow that import for this
        # entire function scope (Python resolves free-variable closures at
        # function level, not line level) and break macro_advisory with an
        # UnboundLocalError on any code path where this `if sig:` block
        # doesn't run. Found and fixed during Day 11 testing.
        dxy_macro = co.read_macro()
        dxy = dxy_macro.get("trend") if dxy_macro else None
        guard = rgd.evaluate(symbol, sig.direction, r.get("pos"), dxy, reg)
        g_conf = max(0, adj_conf + guard["penalty"])

        try:
            cread = cf.analyze(df.tail(12000), symbol=symbol, min_score=s.confluence_min_score)
        except Exception:  # noqa: BLE001
            cread = None

        score = cread.score if cread else 0
        tier = cread.final_tier if cread else sig.tier
        grade = gr.grade_for(score, tier)

        rguard = risk_guard.evaluate(symbol)

        # --- Day 6: Confidence Engine — read-only, display-only here (this
        # function never gates publication, it only reports). Reuses every
        # object already computed above (sig, cread, guard, rguard) plus one
        # fresh regime_engine.classify() call (the dashboard is a separate
        # process from alert_signals.py's scan loop, so it cannot reuse that
        # scan's mkt_regime object — every entry point independently calling
        # regime_engine.classify() is the same pattern Day 4/5 already
        # established, not a new duplication). Fail-safe: never blocks the
        # rest of the payload from building.
        try:
            d_regime = rgeng.classify(df, symbol)
            d_pr = pr.evaluate(symbol, sig.direction, sig.entry, sig.stop,
                               settings=s, session_label=r.get("session"))
            d_news = news_guard.evaluate()
            d_assessment = confeng.assess(
                symbol, sig.direction, sig=sig, mkt_regime=d_regime, cr=cread,
                portfolio_verdict=d_pr, guard=guard, news_state=d_news,
                session=r.get("session"), risk_locked=bool(rguard.get("locked")),
                settings=s)
            confidence_payload = {
                "overall_confidence": d_assessment.overall_confidence,
                "tier": d_assessment.tier,
                "is_calibrated": d_assessment.is_calibrated,
                "calibrated_probability": d_assessment.calibrated_probability,
                "probability_label": d_assessment.probability_label,
                "evidence_quality": d_assessment.evidence_quality,
                "evidence_diversity": d_assessment.evidence_diversity,
                "market_quality": d_assessment.market_quality,
                "regime_confidence": d_assessment.regime_confidence,
                "confluence_quality": d_assessment.confluence_quality,
                "uncertainty_indicators": d_assessment.uncertainty_indicators,
                "supporting_rationale": d_assessment.supporting_rationale[:5],
                "conflicting_rationale": d_assessment.conflicting_rationale[:5],
            }
        except Exception:  # noqa: BLE001
            confidence_payload = None

        # --- Day 7: Market Memory Engine — advisory-only, deliberately kept
        # OUT of signal_payload (the mandate: "Keep these clearly separated
        # from live trade recommendations") and surfaced instead as its own
        # top-level `market_memory_advisory` payload key, below.
        try:
            mem_query = mm.query_features_from_live(
                mkt_regime=d_regime, cr=cread, session=r.get("session"),
                portfolio_verdict=d_pr, direction=sig.direction)
            mem_ctx = mm.historical_context(mem_query, as_of=datetime.now(timezone.utc))
            memory_payload = {
                "advisory_only": True,
                "note": "Historical context, not a trade recommendation.",
                "comparable_count": mem_ctx.get("comparable_count"),
                "sufficient_sample": mem_ctx.get("sufficient_sample"),
                "quality": mem_ctx.get("quality"),
                "aggregate": mem_ctx.get("aggregate"),
                "strengths": mem_ctx.get("strengths"),
                "weaknesses": mem_ctx.get("weaknesses"),
            }
        except Exception:  # noqa: BLE001
            memory_payload = None

        signal_payload = {
            "has_setup": True,
            "direction": sig.direction,
            "tier": tier,
            "grade": {"letter": grade.letter, "label": grade.label,
                      "tradeable": grade.tradeable, "score": grade.score},
            "entry": sig.entry, "stop": sig.stop,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "rr": sig.rr,
            "confidence_technical": base_conf, "confidence_context": adj_conf,
            "confidence_guard_adjusted": g_conf,
            "invalidation": sig.invalidation,
            "guard_note": rgd.line(guard),
            "guard_locked": bool(rguard.get("locked")),
            "guard_reason": rguard.get("reason", ""),
            "confluence_agree": cread.agree if cread else [],
            "confluence_disagree": cread.disagree if cread else [],
            "checklist": [{"name": n, "passed": p} for n, p, _ in cread.checklist] if cread else [],
            "reasoning": cread.reasoning if cread else [],
            "confidence_assessment": confidence_payload,   # Day 6 — None on failure, never blocks
            "basis_note": _BASIS_NOTES.get(
                symbol, "Confirm your platform price against the source feed before filling."),
        }

    # --- Day 8: Explainability Dashboard — read-only, advisory. Surfaces the
    # most recent PERSISTED decision snapshots for this symbol (both
    # approved and rejected) with their audit graph and explanation, purely
    # for transparency/learning — never a live re-evaluation, never a signal.
    # Kept as its own top-level payload key, same "clearly separated from
    # live trade recommendations" pattern Day 7's `market_memory_advisory`
    # already established. Fail-safe: never blocks the rest of the payload.
    try:
        recent_rows = dah.tail(5, symbol=symbol)
        decision_audit_payload = {
            "advisory_only": True,
            "note": "Recent decision snapshots — transparency/audit trail, not a live signal.",
            "recent": [
                {"decision_id": row.get("decision_id"), "stage": row.get("stage"),
                 "final_action": row.get("final_action"), "created": row.get("created"),
                 "graph": expl.build_audit_graph(row),
                 "explanation": (expl.explain_rejection(row) if row.get("final_action") == "rejected"
                                else expl.explain_approval(row))}
                for row in recent_rows
            ],
        }
    except Exception:  # noqa: BLE001
        decision_audit_payload = None

    fund_asof, fund_bias, fund_lines, live = _fundamentals(symbol)
    _, level, banner = staleness(fund_asof)

    stats, recent = _stats_and_trades(symbol)
    chart = _chart_data(df)

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol, "display_name": _DISPLAY_NAMES.get(symbol, symbol),
        "price": round(float(r["price"]), 2),
        "signal": signal_payload,
        "market_memory_advisory": memory_payload,   # Day 7 — advisory-only, kept separate from `signal`
        "decision_audit": decision_audit_payload,   # Day 8 — advisory-only, kept separate from `signal`
        # Day 11 — advisory-only, kept separate from `signal`. Shows the
        # MOST RECENTLY RECORDED macro assessment (from alert_signals.py's
        # own Stage-2 logging via macro_history.jsonl), not a fresh live
        # recompute — avoids adding another round of provider fetches to
        # every dashboard page load. `None` until at least one entry has
        # been logged since Day 11 shipped.
        "macro_advisory": _safe_note(lambda: macro.last_assessment(symbol), "Macro"),
        # Day 12: last RECORDED execution report (from execution_history.jsonl,
        # written by alert_signals.py's Stage-2 logging), never a fresh
        # recompute — same reasoning as macro_advisory above. Advisory only.
        "execution_summary": _safe_note(lambda: exhist.last_for(symbol), "Execution"),
        # Day 13: Paper Trading panel — account equity, open positions,
        # pending (resting) orders, realized/unrealized P&L, and recent
        # execution activity from the Paper Broker. Advisory only, same
        # posture as execution_summary/macro_advisory above; the account
        # this reads is symbol-agnostic (one shared paper account across
        # every symbol this platform trades), so this key is IDENTICAL
        # across every symbol's payload by design — see
        # PAPER_BROKER_SPECIFICATION.md Sec.9 "Dashboard".
        "paper_trading": _safe_note(lambda: pbroker.dashboard_snapshot(), "Paper Trading"),
        # Day 14: Data Quality & Feed Health — advisory only, same posture
        # as paper_trading/macro_advisory above. Symbol-agnostic (one
        # platform-wide health report), so this key is IDENTICAL across
        # every symbol's payload by design, same precedent as
        # paper_trading. See DATA_HEALTH_SPECIFICATION.md Sec.9 "Dashboard".
        "data_health": _safe_note(lambda: dhfm.dashboard_snapshot(), "Data Health"),
        "chart": chart,
        "market_structure": {
            "biases": r["biases"], "lean": r["lean"], "prob": r["prob"],
            "dealing_range": r["range"], "ote": r["ote"],
            "session": r["session"], "last_event": r["event"],
            "regime": reg.get("label"),
            # ICT/SMC chart annotations — same read the biases/lean above are
            # built from, just exposed as raw levels so the dashboard chart
            # can draw them instead of only quoting them in text.
            "direction": r.get("direction"),
            "fvg": list(r["fvg"]) if r.get("fvg") else None,
            "order_block": list(r["ob"]) if r.get("ob") else None,
        },
        "institutional": {
            "cot": _safe_note(lambda: cot_feed.note(symbol), "COT"),
            "spreads": _safe_note(lambda: spread_feed.note(symbol), "Spreads"),
            "seasonality": _safe_note(lambda: seasonality.note(symbol), "Seasonality"),
            "risk_sentiment": _safe_note(lambda: risk_sentiment.note(symbol), "Risk sentiment"),
            # EIA weekly crude inventory data is inherently oil-only (there is
            # no gold/BTC equivalent) - only ever shown on the WTI dashboard,
            # never a misleading line on gold/BTC's institutional panel.
            "eia": _safe_note(eia_feed.note, "EIA") if symbol == "WTIUSD" else None,
        },
        "fundamentals": {"asof": fund_asof, "bias": fund_bias,
                         "lines": fund_lines, "live": live, "staleness": level},
        "stats": stats,
        "recent_trades": recent,
        "paper_mode": bool(getattr(s, "paper_mode", 1)),
        "data_stale": data_stale,
        "data_stale_since_s": int(data_stale_since_s or 0),
        "disclaimer": "Research/education only — not financial advice. "
                     "Confluence score is an explainability tool, not a promised win rate.",
    }
    return payload


def publish(payload, symbol) -> bool:
    """Upsert the payload via the publish_snapshot RPC. Never raises."""
    try:
        secret = os.environ.get("DASHBOARD_PUBLISH_SECRET") or None
        if not secret:
            env = ROOT / ".env"
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.strip().startswith("DASHBOARD_PUBLISH_SECRET"):
                        secret = line.split("=", 1)[1].strip()
        if not secret:
            print("dashboard_publish: DASHBOARD_PUBLISH_SECRET not set in .env — skipping publish")
            return False
        body = json.dumps({"p_secret": secret, "p_payload": payload, "p_symbol": symbol}).encode("utf-8")
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/rpc/publish_snapshot",
            data=body, method="POST",
            headers={"apikey": SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                    "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"dashboard_publish: publish failed ({exc}) — dashboard will show stale data, pipeline continues")
        return False


def main():
    """Publish a snapshot for every configured symbol. Each symbol is fully
    isolated — a build/publish failure on one (e.g. a bad feed for BTC) must
    never block the others (e.g. oil and gold still get published)."""
    s = config.load()
    syms = markets.symbols(s)
    any_ok = False
    for symbol in syms:
        try:
            payload = build_payload(symbol, s=s)
        except Exception as exc:  # noqa: BLE001
            print(f"dashboard_publish[{symbol}]: build_payload failed ({exc}) — skipping this symbol")
            continue
        ok = publish(payload, symbol)
        any_ok = any_ok or ok
        print(f"dashboard_publish[{symbol}]: {'published' if ok else 'NOT published'} "
              f"(signal: {'setup' if payload['signal']['has_setup'] else 'none'})")
    if not syms:
        print("dashboard_publish: no symbols configured (check SYMBOLS in .env)")

    # Day 14: record a "last successful publish" timestamp. Prior Days had
    # no persisted publish heartbeat at all — a gap identified during this
    # Day's Phase 1 audit — so engine/data_health/heartbeat.py's
    # dashboard_publish_status() has something to read. Written only when
    # at least one symbol actually published; never raises.
    if any_ok:
        try:
            hb_path = ROOT / "dashboard_publish_heartbeat.json"
            hb_path.write_text(json.dumps({
                "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "symbols_published": syms,
            }), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"dashboard_publish: heartbeat write failed ({exc}) — non-fatal")


if __name__ == "__main__":
    main()
