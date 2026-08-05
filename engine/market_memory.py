"""Day 7 — Market Memory Engine (institutional memory, advisory-only).

Answers, for any candidate trade situation: "have we seen a materially
similar situation before, and what were the historical outcomes?" This
module does NOT generate trades and does NOT change any production
decision — see CONFIDENCE_ENGINE_SPECIFICATION.md's "advisory, never
gating" precedent (Day 6) and MARKET_MEMORY_SPECIFICATION.md for the full
design rationale.

STORAGE DESIGN — no new duplicate database. Every `MemoryRecord` is
ASSEMBLED ON DEMAND by joining `trades.json` (the journal) with
`regime_history.jsonl`, `confluence_history.jsonl`, and
`confidence_history.jsonl` via the UNIFIED TRADE ID (`journal.make_ref()`
/ `Trade.id`, mirrored on every trade as `regime_ref`/`confluence_ref`/
`confidence_ref` from Day 6/7 onward — see `engine/journal.py`). This
directly satisfies the mandate's "reuse existing journals and histories...
avoid duplicate storage... avoid redundant databases."

LOOK-AHEAD PROTECTION — every similarity/historical-context function takes
an explicit `as_of` timestamp and only considers candidate records whose
trade CLOSED strictly before `as_of` (not just opened before — an open
trade's outcome is not yet knowable, so using it would leak future
information into a "historical" comparison). See `_look_ahead_safe()` and
`tests/test_market_memory_lookahead.py`.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import store  # noqa: E402
from engine import regime_history as rh  # noqa: E402
from engine import confluence_history as cfh  # noqa: E402
from engine import confidence_history as cfdh  # noqa: E402

VERSION = "1.0.0"
SCHEMA_VERSION = 1

# --- session derivation --------------------------------------------------------
# Deliberately mirrors engine/ict.py's exact hour boundaries rather than
# inventing new ones or adding a new stored field to Trade — session is a
# pure function of the already-persisted `opened` timestamp, so no new
# storage is needed to recover it later (see module docstring's storage
# design principle).
def _session_from_hour(hour: int) -> str:
    if 7 <= hour < 10:
        return "London KZ"
    if 12 <= hour < 15:
        return "New York KZ"
    if 0 <= hour < 6:
        return "Asian"
    return "off-session"


def _parse_ts(ts: str):
    try:
        return datetime.fromisoformat(str(ts).replace(" ", "T"))
    except Exception:  # noqa: BLE001
        return None


# --- Phase 2: MemoryRecord ------------------------------------------------------

@dataclass
class MemoryRecord:
    """Standardized memory record — one per journal trade. Every field
    documented here; see MARKET_MEMORY_SPECIFICATION.md Sec.3 for the
    narrative version."""
    trade_id: str                  # the unified trade ID (Trade.id)
    symbol: str
    direction: str
    opened: str
    closed: str
    status: str                    # win | loss | scratch | open | expired
    result_r: float
    regime: dict                   # {primary, confidence, quality_score, transition_label, source}
    strategy: str                  # config.regime_strategy at assembly time — one production
                                    # strategy platform-wide today (Day 4 precedent), not per-trade
    confluence_summary: dict       # {score, final_tier, agree, disagree, quality_score, source}
    confidence_assessment: dict    # {overall_confidence, tier, is_calibrated, source} or {} if never assessed
    risk_profile: dict             # {guard_action, guard_penalty, guard_headwind}
    portfolio_context: dict        # {allow, would_block, category, heat, source} — best-effort,
                                    # recovered from the confidence assessment's portfolio_status
                                    # sub-object (Day 6), not separately persisted (see Sec.6 limitation)
    session: str                   # derived from `opened`'s hour (see _session_from_hour)
    news_context: dict             # {signal, strength, delta} — already on Trade since Day 1-2
    outcome: dict                  # {status, result_r, closed}
    post_trade_review: dict        # {} today — placeholder for a future self-review integration
                                    # (see Sec.6 "Known limitations"), not yet implemented
    data_completeness: dict        # {regime, confluence, confidence} -> "matched"|"trade_row_only"|"missing"
    version: dict = field(default_factory=lambda: {"market_memory": VERSION, "schema": SCHEMA_VERSION})

    def as_dict(self) -> dict:
        return asdict(self)


def _strategy_default() -> str:
    try:
        from engine import config
        return str(getattr(config.load(), "regime_strategy", "ict_smc_mast") or "ict_smc_mast")
    except Exception:  # noqa: BLE001
        return "ict_smc_mast"


def build_memory_record(trade_row: dict, regime_row: dict = None,
                        confluence_row: dict = None, confidence_row: dict = None,
                        strategy: str = None) -> MemoryRecord:
    """Assemble one MemoryRecord from a trades.json row plus (optionally,
    pre-fetched) history rows. When a history row is not supplied, this
    looks it up via the trade's own `*_ref` field — falling back to the
    trade row's own already-persisted summary fields (e.g.
    `confluence_score`/`confluence_agree`, `regime_trend`/`regime_vol`)
    when no ref exists or the referenced row can't be found (pre-Day-6/7
    trades). Never raises."""
    try:
        tid = trade_row.get("id", "")
        sym = trade_row.get("symbol", "XAUUSD")
        completeness = {"regime": "missing", "confluence": "missing", "confidence": "missing"}

        # --- regime ---
        r_ref = trade_row.get("regime_ref", "")
        rrow = regime_row if regime_row is not None else (rh.find_by_ref(r_ref) if r_ref else None)
        if rrow:
            regime = {"primary": rrow.get("primary"), "confidence": rrow.get("confidence"),
                     "quality_score": rrow.get("quality_score"),
                     "transition_label": rrow.get("transition_label"), "source": "regime_history"}
            completeness["regime"] = "matched"
        else:
            regime = {"primary": None, "trend": trade_row.get("regime_trend", ""),
                     "vol": trade_row.get("regime_vol", ""), "source": "trade_row"}
            completeness["regime"] = "trade_row_only" if (trade_row.get("regime_trend")
                                                          or trade_row.get("regime_vol")) else "missing"

        # --- confluence ---
        c_ref = trade_row.get("confluence_ref", "")
        crow = confluence_row if confluence_row is not None else (cfh.find_by_ref(c_ref) if c_ref else None)
        if crow:
            confluence_summary = {"score": crow.get("score"), "final_tier": crow.get("final_tier"),
                                  "agree": crow.get("agree", []), "disagree": crow.get("disagree", []),
                                  "quality_score": crow.get("quality_score"), "source": "confluence_history"}
            completeness["confluence"] = "matched"
        else:
            cs = trade_row.get("confluence_score", -1)
            confluence_summary = {"score": cs if cs != -1 else None,
                                  "agree_count": trade_row.get("confluence_agree", 0),
                                  "source": "trade_row"}
            completeness["confluence"] = "trade_row_only" if cs != -1 else "missing"

        # --- confidence ---
        cf_ref = trade_row.get("confidence_ref", "")
        cfrow = confidence_row if confidence_row is not None else (cfdh.find_by_ref(cf_ref) if cf_ref else None)
        if cfrow:
            confidence_assessment = {"overall_confidence": cfrow.get("overall_confidence"),
                                     "tier": cfrow.get("tier"), "is_calibrated": cfrow.get("is_calibrated"),
                                     "source": "confidence_history"}
            portfolio_context = dict(cfrow.get("portfolio_status") or {}, source="confidence_history")
            completeness["confidence"] = "matched"
        else:
            confidence_assessment = {}
            portfolio_context = {}
            completeness["confidence"] = "missing"

        opened = trade_row.get("opened", "")
        hour = None
        ts = _parse_ts(opened)
        if ts is not None:
            hour = ts.hour
        session = _session_from_hour(hour) if hour is not None else "unknown"

        return MemoryRecord(
            trade_id=tid, symbol=sym, direction=trade_row.get("direction", ""),
            opened=opened, closed=trade_row.get("closed", ""),
            status=trade_row.get("status", "open"), result_r=float(trade_row.get("result_r", 0) or 0),
            regime=regime, strategy=strategy or _strategy_default(),
            confluence_summary=confluence_summary, confidence_assessment=confidence_assessment,
            risk_profile={"guard_action": trade_row.get("guard_action", ""),
                         "guard_penalty": trade_row.get("guard_penalty", 0),
                         "guard_headwind": trade_row.get("guard_headwind", "")},
            portfolio_context=portfolio_context, session=session,
            news_context={"signal": trade_row.get("news_signal", ""),
                         "strength": trade_row.get("news_strength", ""),
                         "delta": trade_row.get("news_delta", 0)},
            outcome={"status": trade_row.get("status", "open"),
                    "result_r": float(trade_row.get("result_r", 0) or 0),
                    "closed": trade_row.get("closed", "")},
            post_trade_review={},
            data_completeness=completeness,
        )
    except Exception as exc:  # noqa: BLE001
        return MemoryRecord(
            trade_id=trade_row.get("id", "") if isinstance(trade_row, dict) else "",
            symbol=trade_row.get("symbol", "") if isinstance(trade_row, dict) else "",
            direction="", opened="", closed="", status="error", result_r=0.0,
            regime={}, strategy=_strategy_default(), confluence_summary={},
            confidence_assessment={}, risk_profile={}, portfolio_context={}, session="unknown",
            news_context={}, outcome={}, post_trade_review={},
            data_completeness={"error": str(exc)},
        )


def build_memory_records(trades_rows: list = None) -> list:
    """Bulk-assemble MemoryRecords for every trade in trades.json (or a
    supplied list). Sorted by `opened` ascending — the ordering
    similarity/context functions rely on for look-ahead filtering."""
    trades_rows = trades_rows if trades_rows is not None else store.load_array(ROOT / "trades.json")
    recs = [build_memory_record(t) for t in trades_rows]
    recs.sort(key=lambda r: str(r.opened or ""))
    return recs


# --- Phase 3: Similarity framework ----------------------------------------------
# Configurable, disclosed, NOT statistically fitted — same convention as
# every other cross-day formula in this codebase (Day 4's transition-risk
# weights, Day 5's quality-score weights, Day 6's confidence-composite
# weights). Each dimension contributes its weight only when BOTH records
# have a known (non-"unknown"/None) value for it — a dimension neither side
# has data for is excluded from both the numerator and the denominator, so
# missing data neither inflates nor unfairly punishes the score (data
# completeness is reported separately, see memory_quality()).
DEFAULT_SIMILARITY_WEIGHTS = {
    "regime_primary": 0.25,
    "confluence_profile": 0.20,
    "session": 0.15,
    "volatility": 0.15,
    "macro_alignment": 0.10,
    "portfolio_state": 0.10,
    "direction": 0.05,
}


def _confluence_profile(confluence_summary: dict) -> frozenset:
    """Coarse profile: which independence CATEGORIES (Day 5's
    SOURCE_REGISTRY classification) are represented among the agreeing
    sources — reused directly, not recomputed, so this stays consistent
    with confluence_analysis.py's own taxonomy."""
    agree = confluence_summary.get("agree") or []
    if not agree:
        return frozenset()
    try:
        from engine import confluence_analysis as cfa
        cats = set()
        for label in agree:
            key = cfa._match_source(label)
            reg = cfa.SOURCE_REGISTRY.get(key)
            if reg:
                cats.add(reg["category"])
        return frozenset(cats)
    except Exception:  # noqa: BLE001
        return frozenset()


