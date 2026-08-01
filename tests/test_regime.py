import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from engine import regime as rg


def _df(closes):
    closes = np.asarray(closes, float)
    return pd.DataFrame({"Open": closes, "High": closes + 0.5, "Low": closes - 0.5, "Close": closes,
                         "Volume": np.ones(len(closes))},
                        index=pd.date_range("2026-01-01", periods=len(closes), freq="1h", tz="UTC"))


def test_er_trend_vs_random():
    trend = rg.efficiency_ratio(np.arange(100).astype(float), 20)
    rng = np.random.default_rng(0)
    chop = rg.efficiency_ratio(100 + rng.normal(0, 1, 100).cumsum(), 20)
    assert trend > 0.9 and chop < trend


def test_classify_uptrend():
    r = rg.classify(_df(np.linspace(50, 80, 200)))
    assert r["trend"] == "trend" and "markup" in r["phase"]


def test_classify_range():
    rng = np.random.default_rng(3)
    r = rg.classify(_df(70 + rng.normal(0, 0.5, 200)))
    assert r["trend"] == "range"


def test_thin_data_unknown():
    assert rg.classify(_df([1, 2, 3]))["trend"] == "unknown"
