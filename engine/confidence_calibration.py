"""Confidence Engine calibration framework — Day 6.

Answers the mandate's core question: "is `overall_confidence` an honest
probability, or just a score?" It is only ever the former once this module
says it has enough real matched outcomes to say so — see
`calibrated_probability_for()`, which is the single function
`confidence_engine.assess()` calls to decide `is_calibrated`.

This deliberately mirrors `engine/calibration.py` (the pre-existing,
already-in-production calibration of Layer 1's raw `sig.confidence`) rather
than inventing a new methodology: same bucket/reliability/Brier-score
approach, same "insufficient data -> don't pretend" posture. It is a
separate module, not an extension of `calibration.py`, because it
calibrates a DIFFERENT number — Day 6's composite `overall_confidence`,
which folds in confluence quality, regime confidence, and risk/portfolio
penalties that `calibration.py`'s raw-confidence bucketing never saw — and
because it must join against `confidence_history.jsonl` (Day 6) rather than
reading `confidence` directly off `trades.json`.

Why MIN_N=30, not calibration.py's MIN_N=8: `overall_confidence` is a
newer, compound metric (five sub-scores combined via disclosed, not yet
statistically fitted, weights — see confidence_engine.py). A higher trust
bar before treating its buckets as reliable is deliberate, matching
Day 5's MIN_N_FOR_CONTRIBUTION=30 precedent for the same reason: more
moving parts warrants more evidence before trusting a systematic-bias
finding.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confidence_history as ch  # noqa: E402
from engine import store  # noqa: E402

MIN_N_FOR_CALIBRATION = 30

# Mirrors confidence_engine.DEFAULT_TIERS' band edges exactly (not
# calibration.py's raw-score bands) — this calibrates overall_confidence,
# the Day 6 composite, not Layer 1's raw sig.confidence.
BUCKETS = [
    ("<40", 0, 40, 20), ("40-54", 40, 55, 47), ("55-69", 55, 70, 62),
    ("70-84", 70, 85, 77), ("85-100", 85, 101, 92),
]


def _norm(ts: str) -> str:
    """Same fix as Day 5's join: normalize the 'T'/' ' separator so
    lexicographic timestamp comparison is correct (see
    confluence_analysis.join_trades_with_confluence's docstring for the
    original bug this guards against)."""
    return str(ts or "").replace("T", " ")


def join_trades_with_confidence(trades_rows=None, history_rows=None) -> list:
    """Join closed trades.json rows to their Confidence Engine assessment.
    Prefers the direct stable `ref` match (Day 6's improvement — see
    journal.py's Trade.id / alert_signals.py's Phase 4 wiring); falls back
    to the nearest-preceding-timestamp join Day 4/5 established when `ref`
    is empty or unmatched (e.g. assessments made for a Stage-1 heads-up that
    never became a filled trade, or rows recorded before this field
    existed). Never raises. Returns a list of
    {symbol, trade_id, opened, overall_confidence, tier, matched_via,
     outcome, result_r, status}."""
    try:
        trades_rows = trades_rows if trades_rows is not None else store.load_array(ROOT / "trades.json")
        history_rows = history_rows if history_rows is not None else ch.all_rows()

        closed = [t for t in trades_rows if t.get("status") in ("win", "loss", "scratch")]
        by_ref = {h.get("ref"): h for h in history_rows if h.get("ref")}

        by_symbol = {}
        for h in history_rows:
            by_symbol.setdefault(h.get("symbol"), []).append(h)
        for sym in list(by_symbol):
            by_symbol[sym] = sorted(by_symbol[sym], key=lambda r: _norm(r.get("timestamp", "")))

        out = []
        for t in closed:
            h = by_ref.get(t.get("id"))
            matched_via = "ref"
            if h is None:
                matched_via = "timestamp"
                opened = _norm(t.get("opened", ""))
                sym = t.get("symbol", "XAUUSD")
                candidates = [r for r in by_symbol.get(sym, [])
                             if _norm(r.get("timestamp", "")) <= opened]
                h = candidates[-1] if candidates else None
            if h is None:
                continue
            out.append({
                "symbol": t.get("symbol"), "trade_id": t.get("id"),
                "opened": t.get("opened", ""),
                "overall_confidence": h.get("overall_confidence"),
                "tier": h.get("tier"), "matched_via": matched_via,
                "outcome": 1.0 if t.get("status") == "win" else 0.0,
                "result_r": float(t.get("result_r", 0) or 0),
                "status": t.get("status"),
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def reliability(joined: list = None, min_n: int = MIN_N_FOR_CALIBRATION) -> list:
    joined = join_trades_with_confidence() if joined is None else joined
    out = []
    for name, lo, hi, mid in BUCKETS:
        grp = [j for j in joined if lo <= int(j.get("overall_confidence") or 0) < hi]
        n = len(grp)
        if not n:
            continue
        wr = sum(j["outcome"] for j in grp) / n
        out.append({"bucket": name, "predicted": mid / 100.0, "realized": round(wr, 3),
                    "n": n, "gap": round(wr - mid / 100.0, 3), "sufficient": n >= min_n})
    return out


def brier(joined: list = None) -> float | None:
    joined = join_trades_with_confidence() if joined is None else joined
    if not joined:
        return None
    s = sum((int(j.get("overall_confidence") or 0) / 100.0 - j["outcome"]) ** 2 for j in joined)
    return round(s / len(joined), 4)


def calibrated_probability_for(overall_confidence: int, joined: list = None,
                               min_n: int = MIN_N_FOR_CALIBRATION) -> tuple:
    """Returns (probability_or_None, is_calibrated, n_in_bucket). Only
    returns a real probability when the matching bucket has >= min_n real
    matched outcomes; otherwise (None, False, n) — this is the single
    function that keeps `confidence_engine.assess()` honest about
    `is_calibrated`. Never raises."""
    try:
        rel = reliability(joined, min_n=min_n)
        score = max(0, min(100, int(overall_confidence or 0)))
        for name, lo, hi, _mid in BUCKETS:
            if lo <= score < hi:
                match = next((r for r in rel if r["bucket"] == name), None)
                if match and match["sufficient"]:
                    return match["realized"], True, match["n"]
                return None, False, (match["n"] if match else 0)
        return None, False, 0
    except Exception:  # noqa: BLE001
        return None, False, 0


def recommend_recalibration(joined: list = None, min_n: int = MIN_N_FOR_CALIBRATION,
                            bias_threshold: float = 0.15) -> list:
    """Flags systematic over/under-confidence per bucket where enough data
    exists to trust the finding. NEVER recalibrates automatically — mirrors
    Day 5's recommend_weight_adjustments(): advisory only. Any actual change
    to confidence_engine.py's weights remains a deliberate, human-reviewed
    code edit."""
    rel = reliability(joined, min_n=min_n)
    out = []
    for r in rel:
        if not r["sufficient"]:
            out.append({**r, "recommendation": "insufficient_data"})
            continue
        if abs(r["gap"]) > bias_threshold:
            direction = "overconfident" if r["gap"] < 0 else "underconfident"
            out.append({**r, "recommendation":
                       f"recalibrate — {direction} by {abs(r['gap']) * 100:.0f}pt "
                       f"(n={r['n']})"})
        else:
            out.append({**r, "recommendation": "well_calibrated"})
    return out


def rolling_evaluation(window_trades: int = 50, joined: list = None) -> dict:
    """Calibration over the most recent `window_trades` matched, closed
    trades only (by open time) — supports drift detection over time rather
    than only judging against the full, ever-growing history. `min_n=1` is
    used for the reliability view here deliberately: this is a descriptive
    rolling snapshot for drift-watching, not a trust gate (the trust gate is
    `calibrated_probability_for`'s `min_n`, unaffected by this)."""
    joined = join_trades_with_confidence() if joined is None else joined
    ordered = sorted(joined, key=lambda j: _norm(j.get("opened", "")))
    recent = ordered[-window_trades:] if window_trades else ordered
    return {
        "n": len(recent),
        "window_trades": window_trades,
        "brier": brier(recent),
        "reliability": reliability(recent, min_n=1),
    }


def report() -> str:
    joined = join_trades_with_confidence()
    rel = reliability(joined)
    b = brier(joined)
    lines = [f"CONFIDENCE ENGINE CALIBRATION ({len(joined)} matched closed trades)",
             f"Brier score: {b}  (0=perfect, lower is better; 0.25 = coin flip)"
             if b is not None else "Brier score: n/a (no matched trades yet)"]
    if not joined:
        lines.append("No confidence_history.jsonl rows have matched a closed trade yet — "
                     "the Confidence Engine went live 2026-08-03 (Day 6); this report becomes "
                     "meaningful as trades close going forward. See RESEARCH_CONFIDENCE_ENGINE.md.")
    for r in rel:
        flag = "" if r["sufficient"] else f"  (thin, n<{MIN_N_FOR_CALIBRATION} — not yet trustworthy)"
        lines.append(f"{r['bucket']:7s}  predicted {r['predicted']*100:5.0f}%  "
                     f"realized {r['realized']*100:5.0f}%  n={r['n']:3d}  "
                     f"gap {r['gap']*100:+4.0f}pt{flag}")
    lines.append("Research/education only - not financial advice.")
    return "\n".join(lines)


def raw_vs_composite_comparison(min_n: int = MIN_N_FOR_CALIBRATION) -> dict:
    """Day 7 addendum (platform owner's explicit decision, 2026-08-04):
    "Build a raw-vs-composite calibration view — yes, but not yet.
    Design the architecture now; keep it inactive until enough live
    observations exist." This function IS the architecture — it compares
    `calibration.py`'s pre-existing raw-`sig.confidence` calibration
    against this module's Day 6 composite calibration, over the SAME
    matched closed trades — but returns `"active": False` and an explicit
    reason whenever fewer than `min_n` trades are matched on BOTH sides,
    exactly like every other insufficient-data gate in this codebase.

    Not wired into any dashboard or Telegram output yet — per the owner's
    instruction, it stays a callable research function until real
    forward-tested volume justifies surfacing it live. See
    RESEARCH_MARKET_MEMORY.md Sec.5 for the activation trigger."""
    try:
        from engine import calibration as raw_cal
        joined = join_trades_with_confidence()
        n = len(joined)
        if n < min_n:
            return {"active": False, "n": n, "min_n": min_n,
                   "reason": (f"only {n} matched trade(s) available; needs >= {min_n} "
                             "before a raw-vs-composite comparison is meaningful rather "
                             "than noise"),
                   "raw": None, "composite": None}
        composite_brier = brier(joined)
        composite_rel = reliability(joined, min_n=min_n)
        raw_brier = raw_cal.brier()
        raw_rel = raw_cal.reliability()
        improved = (raw_brier is not None and composite_brier is not None
                   and composite_brier < raw_brier)
        return {
            "active": True, "n": n, "min_n": min_n,
            "raw": {"brier": raw_brier, "reliability": raw_rel},
            "composite": {"brier": composite_brier, "reliability": composite_rel},
            "composite_improves_on_raw": improved,
        }
    except Exception as exc:  # noqa: BLE001
        return {"active": False, "n": 0, "min_n": min_n,
               "reason": f"comparison error: {exc}", "raw": None, "composite": None}


if __name__ == "__main__":
    print(report())