def _macro_alignment(confluence_summary: dict):
    agree = confluence_summary.get("agree") or []
    disagree = confluence_summary.get("disagree") or []
    if any("macro" in a for a in agree):
        return True
    if any("macro" in d for d in disagree):
        return False
    return None


def _portfolio_bucket(portfolio_context: dict):
    heat = portfolio_context.get("heat")
    if heat is None:
        return None
    try:
        heat = float(heat)
    except Exception:  # noqa: BLE001
        return None
    return "low" if heat < 0.3 else "medium" if heat < 0.7 else "high"


def extract_features(rec: MemoryRecord) -> dict:
    """The comparison vector used by similarity(). Every dimension is
    documented in MARKET_MEMORY_SPECIFICATION.md Sec.4 alongside the
    rationale for including it."""
    regime = rec.regime or {}
    vol = regime.get("vol")  # only present on the trade_row-only fallback shape
    return {
        "regime_primary": regime.get("primary") or (regime.get("trend") or None),
        "confluence_profile": _confluence_profile(rec.confluence_summary or {}),
        "session": rec.session if rec.session != "unknown" else None,
        "volatility": vol or None,
        "macro_alignment": _macro_alignment(rec.confluence_summary or {}),
        "portfolio_state": _portfolio_bucket(rec.portfolio_context or {}),
        "direction": rec.direction or None,
    }


