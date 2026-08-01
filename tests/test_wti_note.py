"""Regression tests for the 2026-07-28 multi-symbol generalization of
wti_note.py. Before this fix, build() only ever produced an oil-branded
note (hardcoded "WTIUSD" everywhere, hardcoded "US OIL" title, hardcoded
WTI basis note and oil-specific risks section) regardless of what symbol
was passed. It also shared dashboard_publish.py's fundamentals bug: calling
ff.load_feed() with no symbol always returned oil's feed.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wti_note as wn  # noqa: E402
from engine import config  # noqa: E402


def _make_df(n=6000, seed=11):
    rng = np.random.default_rng(seed)
    closes = 2000 + rng.normal(0, 3, n).cumsum()
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    return pd.DataFrame({
        "Open": closes, "High": closes + 1.5, "Low": closes - 1.5,
        "Close": closes, "Volume": np.ones(n),
    }, index=idx)


@pytest.mark.parametrize("symbol,expected_label", [
    ("WTIUSD", "US OIL"), ("XAUUSD", "GOLD"), ("BTCUSD", "BITCOIN"),
])
def test_build_titles_and_basis_note_are_symbol_specific(symbol, expected_label):
    df = _make_df()
    s = config.load()
    note = wn.build(df, s, symbol)
    assert f"{expected_label} - INSTITUTIONAL TRADE NOTE" in note
    # oil's basis text must never leak onto gold/BTC notes
    if symbol != "WTIUSD":
        assert "USOIL" not in note


def test_fundamentals_scoped_per_symbol(monkeypatch):
    """Same class of bug fixed in dashboard_publish.py: _fundamentals() used
    to always call ff.load_feed() (no arg -> defaults to WTIUSD)."""
    requested = {}

    def fake_load_feed(symbol="WTIUSD", *a, **k):
        requested["symbol"] = symbol
        return {"asof": f"2099-01-01-{symbol}", "net_bias": f"bias-for-{symbol}"}

    monkeypatch.setattr(wn.ff, "load_feed", fake_load_feed)
    monkeypatch.setattr(wn.ff, "render_lines", lambda feed: [feed["net_bias"]])

    for symbol in ("WTIUSD", "XAUUSD", "BTCUSD"):
        asof, bias, lines, live = wn._fundamentals(symbol)
        assert requested["symbol"] == symbol
        assert bias == f"bias-for-{symbol}"


def test_fundamentals_fallback_preserves_wti_but_not_others(monkeypatch):
    """WTIUSD keeps its existing curated static fallback; other symbols get
    an honest 'no feed yet' line instead of a fabricated bias."""
    monkeypatch.setattr(wn.ff, "load_feed", lambda symbol="WTIUSD", *a, **k: None)
    asof, bias, lines, live = wn._fundamentals("WTIUSD")
    assert bias == wn.FUND_BIAS and lines == wn.FUNDAMENTALS
    asof2, bias2, lines2, live2 = wn._fundamentals("XAUUSD")
    assert bias2 == "neutral"
    assert any("XAUUSD" in l for l in lines2)


def test_main_defaults_to_wti_note_txt_filename(tmp_path, monkeypatch):
    """main() with no args must still write wti_note.txt (not a renamed
    file), preserving compatibility with wti_hourly.py, the .bat launchers,
    and command_center.py, which all look for that exact filename."""
    df = _make_df()
    monkeypatch.setattr(wn, "ROOT", tmp_path)
    monkeypatch.setattr(wn.markets, "fetch", lambda symbol, s: df)
    monkeypatch.setattr(sys, "argv", ["wti_note.py"])
    wn.main()
    assert (tmp_path / "wti_note.txt").exists()
    assert not (tmp_path / "note_xauusd.txt").exists()


def test_main_writes_symbol_specific_filename_for_other_symbols(tmp_path, monkeypatch):
    df = _make_df()
    monkeypatch.setattr(wn, "ROOT", tmp_path)
    monkeypatch.setattr(wn.markets, "fetch", lambda symbol, s: df)
    monkeypatch.setattr(sys, "argv", ["wti_note.py", "--symbol=XAUUSD"])
    wn.main()
    assert (tmp_path / "note_xauusd.txt").exists()
    assert not (tmp_path / "wti_note.txt").exists()


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
