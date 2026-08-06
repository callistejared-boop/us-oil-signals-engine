"""Offline tests for engine/market_memory.py (Day 7): MemoryRecord
assembly, storage-reuse (no duplicate DB), similarity scoring, memory
quality, historical_context(), and the performance-analytics functions.
Look-ahead protection has its own dedicated file,
tests/test_market_memory_lookahead.py.
"""
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import market_memory as mm  # noqa: E402


def _trade_row(tid="XAUUSD-2026-08-01T10:00:00", symbol="XAUUSD", status="win", result_r=2.0,
              opened="2026-08-01 10:00:00", closed="2026-08-01 12:00:00",
              regime_ref="", confluence_ref="", confidence_ref="",
              regime_trend="trend", regime_vol="expansion", confluence_score=80,
              confluence_agree=5, direction="long"):
    return {"id": tid, "symbol": symbol, "status": status, "result_r": result_r,
           "opened": opened, "closed": closed, "direction": direction,
           "regime_ref": regime_ref, "confluence_ref": confluence_ref, "confidence_ref": confidence_ref,
           "regime_trend": regime_trend, "regime_vol": regime_vol,
           "confluence_score": confluence_score, "confluence_agree": confluence_agree,
           "guard_action": "allow", "guard_penalty": 0, "guard_headwind": "no",
           "news_signal": "", "news_strength": "", "news_delta": 0}


# --- Phase 2: MemoryRecord assembly ---------------------------------------------

def test_build_memory_record_falls_back_to_trade_row_when_no_refs():
    rec = mm.build_memory_record(_trade_row())
    assert rec.trade_id == "XAUUSD-2026-08-01T10:00:00"
    assert rec.data_completeness["regime"] == "trade_row_only"
    assert rec.data_completeness["confluence"] == "trade_row_only"
    assert rec.data_completeness["confidence"] == "missing"
    assert rec.regime["trend"] == "trend"
    assert rec.confluence_summary["score"] == 80


def test_build_memory_record_origination_method_defaults_to_config_regime_strategy():
    # V2.2 Priority 2 Item 4 rename (was `strategy`, collided with the new
    # Trade.strategy concept — see MemoryRecord.origination_method's own
    # docstring). Default source is config.regime_strategy, unchanged
    # behavior from before the rename.
    rec = mm.build_memory_record(_trade_row())
    assert rec.origination_method == "ict_smc_mast"


def test_build_memory_record_origination_method_explicit_override():
    rec = mm.build_memory_record(_trade_row(), origination_method="future_strategy_x")
    assert rec.origination_method == "future_strategy_x"


def test_build_memory_record_uses_history_rows_when_refs_resolve(monkeypatch):
    from engine import regime_history as rh, confluence_history as cfh, confidence_history as cfdh
    ref = "XAUUSD-2026-08-01T10:00:00"
    monkeypatch.setattr(rh, "find_by_ref", lambda r: {"primary": "Strong Bull Trend",
                                                       "confidence": 70, "quality_score": 65} if r == ref else None)
    monkeypatch.setattr(cfh, "find_by_ref", lambda r: {"score": 85, "final_tier": "confirmed",
                                                        "agree": ["price action"], "disagree": []} if r == ref else None)
    monkeypatch.setattr(cfdh, "find_by_ref", lambda r: {"overall_confidence": 78, "tier": "High Confidence",
                                                         "is_calibrated": False,
                                                         "portfolio_status": {"heat": 0.3}} if r == ref else None)
    row = _trade_row(regime_ref=ref, confluence_ref=ref, confidence_ref=ref)
    rec = mm.build_memory_record(row)
    assert rec.data_completeness == {"regime": "matched", "confluence": "matched", "confidence": "matched"}
    assert rec.regime["primary"] == "Strong Bull Trend"
    assert rec.confluence_summary["score"] == 85
    assert rec.confidence_assessment["overall_confidence"] == 78
    assert rec.portfolio_context["heat"] == 0.3


def test_build_memory_record_never_raises_on_garbage():
    rec = mm.build_memory_record({"bad": "row"})
    assert isinstance(rec, mm.MemoryRecord)


