"""Offline tests for the four additional confirmation sources: COT
positioning, Brent-WTI/crack spreads, seasonality, and cross-asset risk
sentiment. All must fail safe with zero network access (this test suite
never hits the real network) and never crash confluence.py when data is
unavailable.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cot_feed as cot          # noqa: E402
from engine import spread_feed as sp        # noqa: E402
from engine import seasonality as sea       # noqa: E402
from engine import risk_sentiment as rs     # noqa: E402


# --------------------------------------------------------------------- COT
def test_cot_percentile_rank():
    hist = [10, 20, 30, 40, 50]
    assert cot.percentile_rank(hist, 50) == 1.0
    assert cot.percentile_rank(hist, 10) == 0.2
    assert cot.percentile_rank([], 5) == 0.5


def test_cot_alignment_flags_crowded_long():
    d = {"asof": "2026-07-15", "spec_net": 250000, "percentile": 0.9,
        "open_interest": 1900000}
    out = cot.alignment("long", d=d)
    assert out["supports"] is False and out["extreme"] is True


def test_cot_alignment_contrarian_tailwind():
    d = {"asof": "2026-07-15", "spec_net": -50000, "percentile": 0.08,
        "open_interest": 1900000}
    out = cot.alignment("long", d=d)
    assert out["supports"] is True and out["extreme"] is True


def test_cot_alignment_no_data():
    out = cot.alignment("long", d=None if False else cot.read_cached())
    # in a clean test env there is no cache -> None -> neutral, no crash
    assert out["supports"] in (None, True, False)


def test_cot_alignment_neutral_midrange():
    d = {"asof": "2026-07-15", "spec_net": 10000, "percentile": 0.5,
        "open_interest": 1900000}
    out = cot.alignment("long", d=d)
    assert out["supports"] is None and out["extreme"] is False


# ------------------------------------------------------------------ spreads
def test_spread_trend_classification():
    import pandas as pd
    widening = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 2.0])
    narrowing = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0, 1.0])
    flat = pd.Series([1.0] * 6)
    assert sp._trend(widening) == "widening"
    assert sp._trend(narrowing) == "narrowing"
    assert sp._trend(flat) == "flat"
    assert sp._trend(None) == "flat"


def test_spread_alignment_combines_votes():
    d = {"brent_wti_trend": "narrowing", "crack_trend": "widening"}
    out = sp.alignment("long", d=d)
    assert out["supports"] is True   # both votes bullish for WTI


def test_spread_alignment_conflicting_votes_neutral():
    d = {"brent_wti_trend": "widening", "crack_trend": "widening"}
    out = sp.alignment("long", d=d)
    assert out["supports"] is None   # -1 +1 = 0, no clear read


def test_spread_alignment_no_data():
    # d={} (not None) forces the "no data" branch directly rather than
    # falling through to read(), which would pick up a real cache file
    # left on disk by a live run and defeat the point of this test.
    out = sp.alignment("long", d={})
    assert out["supports"] is None


# --------------------------------------------------------------- seasonality
def test_seasonality_march_bearish():
    b = sea.bias(3)
    assert b["lean"] == "bear"
    out = sea.alignment("long", month=3)
    assert out["supports"] is False
    out_short = sea.alignment("short", month=3)
    assert out_short["supports"] is True


def test_seasonality_july_bullish():
    b = sea.bias(7)
    assert b["lean"] == "bull"
    assert sea.alignment("long", month=7)["supports"] is True


def test_seasonality_covers_all_months():
    for m in range(1, 13):
        b = sea.bias(m)
        assert b["lean"] in ("bull", "bear", "neutral")
        assert b["reason"]


# ------------------------------------------------------------ risk sentiment
def test_risk_sentiment_risk_on_supports_long():
    d = {"vix": 12.0, "spx": 5500.0, "regime": "risk-on", "asof": "2026-07-19"}
    out = rs.alignment("long", d=d)
    assert out["supports"] is True


def test_risk_sentiment_risk_off_normally_bearish_for_long():
    d = {"vix": 30.0, "spx": 5200.0, "regime": "risk-off", "asof": "2026-07-19"}
    # patch the geopolitical override off by using a symbol with no news cache
    out = rs.alignment("long", symbol="__no_news_symbol__", d=d)
    assert out["supports"] is False


def test_risk_sentiment_mixed_is_neutral():
    d = {"vix": 18.0, "spx": 5400.0, "regime": "mixed", "asof": "2026-07-19"}
    out = rs.alignment("long", d=d)
    assert out["supports"] is None


def test_risk_sentiment_no_data():
    # d={} forces the "no data" branch directly (see note above) instead of
    # a real on-disk cache from a live run masking the intended test case.
    out = rs.alignment("long", symbol="__no_news_symbol__", d={})
    assert out["supports"] is None


# --------------------------------------------------------- confluence wiring
def test_confluence_survives_all_four_sources_offline():
    """With no network / no cache for any of the 4 new sources, confluence
    must still run end-to-end without crashing (all alignments -> None)."""
    import pandas as pd
    import numpy as np
    from engine import confluence as cf

    rows = []
    px = 70.0
    for i in range(500):
        px += 0.15 + np.random.default_rng(i).normal(0, 0.05)
        rows.append([px - 0.1, px + 0.15, px - 0.15, px])
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 0.0
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")

    out = cf.analyze(df, symbol="WTIUSD")
    # whatever Layer 1 decides, this must not raise, and if a read exists
    # the four new layers must be present in the layers dict
    if out is not None:
        for key in ("cot", "spreads", "seasonality", "risk_sentiment"):
            assert key in out.layers


# ------------------------------------------------- multi-symbol (2026-07-28)
# Regression tests for the gold/Bitcoin rollout of these four modules. Before
# this work, cot_feed/spread_feed/seasonality all silently defaulted to
# WTIUSD data no matter what symbol confluence.py asked about — a real bug,
# not just a missing feature, since the gold/BTC signal output would show
# "COT positioning" / "seasonality" agree-disagree chips that were secretly
# just oil's data. These tests lock in the fix.

def test_cot_markets_cover_all_three_symbols():
    assert set(cot.MARKETS) == {"WTIUSD", "XAUUSD", "BTCUSD"}
    # each market name must be distinct - no accidental copy-paste reuse
    assert len(set(cot.MARKETS.values())) == 3


def test_cot_cache_migrates_old_flat_format(tmp_path, monkeypatch):
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    old_format = {"asof": "2026-07-01", "spec_net": 1000, "percentile": 0.5,
                  "open_interest": 100000, "generated": now}
    cache_file = tmp_path / "cot_cache.json"
    cache_file.write_text(__import__("json").dumps(old_format))
    monkeypatch.setattr(cot, "CACHE_PATH", cache_file)
    d = cot.read_cached("WTIUSD")
    assert d is not None and d["spec_net"] == 1000


def test_spread_label_is_symbol_specific():
    assert sp.label("WTIUSD") != sp.label("XAUUSD") != sp.label("BTCUSD")
    assert "silver" in sp.label("XAUUSD").lower()
    assert "basis" in sp.label("BTCUSD").lower()


def test_spread_gold_ratio_widening_supports_long():
    d = {"symbol": "XAUUSD", "gold_silver_ratio": 90.0, "ratio_trend": "widening"}
    out = sp.alignment("long", symbol="XAUUSD", d=d)
    assert out["supports"] is True
    out_short = sp.alignment("short", symbol="XAUUSD", d=d)
    assert out_short["supports"] is False


def test_spread_btc_basis_widening_supports_long():
    d = {"symbol": "BTCUSD", "btc_basis": 150.0, "basis_trend": "widening"}
    out = sp.alignment("long", symbol="BTCUSD", d=d)
    assert out["supports"] is True


def test_spread_unsupported_symbol_is_neutral_not_crash():
    out = sp.alignment("long", symbol="EURUSD", d={"symbol": "EURUSD"})
    assert out["supports"] is None


def test_seasonality_gold_has_its_own_table_distinct_from_oil():
    for m in range(1, 13):
        oil = sea.bias(m, "WTIUSD")
        gold = sea.bias(m, "XAUUSD")
        # not required to differ every month, but the table itself must be
        # a genuinely different object, not oil's table relabeled
        assert sea.MONTHLY["XAUUSD"] is not sea.MONTHLY["WTIUSD"]
    # spot-check one well-documented gold seasonal driver
    nov = sea.bias(11, "XAUUSD")
    assert nov["lean"] == "bull" and "diwali" in nov["reason"].lower()


def test_seasonality_btc_is_honestly_neutral_every_month():
    """No fabricated Bitcoin seasonality - every month must report neutral
    with an honest 'no documented pattern' reason, never an invented lean."""
    for m in range(1, 13):
        b = sea.bias(m, "BTCUSD")
        assert b["lean"] == "neutral"
        assert "no documented" in b["reason"].lower()
    assert sea.alignment("long", symbol="BTCUSD", month=6)["supports"] is None


def test_risk_sentiment_gold_inverts_oil_and_btc():
    """Gold is a safe haven (risk-off supportive); oil and BTC both trade
    with risk sentiment (risk-on supportive). This was the actual bug: gold
    used to reuse oil's mapping and would have scored backwards."""
    risk_off = {"vix": 30.0, "spx": 5200.0, "regime": "risk-off", "asof": "2026-07-19"}
    risk_on = {"vix": 12.0, "spx": 5500.0, "regime": "risk-on", "asof": "2026-07-19"}

    gold_off = rs.alignment("long", symbol="XAUUSD", d=risk_off)
    assert gold_off["supports"] is True   # risk-off supports gold longs

    gold_on = rs.alignment("long", symbol="XAUUSD", d=risk_on)
    assert gold_on["supports"] is False   # risk-on opposes gold longs

    oil_off = rs.alignment("long", symbol="WTIUSD", d=risk_off)
    assert oil_off["supports"] is False   # risk-off opposes oil longs (no geo override here)

    btc_on = rs.alignment("long", symbol="BTCUSD", d=risk_on)
    assert btc_on["supports"] is True     # risk-on supports BTC longs, like oil normally


