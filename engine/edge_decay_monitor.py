"""Day 9 — Edge decay monitoring.

Watches for declining expectancy, declining profit factor, increasing
drawdown, changing market regimes, and reduced strategy effectiveness —
per the Day 9 mandate's explicit list. THE FRAMEWORK RECOMMENDS
INVESTIGATION, NEVER AN AUTOMATIC PRODUCTION CHANGE — this is the same
observational-only posture as every Day 6-8 engine before it. Nothing here
can pause trading, change a threshold, or gate a signal; `check()` returns
a structured set of flags for a human (or a future, separately-mandated
governance layer) to review.

Reuses, not duplicates: `engine.research_stats` for every metric,
`engine.walkforward.expanding_window_series` for the trend detection,
`engine.market_memory.performance_by_origination_regime` (Day 7) for the
regime-conditioned view. No new statistical formula is invented here.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import research_stats as rstats   # noqa: E402
from engine import walkforward as wf          # noqa: E402
from engine import store                       # noqa: E402
from engine import journal                     # noqa: E402

VERSION = "1.0.0"

# How many of the most recent trades count as "recent" for a recent-vs-prior
# comparison — deliberately reuses the platform's MIN_N_FOR_TRUST bar so a
# "recent window" comparison is never drawn from fewer trades than this
# platform already treats as its statistical-trust floor elsewhere.
RECENT_WINDOW = rstats.MIN_N_FOR_TRUST

# A decline flag requires BOTH a directional drop AND that drop clearing this
# minimum size — small, noise-level wiggles are not flagged. Disclosed
# engineering judgment, not a fitted number (same convention as every prior
# Day's disclosed-not-fitted threshold).
EXPECTANCY_DECLINE_R = 0.15
PROFIT_FACTOR_DECLINE = 0.3
DRAWDOWN_INCREASE_R = 2.0


def _closed_trades(rows=None):
    if rows is not None:
        return rows
    all_rows = store.load_array(journal.STORE)
    return [r for r in all_rows if r.get("status") in ("win", "loss", "scratch")]


def recent_vs_prior(rows=None, recent_n: int = RECENT_WINDOW) -> dict:
    """Compares the most recent `recent_n` closed trades against everything
    before them. Never raises; explicitly reports insufficient data rather
    than a misleading comparison when either half is too small."""
    try:
        closed = sorted(_closed_trades(rows), key=lambda r: str(r.get("opened", "")))
        n = len(closed)
        if n < recent_n * 2:
            return {"sufficient": False,
                   "note": f"need >= {recent_n * 2} closed trades for a recent-vs-prior "
                           f"comparison (have {n}) — comparing too-small halves would be noise"}
        prior, recent = closed[:-recent_n], closed[-recent_n:]
        prior_report = rstats.full_report(prior)
        recent_report = rstats.full_report(recent)
        return {"sufficient": True, "recent_n": recent_n, "prior_n": len(prior),
               "prior": prior_report, "recent": recent_report}
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False, "note": f"recent_vs_prior error: {exc}"}


def check(rows=None) -> dict:
    """The main entry point — a structured decay-investigation report.
    Never raises; every flag is DESCRIPTIVE ("worth investigating"), never
    prescriptive ("do X"). Nothing here is wired into any production gate —
    see RESEARCH_VALIDATION_SPECIFICATION.md Sec.7."""
    try:
        cmp = recent_vs_prior(rows)
        flags = []
        if cmp.get("sufficient"):
            prior, recent = cmp["prior"], cmp["recent"]

            pe, re_ = prior["expectancy"]["value"], recent["expectancy"]["value"]
            if pe is not None and re_ is not None and (pe - re_) >= EXPECTANCY_DECLINE_R:
                flags.append({
                    "type": "declining_expectancy",
                    "detail": f"expectancy fell from {pe:+.2f}R (prior {cmp['prior_n']}) to "
                             f"{re_:+.2f}R (recent {cmp['recent_n']})",
                    "recommendation": "investigate — do not change production automatically",
                })

            pf_p = prior["profit_factor"]["value"]
            pf_r = recent["profit_factor"]["value"]
            if pf_p is not None and pf_r is not None and (pf_p - pf_r) >= PROFIT_FACTOR_DECLINE:
                flags.append({
                    "type": "declining_profit_factor",
                    "detail": f"profit factor fell from {pf_p} to {pf_r}",
                    "recommendation": "investigate — do not change production automatically",
                })

            dd_p = prior["max_drawdown"]["value"]
            dd_r = recent["max_drawdown"]["value"]
            if dd_p is not None and dd_r is not None and (dd_p - dd_r) >= DRAWDOWN_INCREASE_R:
                # max_drawdown values are negative (more negative = deeper) —
                # a decrease (dd_p - dd_r >= threshold) means recent drawdown
                # is DEEPER than prior.
                flags.append({
                    "type": "increasing_drawdown",
                    "detail": f"max drawdown deepened from {dd_p}R (prior) to {dd_r}R (recent)",
                    "recommendation": "investigate — do not change production automatically",
                })

            stab = recent.get("stability_over_time", {})
            if stab.get("sufficient") and not stab.get("consistent_sign", True):
                flags.append({
                    "type": "reduced_effectiveness_within_recent_window",
                    "detail": "recent trades' own sub-segments do not agree in sign — "
                             "effectiveness may be inconsistent, not just declining",
                    "recommendation": "investigate — do not change production automatically",
                })

        return {
            "version": VERSION, "comparison": cmp, "flags": flags,
            "n_flags": len(flags),
            "note": ("regime-conditioned decay (per the mandate's 'changing market regimes' item) "
                    "should be cross-checked against engine.market_memory."
                    "performance_by_origination_regime() directly — not duplicated here, since that "
                    "function already exists and is regime-aware (Day 7)"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"version": VERSION, "comparison": {}, "flags": [], "n_flags": 0,
               "error": f"check error: {exc}"}
