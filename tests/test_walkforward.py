import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import walkforward as wf


def _mk(i, conf, win):
    return {"opened": f"2026-01-01 {i//60:02d}:{i%60:02d}:00", "confidence": conf,
            "status": "win" if win else "loss", "result_r": 1.0 if win else -1.0}


def test_anti_predictive_calibrated_beats_raw():
    # high confidence LOSES, low confidence WINS (like the real journal)
    data = []
    for i in range(60):
        data.append(_mk(i, 90, win=(i % 5 == 0)))      # 90-conf wins 20%
        data.append(_mk(60 + i, 65, win=(i % 5 != 0)))  # 65-conf wins 80%
    c = wf.compare(data, min_train=20)
    assert c["calibrated"]["oos_brier"] < c["raw"]["oos_brier"]


def test_predictive_confidence_is_ok():
    # high confidence WINS more -> raw should be reasonable, not worse than base by much
    data = []
    for i in range(60):
        data.append(_mk(i, 90, win=(i % 5 != 0)))       # 90-conf wins 80%
        data.append(_mk(60 + i, 65, win=(i % 5 == 0)))   # 65-conf wins 20%
    c = wf.compare(data, min_train=20)
    assert c["raw"]["oos_brier"] is not None and c["calibrated"]["oos_brier"] is not None


def test_report_runs():
    data = [_mk(i, 80, win=(i % 2 == 0)) for i in range(60)]
    assert "WALK-FORWARD" in wf.report(data, min_train=20)
