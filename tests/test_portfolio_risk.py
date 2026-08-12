"""Offline tests for the Day 3 centralized Portfolio Risk Engine
(engine/portfolio_risk.py). All rows are injected directly (same pattern as
tests/test_risk_guard.py) so nothing here touches disk or the network.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import portfolio_risk as pr   # noqa: E402
from engine import risk, config          # noqa: E402


class _Settings:
    portfolio_equity = 10000.0
    portfolio_risk_mode = "block"
    portfolio_max_risk_pct = 6.0
    portfolio_day_stop_r = 2.0
    portfolio_max_drawdown_r = 6.0
    portfolio_max_directional = 2
    correlation_high_threshold = 0.6


def _open(symbol, direction, entry=2000.0, stop=1995.0, opened="2026-08-01T00:00:00"):
    return {"status": "open", "symbol": symbol, "direction": direction,
            "entry": entry, "stop": stop, "opened": opened}


def test_config_cap_matches_risk_module():
    """Regression guard: engine.risk.MAX_PORTFOLIO_RISK_PCT and
    Settings.portfolio_max_risk_pct are two literals by design (see the
    comment in engine/config.py) — this fails loudly if they ever drift."""
    assert config.Settings().portfolio_max_risk_pct == risk.MAX_PORTFOLIO_RISK_PCT


def test_clean_book_allows():
    v = pr.evaluate("XAUUSD", "long", 2000.0, 1990.0, settings=_Settings(), rows=[])
    assert v["allow"] is True
    assert v["category"] is None


def test_exposure_cap_breach_blocks():
    # DEFAULT_RISK_PCT=1% fixed sizing -> each position risks exactly $100 of
    # $10,000 equity regardless of stop distance. 6 open + 1 candidate = 7%
    # of equity, which breaches the 6% cap.
    rows = [_open("XAUUSD", "long") for _ in range(6)]
    v = pr.evaluate("WTIUSD", "long", 80.0, 79.0, settings=_Settings(), rows=rows)
    assert v["allow"] is False
    assert v["would_block"] is True
    assert v["category"] == pr.PORTFOLIO_EXPOSURE_EXCEEDED


def test_warn_mode_flags_but_does_not_block():
    s = _Settings()
    s.portfolio_risk_mode = "warn"
    rows = [_open("XAUUSD", "long") for _ in range(6)]
    v = pr.evaluate("WTIUSD", "long", 80.0, 79.0, settings=s, rows=rows)
    assert v["allow"] is True            # shadow mode never blocks
    assert v["would_block"] is True       # but the violation is still visible
    assert v["category"] == pr.PORTFOLIO_EXPOSURE_EXCEEDED


def test_directional_concentration_blocks():
    rows = [_open("XAUUSD", "long"), _open("BTCUSD", "long", entry=60000, stop=59500)]
    v = pr.evaluate("WTIUSD", "long", 80.0, 79.0, settings=_Settings(), rows=rows)
    assert v["allow"] is False
    assert v["category"] == pr.TRADE_FREQUENCY_CONTROL


def test_directional_concentration_at_exact_cap_allows(monkeypatch):
    """max_directional=2: 1 existing + this candidate = 2, at (not over) the
    cap, must still be allowed. Correlation is monkeypatched to a neutral
    reading purely to keep this test offline/deterministic — it is not what
    this test is checking."""
    monkeypatch.setattr(pr.corr_dyn, "get_correlation",
                        lambda a, b, settings=None, **kw: {
                            "corr": 0.0, "n": 0, "sample": "test",
                            "method": "test", "source": "test"})
    rows = [_open("XAUUSD", "long")]
    v = pr.evaluate("WTIUSD", "long", 80.0, 79.0, settings=_Settings(), rows=rows)
    assert v["allow"] is True


def test_correlation_too_high_blocks(monkeypatch):
    rows = [_open("XAUUSD", "long")]
    monkeypatch.setattr(pr.corr_dyn, "get_correlation",
                        lambda a, b, settings=None, **kw: {
                            "corr": 0.8, "n": 40, "sample": "ok",
                            "method": "test", "source": "test"})
    v = pr.evaluate("BTCUSD", "long", 60000.0, 59500.0, settings=_Settings(), rows=rows)
    assert v["allow"] is False
    assert v["category"] == pr.CORRELATION_TOO_HIGH
    assert v["detail"]["correlation"]["against"] == "XAUUSD"


def test_correlation_low_does_not_block(monkeypatch):
    rows = [_open("XAUUSD", "long")]
    monkeypatch.setattr(pr.corr_dyn, "get_correlation",
                        lambda a, b, settings=None, **kw: {
                            "corr": 0.1, "n": 40, "sample": "ok",
                            "method": "test", "source": "test"})
    v = pr.evaluate("BTCUSD", "long", 60000.0, 59500.0, settings=_Settings(), rows=rows)
    assert v["allow"] is True


def test_opposite_direction_skips_correlation_check(monkeypatch):
    """Correlated exposure only matters when both positions bet the SAME
    direction; a hedge (short one, long the other) is not concentration."""
    rows = [_open("XAUUSD", "short")]
    monkeypatch.setattr(pr.corr_dyn, "get_correlation",
                        lambda a, b, settings=None, **kw: {
                            "corr": 0.95, "n": 40, "sample": "ok",
                            "method": "test", "source": "test"})
    v = pr.evaluate("BTCUSD", "long", 60000.0, 59500.0, settings=_Settings(), rows=rows)
    assert v["allow"] is True


def test_portfolio_day_stop_blocks():
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [
        {"status": "loss", "result_r": -1.2, "closed": today + "T09:00:00", "symbol": "XAUUSD"},
        {"status": "loss", "result_r": -1.2, "closed": today + "T11:00:00", "symbol": "WTIUSD"},
    ]
    v = pr.evaluate("BTCUSD", "long", 60000.0, 59500.0, settings=_Settings(), rows=rows)
    assert v["allow"] is False
    assert v["category"] == pr.DRAWDOWN_PROTECTION
    assert "PORTFOLIO DAY STOP" in v["reason"]


def test_portfolio_day_stop_ignores_yesterday():
    rows = [
        {"status": "loss", "result_r": -5.0, "closed": "2026-01-01T09:00:00", "symbol": "XAUUSD"},
    ]
    v = pr.evaluate("BTCUSD", "long", 60000.0, 59500.0, settings=_Settings(), rows=rows)
    assert v["allow"] is True


def test_trailing_drawdown_cap_blocks():
    # 10 wins (+1R) then 7 losses (-1R), pooled across symbols, on dates
    # that are NOT today (so the day-stop check doesn't fire first) but are
    # recent enough (2-3 days back) to survive the V2.2
    # portfolio_drawdown_max_age_days staleness filter regardless of when
    # this test suite is actually run.
    # Peak-to-trough: cum climbs to +10, then drops to +3 -> dd = 7R > 6R cap.
    d1 = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    d2 = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    rows = []
    for i in range(10):
        rows.append({"status": "win", "result_r": 1.0,
                    "closed": f"{d1}T{i % 23:02d}:00:00",
                    "symbol": "XAUUSD" if i % 2 else "WTIUSD"})
    for i in range(7):
        rows.append({"status": "loss", "result_r": -1.0,
                    "closed": f"{d2}T{i % 23:02d}:00:00", "symbol": "BTCUSD"})
    v = pr.evaluate("EURUSD", "long", 1.10, 1.09, settings=_Settings(), rows=rows)
    assert v["allow"] is False
    assert v["category"] == pr.DRAWDOWN_PROTECTION
    assert "drawdown" in v["reason"].lower()


def test_fail_open_on_bad_input():
    v = pr.evaluate("XAUUSD", "long", "not-a-number", 1990.0, settings=_Settings(), rows=[])
    assert v["allow"] is True
    assert "failing open" in v["reason"]


def test_line_helper_clear():
    v = pr.evaluate("XAUUSD", "long", 2000.0, 1990.0, settings=_Settings(), rows=[])
    assert pr.line(v) == "portfolio: clear"


def test_line_helper_rejected():
    rows = [_open("XAUUSD", "long") for _ in range(6)]
    v = pr.evaluate("WTIUSD", "long", 80.0, 79.0, settings=_Settings(), rows=rows)
    assert "REJECTED" in pr.line(v)


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