def test_build_memory_record_derives_session_from_opened_hour():
    row = _trade_row(opened="2026-08-01 08:00:00")   # 08:00 UTC -> London KZ
    rec = mm.build_memory_record(row)
    assert rec.session == "London KZ"

    row2 = _trade_row(opened="2026-08-01 02:00:00")  # 02:00 UTC -> Asian
    rec2 = mm.build_memory_record(row2)
    assert rec2.session == "Asian"


def test_build_memory_records_reuses_trades_json_no_duplicate_store():
    """The storage-design guarantee: build_memory_records() reads directly
    from trades.json (via engine.store), it does not read from or require
    a separate 'memory' database file."""
    import inspect
    src = inspect.getsource(mm.build_memory_records)
    assert "trades.json" in src


def test_build_memory_records_sorted_by_opened():
    rows = [_trade_row(tid="b", opened="2026-08-02 10:00:00"),
           _trade_row(tid="a", opened="2026-08-01 10:00:00")]
    recs = mm.build_memory_records(rows)
    assert [r.trade_id for r in recs] == ["a", "b"]


# --- Phase 3: similarity ---------------------------------------------------------

def test_similarity_identical_features_scores_high():
    f = {"regime_primary": "Strong Bull Trend", "confluence_profile": frozenset({"primary"}),
        "session": "London KZ", "volatility": "expansion", "macro_alignment": True,
        "portfolio_state": "low", "direction": "long"}
    assert mm.similarity(f, dict(f)) == 1.0


def test_similarity_completely_different_features_scores_zero():
    a = {"regime_primary": "Strong Bull Trend", "session": "London KZ", "direction": "long"}
    b = {"regime_primary": "Range", "session": "Asian", "direction": "short"}
    assert mm.similarity(a, b) == 0.0


def test_similarity_missing_dimension_on_either_side_excluded_not_penalized():
    a = {"regime_primary": "Strong Bull Trend", "session": None}
    b = {"regime_primary": "Strong Bull Trend", "session": "London KZ"}
    # session is unknown on side A -> excluded from comparison entirely;
    # regime_primary matches -> should score 1.0, not partial-credit-penalized
    assert mm.similarity(a, b) == 1.0


def test_similarity_confluence_profile_uses_jaccard_overlap():
    a = {"confluence_profile": frozenset({"primary", "supporting"})}
    b = {"confluence_profile": frozenset({"primary"})}
    s = mm.similarity(a, b, weights={"confluence_profile": 1.0})
    assert 0.0 < s < 1.0   # partial overlap, not exact match


def test_similarity_never_raises_on_garbage():
    assert mm.similarity(None, None) == 0.0
    assert mm.similarity({}, {}) == 0.0


def test_similarity_no_comparable_dimensions_returns_zero():
    assert mm.similarity({"session": None}, {"session": None}) == 0.0


def test_extract_features_shape():
    rec = mm.build_memory_record(_trade_row())
    f = mm.extract_features(rec)
    for k in ("regime_primary", "confluence_profile", "session", "volatility",
             "macro_alignment", "portfolio_state", "direction"):
        assert k in f


def test_query_features_from_live_matches_extract_features_shape():
    q = mm.query_features_from_live(mkt_regime={"primary": "Range"}, cr=None,
                                    session="London KZ", portfolio_verdict=None, direction="long")
    rec = mm.build_memory_record(_trade_row())
    f = mm.extract_features(rec)
    assert set(q.keys()) == set(f.keys())


# --- Phase 4: memory quality + historical_context --------------------------------

def test_memory_quality_empty_matches():
    q = mm.memory_quality([])
    assert q["sample_size"] == 0
    assert q["confidence_label"] == "insufficient"


def test_memory_quality_sparse_below_trust_bar():
    matches = [{"record": mm.build_memory_record(_trade_row(tid=str(i))), "similarity": 0.8}
              for i in range(10)]
    q = mm.memory_quality(matches)
    assert q["sample_size"] == 10
    assert q["confidence_label"] == "sparse"


def test_memory_quality_rich_above_trust_bar_and_high_similarity():
    matches = [{"record": mm.build_memory_record(_trade_row(tid=str(i))), "similarity": 0.9}
              for i in range(35)]
    q = mm.memory_quality(matches)
    assert q["confidence_label"] == "rich"


