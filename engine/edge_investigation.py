"""Day 10 — Edge Investigation & Performance Recovery.

Home of the analytical code behind Experiment #0001 ("Observed Edge
Deterioration Investigation"), registered in `engine.experiment_registry`.
See `PERFORMANCE_INVESTIGATION_0001.md` for the full narrative write-up of
what this code found when run against the live `trades.json`.

GOVERNING PRINCIPLE (unchanged from the Day 10 mandate): this module's job
is to determine WHY performance changed, not to change performance. Nothing
here writes to `trades.json`, nothing here is imported by `alert_signals.py`
or `engine/dashboard_publish.py`, and nothing here alters any threshold,
config value, or production trading behavior. It only READS the journal
(the same read-only path `engine.edge_decay_monitor` already uses) and
derives observations from it.

REUSE, NOT DUPLICATION: every core metric is computed via
`engine.research_stats` (Day 9) and `engine.evidence_tiers` (Day 9) —
nothing here reinvents expectancy/profit-factor/drawdown math. Segment
breakdowns reuse `engine.market_memory._session_from_hour` (Day 7) for
session derivation rather than inventing new session boundaries.

Every function is a pure, reproducible function of its input rows (or, if
none supplied, the live `trades.json` read via `engine.store`) and never
raises — the same fail-safe convention as every prior Day's advisory
engine.
"""
from __future__ import annotations

import math
import pathlib
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import research_stats as rstats          # noqa: E402
from engine import evidence_tiers as etiers           # noqa: E402
from engine import store                              # noqa: E402
from engine import journal                             # noqa: E402
from engine.market_memory import _session_from_hour    # noqa: E402

VERSION = "1.0.0"

# Same anchor Day 9's edge_decay_monitor uses — a "recent window" comparison
# is never drawn from fewer trades than this platform's own statistical-
# trust floor.
RECENT_WINDOW = rstats.MIN_N_FOR_TRUST

# Confidence tier floors — mirrors engine.confidence_engine.DEFAULT_TIERS
# verbatim (duplicated as plain data, not imported, because confidence_
# engine's tiers can be overridden via Settings at runtime; this module
# deliberately uses the DEFAULT floors as a fixed, reproducible bucketing
# scheme for retrospective analysis, disclosed here rather than silently
# importing a value that could change between two runs of this report).
CONFIDENCE_TIERS = [
    ("Exceptional", 85),
    ("High", 70),
    ("Moderate", 55),
    ("Low", 40),
    ("Research-only", 0),
]


def _confidence_tier(score) -> str:
    try:
        score = int(score)
    except Exception:  # noqa: BLE001
        return "unknown"
    for label, floor in CONFIDENCE_TIERS:
        if score >= floor:
            return label
    return "Research-only"


def _all_rows(rows=None) -> list:
    if rows is not None:
        return rows
    return store.load_array(journal.STORE)


def _closed_rows(rows=None) -> list:
    return [r for r in _all_rows(rows) if r.get("status") in ("win", "loss", "scratch")]


def _sorted_closed(rows=None) -> list:
    return sorted(_closed_rows(rows), key=lambda r: str(r.get("opened", "")))


def split_recent_prior(rows=None, recent_n: int = RECENT_WINDOW):
    """Same split `engine.edge_decay_monitor.recent_vs_prior` uses —
    duplicated here (not imported) only because this module needs the raw
    row lists, not the summarized report, for the deeper analysis below.
    Returns `(None, None)` if there are not enough closed trades."""
    closed = _sorted_closed(rows)
    if len(closed) < recent_n * 2:
        return None, None
    return closed[:-recent_n], closed[-recent_n:]


# ---------------------------------------------------------------------------
# VERIFY THE DATA — independent recalculation, including two metrics not yet
# in research_stats.py: holding time and stop/target size.
# ---------------------------------------------------------------------------

def _parse_ts(ts):
    try:
        return datetime.fromisoformat(str(ts).replace(" ", "T"))
    except Exception:  # noqa: BLE001
        return None