def query_features_from_live(mkt_regime: dict = None, cr=None, session: str = None,
                             portfolio_verdict: dict = None, direction: str = None) -> dict:
    """Builds the same feature-vector shape extract_features() produces
    for a MemoryRecord, but directly from a LIVE candidate's already-
    computed objects (mkt_regime dict, ConfluenceRead, portfolio_verdict
    dict) — this is the query side of find_similar()/historical_context()
    for a trade that hasn't happened yet, so there is no MemoryRecord to
    extract from. Reuses the exact same helper functions as
    extract_features() so the two sides of every comparison are computed
    identically. Never raises."""
    try:
        mkt_regime = mkt_regime or {}
        confluence_summary = {}
        if cr is not None:
            confluence_summary = {"agree": list(getattr(cr, "agree", []) or []),
                                  "disagree": list(getattr(cr, "disagree", []) or [])}
        portfolio_context = {}
        if portfolio_verdict is not None:
            heat = (portfolio_verdict.get("detail", {}) or {}).get("portfolio_heat")
            portfolio_context = {"heat": heat}
        return {
            "regime_primary": mkt_regime.get("primary") or None,
            "confluence_profile": _confluence_profile(confluence_summary),
            "session": session or None,
            "volatility": mkt_regime.get("vol_trend") or None,
            "macro_alignment": _macro_alignment(confluence_summary),
            "portfolio_state": _portfolio_bucket(portfolio_context),
            "direction": direction or None,
        }
    except Exception:  # noqa: BLE001
        return {}


