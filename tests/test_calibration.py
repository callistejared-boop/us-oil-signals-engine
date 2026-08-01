import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import calibration as cal


def _mk(conf, status):
    return {"confidence": conf, "status": status, "result_r": 1.0 if status == "win" else -1.0}


def test_reliability_and_brier():
    closed = [_mk(75, "win")] * 6 + [_mk(75, "loss")] * 4   # 60% realized vs 75% predicted
    rel = cal.reliability(closed)
    b = next(x for x in rel if x["bucket"] == "70-79")
    assert b["n"] == 10 and b["realized"] == 0.6 and b["predicted"] == 0.75
    assert cal.brier(closed) is not None


def test_calibrated_probability_uses_history():
    closed = [_mk(85, "win")] * 5 + [_mk(85, "loss")] * 5   # 50% realized in 80-89
    cmap = cal.calibrated_map(closed, min_n=8)
    assert cmap.get("80-89") == 0.5
    assert cal.calibrated_probability(85, cmap) == 0.5


def test_calibration_falls_back_when_thin():
    assert cal.calibrated_probability(85, {}) == 0.85   # no history -> raw