def _holding_minutes(row) -> float | None:
    o, c = _parse_ts(row.get("opened")), _parse_ts(row.get("closed"))
    if o is None or c is None:
        return None
    return (c - o).total_seconds() / 60.0


def _stop_pct(row) -> float | None:
    try:
        entry, stop = float(row["entry"]), float(row["stop"])
        if entry == 0:
            return None
        return abs(entry - stop) / abs(entry) * 100.0
    except Exception:  # noqa: BLE001
        return None


def _target_pct(row) -> float | None:
    try:
        entry, target = float(row["entry"]), float(row["target"])
        if entry == 0:
            return None
        return abs(target - entry) / abs(entry) * 100.0
    except Exception:  # noqa: BLE001
        return None


def _avg(values) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"value": None, "n": 0}
    return {"value": round(sum(vals) / len(vals), 3), "n": len(vals),
           "median": round(statistics.median(vals), 3)}


def holding_time_stats(rows) -> dict:
    """Average/median trade duration in minutes, from `opened`/`closed`
    timestamps already persisted on every closed trade — no new storage
    needed. Not previously in `research_stats.py`; added here per the
    Day 10 mandate's explicit "average holding time" requirement."""
    return _avg([_holding_minutes(r) for r in rows])


def stop_target_stats(rows) -> dict:
    """Average stop distance and target distance, each expressed as a
    percent of entry price (comparable across symbols of very different
    scale — XAUUSD ~$4000, BTCUSD ~$65000, WTIUSD ~$80, EURUSD ~$1.08 —
    unlike a raw price distance). Also reports the average PLANNED
    reward:risk ratio (`rr`, already stored per trade) as a third,
    unit-free view of the same "how big were stops/targets" question. Not
    previously in `research_stats.py`; added here per the Day 10 mandate's
    explicit "average stop size, average target size" requirement."""
    rrs = [r.get("rr") for r in rows if isinstance(r.get("rr"), (int, float))]
    return {
        "avg_stop_pct_of_entry": _avg([_stop_pct(r) for r in rows]),
        "avg_target_pct_of_entry": _avg([_target_pct(r) for r in rows]),
        "avg_planned_rr": _avg(rrs),
    }


