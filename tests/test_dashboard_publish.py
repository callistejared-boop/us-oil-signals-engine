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


# --- Day 11: "macro_advisory" payload key -----------------------------------------

def test_build_payload_includes_macro_advisory_from_last_recorded_assessment(monkeypatch):
    """dashboard_publish must read the LAST RECORDED macro assessment (from
    macro_history.jsonl, written by alert_signals.py's Stage-2 logging) —
    never a fresh live recompute — to avoid adding another round of
    provider fetches to every dashboard page load."""
    df = _make_df()
    calls = []

    def fake_last_assessment(symbol):
        calls.append(symbol)
        return {"labels": ["Risk-On"], "macro_confidence": "high", "evidence_quality": "medium"}

    monkeypatch.setattr(dp.macro, "last_assessment", fake_last_assessment)
    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["macro_advisory"] == {"labels": ["Risk-On"], "macro_confidence": "high",
                                         "evidence_quality": "medium"}
    assert calls == ["XAUUSD"]  # exactly one read, scoped to this symbol


def test_build_payload_macro_advisory_never_raises_when_history_read_fails(monkeypatch):
    def boom(symbol):
        raise RuntimeError("macro_history.jsonl unreadable")
    monkeypatch.setattr(dp.macro, "last_assessment", boom)
    df = _make_df()
    payload = dp.build_payload("WTIUSD", df=df)
    assert "macro_advisory" in payload
    assert "unavailable" in payload["macro_advisory"]


def test_build_payload_macro_advisory_none_when_no_history_yet(monkeypatch):
    monkeypatch.setattr(dp.macro, "last_assessment", lambda symbol: None)
    df = _make_df()
    payload = dp.build_payload("BTCUSD", df=df)
    assert payload["macro_advisory"] is None


# --- Day 12: "execution_summary" payload key --------------------------------------

def test_build_payload_includes_execution_summary_from_last_recorded_report(monkeypatch):
    """dashboard_publish must read the LAST RECORDED execution report (from
    execution_history.jsonl, written by alert_signals.py's Stage-2
    logging) — never a fresh simulate/recompute — same reasoning as
    macro_advisory above."""
    df = _make_df()
    calls = []

    def fake_last_for(symbol):
        calls.append(symbol)
        return {"execution_score": "Good", "cost_r": 0.08}

    monkeypatch.setattr(dp.exhist, "last_for", fake_last_for)
    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["execution_summary"] == {"execution_score": "Good", "cost_r": 0.08}
    assert calls == ["XAUUSD"]


def test_build_payload_execution_summary_never_raises_when_history_read_fails(monkeypatch):
    def boom(symbol):
        raise RuntimeError("execution_history.jsonl unreadable")
    monkeypatch.setattr(dp.exhist, "last_for", boom)
    df = _make_df()
    payload = dp.build_payload("WTIUSD", df=df)
    assert "execution_summary" in payload
    assert "unavailable" in payload["execution_summary"]


def test_build_payload_execution_summary_none_when_no_history_yet(monkeypatch):
    monkeypatch.setattr(dp.exhist, "last_for", lambda symbol: None)
    df = _make_df()
    payload = dp.build_payload("BTCUSD", df=df)
    assert payload["execution_summary"] is None


# --- Day 13: "paper_trading" payload key -------------------------------------

def test_build_payload_includes_paper_trading_snapshot(monkeypatch):
    """dashboard_publish must read PaperBroker's current snapshot (balances/
    positions/pending orders/recent activity) via the dedicated
    `pbroker.dashboard_snapshot()` helper — never assemble it inline."""
    df = _make_df()
    calls = []

    def fake_snapshot(account_id="paper-default", n_events=10):
        calls.append(account_id)
        return {"account_id": "paper-default", "balances": {"equity": 10050.0},
               "open_positions": [], "pending_orders": [], "recent_activity": []}

    monkeypatch.setattr(dp.pbroker, "dashboard_snapshot", fake_snapshot)
    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["paper_trading"]["balances"]["equity"] == 10050.0
    assert calls == ["paper-default"]


def test_build_payload_paper_trading_never_raises_when_broker_read_fails(monkeypatch):
    def boom(account_id="paper-default", n_events=10):
        raise RuntimeError("broker_history.jsonl unreadable")
    monkeypatch.setattr(dp.pbroker, "dashboard_snapshot", boom)
    df = _make_df()
    payload = dp.build_payload("WTIUSD", df=df)
    assert "paper_trading" in payload
    assert "unavailable" in payload["paper_trading"]


