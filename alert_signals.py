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
import time
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
                    confluence as cf, grade as gr, symbol_meta as sm,
                    portfolio_risk as pr, regime_engine as rgeng,
                    regime_history as rhist, confluence_analysis as cfa,
                    confluence_history as cfh, confidence_engine as confeng,
                    confidence_history as cfdh, market_memory as mm,
                    explainability_engine as expl, decision_audit_history as dah,
                    macro_engine as macro)
from engine.execution import execution_report as exrep, execution_history as exhist  # noqa: E402
from engine.broker.contract import OrderRequest  # noqa: E402
from engine.data_health import feed_monitor as dh_monitor, freshness as dh_freshness  # noqa: E402
from engine import scan_latency, scan_latency_history as slhist        # noqa: E402

# Day 13: one PaperBroker instance per (account_id, process). Constructed
# lazily on first use — see `_broker()` below — and cached for the rest
# of this process's lifetime so the per-symbol loop in `main()` doesn't
# re-run `PaperBroker.__init__()`'s rebuild-from-history scan once per
# symbol. See engine/broker/PAPER_BROKER_SPECIFICATION.md Sec.6
# "Persistence Model" for why that rebuild step exists at all (this
# platform's scan loop is itself a fresh process each ~15-minute
# invocation, so the rebuild is what makes account/position state
# durable ACROSS scans, not just within one).
_BROKER_CACHE = {}


def _broker(account_id: str = "paper-default"):
    if account_id not in _BROKER_CACHE:
        from engine.broker.paper_broker import PaperBroker
        _BROKER_CACHE[account_id] = PaperBroker(account_id=account_id)
    return _BROKER_CACHE[account_id]


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


def build_prealert(sig, r, guard=None, confluence=None, confidence=None) -> str:
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
        (f"confidence: {confidence.tier} ({confidence.overall_confidence}/100, "
         "uncalibrated est.)" if confidence and not confidence.is_calibrated else
         f"confidence: {confidence.tier} ({confidence.overall_confidence}/100, "
         f"~{confidence.calibrated_probability*100:.0f}% calibrated)" if confidence else None),
        f"➡️ I'll send the ENTRY the moment price taps {sig.entry}.",
        "Research/education only - not financial advice.",
    ]
    return "\n".join(x for x in L if x)


def apply_regime_gate(mkt_regime: dict, mode: str, min_quality: int) -> tuple:
    """Day 4 advisory/block decision, extracted as its own pure function so
    it is independently unit-testable (tests/test_regime_engine.py) without
    driving all of main(). Returns (blocked: bool, note: str).

    "advisory" (default) never blocks — see engine/regime_engine.py's module
    docstring and MARKET_REGIME_SPECIFICATION.md Sec.7 for why filtering is
    not enabled by default. "block" suppresses a NEW Stage-1 origination
    when the regime's quality_score falls below `min_quality`.
    """
    if mode != "block":
        return False, ""
    if mkt_regime.get("quality_score", 100) < min_quality:
        return True, (f"regime quality {mkt_regime.get('quality_score')} below "
                      f"threshold {min_quality} ({mkt_regime.get('primary')}, "
                      f"{mkt_regime.get('compatibility')})")
    return False, ""


def log_confluence_explainability(sym, cr, ref: str = ""):
    """Day 5: purely additive explainability/quality/conflict logging for a
    MAST ConfluenceRead. Does NOT touch cr.score, cr.final_tier, or any
    other field confluence.py already computed — this only READS cr and
    records the analysis to confluence_history.jsonl + the ledger. Called
    right after every cf.analyze() call, both alert stages. Fail-safe: an
    error here must never affect whether the underlying trade publishes,
    matching every other logging call in this pipeline (ledger.log, etc.).

    `ref` (Day 6, optional): the stable trade-journal reference — see
    journal.make_ref() — passed through to confluence_history.record() so
    Trade.confluence_ref can later resolve directly to this row instead of
    relying on a nearest-timestamp join. Empty at Stage-1 (heads-up reads
    have no trade yet)."""
    if cr is None:
        return
    try:
        q = cfa.quality_score(cr)
        conflicts = cfa.conflict_resolution(cr)
        cfh.record(sym, cr.direction, cr.score, cr.final_tier,
                  cr.agree, cr.disagree, q, conflicts, ref=ref)
        ledger.log({"event": "confluence_quality", "symbol": sym,
                    "score": cr.score, "quality_score": q.get("score"),
                    "independent_agreement": q.get("independent_agreement"),
                    "n_conflicts": len(conflicts)})
    except Exception:  # noqa: BLE001
        pass