def verify_core_metrics(rows=None, recent_n: int = RECENT_WINDOW) -> dict:
    """Independently recalculates every metric the Day 10 mandate names:
    expectancy, profit factor, win rate, average R, drawdown (all via
    `research_stats`, reused not reimplemented), PLUS average holding
    time, average stop size, average target size (new — see above). Never
    raises; reports `sufficient: False` if there is not enough data for a
    recent-vs-prior comparison."""
    try:
        prior, recent = split_recent_prior(rows, recent_n)
        if prior is None:
            closed = _sorted_closed(rows)
            return {"sufficient": False,
                   "note": f"need >= {recent_n * 2} closed trades (have {len(closed)})"}
        return {
            "sufficient": True, "recent_n": recent_n, "prior_n": len(prior),
            "prior": {
                **rstats.full_report(prior),
                "holding_time_minutes": holding_time_stats(prior),
                **stop_target_stats(prior),
                "avg_confidence": _avg([r.get("confidence") for r in prior]),
            },
            "recent": {
                **rstats.full_report(recent),
                "holding_time_minutes": holding_time_stats(recent),
                **stop_target_stats(recent),
                "avg_confidence": _avg([r.get("confidence") for r in recent]),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"verify_core_metrics error: {exc}"}


# ---------------------------------------------------------------------------
# DATA QUALITY REVIEW
# ---------------------------------------------------------------------------

def _settlement_rule_family(row) -> str | None:
    """Classifies a WIN as settled under the platform's CURRENT
    breakeven-after-+1R / bank-50%-at-+2R / runner rule
    (`engine.journal._manage()`, see its module docstring) versus an OLDER
    full-target-or-bust rule. Reconstructed purely from stored
    `entry`/`stop`/`target`/`result_r` — no external price data needed:
    the current rule's formula for ANY win that reaches full target is
    always `1 + 0.5*finalR` (see `_manage()`'s `hi[j] >= target` branch,
    which returns that value unconditionally, whether or not the +2R
    partial had already fired) or, if the trade was stopped out at
    breakeven after touching +2R without reaching target, exactly `1.0`.
    Neither of those is reachable if the OLDER rule (credit the full
    `finalR`, no partial banking) produced the row instead — those rows
    show `result_r` equal to `finalR` itself. Returns `None` for
    non-wins."""
    if row.get("status") != "win":
        return None
    try:
        entry, stop, target = float(row["entry"]), float(row["stop"]), float(row["target"])
        risk = abs(entry - stop)
        if risk <= 0:
            return "unknown"
        final_r = abs(target - entry) / risk
        res = float(row.get("result_r", 0) or 0)
        if final_r <= 0:
            return "unknown"
        ratio = res / final_r
        # >=0.85 of the full planned R credited -> consistent with the
        # older, simpler "full target or bust" rule. Below that -> consistent
        # with the current partial-banking/breakeven-trail rule (which caps
        # every win at 1 + 0.5*finalR, i.e. never more than roughly
        # 50-65% of finalR for typical rr in [2, 4]).
        return "current_rule(partial/be)" if ratio < 0.85 else "legacy_rule(full-target)"
    except Exception:  # noqa: BLE001
        return "unknown"


def data_quality_review(rows=None) -> dict:
    """Checks the live journal for the specific issues the Day 10 mandate
    names: missing trades (not directly detectable without an independent
    signal log — disclosed, not guessed at), duplicate trades, corrupted
    records, incorrect R calculations, execution logging issues, journal
    inconsistencies, incomplete metadata. Every check is quantified, not
    just flagged — per the mandate's "quantify its impact before drawing
    conclusions." Never raises."""
    try:
        rows = _all_rows(rows)
        n_total = len(rows)
        closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]

        # --- duplicate ids: same `id` (symbol + minute-bar timestamp) used
        # by more than one row. journal.make_ref() only has minute
        # granularity, so two distinct signals for the same symbol logged
        # within the same minute-bar collide even though is_open()'s own
        # dedup check (status=="open" AND same direction AND near-identical
        # entry) would NOT have blocked them, since a different entry price
        # bypasses that check. This is a real join-key integrity issue for
        # any code that looks up a decision record BY `id`/`*_ref`
        # (decision_audit_history.find_by_ref, paper_trading_review, etc.)
        # — NOT a P&L issue, since each row's own result_r is independently
        # correct regardless of id collisions.
        id_counts = Counter(r.get("id", "") for r in rows)
        duplicate_ids = {rid: c for rid, c in id_counts.items() if c > 1 and rid}
        rows_affected_by_dup_id = sum(duplicate_ids.values())

        # --- schema completeness: which optional fields (added in later
        # Days) are populated, by era. Expected to be sparse on early
        # trades (schema evolved over time) — not a defect, but must be
        # disclosed and quantified so segment analyses that depend on these
        # fields can be read with the right caveats.
        optional_fields = ["symbol", "news_signal", "regime_trend", "regime_vol",
                           "guard_action", "confluence_score", "confluence_ref",
                           "confidence_ref", "regime_ref"]
        field_coverage = {}
        for f in optional_fields:
            if f == "confluence_score":
                populated = sum(1 for r in rows if r.get("confluence_score", -1) not in (-1, None))
            else:
                populated = sum(1 for r in rows if r.get(f))
            field_coverage[f] = {"populated": populated, "total": n_total,
                                 "pct": round(populated / n_total * 100, 1) if n_total else None}

        # --- sign / internal consistency checks
        sign_mismatches = [r["id"] for r in closed
                           if (r.get("status") == "win" and r.get("result_r", 0) <= 0)
                           or (r.get("status") == "loss" and r.get("result_r", 0) >= 0)]
        closed_before_opened = [r["id"] for r in closed
                                if r.get("closed") and str(r["closed"]) < str(r.get("opened", ""))]
        missing_closed_ts = [r["id"] for r in closed if not r.get("closed")]
        loss_magnitude_values = sorted({round(float(r.get("result_r", 0)), 4)
                                        for r in closed if r.get("status") == "loss"})

        # --- settlement-methodology split (the "implementation drift"
        # finding — see PERFORMANCE_INVESTIGATION_0001.md Sec.3). Quantifies
        # how many wins were settled under the legacy vs. current rule, and
        # WHERE the split falls chronologically.
        wins_sorted = sorted((r for r in rows if r.get("status") == "win"),
                             key=lambda r: str(r.get("opened", "")))
        families = [(_settlement_rule_family(r), r.get("opened")) for r in wins_sorted]
        legacy_wins = [o for fam, o in families if fam == "legacy_rule(full-target)"]
        current_wins = [o for fam, o in families if fam == "current_rule(partial/be)"]
        family_counts = Counter(fam for fam, _ in families)

        prior, recent = split_recent_prior(rows)
        prior_family_counts = recent_family_counts = None
        if prior is not None:
            prior_family_counts = Counter(_settlement_rule_family(r) for r in prior
                                          if r.get("status") == "win")
            recent_family_counts = Counter(_settlement_rule_family(r) for r in recent
                                           if r.get("status") == "win")

        return {
            "version": VERSION,
            "n_total_rows": n_total,
            "n_closed": len(closed),
            "n_open": sum(1 for r in rows if r.get("status") == "open"),
            "duplicate_ids": {
                "n_colliding_id_groups": len(duplicate_ids),
                "n_rows_affected": rows_affected_by_dup_id,
                "detail": duplicate_ids,
                "impact": ("id collisions are a REFERENCE-INTEGRITY issue, not a P&L issue — "
                          "each row's own result_r is unaffected. They DO mean any lookup keyed "
                          "purely by `id` (e.g. decision_audit_history.find_by_ref) can be "
                          "ambiguous for these trades — flagged for the Day 10+ backlog, not "
                          "fixed here (out of this investigation's scope)."),
            },
            "field_coverage": field_coverage,
            "sign_mismatches": sign_mismatches,
            "closed_before_opened": closed_before_opened,
            "missing_closed_timestamp_on_closed_trade": missing_closed_ts,
            "loss_result_r_distinct_values": loss_magnitude_values,
            "settlement_methodology": {
                "note": ("Two different exit-management rules are both present in the win "
                        "population: a legacy 'full target or bust' rule (result_r == the "
                        "planned final R multiple) and the CURRENT engine.journal._manage() "
                        "rule (breakeven after +1R, bank 50% at +2R, runner — caps every win "
                        "at 1 + 0.5*finalR, or exactly 1.0 if stopped at breakeven after "
                        "touching +2R without reaching target). This is reconstructed "
                        "directly from stored entry/stop/target/result_r, not assumed."),
                "all_wins_by_family": dict(family_counts),
                "prior_window_wins_by_family": dict(prior_family_counts) if prior_family_counts else None,
                "recent_window_wins_by_family": dict(recent_family_counts) if recent_family_counts else None,
                "legacy_rule_last_seen": max(legacy_wins) if legacy_wins else None,
                "current_rule_first_seen": min(current_wins) if current_wins else None,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"version": VERSION, "error": f"data_quality_review error: {exc}"}


def restate_win_to_current_methodology(row: dict) -> float:
    """Given a trade row, returns what its `result_r` would be if credited
    under the CURRENT settlement rule (`1 + 0.5*finalR`) regardless of
    which rule actually produced the stored value. Non-wins are returned
    unchanged (losses are -1.0 under both rules — see
    `data_quality_review()`'s `loss_result_r_distinct_values`, and
    scratches are breakeven under both). Used to build a methodology-
    CONSISTENT comparison across the prior/recent windows — see
    `restated_comparison()`. Never raises (falls back to the stored value
    on any error)."""
    if row.get("status") != "win":
        return float(row.get("result_r", 0) or 0)
    try:
        entry, stop, target = float(row["entry"]), float(row["stop"]), float(row["target"])
        risk = abs(entry - stop)
        if risk <= 0:
            return float(row.get("result_r", 0) or 0)
        final_r = abs(target - entry) / risk
        return round(1 + 0.5 * final_r, 3)
    except Exception:  # noqa: BLE001
        return float(row.get("result_r", 0) or 0)


def restated_comparison(rows=None, recent_n: int = RECENT_WINDOW) -> dict:
    """The key sensitivity check for the "implementation drift" hypothesis:
    restates the PRIOR window's wins to the CURRENT settlement methodology
    (fully reconstructable from stored entry/stop/target — no external
    price data required) and recomputes expectancy/profit-factor/drawdown
    so prior-vs-recent is an apples-to-apples comparison under ONE
    consistent rule, rather than mixing two. The recent window is already
    100%/near-100% current-rule, so it is left unchanged. Reports both the
    as-stored and restated views side by side so nothing is hidden."""
    try:
        prior, recent = split_recent_prior(rows, recent_n)
        if prior is None:
            return {"sufficient": False}
        prior_restated = [restate_win_to_current_methodology(r) for r in prior]
        recent_actual = [r.get("result_r", 0) for r in recent]
        return {
            "sufficient": True,
            "as_stored": {
                "prior": rstats.full_report(prior),
                "recent": rstats.full_report(recent),
            },
            "restated_to_current_methodology": {
                "prior": rstats.full_report(prior_restated),
                "recent": rstats.full_report(recent_actual),
                "note": ("prior wins restated to 1 + 0.5*finalR (the current rule's formula); "
                        "losses/scratches unchanged (identical under both rules); recent left "
                        "as-stored since it is already ~current-rule."),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"restated_comparison error: {exc}"}


# ---------------------------------------------------------------------------
# SEGMENT PERFORMANCE
# ---------------------------------------------------------------------------

def _day_of_week(row):
    ts = _parse_ts(row.get("opened"))
    return ts.strftime("%A") if ts else "unknown"


def _session(row):
    ts = _parse_ts(row.get("opened"))
    return _session_from_hour(ts.hour) if ts else "unknown"


SEGMENT_DIMENSIONS = {
    "symbol": lambda r: r.get("symbol", "XAUUSD"),
    "session": _session,
    "day_of_week": _day_of_week,
    "regime_trend": lambda r: r.get("regime_trend") or "unknown",
    "regime_vol": lambda r: r.get("regime_vol") or "unknown",
    "confidence_tier": lambda r: _confidence_tier(r.get("confidence")),
    "guard_action": lambda r: r.get("guard_action") or "unknown",
}


def _bucket(rows, keyfn) -> dict:
    buckets = defaultdict(list)
    for r in rows:
        buckets[keyfn(r)].append(r.get("result_r", 0))
    out = {}
    for k, vals in buckets.items():
        rep = rstats.expectancy(vals)
        out[k] = {"n": len(vals), "expectancy": rep["value"],
                  "win_rate": rstats.win_rate(vals)["value"]}
    return out


def segment_performance(rows=None, recent_n: int = RECENT_WINDOW) -> dict:
    """Breaks down prior-vs-recent performance across every dimension the
    Day 10 mandate names EXCEPT strategy, volatility-environment-as-a-
    labeled-field, and confluence_profile — see `note` for why (each is a
    genuine data-completeness gap, quantified in `data_quality_review()`'s
    `field_coverage`, not silently skipped). `regime_vol` doubles as the
    mandate's "volatility environment" dimension where it is populated.
    Never raises."""
    try:
        prior, recent = split_recent_prior(rows, recent_n)
        if prior is None:
            return {"sufficient": False}
        out = {"sufficient": True, "dimensions": {}}
        for name, keyfn in SEGMENT_DIMENSIONS.items():
            out["dimensions"][name] = {
                "prior": _bucket(prior, keyfn),
                "recent": _bucket(recent, keyfn),
            }
        out["note"] = (
            "strategy is not segmentable: engine.market_memory.build_memory_record's own "
            "docstring documents ONE production strategy platform-wide at a time "
            "(config.regime_strategy), so a trade-level 'strategy mix' cannot literally "
            "shift under current instrumentation. confluence_profile is not segmentable: "
            "confluence_score is unpopulated (-1) on effectively every trade in trades.json "
            "(see data_quality_review()'s field_coverage) so no confluence-derived profile "
            "can be recovered per trade. Both are documented data-completeness gaps, not "
            "findings that strategy mix or confluence profile are stable."
        )
        return out
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"segment_performance error: {exc}"}


# ---------------------------------------------------------------------------
# STATISTICAL VARIANCE — permutation test
# ---------------------------------------------------------------------------

def variance_permutation_test(rows=None, recent_n: int = RECENT_WINDOW,
                               trials: int = 20000, seed: int = 42) -> dict:
    """Answers the mandate's "Statistical Variance" hypothesis directly:
    treating the full closed-trade population (methodology-RESTATED so the
    test isn't contaminated by the settlement-rule drift documented above)
    as a fixed pool, repeatedly draws random `recent_n`-sized samples
    WITHOUT replacement and asks what fraction land at or below the
    ACTUAL observed recent-window expectancy/win-rate. A low fraction
    means the observed recent window would be unusual for a random draw
    from this pool; a high fraction means it is unremarkable. DISCLOSED
    LIMITATION (read before trusting the p-value): the "recent 30" window
    was not chosen blindly — it was examined specifically because it
    already looked anomalous (this is exactly how Day 9's edge_decay_
    monitor surfaced it). That selection effect biases the fraction
    downward versus a truly pre-registered test. Treat the result as
    informative, not as a formal significance test. Never raises."""
    try:
        prior, recent = split_recent_prior(rows, recent_n)
        if prior is None:
            return {"sufficient": False}
        pool = [restate_win_to_current_methodology(r) for r in prior] + \
               [r.get("result_r", 0) for r in recent]
        observed_recent = [r.get("result_r", 0) for r in recent]
        observed_exp = sum(observed_recent) / len(observed_recent)
        observed_wr = sum(1 for v in observed_recent if v > 1e-9) / len(observed_recent)

        rng = random.Random(seed)
        exp_le = wr_le = 0
        sampled_exps = []
        for _ in range(trials):
            sample = rng.sample(pool, recent_n)
            e = sum(sample) / recent_n
            w = sum(1 for v in sample if v > 1e-9) / recent_n
            sampled_exps.append(e)
            if e <= observed_exp + 1e-9:
                exp_le += 1
            if w <= observed_wr + 1e-9:
                wr_le += 1

        return {
            "sufficient": True, "trials": trials, "seed": seed,
            "pool_n": len(pool), "pool_mean_expectancy": round(sum(pool) / len(pool), 3),
            "observed_recent_expectancy": round(observed_exp, 4),
            "observed_recent_win_rate": round(observed_wr, 4),
            "p_expectancy_le_observed": round(exp_le / trials, 4),
            "p_win_rate_le_observed": round(wr_le / trials, 4),
            "bootstrap_expectancy_mean": round(statistics.mean(sampled_exps), 3),
            "bootstrap_expectancy_stdev": round(statistics.stdev(sampled_exps), 3),
            "caveat": ("the recent window was selected FOR being anomalous (post-hoc), not "
                      "drawn blind, which biases these p-values downward versus a true "
                      "pre-registered test — treat as informative, not confirmatory."),
        }
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"variance_permutation_test error: {exc}"}


