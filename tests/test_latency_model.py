"""Offline tests for engine/execution/latency_model.py (Day 12)."""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import latency_model as lm  # noqa: E402


def test_estimate_latency_market_includes_human_reaction():
    r = random.Random(1)
    out = lm.estimate_latency("market", rng=r)
    assert out["include_human_reaction"] is True
    assert out["stages_ms"]["human_reaction"] > 0


def test_estimate_latency_limit_excludes_human_reaction_by_default():
    r = random.Random(1)
    out = lm.estimate_latency("limit", rng=r)
    assert out["include_human_reaction"] is False
    assert out["stages_ms"]["human_reaction"] == 0.0


def test_estimate_latency_stop_includes_human_reaction():
    r = random.Random(1)
    out = lm.estimate_latency("stop", rng=r)
    assert out["include_human_reaction"] is True


def test_estimate_latency_override_forces_human_reaction_off():
    r = random.Random(1)
    out = lm.estimate_latency("market", include_human_reaction=False, rng=r)
    assert out["stages_ms"]["human_reaction"] == 0.0


def test_estimate_latency_override_forces_human_reaction_on():
    r = random.Random(1)
    out = lm.estimate_latency("limit", include_human_reaction=True, rng=r)
    assert out["stages_ms"]["human_reaction"] > 0


def test_estimate_latency_total_equals_sum_of_stages():
    r = random.Random(2)
    out = lm.estimate_latency("market", rng=r)
    assert abs(out["total_latency_ms"] - sum(out["stages_ms"].values())) < 0.01


def test_estimate_latency_reproducible_with_same_seed():
    out1 = lm.estimate_latency("market", rng=random.Random(55))
    out2 = lm.estimate_latency("market", rng=random.Random(55))
    assert out1 == out2


def test_estimate_latency_unknown_order_type_falls_back_to_market():
    r = random.Random(3)
    out = lm.estimate_latency("bogus", rng=r)
    assert out["order_type"] == "market"


def test_estimate_latency_stages_within_documented_ranges():
    r = random.Random(4)
    out = lm.estimate_latency("market", rng=r)
    for stage, (lo, hi) in lm.STAGE_RANGES_MS.items():
        val = out["stages_ms"][stage]
        assert val == 0.0 or lo <= val <= hi


def test_estimated_execution_timestamp_adds_latency():
    ts = pd.Timestamp("2026-08-03 12:00:00")
    result = lm.estimated_execution_timestamp(ts, 5000.0)
    assert result == ts + pd.Timedelta(milliseconds=5000.0)


def test_estimated_execution_timestamp_never_raises_on_bad_input():
    assert lm.estimated_execution_timestamp(None, 100) is None
    assert lm.estimated_execution_timestamp("not-a-ts", "bad-latency") == "not-a-ts"


def test_estimate_latency_never_raises_on_internal_error(monkeypatch):
    class BoomRandom:
        def uniform(self, *a, **k):
            raise RuntimeError("boom")
    out = lm.estimate_latency("market", rng=BoomRandom())
    assert out["total_latency_ms"] == 0.0
    assert "error" in out["assumption"]