def log_confidence_assessment(sym, direction, sig=None, mkt_regime=None, cr=None,
                              portfolio_verdict=None, guard=None, news_state=None,
                              session=None, risk_locked=False, settings=None,
                              ref: str = "", memory_context=None):
    """Day 6: assembles and persists one Confidence Engine assessment.
    Purely additive — consumes already-computed upstream objects (never
    re-fetches), never influences whether a signal publishes, and never
    raises. Returns the ConfidenceAssessment (or None on total failure) so
    the caller can also show it in the Telegram message / dashboard
    payload.

    `memory_context` (Day 7, optional): a market_memory.historical_context()
    result, passed straight through to confidence_engine.assess() where it
    can only affect rationale/assumption TEXT, never the score — see that
    function's docstring."""
    try:
        assessment = confeng.assess(
            sym, direction, sig=sig, mkt_regime=mkt_regime, cr=cr,
            portfolio_verdict=portfolio_verdict, guard=guard, news_state=news_state,
            session=session, risk_locked=risk_locked, settings=settings,
            memory_context=memory_context)
        cfdh.record(assessment, ref=ref)
        ledger.log({"event": "confidence_assessment", "symbol": sym,
                    "direction": direction,
                    "overall_confidence": assessment.overall_confidence,
                    "tier": assessment.tier, "is_calibrated": assessment.is_calibrated})
        return assessment
    except Exception:  # noqa: BLE001
        return None


def log_market_memory_context(sym, direction, mkt_regime=None, cr=None,
                              portfolio_verdict=None, session=None, as_of=None):
    """Day 7: purely advisory. Builds the live query feature vector, looks
    up look-ahead-safe comparable historical situations, and logs the
    result to the ledger. Never raises, never used for any gate — the
    caller decides separately (via memory_context= on
    log_confidence_assessment) whether to surface this as rationale text."""
    try:
        query = mm.query_features_from_live(mkt_regime=mkt_regime, cr=cr, session=session,
                                            portfolio_verdict=portfolio_verdict, direction=direction)
        ctx = mm.historical_context(query, as_of=as_of)
        ledger.log({"event": "market_memory_context", "symbol": sym, "direction": direction,
                    "comparable_count": ctx.get("comparable_count"),
                    "sufficient_sample": ctx.get("sufficient_sample"),
                    "confidence_label": (ctx.get("quality") or {}).get("confidence_label")})
        return ctx
    except Exception:  # noqa: BLE001
        return None


def log_decision_snapshot(sym, direction, when, stage, final_action, *, mkt_regime=None,
                          regime_ref="", cr=None, confluence_ref="",
                          confidence_assessment=None, confidence_ref="",
                          memory_context=None, trade_ref="", rejection=None, settings=None):
    """Day 8: purely observational — builds and persists one immutable
    DecisionSnapshot (approved, heads-up, or rejected). Never influences
    whether a signal publishes; never raises. Called at every point where a
    SPECIFIC candidate direction/opportunity is already known (Stage-1
    origination onward), matching every other `log_*` helper's fail-safe
    posture in this file. See EXPLAINABILITY_SPECIFICATION.md Sec.7 for the
    explicit scope boundary (account-level gates that run before any
    specific opportunity exists — news blackout, a symbol-wide risk lock
    checked before origination — are NOT snapshotted; they remain
    single-line ledger events only, same as before Day 8)."""
    try:
        snap = expl.build_decision_snapshot(
            sym, direction, when, stage=stage, final_action=final_action,
            mkt_regime=mkt_regime, regime_ref=regime_ref, cr=cr, confluence_ref=confluence_ref,
            confidence_assessment=confidence_assessment, confidence_ref=confidence_ref,
            memory_context=memory_context, trade_ref=trade_ref, rejection=rejection,
            settings=settings)
        row = dah.record(snap)
        ledger.log({"event": "decision_snapshot", "symbol": sym, "direction": direction,
                    "decision_id": row.get("decision_id"), "stage": stage,
                    "final_action": final_action})
        return row
    except Exception:  # noqa: BLE001
        return None


def log_macro_context(sym, direction, ref=""):
    """Day 11: purely observational — computes one Macro Intelligence
    Engine assessment and persists it to macro_history.jsonl. Never
    influences whether a signal publishes, never touches confidence or
    confluence; never raises. Called ONLY at Stage-2 entry (not every
    scan) — a deliberate, disclosed difference from the Market Regime
    Engine's routine per-scan capture: macro context is direction-
    dependent (see engine.macro_cross_asset), so computing it before a
    specific candidate direction exists would need recomputing anyway,
    and nothing reads a no-trade routine snapshot today. See
    MACRO_ENGINE_SPECIFICATION.md Sec.5 for the full reasoning."""
    try:
        assessment = macro.assess(sym, direction)
        row = macro.record_assessment(sym, assessment, ref=ref)
        ledger.log({"event": "macro_assessment", "symbol": sym, "direction": direction,
                    "labels": row.get("labels"), "macro_confidence": row.get("macro_confidence"),
                    "evidence_quality": row.get("evidence_quality"), "ref": ref})
        return assessment
    except Exception:  # noqa: BLE001
        return None