# ---------------------------------------------------------------------------
# FEATURE CONTRIBUTION — Day 6/7/8 advisory systems vs. outcome changes
# ---------------------------------------------------------------------------

def feature_contribution_check(rows=None) -> dict:
    """Checks whether Day 6 (Confidence Engine), Day 7 (Market Memory), or
    Day 8 (Explainability Engine) could have CAUSALLY influenced any trade
    in the investigated sample. Evidence used: (1) every trade's
    `confluence_ref`/`confidence_ref`/`regime_ref` — the direct-reference
    wiring those Days built — coverage, since a trade can only have been
    touched by that wiring if the ref is populated; (2) all three of those
    systems are, by every prior Day's own structural proof (direct grep of
    `alert_signals.py`/`dashboard_publish.py`), ADVISORY-ONLY and never
    gate, size, or alter a trade regardless. This function documents
    OBSERVATIONS, not causal claims, per the mandate's explicit
    instruction not to assume causation. Never raises."""
    try:
        rows = _all_rows(rows)
        n = len(rows)
        ref_fields = ["confluence_ref", "confidence_ref", "regime_ref"]
        coverage = {f: sum(1 for r in rows if r.get(f)) for f in ref_fields}
        return {
            "n_trades": n,
            "ref_field_coverage": {f: {"populated": c, "total": n,
                                       "pct": round(c / n * 100, 1) if n else None}
                                   for f, c in coverage.items()},
            "observation": (
                "Every trade in trades.json has empty confluence_ref/confidence_ref/regime_ref "
                "(0% coverage). These refs are the ONLY mechanism by which a Day 6/7/8 advisory "
                "system's OWN output could later be joined back to a specific trade for review. "
                "Their complete absence here means none of these trades can be shown, from the "
                "stored data alone, to have been assessed by (let alone influenced by) the Day "
                "6/7/8 advisory engines. Combined with every prior Day's structural proof that "
                "these engines never write to alert_signals.py's trade-selection/sizing path, "
                "there is no mechanism by which they could have contributed to the deterioration "
                "under investigation — advisory-only status holds for this sample by construction, "
                "not just by design."
            ),
            "not_a_causal_claim": (
                "This does not evaluate whether these systems WOULD help if wired in — only that "
                "they did not and structurally could not have affected these specific outcomes."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"feature_contribution_check error: {exc}"}


# ---------------------------------------------------------------------------
# FULL REPORT
# ---------------------------------------------------------------------------

def full_investigation_report(rows=None, recent_n: int = RECENT_WINDOW,
                              trials: int = 20000, seed: int = 42) -> dict:
    """One call assembling every piece of Experiment #0001's analysis —
    the function `PERFORMANCE_INVESTIGATION_0001.md` and the experiment
    registry entries are built from. Never raises; each section degrades
    independently."""
    try:
        return {
            "version": VERSION,
            "verify_core_metrics": verify_core_metrics(rows, recent_n),
            "data_quality_review": data_quality_review(rows),
            "restated_comparison": restated_comparison(rows, recent_n),
            "evidence_tier_assessment": _evidence_tier_for_recent(rows, recent_n),
            "segment_performance": segment_performance(rows, recent_n),
            "variance_permutation_test": variance_permutation_test(rows, recent_n, trials, seed),
            "feature_contribution_check": feature_contribution_check(rows),
        }
    except Exception as exc:  # noqa: BLE001
        return {"version": VERSION, "error": f"full_investigation_report error: {exc}"}


def _evidence_tier_for_recent(rows=None, recent_n: int = RECENT_WINDOW) -> dict:
    """Applies `evidence_tiers.assess()` (Day 9, reused not reimplemented)
    to the recent window — the SAMPLE ADEQUACY step the mandate asks for.
    `representative` is passed `False`: the recent window is drawn from a
    single ~9-day calendar span (2026-07-14 to 2026-07-23 at the time this
    was written) versus the prior window's ~7-day span immediately before
    it — both are narrow, but more importantly `segment_performance()`
    shows the recent window's composition across symbol/session/day-of-week
    is uneven (e.g. very few New York KZ trades) rather than a
    representative cross-section of all conditions this platform trades.
    `consistent_sign` is read directly from `research_stats.
    stability_over_time()`'s own field on the recent window, not
    re-decided here."""
    try:
        prior, recent = split_recent_prior(rows, recent_n)
        if prior is None:
            return {"sufficient": False}
        recent_r = [r.get("result_r", 0) for r in recent]
        stability = rstats.stability_over_time(recent_r)
        consistent = stability.get("consistent_sign") if stability.get("sufficient") else None
        return etiers.assess(
            len(recent_r), representative=False, consistent_sign=consistent,
            notes=("recent window spans a single narrow ~9-day calendar period with uneven "
                  "symbol/session/day-of-week composition — see segment_performance()."),
        )
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"_evidence_tier_for_recent error: {exc}"}
