"""Offline tests for engine/confluence_analysis.py (Day 5).

Uses a lightweight fake ConfluenceRead (SimpleNamespace) rather than
driving real confluence.analyze() (which needs a live Layer-1-triggering
signal, hard to synthesize deterministically) — this matches the approach
Day 3/4 already used for hourly_briefing.apply_risk_gate() and
alert_signals.apply_regime_gate(): test the analysis function in isolation
from data-fetching concerns.

The label-matching regression test (test_every_known_confluence_label_matches)
is the most important test in this file: it hard-codes every literal
agree/disagree string engine/confluence.py's source code can actually
produce (verified by direct read on 2026-08-03) and asserts each one
resolves to a SOURCE_REGISTRY key — so a future edit to confluence.py's
wording breaks this test loudly instead of silently degrading
explain()/quality_score() to "unclassified".
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confluence_analysis as cfa  # noqa: E402


def _cr(score=75, final_tier="confirmed", direction="long",
       agree=None, disagree=None, layers=None):
    return SimpleNamespace(
        symbol="XAUUSD", direction=direction, base_tier="confirmed",
        final_tier=final_tier, score=score,
        agree=agree or [], disagree=disagree or [],
        layers=layers or {},
    )


# --- Phase 1/2: registry integrity ------------------------------------------

def test_registry_has_27_sources_including_layer1():
    assert len(cfa.SOURCE_REGISTRY) == 27


def test_registry_summary_counts_add_up():
    s = cfa.registry_summary()
    assert sum(s.values()) == 26   # excludes layer1_ict


def test_every_source_has_required_fields():
    for key, v in cfa.SOURCE_REGISTRY.items():
        assert v["category"] in ("primary", "supporting", "derived",
                                 "duplicate", "legacy")
        assert isinstance(v["nominal_pos"], (int, float))
        assert isinstance(v["nominal_neg"], (int, float))
        assert isinstance(v["shares_with"], list)
        assert len(v["note"]) > 20


def test_every_known_confluence_label_matches():
    """Every literal agree/disagree string confluence.py's source code can
    produce (read directly, 2026-08-03) must resolve to a registry key."""
    labels = [
        "price action", "trend (HTF stack + ADX)", "trend (HTF direction only)",
        "trend (HTF stack disagrees)", "breakout quality",
        "breakout quality (recent false break)", "mean reversion (overextended)",
        "volume profile (fair value)", "volume profile (buying above value)",
        "volume profile (selling below value)", "Wyckoff (Spring)",
        "Wyckoff (SOS)", "Wyckoff (absorption / composite-operator warning)",
        "macro (USD)", "macro (USD headwind)", "news",
        "session/kill-zone timing", "COT positioning",
        "Brent-WTI/crack spreads", "gold/silver ratio", "BTC futures basis",
        "seasonality", "cross-asset risk sentiment", "RSI divergence",
        "RSI divergence (active divergence warns against this)",
        "pivot level confluence", "candlestick pattern",
        "candlestick pattern (opposing pattern just printed)",
        "breaker/mitigation block",
        "breaker/mitigation block (zone works against this)",
        "Fibonacci confluence", "chart pattern",
        "chart pattern (opposing formation just confirmed)",
        "liquidity strength (weak level ahead)",
        "liquidity strength (strong level may hold)",
        "balanced price range / consequent encroachment",
        "Fibonacci ABC expansion",
        "session model (Judas Swing -> NY continuation)",
        "session model (Judas Swing implies the opposite direction)",
        "Elliott Wave (rule-valid impulse -> expected correction)",
        "Elliott Wave (rule-valid impulse expects the opposite direction)",
        "ICC (indication/correction/continuation)",
        "ICC (continuation confirmed the opposite direction)",
        # Day 6 observability fix (2026-08-03): regime_vol is no longer
        # invisible — confluence.py now labels it too.
        "regime volatility (expansion)", "regime volatility (normal)",
    ]
    unmatched = [lbl for lbl in labels if cfa._match_source(lbl) is None]
    assert unmatched == [], f"unmatched labels: {unmatched}"


def test_fibonacci_and_fibonacci_abc_do_not_cross_match():
    assert cfa._match_source("Fibonacci confluence") == "fibonacci"
    assert cfa._match_source("Fibonacci ABC expansion") == "fibonacci_abc"


def test_session_timing_triplicate_documented():
    assert set(cfa.SESSION_TIMING_TRIPLICATE) == {"layer1_ict", "session_timing", "session_model"}


def test_weak_provenance_sources_documented():
    assert set(cfa.WEAK_PROVENANCE_SOURCES) == {"bpr_ce", "session_model", "icc"}


# --- Phase 5: explain() ------------------------------------------------------

def test_explain_never_raises_on_empty_read():
    cr = _cr(agree=[], disagree=[])
    out = cfa.explain(cr)
    assert out["positive"] == [] and out["negative"] == []
    assert len(out["neutral"]) == 26   # everything is "missing evidence"


def test_explain_splits_positive_and_negative():
    cr = _cr(agree=["price action", "COT positioning"],
             disagree=["mean reversion (overextended)"])
    out = cfa.explain(cr)
    assert len(out["positive"]) == 2
    assert len(out["negative"]) == 1
    assert out["negative"][0]["key"] == "mean_reversion"


def test_explain_highest_impact_is_largest_magnitude():
    cr = _cr(agree=["price action"], disagree=["mean reversion (overextended)"])
    out = cfa.explain(cr)
    # mean_reversion nominal_neg=-10, price_action nominal_pos=8 -> mean_reversion wins
    assert out["highest_impact"]["key"] == "mean_reversion"


def test_explain_detects_conflict_between_related_sources():
    # layer1_ict shares_with is empty, but session_timing shares_with
    # includes layer1_ict and session_model - use session_timing vs
    # session_model disagreement to trigger the conflict detector.
    cr = _cr(agree=["session/kill-zone timing"],
             disagree=["session model (Judas Swing implies the opposite direction)"])
    out = cfa.explain(cr)
    assert len(out["conflicting_evidence"]) >= 1


def test_explain_regime_vol_no_longer_unlabeled():
    """Day 6 observability fix: regime_vol used to always be silently
    invisible (no agree/disagree label from confluence.py at all). It is
    now labeled like every other source, so unlabeled_sources is always
    empty, and a regime_vol agreement is visible in `positive` like any
    other confirming source."""
    cr = _cr()
    out = cfa.explain(cr)
    assert out["unlabeled_sources"] == []

    cr2 = _cr(agree=["regime volatility (expansion)"])
    out2 = cfa.explain(cr2)
    assert any(p["key"] == "regime_vol" for p in out2["positive"])
    assert "regime_vol" not in out2["neutral"]


def test_explain_handles_garbage_input_without_raising():
    # cr=None never raises: explain()'s getattr(cr, "agree", []) defaults
    # gracefully handle it, so this returns a normal all-neutral structure
    # rather than needing the except branch. Confirms the DEFENSIVE PATH
    # (not just the except clause) is what makes this fail-safe.
    out = cfa.explain(None)
    assert out["positive"] == [] and out["negative"] == []
    assert len(out["neutral"]) == 26


# --- Phase 6: quality_score() -----------------------------------------------

def test_quality_score_never_raises_on_empty_read():
    out = cfa.quality_score(_cr())
    assert 0 <= out["score"] <= 100


def test_quality_score_rewards_diverse_independent_agreement():
    # Five duplicate/derived sources agreeing...
    dup_heavy = _cr(agree=["Wyckoff (Spring)", "session/kill-zone timing",
                           "trend (HTF stack + ADX)", "Fibonacci confluence",
                           "balanced price range / consequent encroachment"])
    # ...vs five primary/supporting sources agreeing (same COUNT).
    primary_heavy = _cr(agree=["price action", "COT positioning", "seasonality",
                               "cross-asset risk sentiment", "chart pattern"])
    q_dup = cfa.quality_score(dup_heavy)
    q_primary = cfa.quality_score(primary_heavy)
    assert q_primary["independent_agreement"] > q_dup["independent_agreement"]
    assert q_primary["score"] > q_dup["score"]


def test_quality_score_penalized_by_conflicts():
    clean = _cr(agree=["price action", "COT positioning"])
    conflicted = _cr(agree=["price action"], disagree=["COT positioning"])
    q_clean = cfa.quality_score(clean)
    q_conflicted = cfa.quality_score(conflicted)
    assert q_clean["conflict_penalty"] < q_conflicted["conflict_penalty"]


def test_quality_score_uses_trend_layer_for_cross_tf_consistency():
    cr = _cr(layers={"trend": {"continuation_ok": True, "htf_agrees": True}})
    out = cfa.quality_score(cr)
    assert out["cross_tf_consistency"] == 1.0


# --- Phase 7: conflict_resolution() -----------------------------------------

def test_strong_ict_weak_macro_pattern_detected():
    cr = _cr(score=85, layers={"macro": {"aligned": False, "note": "USD fights it"}})
    out = cfa.conflict_resolution(cr)
    patterns = [c["pattern"] for c in out]
    assert "strong_ict_weak_macro" in patterns


def test_strong_structure_poor_liquidity_pattern_detected():
    cr = _cr(final_tier="confirmed",
             disagree=["liquidity strength (strong level may hold)"])
    cr.base_tier = "confirmed"
    out = cfa.conflict_resolution(cr)
    patterns = [c["pattern"] for c in out]
    assert "strong_structure_poor_liquidity" in patterns


def test_high_impact_news_pattern_detected():
    cr = _cr(score=75, layers={"news": {"strength": "HIGH"}})
    out = cfa.conflict_resolution(cr)
    patterns = [c["pattern"] for c in out]
    assert "bullish_technicals_high_impact_news" in patterns


def test_no_patterns_on_clean_aligned_read():
    cr = _cr(score=90, direction="long",
             layers={"macro": {"aligned": True}, "news": {"strength": "LOW"},
                    "volume_profile": {"location": "at_poc"}})
    out = cfa.conflict_resolution(cr)
    assert out == []


def test_conflict_resolution_never_raises_on_garbage():
    assert cfa.conflict_resolution(None) == []


# --- Phase 3/4/9: contribution measurement + adaptive weighting -----------

def _labeled(n_agree_win, n_agree_loss, n_disagree_win, n_disagree_loss, source_label):
    out = []
    for _ in range(n_agree_win):
        out.append({"result_r": 2.0, "agree": [source_label], "disagree": []})
    for _ in range(n_agree_loss):
        out.append({"result_r": -1.0, "agree": [source_label], "disagree": []})
    for _ in range(n_disagree_win):
        out.append({"result_r": 2.0, "agree": [], "disagree": [source_label]})
    for _ in range(n_disagree_loss):
        out.append({"result_r": -1.0, "agree": [], "disagree": [source_label]})
    return out


def test_measure_contribution_insufficient_with_small_sample():
    labeled = _labeled(3, 2, 2, 3, "COT positioning")
    m = cfa.measure_contribution("cot", labeled)
    assert m["sufficient"] is False


def test_measure_contribution_sufficient_with_min_n():
    labeled = _labeled(25, 5, 5, 25, "COT positioning")   # 30 agree, 30 disagree
    m = cfa.measure_contribution("cot", labeled, min_n=30)
    assert m["sufficient"] is True
    assert m["expectancy_when_agree"] > m["expectancy_when_disagree"]


def test_recommend_weight_adjustments_returns_insufficient_for_empty_data():
    recs = cfa.recommend_weight_adjustments([])
    assert len(recs) == 26   # every non-anchor source
    assert all(r["recommendation"] == "insufficient_data" for r in recs)


def test_recommend_weight_adjustments_recommends_increase_on_strong_gap():
    labeled = _labeled(28, 2, 2, 28, "COT positioning")
    recs = cfa.recommend_weight_adjustments(labeled, min_n=30)
    cot_rec = next(r for r in recs if r["source"] == "cot")
    assert cot_rec["recommendation"] == "increase"


def test_recommend_weight_adjustments_never_recommends_without_data():
    """The core Phase 4 guarantee: no recommendation is ever anything but
    'insufficient_data' when n < min_n, regardless of source."""
    recs = cfa.recommend_weight_adjustments([], min_n=30)
    assert all(r["recommendation"] == "insufficient_data" for r in recs)
    assert all("rationale" in r for r in recs)


def test_join_trades_with_confluence_nearest_timestamp():
    trades = [{"status": "win", "result_r": 2.0, "symbol": "XAUUSD",
              "opened": "2026-08-01 10:00:00"}]
    history = [
        {"ts": "2026-08-01T09:00:00", "symbol": "XAUUSD",
         "agree": ["price action"], "disagree": [], "quality_score": 70},
        {"ts": "2026-08-01T11:00:00", "symbol": "XAUUSD",  # after the trade - must not be picked
         "agree": ["COT positioning"], "disagree": [], "quality_score": 80},
    ]
    joined = cfa.join_trades_with_confluence(trades, history)
    assert len(joined) == 1
    assert joined[0]["agree"] == ["price action"]


def test_join_trades_with_confluence_skips_open_trades():
    trades = [{"status": "open", "result_r": 0.0, "symbol": "XAUUSD",
              "opened": "2026-08-01 10:00:00"}]
    joined = cfa.join_trades_with_confluence(trades, [])
    assert joined == []


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