def log_execution_context(sym, direction, entry, stop, target, atr_pct=None,
                          news_blackout=False, session=None, when=None, ref="",
                          style=None):
    """Day 12: purely observational — simulates this trade's entry fill
    (spread + slippage + latency, per the disclosed assumption model in
    engine/execution/) and persists a normalized report to
    execution_history.jsonl. Never influences whether a signal publishes,
    never touches confidence, confluence, or the trade's own
    entry/stop/target (those remain the strategy's INTENDED levels — this
    only records what a REALISTIC fill of that intent might have cost).
    Never raises. Called at Stage-2 entry, same placement as
    log_macro_context() above. See EXECUTION_SIMULATOR_SPECIFICATION.md
    Sec.5.

    `style` (V2.2 Priority 1 Item 3, optional): passed straight through to
    build_trade_execution_report()'s own `style` parameter — see that
    docstring and engine/execution/execution_profile.py. Callers today
    pass `settings.execution_style` (one global config value, since no
    Strategy Registry exists yet to assign a style per-strategy — see
    config.py's own execution_style docstring)."""
    try:
        report = exrep.build_trade_execution_report(
            sym, direction, entry, exit_price=None, stop_price=stop,
            signal_ts=when, atr_pct=atr_pct, news_blackout=news_blackout, session=session,
            style=style)
        row = exhist.record(sym, report, ref=ref)
        prof_eval = report.get("execution_profile_evaluation") or {}
        ledger.log({"event": "execution_report", "symbol": sym, "direction": direction,
                    "execution_score": row.get("execution_score"),
                    "cost_r": row.get("cost_r"), "ref": ref,
                    "execution_profile_style": prof_eval.get("style"),
                    "execution_profile_within_tolerance": prof_eval.get("all_within_tolerance")})
        return report
    except Exception:  # noqa: BLE001
        return None


def log_paper_broker_submission(sym, direction, entry, stop, target, atr_pct=None,
                                news_blackout=False, session=None, when=None, ref=""):
    """Day 13: purely observational — submits this trade's ENTRY to the
    Paper Broker (`engine.broker.paper_broker.PaperBroker`), which
    consumes the same Day 12 execution simulator `log_execution_context()`
    above already uses, but additionally tracks a real virtual account
    (balance, margin, aggregate position) rather than only a per-trade
    fill-quality report. Never influences whether a signal publishes,
    never touches confidence, confluence, or the trade's own entry/stop/
    target (those remain the strategy's INTENDED levels — same posture
    as every advisory subsystem since Day 7). Never raises. Called at
    Stage-2 entry, same placement as `log_execution_context()` above. See
    PAPER_BROKER_SPECIFICATION.md Sec.8 "alert_signals.py Integration"."""
    try:
        broker = _broker()
        side = "buy" if direction == "long" else "sell"
        req = OrderRequest(
            client_order_id=ref, account_id=broker.account_id, symbol=sym, side=side,
            order_type="market", intended_price=entry, stop_price=stop, signal_ts=when,
            ref=ref, atr_pct=atr_pct, news_blackout=news_blackout, session=session)
        order = broker.submit_order(req)
        ledger.log({"event": "broker_order", "symbol": sym, "direction": direction,
                    "status": order.status, "quantity": order.quantity,
                    "avg_fill_price": order.avg_fill_price, "ref": ref})
        return order
    except Exception:  # noqa: BLE001
        return None


def sync_paper_broker_closures(sym):
    """Day 13: closes the Paper Broker's aggregate position for `sym`
    against any trade that `journal.settle()` (called immediately before
    this, at the top of the per-symbol loop) just marked win/loss/
    scratch/expired. Purely observational — this only updates the paper
    account's balance/positions for later review, never the trade
    journal or any gating decision. Never raises. See
    PAPER_BROKER_SPECIFICATION.md Sec.8."""
    try:
        results = _broker().sync_closures(sym)
        for r in results:
            if r.get("closed"):
                ledger.log({"event": "broker_close", "symbol": sym, "ref": r.get("ref"),
                            "realized_pnl_delta": r.get("realized_pnl_delta")})
        return results
    except Exception:  # noqa: BLE001
        return []


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


def build_entry(rec, lt, confluence=None, confidence=None, macro=None, execution=None, broker=None) -> str:
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
        (f"confidence: {confidence.tier} ({confidence.overall_confidence}/100"
         f"{f', ~{confidence.calibrated_probability*100:.0f}% calibrated' if confidence.is_calibrated and confidence.calibrated_probability is not None else ', uncalibrated est.'})"
         if confidence else None),
        # Day 11: informational only, exactly like the confidence line above
        # — never a gate, never a score. See MACRO_ENGINE_SPECIFICATION.md.
        (f"macro: {', '.join(macro['regime']['labels'])} "
         f"(macro_confidence={macro['regime']['macro_confidence']}, "
         f"evidence_quality={macro['regime']['evidence_quality']})"
         if macro and macro.get("regime", {}).get("labels") else None),
        # Day 12: informational only, same posture as confidence/macro above
        # — a simulated fill-quality estimate, never a gate. See
        # EXECUTION_SIMULATOR_SPECIFICATION.md.
        (f"est. execution: {execution['execution_score']} "
         f"(spread~{execution['entry_detail']['spread']['estimated_spread']}, "
         f"cost~{execution['cost_r']}R)"
         if execution and execution.get("entry_filled") else None),
        # Day 13: informational only, same posture as macro/execution above
        # — the Paper Broker's simulated order outcome + resulting
        # virtual account state, never a gate. See
        # PAPER_BROKER_SPECIFICATION.md.
        (f"paper broker: {broker.status} (qty {broker.quantity} lot"
         f"{f', avg fill {broker.avg_fill_price}' if broker.avg_fill_price else ''})"
         if broker is not None else None),
        "Research/education only - not financial advice.",
    ]
    return "\n".join(x for x in L if x)


