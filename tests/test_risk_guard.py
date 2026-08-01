"""Offline tests for the risk circuit breaker + forward-test scoreboard."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import risk_guard as rg  # noqa: E402

TODAY = "2026-07-17"


def _t(status="loss", r=-1.0, closed=TODAY + "T10:00:00", symbol="WTIUSD"):
    return {"status": status, "result_r": r, "closed": closed, "symbol": symbol}


def test_day_loss_lock_triggers_at_minus_2r():
    rows = [_t(r=-1.0), _t(r=-1.0)]
    v = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert v["locked"] and "DAILY LOSS" in v["reason"]
    assert v["day_r"] == -2.0


def test_day_loss_only_counts_today():
    rows = [_t(r=-3.0, closed="2026-07-16T10:00:00")]  # yesterday's pain
    v = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert not v["locked"]


def test_wins_offset_losses():
    rows = [_t(r=-1.5), _t(status="win", r=2.0)]
    v = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert not v["locked"] and v["day_r"] == 0.5


def test_position_cap_blocks_stacking():
    rows = [{"status": "open", "symbol": "WTIUSD"}]
    v = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert v["locked"] and "POSITION CAP" in v["reason"]


def test_position_cap_is_per_symbol():
    rows = [{"status": "open", "symbol": "XAUUSD"}]
    v = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert not v["locked"]


def test_daily_loss_lock_is_per_symbol():
    """Regression test for the 2026-07-28 fix: a -3R day on gold must NOT
    lock oil (or any other symbol) out of new signals."""
    rows = [_t(r=-1.5, symbol="XAUUSD"), _t(r=-1.5, symbol="XAUUSD")]
    gold = rg.evaluate("XAUUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    oil = rg.evaluate("WTIUSD", rows=rows, max_daily_loss_r=2, max_open=1, today=TODAY)
    assert gold["locked"] and "DAILY LOSS" in gold["reason"]
    assert not oil["locked"]
    assert oil["day_r"] == 0.0   # oil's own tally, unaffected by gold's loss


def test_failsafe_on_garbage():
    v = rg.evaluate("WTIUSD", rows=[{"weird": True}], max_daily_loss_r=2,
                    max_open=1, today=TODAY)
    assert v["locked"] is False


def test_forward_report_builds_and_verdicts():
    import forward_report as fr
    # realistic interleaving: 2 wins then 1 loss, repeated (dd stays ~1R)
    rows = []
    day = 0
    for block in range(10):
        for r, st in ((2.0, "win"), (2.0, "win"), (-1.0, "loss")):
            day += 1
            rows.append({"status": st, "result_r": r,
                         "closed": f"2026-07-17T{(day % 23) + 1:02d}:00:00"
                         if day <= 23 else f"2026-07-18T{(day % 23) + 1:02d}:00:00"})
    text, kpi = fr.build(rows=rows, window_start="2026-07-17", target=30, symbol=None)
    assert kpi["n"] == 30 and kpi["exp"] == 1.0
    assert "VALIDATED" in text
    # the same profits with 10 CONSECUTIVE losses (dd 10R) must NOT validate
    bad = ([{"status": "win", "result_r": 2.0, "closed": "2026-07-18T10:00:00"}] * 20
           + [{"status": "loss", "result_r": -1.0, "closed": "2026-07-19T10:00:00"}] * 10)
    text_bad, _ = fr.build(rows=bad, window_start="2026-07-17", target=30, symbol=None)
    assert "VALIDATED" not in text_bad  # drawdown gate correctly blocks it
    text2, kpi2 = fr.build(rows=rows[:5], window_start="2026-07-17", target=30, symbol=None)
    assert "IN PROGRESS" in text2 and kpi2["n"] == 5


def test_forward_report_excludes_other_symbols_by_default():
    import forward_report as fr
    rows = [
        {"status": "win", "result_r": 3.0, "closed": "2026-07-17T06:15:00",
         "symbol": "WTIUSD"},
        {"status": "loss", "result_r": -1.0, "closed": "2026-07-17T11:15:00",
         "symbol": "WTIUSD"},
        {"status": "win", "result_r": 5.0, "closed": "2026-07-17T12:00:00",
         "symbol": "BTCUSD"},   # legacy pre-pivot trade - must be excluded
        {"status": "open", "symbol": "BTCUSD"},   # legacy stale open position
        {"status": "open", "symbol": "WTIUSD"},
    ]
    text, kpi = fr.build(rows=rows, window_start="2026-07-17", target=30)
    assert kpi["n"] == 2   # only the two WTIUSD closes count
    assert kpi["net"] == 2.0   # +3 -1, the BTC +5 must NOT be included
    assert "1 open now" in text   # only the WTIUSD open position counts
    assert "legacy trade(s)" in text   # the stale BTC open is called out


def test_forward_report_drawdown():
    import forward_report as fr
    assert fr.drawdown_r([1, -1, -1, 2]) == 2.0
    assert fr.drawdown_r([]) == 0.0


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} risk-guard tests passed")