def test_historical_context_insufficient_sample_states_explicitly():
    ctx = mm.historical_context({"regime_primary": "Range"}, datetime(2026, 8, 3), records=[])
    assert ctx["sufficient_sample"] is False
    assert ctx["comparable_count"] == 0
    assert "too few" in ctx["note"].lower()


def test_historical_context_computes_aggregate_when_sufficient():
    rows = [_trade_row(tid=f"t{i}", status="win" if i % 2 == 0 else "loss",
                       result_r=2.0 if i % 2 == 0 else -1.0,
                       opened=f"2026-07-{(i%27)+1:02d} 10:00:00",
                       closed=f"2026-07-{(i%27)+1:02d} 12:00:00")
           for i in range(10)]
    records = mm.build_memory_records(rows)
    query = mm.extract_features(records[0])
    ctx = mm.historical_context(query, datetime(2026, 8, 3), records=records, top_k=20)
    assert ctx["sufficient_sample"] is True
    assert ctx["aggregate"]["n"] == ctx["comparable_count"]
    assert 0.0 <= ctx["aggregate"]["win_rate"] <= 1.0


def test_historical_context_never_raises_on_garbage():
    ctx = mm.historical_context(None, "not-a-date", records=None)
    assert isinstance(ctx, dict)
    assert ctx["sufficient_sample"] is False


# --- Performance analytics -----------------------------------------------------

def test_performance_by_session_reports_sufficiency():
    rows = [_trade_row(tid=f"t{i}", opened="2026-08-01 08:00:00",  # always London KZ
                       status="win" if i % 3 else "loss")
           for i in range(10)]
    records = mm.build_memory_records(rows)
    out = mm.performance_by_session(records)
    london = next((b for b in out if b["key"] == "London KZ"), None)
    assert london is not None
    assert london["n"] == 10
    assert london["sufficient"] is False   # below MIN_N_FOR_TRUST=30


def test_performance_by_origination_regime_groups_correctly():
    # Renamed from performance_by_strategy_regime() (V2.2 Priority 2 Item 4 /
    # TECHNICAL_DEBT_REGISTER Item 8) — "strategy" meant origination method,
    # not the new per-trade Trade.strategy concept.
    rows = [_trade_row(tid=f"t{i}", regime_trend="trend") for i in range(5)]
    rows += [_trade_row(tid=f"t{i+5}", regime_trend="range") for i in range(5)]
    records = mm.build_memory_records(rows)
    out = mm.performance_by_origination_regime(records)
    keys = {b["key"] for b in out}
    assert ("ict_smc_mast", "trend") in keys
    assert ("ict_smc_mast", "range") in keys


def test_risk_adjusted_by_combo_flags_insufficient_below_trust_bar():
    rows = [_trade_row(tid=f"t{i}") for i in range(5)]
    records = mm.build_memory_records(rows)
    out = mm.risk_adjusted_by_combo(records)
    assert all(c["risk_adjusted"] is None for c in out if not c["sufficient"])


def test_performance_analytics_never_raise_on_empty_history():
    assert mm.performance_by_session([]) == []
    assert mm.performance_by_origination_regime([]) == []
    assert mm.risk_adjusted_by_combo([]) == []


def test_performance_analytics_exclude_open_trades():
    rows = [_trade_row(tid="open1", status="open")]
    records = mm.build_memory_records(rows)
    assert mm.performance_by_session(records) == []


# --- Duplicate detection ---------------------------------------------------------

def test_duplicate_trade_ids_do_not_double_count_in_performance_analytics():
    """Two trade rows sharing an id (a data-entry accident, or a legacy
    id-format collision — see MARKET_MEMORY_SPECIFICATION.md Sec.6 for the
    pre-Day-6 id-format finding) must not silently double-weight a bucket's
    statistics beyond what build_memory_records() actually assembled —
    each row is assembled and counted independently and explicitly, so a
    caller inspecting `n` always sees the true row count, not a
    deduplicated-then-inflated one."""
    rows = [_trade_row(tid="XAUUSD-2026-08-01T10:00:00", status="win", opened="2026-08-01 08:00:00"),
           _trade_row(tid="XAUUSD-2026-08-01T10:00:00", status="win", opened="2026-08-01 08:00:00")]  # duplicate id
    records = mm.build_memory_records(rows)
    assert len(records) == 2   # both rows assembled, nothing silently dropped
    out = mm.performance_by_session(records)
    london = next(b for b in out if b["key"] == "London KZ")
    assert london["n"] == 2   # explicit, matches the two rows — not deduplicated to 1


