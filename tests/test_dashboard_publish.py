"""Regression tests for the 2026-07-28 multi-symbol migration of
dashboard_publish.py. Before this fix, build_payload() only worked for the
hardcoded WTIUSD SYMBOL global and would raise NameError for any other
symbol once that global was removed mid-refactor. These tests exercise the
full build_payload() path (with a synthetic OHLCV df, no network) for all
three target symbols and assert the per-symbol fields are wired correctly.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import dashboard_publish as dp  # noqa: E402
from engine import signals  # noqa: E402


def _make_df(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    closes = 2000 + rng.normal(0, 3, n).cumsum()
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    return pd.DataFrame({
        "Open": closes, "High": closes + 1.5, "Low": closes - 1.5,
        "Close": closes, "Volume": np.ones(n),
    }, index=idx)


@pytest.mark.parametrize("symbol", ["WTIUSD", "XAUUSD", "BTCUSD"])
def test_build_payload_no_crash_and_correct_identity(symbol):
    """Every configured symbol must build a payload (no NameError from the
    old SYMBOL global) and carry its own symbol/display_name."""
    df = _make_df()
    payload = dp.build_payload(symbol, df=df)
    assert payload["symbol"] == symbol
    assert payload["display_name"] == dp._DISPLAY_NAMES[symbol]
    assert "signal" in payload and "has_setup" in payload["signal"]


@pytest.mark.parametrize("symbol", ["WTIUSD", "XAUUSD", "BTCUSD"])
def test_signal_basis_note_matches_symbol(monkeypatch, symbol):
    """When a setup is present, its basis_note must be the symbol-specific
    text, not the old hardcoded WTI-only string."""
    df = _make_df()

    fake_sig = signals.Signal(
        time=df.index[-1], direction="long", entry=100.0, stop=99.0,
        target=103.0, rr=3.0, confidence=70, symbol=symbol,
        tier="confirmed",
    )
    monkeypatch.setattr(dp.signals, "analyze", lambda *a, **k: fake_sig)

    payload = dp.build_payload(symbol, df=df)
    assert payload["signal"]["has_setup"] is True
    assert payload["signal"]["basis_note"] == dp._BASIS_NOTES[symbol]
    # sanity: oil's note must never leak onto gold/BTC payloads
    if symbol != "WTIUSD":
        assert "USOIL" not in payload["signal"]["basis_note"]


def test_fundamentals_scoped_per_symbol(monkeypatch):
    """Regression test for a second bug found during the same refactor:
    _fundamentals() used to call ff.load_feed() with no symbol, which
    defaults to WTIUSD — so gold/BTC payloads silently showed oil's
    fundamentals feed. Must now request each symbol's own feed."""
    from engine import fundamentals_feed as ff

    requested = {}

    def fake_load_feed(symbol="WTIUSD", *a, **k):
        requested["symbol"] = symbol
        return {"asof": f"2099-01-01-{symbol}", "net_bias": f"bias-for-{symbol}"}

    monkeypatch.setattr(dp.ff, "load_feed", fake_load_feed)
    monkeypatch.setattr(dp.ff, "render_lines", lambda feed: [feed["net_bias"]])

    for symbol in ("WTIUSD", "XAUUSD", "BTCUSD"):
        asof, bias, lines, live = dp._fundamentals(symbol)
        assert requested["symbol"] == symbol
        assert bias == f"bias-for-{symbol}"
        assert asof == f"2099-01-01-{symbol}"


def test_fundamentals_fallback_is_not_fabricated(monkeypatch):
    """When no cached feed exists for a symbol, the fallback must say so
    honestly (no invented 'bullish' claim, no stale oil-only date)."""
    monkeypatch.setattr(dp.ff, "load_feed", lambda symbol="WTIUSD", *a, **k: None)
    asof, bias, lines, live = dp._fundamentals("BTCUSD")
    assert live is False
    assert bias == "neutral"
    assert any("BTCUSD" in l for l in lines)


def test_publish_includes_symbol_in_rpc_body(monkeypatch):
    """publish() must send p_symbol so the RPC upserts the right row."""
    captured = {}

    class FakeResp:
        def read(self):
            return b"{}"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=20):
        import json
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(dp.os.environ, "get", lambda k, d=None: "test-secret" if k == "DASHBOARD_PUBLISH_SECRET" else d)
    monkeypatch.setattr(dp.urllib.request, "urlopen", fake_urlopen)

    ok = dp.publish({"foo": "bar"}, "XAUUSD")
    assert ok is True
    assert captured["body"]["p_symbol"] == "XAUUSD"
    assert captured["body"]["p_secret"] == "test-secret"


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