def similarity(features_a: dict, features_b: dict, weights: dict = None) -> float:
    """0.0-1.0 similarity between two feature vectors (see
    extract_features()). Never raises; returns 0.0 on any error or when no
    dimension is comparable on both sides."""
    try:
        weights = weights or DEFAULT_SIMILARITY_WEIGHTS
        total_weight = 0.0
        score = 0.0
        for dim, w in weights.items():
            a = features_a.get(dim)
            b = features_b.get(dim)
            if a in (None, "", frozenset()) or b in (None, "", frozenset()):
                continue
            total_weight += w
            if dim == "confluence_profile":
                # Jaccard overlap for the category-set dimension
                union = a | b
                inter = a & b
                score += w * (len(inter) / len(union) if union else 0.0)
            else:
                score += w if a == b else 0.0
        return round(score / total_weight, 4) if total_weight > 0 else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


# --- Look-ahead protection --------------------------------------------------------

def _look_ahead_safe(rec: MemoryRecord, as_of) -> bool:
    """A candidate is usable for a historical comparison ONLY if its
    outcome was already knowable at `as_of` — i.e. it is fully closed
    (status in win/loss/scratch; an `open` or `expired`-without-settlement
    trade has no realized outcome to compare against) AND its `closed`
    timestamp is strictly before `as_of`. This is the single choke point
    every similarity/context function in this module routes through — see
    tests/test_market_memory_lookahead.py for the dedicated regression
    coverage."""
    if rec.status not in ("win", "loss", "scratch"):
        return False
    closed_ts = _parse_ts(rec.closed)
    as_of_ts = as_of if isinstance(as_of, datetime) else _parse_ts(as_of)
    if closed_ts is None or as_of_ts is None:
        return False
    return closed_ts < as_of_ts


def find_similar(query_features: dict, as_of, records: list = None, top_k: int = 20,
                 min_similarity: float = 0.0, weights: dict = None) -> list:
    """Top-K historically comparable, look-ahead-safe MemoryRecords for a
    query situation. Returns a list of {record, similarity} dicts, sorted
    by similarity descending. Never raises."""
    try:
        records = records if records is not None else build_memory_records()
        candidates = [r for r in records if _look_ahead_safe(r, as_of)]
        scored = []
        for r in candidates:
            s = similarity(query_features, extract_features(r), weights)
            if s >= min_similarity:
                scored.append({"record": r, "similarity": s})
        scored.sort(key=lambda x: -x["similarity"])
        return scored[:top_k]
    except Exception:  # noqa: BLE001
        return []


# --- Phase 4: Historical context + memory quality -----------------------------

