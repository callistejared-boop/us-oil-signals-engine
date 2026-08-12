"""Regression tests for V2.2 Priority 2 Item 7 (TECHNICAL_DEBT_REGISTER.md
P0 Item 3): journal.make_ref() must never hand out an id that already
belongs to an existing trades.json row. Originally flagged
DAY10_NEXT_DAY_READINESS_REPORT.md, confirmed with 5 live duplicates by
Research & Validation Cycle #2 (RESEARCH_VALIDATION_CYCLE_2_REPORT.md
Sec.3.1) — no regression test guarded this until now.
"""
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import journal as J  # noqa: E402


class _Sig:
    symbol = "XAUUSD"
    direction = "long"
    entry = 2000.0
    stop = 1990.0
    target = 2030.0
    rr = 3.0
    confidence = 80


class _SigAlt:
    """Same symbol + same candle timestamp as _Sig, but a genuinely
    different setup (different entry) — exactly the live collision
    scenario engine/edge_investigation.py's duplicate-id check documents:
    a different entry price bypasses is_open()'s own dedup check, so two
    distinct signals for the same symbol/timestamp both reach
    log_signal()."""
    symbol = "XAUUSD"
    direction = "long"
    entry = 2050.0
    stop = 2040.0
    target = 2080.0
    rr = 3.0
    confidence = 75


def test_make_ref_returns_base_ref_when_no_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    assert J.make_ref("XAUUSD", when) == "XAUUSD-2026-08-03T10:00:00"


def test_make_ref_appends_dup_suffix_on_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    base = J.make_ref("XAUUSD", when)
    (tmp_path / "t.json").write_text(
        '[{"id": "%s", "status": "open"}]' % base, encoding="utf-8")
    ref2 = J.make_ref("XAUUSD", when)
    assert ref2 == f"{base}-dup2"
    assert ref2 != base


def test_make_ref_increments_dup_suffix_for_repeated_collisions(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    base = J.make_ref("XAUUSD", when)
    import json
    (tmp_path / "t.json").write_text(json.dumps([
        {"id": base, "status": "open"},
        {"id": f"{base}-dup2", "status": "open"},
        {"id": f"{base}-dup3", "status": "open"},
    ]), encoding="utf-8")
    assert J.make_ref("XAUUSD", when) == f"{base}-dup4"


def test_make_ref_only_disambiguates_the_colliding_symbol(tmp_path, monkeypatch):
    """A collision on XAUUSD-<ts> must not affect WTIUSD-<ts> at the same
    timestamp — the check is scoped by the full base ref (symbol included),
    not by timestamp alone."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    xau_base = J.make_ref("XAUUSD", when)
    (tmp_path / "t.json").write_text(
        '[{"id": "%s", "status": "open"}]' % xau_base, encoding="utf-8")
    assert J.make_ref("WTIUSD", when) == "WTIUSD-2026-08-03T10:00:00"


def test_make_ref_idempotent_across_repeated_calls_before_any_write(tmp_path, monkeypatch):
    """The invariant the whole cross-reference design depends on:
    alert_signals.py computes `trade_ref = journal.make_ref(sym, when)`
    BEFORE calling journal.log_signal(), which internally calls
    make_ref(sym, when) again to build the row's own `id`. Nothing writes
    to trades.json between those two calls, so both must return the exact
    same (possibly disambiguated) string, or id/confluence_ref/
    confidence_ref/etc. would silently drift apart."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    when = pd.Timestamp("2026-08-03 10:00:00")
    ref_a = J.make_ref("XAUUSD", when)
    ref_b = J.make_ref("XAUUSD", when)
    assert ref_a == ref_b

    # Same check again, but with a pre-existing collision on disk, so the
    # disambiguated (suffixed) case is covered too.
    (tmp_path / "t.json").write_text(
        '[{"id": "%s", "status": "open"}]' % ref_a, encoding="utf-8")
    ref_c = J.make_ref("XAUUSD", when)
    ref_d = J.make_ref("XAUUSD", when)
    assert ref_c == ref_d == f"{ref_a}-dup2"


def test_log_signal_two_distinct_signals_same_symbol_same_candle_get_unique_ids(
    tmp_path, monkeypatch,
):
    """The literal live bug, reproduced end-to-end: two distinct signals
    for the same symbol, logged against the same candle timestamp, must
    not collide in trades.json — this is exactly the scenario that
    produced 5 duplicate ids in production."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    from engine import bias_adjust as ba
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))

    when = pd.Timestamp("2026-08-03 10:00:00")
    assert J.log_signal(_Sig(), when) is True
    assert J.log_signal(_SigAlt(), when) is True

    import json
    rows = json.loads((tmp_path / "t.json").read_text())
    ids = [r["id"] for r in rows]
    assert len(ids) == 2
    assert len(set(ids)) == 2, f"duplicate ids: {ids}"
    assert ids[0] == "XAUUSD-2026-08-03T10:00:00"
    assert ids[1] == "XAUUSD-2026-08-03T10:00:00-dup2"


def test_log_signal_id_matches_caller_computed_trade_ref_under_collision(
    tmp_path, monkeypatch,
):
    """Mirrors alert_signals.py's actual call pattern: the caller computes
    trade_ref BEFORE log_signal(), passes it through as confluence_ref/
    confidence_ref/etc., and log_signal() independently computes the row's
    `id`. Under a collision, both must still agree."""
    monkeypatch.setattr(J, "STORE", tmp_path / "t.json")
    monkeypatch.setattr(J, "BAK", tmp_path / "t.json.bak")
    monkeypatch.setattr(J, "TMP", tmp_path / "t.json.tmp")
    from engine import bias_adjust as ba
    monkeypatch.setattr(ba, "news_view", lambda s, **k: {})
    monkeypatch.setattr(ba, "adjustment", lambda s, d, **k: (0, ""))

    when = pd.Timestamp("2026-08-03 10:00:00")
    assert J.log_signal(_Sig(), when) is True  # occupies the base ref

    trade_ref = J.make_ref("XAUUSD", when)  # caller-side, pre-log_signal
    assert trade_ref == "XAUUSD-2026-08-03T10:00:00-dup2"
    ok = J.log_signal(_SigAlt(), when, confluence_ref=trade_ref,
                       confidence_ref=trade_ref)
    assert ok is True

    import json
    rows = json.loads((tmp_path / "t.json").read_text())
    second = rows[1]
    assert second["id"] == trade_ref
    assert second["confluence_ref"] == trade_ref
    assert second["confidence_ref"] == trade_ref
