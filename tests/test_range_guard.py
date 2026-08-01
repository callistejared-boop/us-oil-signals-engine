"""Offline unit tests for the range-extension / dollar-headwind guard.

Pure logic, no network. Verifies the guard:
  * lets breakouts and trending continuation through (no false brake),
  * downgrades premium-range chases in a range regime,
  * compounds the penalty when the trade fights the dollar,
  * caps grades conservatively and stays fail-safe on bad input.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import range_guard as rgd  # noqa: E402

RANGE = {"trend": "range", "vol": "normal", "phase": "distribution"}
RANGE_CLEAN = {"trend": "range", "vol": "normal", "phase": "accumulation"}
TREND = {"trend": "trend", "vol": "expansion", "phase": "trending"}
EXPANSION = {"trend": "range", "vol": "expansion", "phase": "markup"}


def test_breakout_long_is_allowed():
    # price above the range edge = momentum, not a chase
    v = rgd.evaluate("WTIUSD", "long", 1.2, "up", RANGE)
    assert v["action"] == "allow"
    assert v["penalty"] == 0


def test_trend_continuation_not_penalised():
    # premium long, but structure says TREND → continuation, guard stands down
    v = rgd.evaluate("XAUUSD", "long", 0.92, "up", TREND)
    assert v["action"] == "allow"
    assert v["penalty"] == 0


def test_equilibrium_long_is_allowed():
    # below the premium floor → not extended
    v = rgd.evaluate("XAUUSD", "long", 0.50, "up", RANGE)
    assert v["action"] == "allow"


def test_premium_long_range_headwind_downgrades():
    # the exact failure mode: premium long, range regime, dollar up
    v = rgd.evaluate("XAUUSD", "long", 0.92, "up", RANGE)
    assert v["action"] == "downgrade"
    assert v["penalty"] < 0
    assert v["grade_cap"] is not None
    assert v["macro_headwind"] is True
    assert v["size_factor"] < 1.0


def test_wti_today_case():
    # WTI $80.13 in 68.63-81.27 ≈ pos 0.91, range/distribution, USD up
    v = rgd.evaluate("WTIUSD", "long", 0.91, "up", RANGE)
    assert v["action"] == "downgrade"
    assert v["macro_headwind"] is True
    assert v["grade_cap"] in ("B", "C (chase)")


def test_discount_short_range_headwind_downgrades():
    # mirror: short into range low, EURUSD, dollar down → short fights dollar
    v = rgd.evaluate("EURUSD", "short", 0.08, "down", RANGE)
    assert v["action"] == "downgrade"
    assert v["penalty"] < 0
    assert v["macro_headwind"] is True


def test_premium_long_no_headwind_still_flags_but_lighter():
    # premium chase but dollar falling (tailwind) → flagged on structure, no macro add
    v = rgd.evaluate("XAUUSD", "long", 0.92, "down", RANGE)
    assert v["action"] == "downgrade"
    assert v["macro_headwind"] is False


def test_expansion_gets_half_weight():
    strong = rgd.evaluate("XAUUSD", "long", 0.95, "flat", RANGE_CLEAN)
    weak = rgd.evaluate("XAUUSD", "long", 0.95, "flat", EXPANSION)
    # expansion halves the regime factor → smaller (less negative) penalty
    assert weak["penalty"] >= strong["penalty"]


def test_suppress_mode_off_by_default():
    # extreme chase + headwind, but SUPPRESS_MODE False → downgrade, never suppress
    v = rgd.evaluate("XAUUSD", "long", 1.0, "up", RANGE)
    assert v["action"] == "downgrade"
    assert rgd.SUPPRESS_MODE is False


def test_failsafe_on_bad_input():
    assert rgd.evaluate("XAUUSD", "long", None, "up", RANGE)["action"] == "allow"
    assert rgd.evaluate("XAUUSD", "sideways", 0.9, "up", RANGE)["action"] == "allow"
    assert rgd.evaluate("XAUUSD", "long", 0.9, None, None)["action"] in ("allow", "downgrade")


def test_cap_grade_ordering():
    assert rgd.cap_grade("A+", "B") == "B"
    assert rgd.cap_grade("B", "A") == "B"          # already lower → keep
    assert rgd.cap_grade("A+", None) == "A+"
    assert rgd.cap_grade("A+", "C (chase)") == "C (chase)"


def test_line_is_stringy():
    v = rgd.evaluate("XAUUSD", "long", 0.92, "up", RANGE)
    assert "RANGE GUARD" in rgd.line(v)
    assert "clear" in rgd.line({"action": "allow"})


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} range_guard tests passed")