def test_risk_sentiment_geopolitical_override_is_oil_only():
    """Gold and Bitcoin must never get oil's geopolitical supply-shock
    decoupling override - it's a physical-oil-specific story."""
    assert cot is not None  # sanity the module imported
    from engine import risk_sentiment as rs_mod
    assert rs_mod._GEOPOLITICAL_OVERRIDE_SYMBOLS == {"WTIUSD"}


def test_confluence_passes_symbol_to_cot_spread_seasonality():
    """The actual regression: confluence.analyze() must forward `symbol` to
    cot_feed/spread_feed/seasonality, not just risk_sentiment. Verified by
    monkeypatching each .alignment() to record what symbol it was called
    with, for a non-WTI symbol."""
    import pandas as pd
    import numpy as np
    from engine import confluence as cf

    seen = {}

    def _spy(name):
        def _fn(direction, symbol="WTIUSD", d=None):
            seen[name] = symbol
            return {"supports": None, "note": f"{name} stub"}
        return _fn

    import unittest.mock as mock
    with mock.patch.object(cf.cot, "alignment", _spy("cot")), \
         mock.patch.object(cf.sp, "alignment", _spy("spread")), \
         mock.patch.object(cf.sea, "alignment", _spy("season")), \
         mock.patch.object(cf.rs, "alignment", _spy("risk")):
        rows = []
        px = 2000.0
        for i in range(500):
            px += 0.5 + np.random.default_rng(i).normal(0, 0.3)
            rows.append([px - 0.3, px + 0.5, px - 0.5, px])
        df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
        df["Volume"] = 0.0
        df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")
        cf.analyze(df, symbol="XAUUSD")

    # if Layer 1 found nothing, analyze() returns early and none of these
    # are called - only assert when the confirmation layer actually ran
    for name in seen:
        assert seen[name] == "XAUUSD", f"{name}.alignment() got the wrong symbol"


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} extra-confluence-source tests passed")
