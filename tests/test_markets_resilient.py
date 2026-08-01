"""Offline tests for engine/markets.py's fetch_resilient() — the cache-backed
fallback added so the dashboard can survive a live-feed outage (both
TwelveData and yfinance down) instead of going blank. No network calls:
markets.fetch is monkeypatched directly.
"""
import pathlib
import sys
import time

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import markets  # noqa: E402


class _Settings:
    twelvedata_api_key = ""


def _bars(n=10):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({
        "Open": px, "High": [p + 0.2 for p in px], "Low": [p - 0.2 for p in px],
        "Close": px, "Volume": [0.0] * n,
    }, index=idx)


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Never touch the real .cache/ dir from tests."""
    monkeypatch.setattr(markets, "CACHE_DIR", tmp_path / ".cache")
    yield


def test_live_success_marks_not_stale_and_writes_cache(monkeypatch):
    df = _bars()
    monkeypatch.setattr(markets, "fetch", lambda symbol, settings, bars=3000: df)
    out = markets.fetch_resilient("WTIUSD", _Settings())
    assert out.attrs["stale"] is False
    assert out.attrs["stale_since"] == 0
    assert markets._cache_path("WTIUSD").exists()


def test_live_failure_falls_back_to_cache_and_marks_stale(monkeypatch):
    df = _bars()
    # First call succeeds and seeds the cache.
    monkeypatch.setattr(markets, "fetch", lambda symbol, settings, bars=3000: df)
    markets.fetch_resilient("WTIUSD", _Settings())

    # Second call: live fetch now fails — must serve the cached snapshot.
    def _boom(symbol, settings, bars=3000):
        raise RuntimeError("both TwelveData and yfinance unreachable")
    monkeypatch.setattr(markets, "fetch", _boom)

    out = markets.fetch_resilient("WTIUSD", _Settings())
    assert out.attrs["stale"] is True
    assert out.attrs["stale_since"] >= 0
    assert list(out["Close"]) == list(df["Close"])


def test_live_failure_with_no_cache_raises(monkeypatch):
    def _boom(symbol, settings, bars=3000):
        raise RuntimeError("no live source")
    monkeypatch.setattr(markets, "fetch", _boom)
    with pytest.raises(RuntimeError):
        markets.fetch_resilient("EURUSD", _Settings())


def test_cache_is_per_symbol(monkeypatch):
    wti_df = _bars(5)
    xau_df = _bars(7)
    calls = {"symbol": None}

    def _fake_fetch(symbol, settings, bars=3000):
        calls["symbol"] = symbol
        return wti_df if symbol == "WTIUSD" else xau_df

    monkeypatch.setattr(markets, "fetch", _fake_fetch)
    markets.fetch_resilient("WTIUSD", _Settings())
    markets.fetch_resilient("XAUUSD", _Settings())
    assert markets._cache_path("WTIUSD").exists()
    assert markets._cache_path("XAUUSD").exists()

    def _boom(symbol, settings, bars=3000):
        raise RuntimeError("outage")
    monkeypatch.setattr(markets, "fetch", _boom)
    out_wti = markets.fetch_resilient("WTIUSD", _Settings())
    out_xau = markets.fetch_resilient("XAUUSD", _Settings())
    assert len(out_wti) == 5
    assert len(out_xau) == 7


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    import inspect
    for fn in fns:
        sig = inspect.signature(fn)
        if "monkeypatch" in sig.parameters or "tmp_path" in sig.parameters:
            print(f"  skip (needs pytest fixtures) {fn.__name__}")
            continue
        fn()
        print("  ok ", fn.__name__)
    print("\nrun via pytest for full fixture support")
