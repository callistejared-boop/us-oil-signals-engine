import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import risk


def test_position_size_math():
    ps = risk.position_size(10000, 1.0, entry=100.0, stop=99.0, value_per_point=1.0)
    assert ps["risk_cash"] == 100.0 and ps["per_unit_risk"] == 1.0 and ps["units"] == 100.0


def test_vol_scaling_expansion():
    assert risk.vol_adjusted_risk(1.0, "expansion") == 0.75
    assert risk.vol_adjusted_risk(1.0, "normal") == 1.0


def test_zero_risk_safe():
    assert risk.position_size(10000, 1.0, 100.0, 100.0)["units"] == 0.0


def test_portfolio_cap_breach():
    pos = [{"risk_cash": 400, "base": "USD"}, {"risk_cash": 400, "base": "USD"}]
    e = risk.portfolio_exposure(pos, 10000)
    assert e["open_risk_pct"] == 8.0 and e["over_cap"] is True and "USD" in e["concentration"]


def test_portfolio_under_cap():
    e = risk.portfolio_exposure([{"risk_cash": 100, "base": "EUR"}], 10000)
    assert e["over_cap"] is False