def test_build_payload_paper_trading_is_symbol_agnostic_same_account_every_symbol(monkeypatch):
    """The paper account is shared across every symbol this platform
    trades — the payload key is identical regardless of which symbol's
    dashboard row is being built, by design (see the Day 13 comment in
    dashboard_publish.py)."""
    df = _make_df()
    monkeypatch.setattr(dp.pbroker, "dashboard_snapshot",
                        lambda account_id="paper-default", n_events=10:
                        {"account_id": account_id, "balances": {"equity": 9999.0}})
    p1 = dp.build_payload("XAUUSD", df=df)
    p2 = dp.build_payload("BTCUSD", df=df)
    assert p1["paper_trading"] == p2["paper_trading"]


# --- Day 14: "data_health" payload key + publish-heartbeat write ------------

def test_build_payload_includes_data_health_snapshot(monkeypatch):
    df = _make_df()
    calls = []

    def fake_snapshot():
        calls.append(True)
        return {"overall_status": "operational", "counts": {"operational": 18}}

    monkeypatch.setattr(dp.dhfm, "dashboard_snapshot", fake_snapshot)
    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["data_health"]["overall_status"] == "operational"
    assert calls == [True]


def test_build_payload_data_health_never_raises_when_check_fails(monkeypatch):
    def boom():
        raise RuntimeError("data_health_history.jsonl unreadable")
    monkeypatch.setattr(dp.dhfm, "dashboard_snapshot", boom)
    df = _make_df()
    payload = dp.build_payload("WTIUSD", df=df)
    assert "data_health" in payload
    assert "unavailable" in payload["data_health"]


def test_build_payload_data_health_is_symbol_agnostic(monkeypatch):
    df = _make_df()
    monkeypatch.setattr(dp.dhfm, "dashboard_snapshot",
                        lambda: {"overall_status": "degraded", "counts": {}})
    p1 = dp.build_payload("XAUUSD", df=df)
    p2 = dp.build_payload("BTCUSD", df=df)
    assert p1["data_health"] == p2["data_health"]


def test_main_writes_dashboard_publish_heartbeat_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "ROOT", tmp_path)

    class FakeSettings:
        pass

    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD"])
    monkeypatch.setattr(dp, "build_payload", lambda symbol, s=None: {
        "signal": {"has_setup": False}})
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: True)

    dp.main()

    hb_path = tmp_path / "dashboard_publish_heartbeat.json"
    assert hb_path.exists()
    import json
    row = json.loads(hb_path.read_text(encoding="utf-8"))
    assert "published_at" in row
    assert row["symbols_published"] == ["XAUUSD"]


def test_main_does_not_write_heartbeat_when_nothing_published(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "ROOT", tmp_path)

    class FakeSettings:
        pass

    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD"])
    monkeypatch.setattr(dp, "build_payload", lambda symbol, s=None: {
        "signal": {"has_setup": False}})
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: False)

    dp.main()

    hb_path = tmp_path / "dashboard_publish_heartbeat.json"
    assert not hb_path.exists()


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)


# --------------------------------------------------------------------------
# V2.2 Priority 5 Item 2: confluence_score/regime_quality fields + the
# ranked-opportunities / why-not views main() attaches to each payload.
# --------------------------------------------------------------------------

def test_build_payload_signal_carries_confluence_score_and_regime_quality(monkeypatch):
    """These two fields are the ONLY new surface area build_payload() gained
    for this Item -- opportunity_ranking.candidate_from_dashboard_payload()
    reads them directly, so they must be present and correctly sourced
    whenever a setup exists."""
    df = _make_df()
    fake_sig = signals.Signal(
        time=df.index[-1], direction="long", entry=100.0, stop=99.0,
        target=103.0, rr=3.0, confidence=70, symbol="XAUUSD", tier="confirmed")
    monkeypatch.setattr(dp.signals, "analyze", lambda *a, **k: fake_sig)

    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["signal"]["has_setup"] is True
    assert "confluence_score" in payload["signal"]
    assert "regime_quality" in payload["signal"]
    assert isinstance(payload["signal"]["confluence_score"], (int, float))
    assert isinstance(payload["signal"]["regime_quality"], (int, float))