def log_data_health(settings, elapsed_seconds, symbol_count) -> dict:
    """Day 14: advisory-only feed-health check, run once per scan (not
    once per symbol — the underlying feeds don't change mid-scan).
    Never raises, never gates: this function's return value is used only
    for a one-line log summary and to feed the heartbeat's processing-
    latency/queue-depth signals. See DATA_HEALTH_SPECIFICATION.md for the
    structural proof that nothing here can affect a trade decision."""
    try:
        return dh_monitor.run_health_check(
            settings=settings, processing_latency_seconds=elapsed_seconds, queue_depth=symbol_count)
    except Exception as exc:  # noqa: BLE001
        return {"overall_status": "unavailable", "counts": {}, "note": f"log_data_health error: {exc}"}


# --- Day 15: scan status — a durable, structured heartbeat -----------------
# Root cause found this Day: alert_heartbeat.txt (this scan's plain-text log)
# is gitignored and entry-scan.yml's persist step never adds it, so it never
# survives past the ephemeral GitHub Actions runner that wrote it — the
# heartbeat watchdog's own fresh checkout can never see it, which is why 11+
# days of total market-data-fetch failure (every symbol raising in the loop
# below, caught by the blanket `except Exception` and silently logged) never
# produced a single alert. Two things fix this, together:
#   1. write a small structured status file into .cache/ — the SAME
#      directory entry-scan.yml already round-trips across runs via
#      actions/cache (see the "Restore last-known-good market data cache"
#      step), so this rides an existing, already-working persistence
#      mechanism instead of a new one, and never touches git at all.
#   2. if EVERY symbol failed to even fetch data this scan (the specific,
#      worst-case condition that has apparently been happening silently),
#      raise once main() is otherwise done — so the "Run entry scanner"
#      step exits non-zero and the failure is visible in the Actions UI
#      instead of being swallowed. See DAY15_IMPLEMENTATION_REPORT.md.
SCAN_STATUS_PATH = ROOT / ".cache" / "heartbeat_status.json"


def write_scan_status(symbol_status: dict, elapsed_seconds: float) -> dict:
    """Writes a structured, cache-durable scan-outcome summary. Never
    raises — a bug here must degrade to a printed line, same fail-safe
    discipline as the rest of this file. Returns the record written (or
    attempted) so callers/tests can inspect it without re-reading the file."""
    n_symbols = len(symbol_status)
    n_fetch_ok = sum(1 for v in symbol_status.values() if v.get("fetch_ok"))
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        "symbols": symbol_status,
        "n_symbols": n_symbols,
        "n_fetch_ok": n_fetch_ok,
        "total_data_outage": bool(n_symbols) and n_fetch_ok == 0,
    }
    try:
        SCAN_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCAN_STATUS_PATH.write_text(json.dumps(record), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"write_scan_status: failed to persist ({exc}) — non-fatal")
    return record