MIN_N_FOR_TRUST = 30    # matches Day 5/6's precedent for "statistically trustworthy"
MIN_N_FOR_CONTEXT = 5   # a much lower bar for "worth mentioning at all" — historical
                        # context is explicitly DESCRIPTIVE, never a trust claim, below
                        # MIN_N_FOR_TRUST (see sufficient_sample vs rich_evidence below)


def memory_quality(matches: list) -> dict:
    """Quality indicators for a set of find_similar() matches — separate
    from the aggregate performance numbers themselves, per the mandate's
    "distinguish between rich historical evidence and sparse evidence."
    Never raises."""
    try:
        n = len(matches)
        if n == 0:
            return {"sample_size": 0, "avg_similarity": 0.0, "data_completeness_rate": 0.0,
                    "confidence_label": "insufficient", "limitations": ["no comparable historical trades found"]}
        avg_sim = round(sum(m["similarity"] for m in matches) / n, 3)
        complete = sum(1 for m in matches
                      if all(v == "matched" for v in m["record"].data_completeness.values()))
        completeness_rate = round(complete / n, 3)
        limitations = []
        if n < MIN_N_FOR_CONTEXT:
            label = "insufficient"
            limitations.append(f"sample size ({n}) is below the minimum ({MIN_N_FOR_CONTEXT}) "
                               "to describe even directionally")
        elif n < MIN_N_FOR_TRUST:
            label = "sparse"
            limitations.append(f"sample size ({n}) is below the statistical trust bar "
                               f"({MIN_N_FOR_TRUST}) — descriptive only, not confirmatory")
        elif avg_sim < 0.5:
            label = "moderate"
            limitations.append("average similarity is moderate — comparisons share some, "
                               "not most, dimensions with the query situation")
        else:
            label = "rich"
        if completeness_rate < 0.5:
            limitations.append(f"only {completeness_rate*100:.0f}% of matches have full "
                               "regime/confluence/confidence history — the rest fall back to "
                               "trade-row-only summary fields")
        return {"sample_size": n, "avg_similarity": avg_sim,
               "data_completeness_rate": completeness_rate,
               "confidence_label": label, "limitations": limitations}
    except Exception as exc:  # noqa: BLE001
        return {"sample_size": 0, "avg_similarity": 0.0, "data_completeness_rate": 0.0,
               "confidence_label": "insufficient", "limitations": [f"memory_quality error: {exc}"]}


def historical_context(query_features: dict, as_of, records: list = None, top_k: int = 20,
                       weights: dict = None) -> dict:
    """The Phase 4 advisory report: comparable historical situations,
    sample size, aggregate performance, strengths/weaknesses, and explicit
    uncertainty when the sample is too small — never infers statistical
    confidence it doesn't have. Never raises, never influences any
    production decision (purely a read/report function)."""
    try:
        matches = find_similar(query_features, as_of, records=records, top_k=top_k, weights=weights)
        quality = memory_quality(matches)
        n = quality["sample_size"]
        if n < MIN_N_FOR_CONTEXT:
            return {
                "comparable_count": n, "sufficient_sample": False,
                "quality": quality,
                "note": (f"Only {n} comparable historical situation(s) found — too few to "
                        "report aggregate performance. This is stated explicitly rather "
                        "than inferring a trend from a handful of trades."),
                "aggregate": None, "strengths": [], "weaknesses": [],
            }
        outcomes = [m["record"].outcome for m in matches]
        wins = sum(1 for o in outcomes if o.get("status") == "win")
        results = [float(o.get("result_r", 0) or 0) for o in outcomes]
        aggregate = {
            "n": n, "win_rate": round(wins / n, 3),
            "avg_result_r": round(sum(results) / n, 3) if results else 0.0,
            "sufficient_for_trust": n >= MIN_N_FOR_TRUST,
        }
        # Simple, disclosed sub-group comparison (session split) — kept
        # intentionally minimal to avoid overfitting a small sample with
        # many simultaneous cuts; a richer breakdown belongs in the
        # performance-analytics functions below, which operate over the
        # FULL history rather than one query's top-K matches.
        by_session = {}
        for m in matches:
            sess = m["record"].session
            by_session.setdefault(sess, []).append(m["record"])
        strengths, weaknesses = [], []
        for sess, recs in by_session.items():
            if len(recs) < 3:
                continue
            wr = sum(1 for r in recs if r.status == "win") / len(recs)
            if wr >= 0.6:
                strengths.append(f"{sess}: {wr*100:.0f}% win rate across {len(recs)} comparable trades")
            elif wr <= 0.35:
                weaknesses.append(f"{sess}: {wr*100:.0f}% win rate across {len(recs)} comparable trades")
        return {
            "comparable_count": n, "sufficient_sample": True, "quality": quality,
            "note": ("Descriptive only — see quality.confidence_label; not a statistically "
                    "confirmed prediction of this trade's outcome.") if n < MIN_N_FOR_TRUST else "",
            "aggregate": aggregate, "strengths": strengths, "weaknesses": weaknesses,
        }
    except Exception as exc:  # noqa: BLE001
        return {"comparable_count": 0, "sufficient_sample": False,
               "quality": {"confidence_label": "insufficient", "limitations": [f"error: {exc}"]},
               "note": "historical_context() encountered an error", "aggregate": None,
               "strengths": [], "weaknesses": []}