def test_find_similar_does_not_return_duplicate_records_beyond_input():
    row = _trade_row(tid="dup1")
    records = mm.build_memory_records([row, row])   # same dict object twice
    query = mm.extract_features(records[0])
    matches = mm.find_similar(query, "2026-08-03T00:00:00", records=records, top_k=10)
    assert len(matches) == 2   # both candidates considered, none silently merged


# --- Missing-history scenarios ---------------------------------------------------

def test_build_memory_record_with_all_history_missing_and_no_trade_row_fallback():
    row = {"id": "x", "symbol": "XAUUSD", "status": "win", "result_r": 1.0,
          "opened": "2026-08-01 10:00:00", "closed": "2026-08-01 11:00:00", "direction": "long"}
    rec = mm.build_memory_record(row)
    assert rec.data_completeness == {"regime": "missing", "confluence": "missing", "confidence": "missing"}
    assert rec.regime["primary"] is None


def test_historical_context_with_no_records_at_all():
    ctx = mm.historical_context({"regime_primary": "Range"}, "2026-08-03T00:00:00", records=[])
    assert ctx["comparable_count"] == 0
    assert ctx["sufficient_sample"] is False


# --- Large-history performance ---------------------------------------------------

def test_large_history_find_similar_completes_and_is_correct():
    import time
    rows = [_trade_row(tid=f"t{i}", opened=f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d} 08:00:00",
                       closed=f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d} 10:00:00",
                       status="win" if i % 3 else "loss", regime_trend="trend" if i % 2 else "range")
           for i in range(2000)]
    records = mm.build_memory_records(rows)
    assert len(records) == 2000
    query = mm.extract_features(records[0])
    start = time.time()
    matches = mm.find_similar(query, "2026-08-03T00:00:00", records=records, top_k=25)
    elapsed = time.time() - start
    assert len(matches) <= 25
    assert elapsed < 5.0   # generous bound — this is a pure-Python O(n) scan, not meant to be a
                          # hard perf contract, just a guard against an accidental O(n^2)/O(n^3) regression


def test_large_history_performance_analytics_completes():
    import time
    rows = [_trade_row(tid=f"t{i}", regime_trend="trend" if i % 2 else "range",
                       status="win" if i % 3 else "loss") for i in range(2000)]
    records = mm.build_memory_records(rows)
    start = time.time()
    mm.performance_by_session(records)
    mm.performance_by_origination_regime(records)
    mm.risk_adjusted_by_combo(records)
    assert time.time() - start < 5.0


# --- Reference integrity ----------------------------------------------------------

def test_reference_integrity_ref_only_matches_correct_row(monkeypatch):
    """A trade's *_ref must resolve to the SPECIFIC history row for that
    trade, not merely the most recent one for the symbol — direct-reference
    lookup (find_by_ref) rather than any positional/latest assumption."""
    from engine import regime_history as rh
    rows_by_ref = {
        "ref-A": {"primary": "Range"},
        "ref-B": {"primary": "Strong Bull Trend"},
    }
    monkeypatch.setattr(rh, "find_by_ref", lambda r: rows_by_ref.get(r))
    rec_a = mm.build_memory_record(_trade_row(tid="a", regime_ref="ref-A"))
    rec_b = mm.build_memory_record(_trade_row(tid="b", regime_ref="ref-B"))
    assert rec_a.regime["primary"] == "Range"
    assert rec_b.regime["primary"] == "Strong Bull Trend"


def test_reference_integrity_empty_ref_never_looked_up(monkeypatch):
    from engine import regime_history as rh
    calls = []
    monkeypatch.setattr(rh, "find_by_ref", lambda r: calls.append(r) or None)
    mm.build_memory_record(_trade_row(tid="x", regime_ref=""))
    assert calls == []   # find_by_ref must not even be called with an empty ref