def main():
    _scan_start = time.monotonic()
    timer = scan_latency.ScanTimer()
    s = config.load()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    news_state = news_guard.evaluate()
    # Day 14: observe this call's own outcome for the news_calendar feed —
    # never a second fetch, just a record of the fetch news_guard already
    # made for the blackout check above. See engine/data_health/freshness.py
    # record_observation()'s docstring for why this is the one place in the
    # whole package that records anything about a live call.
    dh_freshness.record_observation(
        "news_calendar", bool(news_state.get("ok", True)), news_state.get("note", "") or "")
    blackout = news_state.get("blackout", False)
    log = [now + (" [NEWS BLACKOUT]" if blackout else "")]
    regime_mode = str(getattr(s, "regime_filter_mode", "advisory") or "advisory").lower()
    regime_min_quality = int(getattr(s, "regime_min_quality_for_block", 30) or 30)
    regime_strategy = str(getattr(s, "regime_strategy", "ict_smc_mast") or "ict_smc_mast")

    scan_symbol_status = {}   # Day 15: sym -> {"fetch_ok": bool, "error": str|None}
    for sym in markets.symbols(s):
        try:
            with timer.stage("market_fetch"):
                df = markets.fetch(sym, s)
            scan_symbol_status[sym] = {"fetch_ok": True, "error": None}
            journal.settle(df, symbol=sym)

            # --- Day 13: Paper Broker closure sync ---------------------------
            # Closes the Paper Broker's aggregate position for any trade
            # `journal.settle()` just marked win/loss/scratch/expired.
            # Purely observational — updates only the paper account's own
            # balance/positions, never the trade journal or any gate. See
            # PAPER_BROKER_SPECIFICATION.md Sec.8.
            with timer.stage("paper_broker"):
                sync_paper_broker_closures(sym)

            # --- Day 4: centralized Market Regime Engine ---------------------
            # Runs first, per symbol, per scan — the first analytical stage in
            # the pipeline (Market Data -> Regime -> Origination -> Confluence
            # -> Risk -> Portfolio Risk -> Publication), per the Day 4 mandate.
            # Purely additive: engine/regime.py's own single-timeframe call
            # inside _guard_for() below (used by range_guard) is UNCHANGED —
            # this is a separate, new, multi-timeframe classification used
            # only for history/explainability/advisory filtering, so nothing
            # about the existing, already-tested range_guard behavior changes.
            with timer.stage("regime"):
                mkt_regime = rgeng.classify(df, sym, strategy=regime_strategy,
                                            news_state=news_state)
            rhist.record(sym, "strategic", mkt_regime)
            ledger.log({"event": "regime", "symbol": sym, "primary": mkt_regime["primary"],
                        "confidence": mkt_regime["confidence"],
                        "quality": mkt_regime["quality_score"],
                        "transition": mkt_regime["transition_label"],
                        "tags": mkt_regime["tags"], "mode": regime_mode})

            with timer.stage("origination"):
                pending_events = pending.update(sym, df)
            for typ, rec in pending_events:
                if typ == "entry" and not blackout:
                    erk = risk_guard.evaluate(sym)
                    if erk["locked"]:
                        log.append(f"{sym}: entry HELD — {erk['reason']}")
                        ledger.log({"event": "entry_held", "symbol": sym,
                                    "reason": erk["reason"]})
                        with timer.stage("explainability"):
                            log_decision_snapshot(
                            sym, rec["direction"], pd.Timestamp(df.index[-1]),
                            stage="market_regime_assessment", final_action="rejected",
                            mkt_regime=mkt_regime,
                            rejection={"category": expl.RISK_LOCK, "reason": erk["reason"]},
                            settings=s)
                        continue
                    lt = ltf.confirm(rec["direction"]) if sym == "XAUUSD" else {}
                    e_reg = regime.classify(resample(df, "4h"))
                    e_guard = _guard_for(sym, rec["direction"], df)
                    when = pd.Timestamp(df.index[-1])
                    trade_ref = journal.make_ref(sym, when)  # Day 6/7: the unified trade ID,
                                                              # shared by the trade row + every
                                                              # history log (see
                                                              # MARKET_MEMORY_SPECIFICATION.md Sec.2)
                    # Day 7: an additional, ref-tagged regime snapshot — the
                    # unconditional per-scan record (top of this loop, before
                    # Stage-1/Stage-2 branching) already logged this same
                    # mkt_regime with ref="" for routine history; this second,
                    # trade-tied record is what regime_history.find_by_ref()
                    # and the Market Memory Engine actually join against.
                    rhist.record(sym, "strategic", mkt_regime, ref=trade_ref)
                    try:
                        with timer.stage("confluence"):
                            e_cr = cf.analyze(df.tail(12000), symbol=sym,
                                              min_score=s.confluence_min_score)
                        e_conf = ({"score": e_cr.score, "agree": len(e_cr.agree)}
                                  if e_cr else {})
                        log_confluence_explainability(sym, e_cr, ref=trade_ref)  # Day 5/6
                    except Exception:  # noqa: BLE001
                        e_cr = None
                        e_conf = {}

                    # --- Day 3: centralized portfolio risk gate -------------
                    # Last check before publication (Phase 5 hierarchy: session
                    # -> regime -> strategy qualification -> MAST confluence ->
                    # risk_guard [above] -> portfolio validation [here] ->
                    # publication). See engine/portfolio_risk.py and
                    # RISK_SPECIFICATION.md.
                    with timer.stage("portfolio_risk"):
                        e_pr = pr.evaluate(sym, rec["direction"], rec["entry"], rec["stop"],
                                           settings=s, session_label=e_reg.get("session")
                                           if isinstance(e_reg, dict) else None)
                    if not e_pr["allow"]:
                        log.append(f"{sym}: entry HELD (portfolio) — {e_pr['reason']}")
                        ledger.log({"event": "portfolio_held", "symbol": sym,
                                    "category": e_pr["category"], "reason": e_pr["reason"]})
                        with timer.stage("explainability"):
                            log_decision_snapshot(
                            sym, rec["direction"], when, stage="portfolio_risk",
                            final_action="rejected", mkt_regime=mkt_regime, regime_ref=trade_ref,
                            cr=e_cr, confluence_ref=trade_ref,
                            rejection={"category": e_pr["category"], "reason": e_pr["reason"]},
                            settings=s)
                        continue
                    if e_pr.get("would_block"):
                        ledger.log({"event": "portfolio_warn", "symbol": sym,
                                    "category": e_pr["category"], "reason": e_pr["reason"]})

                    # --- Day 7: Market Memory Engine — advisory-only, feeds
                    # informational text into the Confidence Engine's
                    # rationale/assumptions but never its score. See
                    # MARKET_MEMORY_SPECIFICATION.md.
                    e_session = e_reg.get("session") if isinstance(e_reg, dict) else None
                    with timer.stage("memory"):
                        e_memory = log_market_memory_context(
                            sym, rec["direction"], mkt_regime=mkt_regime, cr=e_cr,
                            portfolio_verdict=e_pr, session=e_session, as_of=when)

                    # --- Day 11: Macro Intelligence Engine — advisory-only,
                    # same posture as Market Memory above: computed and
                    # persisted for later review/research, never read by any
                    # gate above and never folded into confidence or
                    # confluence. See MACRO_ENGINE_SPECIFICATION.md Sec.6.
                    with timer.stage("macro"):
                        e_macro = log_macro_context(sym, rec["direction"], ref=trade_ref)

                    # --- Day 12: Execution Simulator — advisory-only, same
                    # posture as Macro/Market-Memory above: simulates this
                    # trade's realistic entry fill (spread/slippage/latency)
                    # and persists a fill-quality report for later research.
                    # Never gates, never resizes, never touches the trade's
                    # own entry/stop/target. See
                    # EXECUTION_SIMULATOR_SPECIFICATION.md Sec.6.
                    with timer.stage("execution_simulation"):
                        e_execution = log_execution_context(
                            sym, rec["direction"], rec["entry"], rec["stop"], rec["target"],
                            atr_pct=e_reg.get("atr_pct") if isinstance(e_reg, dict) else None,
                            news_blackout=blackout, session=e_session, when=when, ref=trade_ref,
                            style=str(getattr(s, "execution_style", "day") or "day"))

                    # --- Day 13: Broker Abstraction Layer — advisory-only,
                    # same posture as Execution/Macro/Market-Memory above:
                    # submits this trade's entry to the Paper Broker
                    # (tracks a real virtual account/position on top of the
                    # same Day 12 fill simulation), and persists a fill-
                    # quality-plus-account report for later research. Never
                    # gates, never resizes, never touches the trade's own
                    # entry/stop/target. See PAPER_BROKER_SPECIFICATION.md
                    # Sec.8.
                    with timer.stage("paper_broker"):
                        e_broker = log_paper_broker_submission(
                            sym, rec["direction"], rec["entry"], rec["stop"], rec["target"],
                            atr_pct=e_reg.get("atr_pct") if isinstance(e_reg, dict) else None,
                            news_blackout=blackout, session=e_session, when=when, ref=trade_ref)

                    # --- Day 6: Confidence Engine — assessed last, after every
                    # upstream gate (origination, regime, confluence, risk,
                    # portfolio) has already run. Purely additive: cannot hold
                    # or downgrade this entry, only records/displays a
                    # transparent synthesis of what already happened. See
                    # CONFIDENCE_ENGINE_SPECIFICATION.md.
                    with timer.stage("confidence"):
                        e_assessment = log_confidence_assessment(
                            sym, rec["direction"], sig=pending.as_signal(rec), mkt_regime=mkt_regime,
                            cr=e_cr, portfolio_verdict=e_pr, guard=e_guard, news_state=news_state,
                            session=e_session, risk_locked=bool(erk.get("locked")), settings=s,
                            ref=trade_ref, memory_context=e_memory)

                    # --- Day 8: Explainability Engine — the final, immutable
                    # decision snapshot for this fill. Recorded AFTER every
                    # upstream gate/assessment above; purely observational,
                    # cannot affect whether this entry publishes. See
                    # EXPLAINABILITY_SPECIFICATION.md.
                    with timer.stage("explainability"):
                        log_decision_snapshot(
                        sym, rec["direction"], when, stage="approval_or_rejection",
                        final_action="approved_entry", mkt_regime=mkt_regime, regime_ref=trade_ref,
                        cr=e_cr, confluence_ref=trade_ref, confidence_assessment=e_assessment,
                        confidence_ref=trade_ref, memory_context=e_memory, trade_ref=trade_ref,
                        settings=s)

                    _send(s, build_entry(rec, lt, confluence=e_cr, confidence=e_assessment,
                                        macro=e_macro, execution=e_execution, broker=e_broker),
                         channel=markets.channel_for(sym, s))
                    with timer.stage("persistence"):
                        journal.log_signal(pending.as_signal(rec), when,
                                           regime=e_reg, guard=e_guard,
                                           confluence=e_conf, confluence_ref=trade_ref,
                                           confidence_ref=trade_ref, regime_ref=trade_ref,
                                           macro_ref=trade_ref, execution_ref=trade_ref,
                                           broker_ref=trade_ref)
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

            with timer.stage("origination"):
                sig = signals.analyze(df.tail(12000),
                                      min_conf=signals.PUBLISH_THRESHOLD, symbol=sym)
            if sig is None:
                log.append(f"{sym}: no setup"); continue
            if pending.exists(sig) or journal.is_open(sym, sig.direction, sig.entry):
                log.append(f"{sym}: already tracked"); continue

            # --- Day 4: Market Regime Engine advisory/block gate -------------
            # Per the documented risk hierarchy (session -> regime -> strategy
            # qualification -> MAST confluence -> risk -> portfolio ->
            # publication), regime is evaluated before confluence. Default
            # mode is "advisory": logged only, never blocks (see
            # MARKET_REGIME_SPECIFICATION.md Sec.7 — no forward-test evidence
            # yet that filtering improves expectancy). Only gates a NEW
            # Stage-1 origination, never an already-published Stage-2 fill.
            regime_blocked, regime_note = apply_regime_gate(mkt_regime, regime_mode,
                                                             regime_min_quality)
            if regime_blocked:
                log.append(f"{sym}: HEADS-UP HELD (regime) — {regime_note}")
                ledger.log({"event": "regime_held", "symbol": sym,
                            "primary": mkt_regime["primary"],
                            "quality_score": mkt_regime["quality_score"],
                            "threshold": regime_min_quality})
                with timer.stage("explainability"):
                    log_decision_snapshot(
                    sym, sig.direction, pd.Timestamp(df.index[-1]),
                    stage="market_regime_assessment", final_action="rejected",
                    mkt_regime=mkt_regime,
                    rejection={"category": pr.MARKET_REGIME_UNSUITABLE, "reason": regime_note},
                    settings=s)
                continue

            # MAST confluence engine — Layer 1 (ICT/SMC) found the setup,
            # Layer 2 confirmations must also clear before this ever reaches
            # a live channel. Confluence can only confirm or reject/downgrade
            # Layer 1's read, never originate a trade on its own.
            try:
                with timer.stage("confluence"):
                    cr = cf.analyze(df.tail(12000), symbol=sym,
                                    min_score=s.confluence_min_score)
            except Exception as exc:  # noqa: BLE001
                cr = None
                log.append(f"{sym}: confluence engine error {exc}")
            log_confluence_explainability(sym, cr)   # Day 5 — logs regardless of tier
            if cr is not None and cr.final_tier != "confirmed":
                log.append(f"{sym}: MAST held — {cr.final_tier} "
                           f"(score {cr.score}, disagree: {', '.join(cr.disagree) or '-'})")
                ledger.log({"event": "confluence_held", "symbol": sym,
                            "score": cr.score, "final_tier": cr.final_tier,
                            "disagree": cr.disagree})
                with timer.stage("explainability"):
                    log_decision_snapshot(
                    sym, sig.direction, pd.Timestamp(df.index[-1]),
                    stage="confluence_assessment", final_action="rejected",
                    mkt_regime=mkt_regime, cr=cr,
                    rejection={"category": expl.WEAK_EVIDENCE,
                              "reason": f"MAST {cr.final_tier} (score {cr.score})"},
                    settings=s)
                continue

            r = ict.read(df)
            guard = _guard_for(sym, sig.direction, df)
            grade = rgd.cap_grade(
                gr.grade_for(cr.score if cr else 0,
                            cr.final_tier if cr else getattr(sig, "tier", "confirmed")).letter,
                guard.get("grade_cap"))

            # --- Day 3: centralized portfolio risk gate ---------------------
            # Stage-1 is a heads-up, not a fill, but it is still a public
            # commitment ("watching for entry") and it seeds `pending.json`,
            # which Stage-2 will act on automatically the moment price taps
            # the level with NO further portfolio check in between. So the
            # portfolio gate must run here too, not just at Stage-2 — see
            # RISK_SPECIFICATION.md Sec.3 for why both stages need it.
            with timer.stage("portfolio_risk"):
                pr_verdict = pr.evaluate(sym, sig.direction, sig.entry, sig.stop,
                                         settings=s, session_label=r.get("session"))
            if not pr_verdict["allow"]:
                log.append(f"{sym}: HEADS-UP HELD (portfolio) — {pr_verdict['reason']}")
                ledger.log({"event": "portfolio_held", "symbol": sym,
                            "category": pr_verdict["category"], "reason": pr_verdict["reason"]})
                with timer.stage("explainability"):
                    log_decision_snapshot(
                    sym, sig.direction, pd.Timestamp(df.index[-1]),
                    stage="portfolio_risk", final_action="rejected",
                    mkt_regime=mkt_regime, cr=cr,
                    rejection={"category": pr_verdict["category"], "reason": pr_verdict["reason"]},
                    settings=s)
                continue
            if pr_verdict.get("would_block"):
                ledger.log({"event": "portfolio_warn", "symbol": sym,
                            "category": pr_verdict["category"], "reason": pr_verdict["reason"]})

            # --- Day 7: Market Memory Engine — advisory only, see Stage-2's
            # identical comment above.
            with timer.stage("memory"):
                heads_up_memory = log_market_memory_context(
                    sym, sig.direction, mkt_regime=mkt_regime, cr=cr,
                    portfolio_verdict=pr_verdict, session=r.get("session"),
                    as_of=pd.Timestamp(df.index[-1]))

            # --- Day 6: Confidence Engine — Stage-1 heads-up assessment. No
            # trade row exists yet (this only seeds pending.json), so `ref`
            # is left empty; the join falls back to nearest-timestamp for
            # any research done on Stage-1 reads specifically.
            with timer.stage("confidence"):
                assessment = log_confidence_assessment(
                    sym, sig.direction, sig=sig, mkt_regime=mkt_regime, cr=cr,
                    portfolio_verdict=pr_verdict, guard=guard, news_state=news_state,
                    session=r.get("session"), risk_locked=bool(rk.get("locked")), settings=s,
                    memory_context=heads_up_memory)

            # --- Day 8: Explainability Engine — heads-up decision snapshot.
            # Purely observational; recorded after every upstream gate above,
            # cannot affect whether this heads-up publishes.
            with timer.stage("explainability"):
                log_decision_snapshot(
                sym, sig.direction, pd.Timestamp(df.index[-1]), stage="approval_or_rejection",
                final_action="approved_heads_up", mkt_regime=mkt_regime, cr=cr,
                confidence_assessment=assessment, memory_context=heads_up_memory, settings=s)

            with timer.stage("persistence"):
                pending.add(sig, pd.Timestamp(df.index[-1]))
            _send(s, build_prealert(sig, r, guard, confluence=cr, confidence=assessment),
                 channel=markets.channel_for(sym, s))
            log.append(f"{sym}: HEADS-UP {sig.direction} @ {sig.entry}"
                       + (f" [{guard['action']}]" if guard.get("action") != "allow" else ""))
            ledger.log({"event": "heads_up", "symbol": sym, "dir": sig.direction,
                        "entry": sig.entry, "conf": sig.confidence, "grade": grade,
                        "guard": guard.get("action"), "guard_pen": guard.get("penalty", 0),
                        "session": r.get("session")})
        except Exception as exc:  # noqa: BLE001
            # Day 15: only record fetch_ok=False if this symbol never got
            # past markets.fetch() above — a later, unrelated exception
            # (e.g. a downstream analysis bug) shouldn't be misreported as
            # a data-fetch failure. fetch_ok being unset here means the
            # `try` never reached the `scan_symbol_status[sym] = ...` line.
            scan_symbol_status.setdefault(sym, {"fetch_ok": False, "error": str(exc)})
            log.append(f"{sym}: ERROR {exc}")

    # --- Day 14: Data Quality & Feed Health check — run once per scan,
    # after every symbol has been processed, never before or during (this
    # is an OBSERVATION of the scan that just happened, not a precondition
    # for it). Advisory only: nothing above this line consulted it, and
    # nothing below it can turn its findings into a gate.
    elapsed = time.monotonic() - _scan_start
    health = log_data_health(s, elapsed, len(markets.symbols(s)))
    log.append(f"data health: {health.get('overall_status')} "
               f"({health.get('counts', {})})")

    with timer.stage("persistence"):
        (ROOT / "alert_heartbeat.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
        print(" | ".join(log))

        # Day 15: durable, cache-backed status (see write_scan_status docstring
        # above) — written before the dashboard publish attempt so a dashboard
        # bug can never suppress the scan-outcome record.
        status = write_scan_status(scan_symbol_status, time.monotonic() - _scan_start)

    try:
        from engine import dashboard_publish as dp
        with timer.stage("dashboard"):
            dp.main()   # keep the live mobile dashboard fresh every scan, not just hourly
    except Exception as exc:  # noqa: BLE001
        print("dashboard publish skipped:", exc)

    # V2.2 Priority 1 Item 2: persist this scan's per-stage latency
    # (scan_latency.ScanTimer -> scan_latency_history.jsonl). "Workflow
    # End" is total_ms itself (timer.total_ms(), captured at record() call
    # time) rather than a separate wrapped stage - there is no code left to
    # time once every stage above has run. Recorded unconditionally, before
    # the total-outage check below, so latency data survives even on a scan
    # that goes on to raise.
    slhist.record(timer.snapshot(), timer.total_ms(),
                   symbol_count=len(markets.symbols(s)),
                   call_counts=timer.call_counts())

    if status.get("total_data_outage"):
        # Every symbol failed to even fetch data this scan. Everything
        # above already degraded gracefully (no crash, no partial state
        # written) — that's correct. But 96 of these in a row, silently,
        # is exactly the failure mode Day 15 was opened to fix: raising
        # here (last thing main() does) makes the "Run entry scanner" step
        # in entry-scan.yml exit non-zero, so a sustained outage shows up
        # as a failed workflow run instead of a permanently-green one.
        raise RuntimeError(
            "total data outage: every symbol failed to fetch market data "
            f"this scan ({status['symbols']})")


if __name__ == "__main__":
    main()
