"""Offline tests for engine/confidence_calibration.py (Day 6). Builds
synthetic trades_rows/history_rows in memory rather than touching
trades.json/confidence_history.jsonl — matches the approach
test_confluence_analysis.py used for measure_contribution()/
recommend_weight_adjustments() (Day 5).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confidence_calibration as cc  # noqa: E402


def _trade(tid, symbol, opened, status, confluence_ref=""):
    return {"id": tid, "symbol": symbol, "opened": opened, "status": status,
           "result_r": (2.0 if status == "win" else -1.0 if status == "loss" else 0.0),
           "confluence_ref": confluence_ref}


def _hist(symbol, ts, overall_confidence, tier, ref=""):
    return {"symbol": symbol, "timestamp": ts, "overall_confidence": overall_confidence,
           "tier": tier, "ref": ref}


# --- join_trades_with_confidence ------------------------------------------------

def test_join_prefers_direct_ref_match():
    trades = [_trade("XAUUSD-2026-08-01T10:00:00", "XAUUSD", "2026-08-01 10:00:00",
                     "win", confluence_ref="XAUUSD-2026-08-01T10:00:00")]
    hist = [_hist("XAUUSD", "2026-08-01T09:55:00", 60, "Moderate Confidence"),   # decoy, earlier ts
           _hist("XAUUSD", "2026-08-01T10:05:00", 80, "High Confidence",
                 ref="XAUUSD-2026-08-01T10:00:00")]                              # exact ref match
    out = cc.join_trades_with_confidence(trades, hist)
    assert len(out) == 1
    assert out[0]["overall_confidence"] == 80   # ref match wins over the nearer-by-time decoy
    assert out[0]["matched_via"] == "ref"


def test_join_falls_back_to_nearest_timestamp_when_no_ref():
    trades = [_trade("XAUUSD-2026-08-01T10:00:00", "XAUUSD", "2026-08-01 10:00:00", "loss")]
    hist = [_hist("XAUUSD", "2026-08-01T08:00:00", 50, "Low Confidence"),
           _hist("XAUUSD", "2026-08-01T09:58:00", 65, "Moderate Confidence")]  # nearest preceding
    out = cc.join_trades_with_confidence(trades, hist)
    assert len(out) == 1
    assert out[0]["overall_confidence"] == 65
    assert out[0]["matched_via"] == "timestamp"


def test_join_normalizes_t_vs_space_separator():
    """Regression guard for the exact bug Day 5's join had (ASCII 'T' vs
    space ordering) — confirms the fix carried over correctly here too."""
    trades = [_trade("XAUUSD-2026-08-01T10:00:00", "XAUUSD", "2026-08-01 10:00:00", "win")]
    hist = [_hist("XAUUSD", "2026-08-01T09:59:59", 70, "High Confidence")]
    out = cc.join_trades_with_confidence(trades, hist)
    assert len(out) == 1 and out[0]["overall_confidence"] == 70


def test_join_skips_open_and_unmatched_trades():
    trades = [_trade("XAUUSD-2026-08-01T10:00:00", "XAUUSD", "2026-08-01 10:00:00", "open"),
             _trade("WTIUSD-2026-08-01T11:00:00", "WTIUSD", "2026-08-01 11:00:00", "win")]
    hist = []  # no confidence history at all
    out = cc.join_trades_with_confidence(trades, hist)
    assert out == []  # open trade excluded by status; win trade excluded by no match


def test_join_never_raises_on_garbage():
    assert cc.join_trades_with_confidence([{"bad": "row"}], [{"also": "bad"}]) == []


# --- reliability / brier --------------------------------------------------------

def _joined_fixture():
    # 40 wins / 10 losses in the 70-84 bucket (realized 0.80, predicted 0.77)
    rows = []
    for i in range(40):
        rows.append({"overall_confidence": 75, "outcome": 1.0})
    for i in range(10):
        rows.append({"overall_confidence": 75, "outcome": 0.0})
    return rows


def test_reliability_computes_realized_rate_per_bucket():
    rel = cc.reliability(_joined_fixture(), min_n=30)
    bucket = next(r for r in rel if r["bucket"] == "70-84")
    assert bucket["n"] == 50
    assert bucket["realized"] == 0.8
    assert bucket["sufficient"] is True


def test_reliability_marks_thin_buckets_insufficient():
    rel = cc.reliability([{"overall_confidence": 75, "outcome": 1.0}], min_n=30)
    bucket = next(r for r in rel if r["bucket"] == "70-84")
    assert bucket["n"] == 1
    assert bucket["sufficient"] is False


def test_reliability_empty_input_returns_empty():
    assert cc.reliability([]) == []


def test_brier_score_perfect_prediction_is_zero():
    joined = [{"overall_confidence": 100, "outcome": 1.0}, {"overall_confidence": 0, "outcome": 0.0}]
    assert cc.brier(joined) == 0.0


def test_brier_score_none_when_empty():
    assert cc.brier([]) is None


# --- calibrated_probability_for --------------------------------------------------

def test_calibrated_probability_insufficient_data_returns_none():
    joined = [{"overall_confidence": 75, "outcome": 1.0}]  # n=1, way under MIN_N
    prob, is_cal, n = cc.calibrated_probability_for(75, joined)
    assert prob is None and is_cal is False and n == 1


def test_calibrated_probability_sufficient_data_returns_realized_rate():
    joined = _joined_fixture()  # n=50 >= MIN_N_FOR_CALIBRATION (30)
    prob, is_cal, n = cc.calibrated_probability_for(75, joined)
    assert is_cal is True
    assert prob == 0.8
    assert n == 50


def test_calibrated_probability_never_raises_on_garbage():
    prob, is_cal, n = cc.calibrated_probability_for(None, [{"bad": "row"}])
    assert prob is None and is_cal is False


# --- recommend_recalibration ------------------------------------------------------

def test_recommend_recalibration_flags_overconfidence():
    # predicted 77%, realized 40% -> overconfident by 37pt, well above threshold
    rows = [{"overall_confidence": 75, "outcome": 1.0 if i < 20 else 0.0} for i in range(50)]
    recs = cc.recommend_recalibration(rows, min_n=30)
    bucket = next(r for r in recs if r["bucket"] == "70-84")
    assert "recalibrate" in bucket["recommendation"]
    assert "overconfident" in bucket["recommendation"]


def test_recommend_recalibration_well_calibrated_when_gap_small():
    rows = [{"overall_confidence": 75, "outcome": 1.0 if i < 39 else 0.0} for i in range(50)]  # 78% realized vs 77% predicted
    recs = cc.recommend_recalibration(rows, min_n=30)
    bucket = next(r for r in recs if r["bucket"] == "70-84")
    assert bucket["recommendation"] == "well_calibrated"


def test_recommend_recalibration_insufficient_data():
    recs = cc.recommend_recalibration([{"overall_confidence": 75, "outcome": 1.0}], min_n=30)
    bucket = next(r for r in recs if r["bucket"] == "70-84")
    assert bucket["recommendation"] == "insufficient_data"


def test_recommend_recalibration_never_writes_anywhere():
    """Advisory-only guarantee, matching Day 5's recommend_weight_adjustments()
    precedent — confirmed structurally: the function takes no settings/path
    argument and confidence_engine.py's DEFAULT_TIERS remain untouched by
    calling it."""
    import engine.confidence_engine as ce
    before = list(ce.DEFAULT_TIERS)
    cc.recommend_recalibration(_joined_fixture(), min_n=30)
    assert ce.DEFAULT_TIERS == before


# --- rolling_evaluation ------------------------------------------------------------

def test_rolling_evaluation_limits_to_window():
    rows = [{"overall_confidence": 75, "outcome": 1.0, "opened": f"2026-08-{d:02d} 10:00:00"}
           for d in range(1, 21)]
    out = cc.rolling_evaluation(window_trades=5, joined=rows)
    assert out["n"] == 5


def test_rolling_evaluation_handles_empty():
    out = cc.rolling_evaluation(window_trades=10, joined=[])
    assert out["n"] == 0
    assert out["brier"] is None


# --- report ----------------------------------------------------------------------

def test_report_never_raises_on_empty_data(monkeypatch):
    monkeypatch.setattr(cc, "join_trades_with_confidence", lambda: [])
    out = cc.report()
    assert "CONFIDENCE ENGINE CALIBRATION" in out
    assert "0 matched closed trades" in out
    assert "not financial advice" in out.lower()


def test_report_shows_reliability_rows(monkeypatch):
    monkeypatch.setattr(cc, "join_trades_with_confidence", lambda: _joined_fixture())
    out = cc.report()
    assert "70-84" in out