def test_build_payload_regime_quality_survives_regime_engine_failure(monkeypatch):
    """d_regime is now initialized before the try block specifically so a
    regime_engine.classify() failure can't leave it undefined -- regression
    guard for exactly that NameError risk."""
    df = _make_df()
    fake_sig = signals.Signal(
        time=df.index[-1], direction="long", entry=100.0, stop=99.0,
        target=103.0, rr=3.0, confidence=70, symbol="XAUUSD", tier="confirmed")
    monkeypatch.setattr(dp.signals, "analyze", lambda *a, **k: fake_sig)
    monkeypatch.setattr(dp.rgeng, "classify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    payload = dp.build_payload("XAUUSD", df=df)
    assert payload["signal"]["has_setup"] is True
    assert payload["signal"]["regime_quality"] == 0


def _fake_payload_with_setup(symbol, overall_confidence, confluence_score=80, regime_quality=70):
    return {
        "symbol": symbol,
        "signal": {
            "has_setup": True,
            "direction": "long",
            "confluence_score": confluence_score,
            "regime_quality": regime_quality,
            "grade": {"letter": "B"},
            "confidence_assessment": {
                "overall_confidence": overall_confidence,
                "calibrated_probability": None,
                "is_calibrated": False,
            },
        },
    }


def test_main_attaches_opportunity_rank_across_symbols(monkeypatch):
    """Two symbols with qualifying setups this cycle -- main() must rank
    them relative to EACH OTHER (not independently), matching
    opportunity_ranking.rank_opportunities()'s own ordering."""
    class FakeSettings:
        pass

    fake_payloads = {
        "XAUUSD": _fake_payload_with_setup("XAUUSD", overall_confidence=90),
        "WTIUSD": _fake_payload_with_setup("WTIUSD", overall_confidence=40),
    }
    published = {}

    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD", "WTIUSD"])
    monkeypatch.setattr(dp, "build_payload", lambda symbol, s=None: fake_payloads[symbol])
    monkeypatch.setattr(dp.wn, "why_not_now", lambda symbol, **k: {"symbol": symbol, "answer_source": "test"})
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: published.setdefault(symbol, payload) or True)

    dp.main()

    assert published["XAUUSD"]["opportunity_rank"]["rank"] == 1
    assert published["WTIUSD"]["opportunity_rank"]["rank"] == 2
    assert published["XAUUSD"]["opportunity_rank"]["of"] == 2
    assert published["XAUUSD"]["why_not"]["symbol"] == "XAUUSD"


def test_main_opportunity_rank_none_when_no_setup(monkeypatch):
    class FakeSettings:
        pass

    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD"])
    monkeypatch.setattr(dp, "build_payload", lambda symbol, s=None: {"signal": {"has_setup": False}})
    monkeypatch.setattr(dp.wn, "why_not_now", lambda symbol, **k: {"symbol": symbol})
    published = {}
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: published.setdefault(symbol, payload) or True)

    dp.main()

    assert published["XAUUSD"]["opportunity_rank"]["rank"] is None
    assert published["XAUUSD"]["opportunity_rank"]["of"] == 0


def test_main_still_isolates_build_failures_from_ranking(monkeypatch):
    """A build_payload() failure on one symbol must still exclude it from
    both publishing AND ranking -- same isolation guarantee main()'s own
    docstring has always claimed, now verified across the two-pass
    restructure this Item introduced."""
    class FakeSettings:
        pass

    def fake_build(symbol, s=None):
        if symbol == "BTCUSD":
            raise RuntimeError("feed down")
        return _fake_payload_with_setup(symbol, overall_confidence=77)

    published = {}
    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD", "BTCUSD"])
    monkeypatch.setattr(dp, "build_payload", fake_build)
    monkeypatch.setattr(dp.wn, "why_not_now", lambda symbol, **k: {"symbol": symbol})
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: published.setdefault(symbol, payload) or True)

    dp.main()

    assert "BTCUSD" not in published
    assert published["XAUUSD"]["opportunity_rank"]["of"] == 1


def test_main_ranking_never_raises_even_if_opportunity_ranking_breaks(monkeypatch):
    class FakeSettings:
        pass

    monkeypatch.setattr(dp.config, "load", lambda: FakeSettings())
    monkeypatch.setattr(dp.markets, "symbols", lambda s: ["XAUUSD"])
    monkeypatch.setattr(dp, "build_payload",
                        lambda symbol, s=None: _fake_payload_with_setup(symbol, overall_confidence=77))
    monkeypatch.setattr(dp.oprank, "rank_opportunities",
                        lambda candidates: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(dp.wn, "why_not_now", lambda symbol, **k: {"symbol": symbol})
    published = {}
    monkeypatch.setattr(dp, "publish", lambda payload, symbol: published.setdefault(symbol, payload) or True)

    dp.main()   # must not raise

    assert published["XAUUSD"]["opportunity_rank"]["rank"] is None