# --- Performance analytics (operate over the FULL history, not one query) ------

def _bucket_stats(records: list, key_fn) -> list:
    groups = {}
    for r in records:
        if r.status not in ("win", "loss", "scratch"):
            continue
        k = key_fn(r)
        if k is None:
            continue
        groups.setdefault(k, []).append(r)
    out = []
    for k, recs in groups.items():
        n = len(recs)
        wins = sum(1 for r in recs if r.status == "win")
        results = [r.result_r for r in recs]
        out.append({
            "key": k, "n": n, "win_rate": round(wins / n, 3) if n else 0.0,
            "avg_result_r": round(sum(results) / n, 3) if n else 0.0,
            "sufficient": n >= MIN_N_FOR_TRUST,
        })
    out.sort(key=lambda x: -x["n"])
    return out


def performance_by_strategy_regime(records: list = None) -> list:
    """Which strategy performs best under which regime — grouped by
    (strategy, regime_primary). Each bucket explicitly reports whether it
    meets MIN_N_FOR_TRUST; never draws a conclusion below that bar."""
    records = records if records is not None else build_memory_records()
    return _bucket_stats(records, lambda r: (r.strategy, (r.regime or {}).get("primary")
                                             or (r.regime or {}).get("trend") or "unknown"))


def performance_by_confluence_profile(records: list = None) -> list:
    """Which confluence profiles (category-set) perform consistently."""
    records = records if records is not None else build_memory_records()
    return _bucket_stats(records, lambda r: _confluence_profile(r.confluence_summary or {}) or None)


def performance_by_session(records: list = None) -> list:
    """Which sessions historically under/over-perform."""
    records = records if records is not None else build_memory_records()
    return _bucket_stats(records, lambda r: r.session if r.session != "unknown" else None)


def risk_adjusted_by_combo(records: list = None) -> list:
    """Regime x session combinations, ranked by a simple risk-adjusted
    metric (avg_result_r / stdev(result_r), only computed where n >=
    MIN_N_FOR_TRUST — a Sharpe-like ratio is meaningless on a handful of
    trades). Combos below the bar are still returned (transparency), just
    with `risk_adjusted=None` and `sufficient=False`."""
    records = records if records is not None else build_memory_records()
    groups = {}
    for r in records:
        if r.status not in ("win", "loss", "scratch"):
            continue
        regime_key = (r.regime or {}).get("primary") or (r.regime or {}).get("trend") or "unknown"
        k = (regime_key, r.session)
        groups.setdefault(k, []).append(r.result_r)
    out = []
    for k, results in groups.items():
        n = len(results)
        avg = sum(results) / n if n else 0.0
        if n >= MIN_N_FOR_TRUST:
            mean = avg
            var = sum((x - mean) ** 2 for x in results) / n
            stdev = var ** 0.5
            risk_adjusted = round(avg / stdev, 3) if stdev > 1e-9 else None
        else:
            risk_adjusted = None
        out.append({"regime": k[0], "session": k[1], "n": n, "avg_result_r": round(avg, 3),
                   "risk_adjusted": risk_adjusted, "sufficient": n >= MIN_N_FOR_TRUST})
    out.sort(key=lambda x: (-(x["risk_adjusted"] or -999), -x["n"]))
    return out
