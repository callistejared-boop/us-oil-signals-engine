# Regime Transition Reporting — Audit Correction + Small Extension

**V2.2 Priority 3, Item 2** (`engine/regime_transitions_report.py`)

## 1. What the audit said, and what's actually true

`PHASE0_FORENSIC_AUDIT.md` Section P listed this as missing:

> Explicit regime-transition event detection/logging (e.g. a logged
> TRENDING→RANGING event) — does not exist as such. `regime_engine.py`
> computes a continuous `transition_risk` score (0–1)... but it is a risk
> adjustment, not a discrete classified/loggable transition event.

Auditing `engine/regime_history.py` before writing any code showed this
is inaccurate. `record()` (Day 4, unmodified since) already computes, on
every call:

- `transition_event` (bool) — `True` when `primary` differs from the
  previous entry for that symbol/timeframe
- `transition_from` — the prior regime label
- `duration_s_since_prev` — how long the previous regime held

`transitions()` already filters history down to just the event rows.
This is wired into the live pipeline — `alert_signals.py::main()` calls
`rhist.record(sym, "strategic", mkt_regime)` every scan cycle, for every
symbol — and checking the live `regime_history.jsonl` confirms it's
firing in production: **42 real transition events across 595 recorded
classifications**, e.g. `WTIUSD: Range → Distribution`,
`BTCUSD: Accumulation → Range`, each with a correct `duration_s_since_prev`.

`tests/test_regime_history.py` already covers this (10 tests, including
`test_transition_event_detected_on_primary_change` and
`test_transitions_filters_to_transition_events_only`).

**Conclusion: no detection/logging code needed rebuilding.** Duplicating
this would have violated the standing extract/reuse-don't-rewrite
discipline for no benefit.

## 2. The actual gap

Grepping the codebase for `transition_event`, `transition_from`, and
`duration_s_since_prev` outside `regime_history.py` and its own test file
returns zero hits. The data is detected, logged, and queryable — but
nothing anywhere turns it into something a person would look at: no
dashboard section, no alert, no explainability mention. Fully-functional,
tested, live infrastructure that nobody can currently see.

## 3. What was built

`engine/regime_transitions_report.py` — a thin, read-only
formatting/reporting layer over the untouched `regime_history.py` data,
in the same spirit as `grade.py` ("this module adds no new judgment of
its own, it only relabels what confluence.py already decided"):

- `format_transition(row) -> str` — one human-readable line for a
  transition row (e.g. `"WTIUSD: Range -> Distribution (after 1.1h in
  Range) at 2026-08-12T10:55:45+00:00"`).
- `recent_transitions_summary(symbol=None, n=10) -> list[str]` — thin
  wrapper over `regime_history.transitions()`.
- `transition_frequency(symbol, hours=24.0) -> dict` — count of
  transitions for a symbol within a trailing window, plus the most
  recent one — a quick "is this symbol's regime currently stable or
  flip-flopping" read.

No new persisted state, no change to detection logic, and — same posture
as `decision_gate.py`, `kill_switch.py`, and `opportunity_ranking.py` —
not wired into `alert_signals.py`'s control flow or any dashboard/alert
output in this landing. A future integration can call
`recent_transitions_summary()` directly.

## 4. Test coverage

`tests/test_regime_transitions_report.py`, 13 tests: `format_transition`
(4 — full row, short-duration minutes formatting, missing-fields
fail-open, missing-duration fallback), `recent_transitions_summary` (5 —
empty history, real transition via the actual `regime_history.record()`
call, non-transition rows excluded, symbol filter, `n` limit),
`transition_frequency` (4 — zero-count case, in-window counting,
out-of-window exclusion via a deliberately stale synthetic row,
malformed-timestamp fail-open).
