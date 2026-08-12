# Kill-Switch Status Reporter — Specification

**Module:** `engine/kill_switch.py`
**V2.2 Priority 2** (rescoped from `PHASE0_FORENSIC_AUDIT.md`'s original item)

## 1. What this is

A read-only status reporter over the platform's three existing protective
stand-downs:

| Stand-down | Underlying function | Scope |
|---|---|---|
| News blackout | `news_guard.evaluate()` | Platform-wide |
| Per-symbol daily loss lock | `risk_guard.evaluate(symbol)` | Symbol |
| Portfolio drawdown protection | `risk_guard.today_realized_r()` + `portfolio_risk.portfolio_drawdown_r()` | Portfolio-wide |

`current_stand_downs(symbol=None, settings=None, rows=None, now=None)`
returns a `list[StandDownStatus]` — one freshly-recomputed snapshot per
mechanism, in one common shape, for any future consumer (dashboard panel,
Opportunity Ranking, Why-Not Engine) that needs to know "is anything
currently standing this platform down" without learning three separate
modules' return schemas. `any_engaged(...)` is a one-line convenience over
the same query.

## 2. What this is NOT

The original debt-register item described a stateful object: "activation
condition / state / reason / owner / recovery criteria / audit trail,"
implying a persisted "engaged since \<timestamp\>" flag with explicit
reset semantics.

Investigating the three actual mechanisms before building anything showed
that description doesn't match what exists, and — more importantly —
what exists is *better* for this platform's operating model:

- `news_guard.evaluate()` takes no state; it re-derives blackout status
  from the news calendar every call.
- `risk_guard.evaluate()` takes no state; it re-sums today's realized R
  every call.
- `portfolio_risk`'s drawdown checks take no state; `portfolio_drawdown_r()`
  re-derives from the trailing trade window every call, with a documented
  time-based staleness ceiling (`max_age_days`) added specifically to
  guarantee the check can never mathematically wedge itself permanently
  engaged (see `portfolio_risk.py`'s `portfolio_drawdown_r()` docstring,
  and the 2026-08-10 production deadlock it was built to fix).

All three are self-healing across process restarts by design — this
platform's scan loop is a fresh process roughly every 15 minutes.
Introducing a persisted "engaged" flag would add a NEW failure mode
(a stale flag surviving past its trigger condition clearing) to a system
that currently cannot have that failure mode. That would be a regression
disguised as hardening.

So `kill_switch.py` builds no state machine, stores nothing, and changes
nothing about when or how any of the three mechanisms engage or clear.
It queries their current truth and reports it in one shape.

## 3. `StandDownStatus`

```python
@dataclass
class StandDownStatus:
    name: str
    engaged: bool
    scope: str            # "symbol" | "portfolio" | "platform"
    reason: str = ""
    category: str | None = None
    source: str = ""      # which existing module/function this wraps
    detail: dict = field(default_factory=dict)
```

`category` reuses `portfolio_risk.DRAWDOWN_PROTECTION` verbatim for the
drawdown status (the same category `decision_gate.py` maps to
`STAND_DOWN`, see `DECISION_GATE_SPECIFICATION.md` Section 3) — no new
vocabulary invented for that one. `news_blackout` / `risk_lock` are
kill_switch-local labels since neither `news_guard` nor `risk_guard`
expose the `portfolio_risk`-style category-constant pattern.

## 4. Faithfulness to the underlying checks

`drawdown_status()` calls the exact same two functions, in the exact same
order, with the exact same settings-attribute names and row filter, as
`portfolio_risk.evaluate()`'s checks #4 and #5:

- `risk_guard.today_realized_r(rows, symbol=None)` — checked first
  (day-stop), matching `evaluate()`'s ordering, so when both conditions
  would engage, the reported reason matches what the live gate would
  have reported.
- `portfolio_risk.portfolio_drawdown_r(closed_rows, window=30, max_age_days=...)`
  on `rows` filtered to `status in ("win", "loss", "scratch")` — identical
  filter to `evaluate()`'s `closed_rows`.
- Settings read via `getattr(settings, "portfolio_day_stop_r", 2.0)` /
  `"portfolio_max_drawdown_r"` / `"portfolio_drawdown_max_age_days"` —
  the same three attribute names, same defaults, `settings=None` falling
  back to `config.load()` exactly as `portfolio_risk.evaluate()` does.
- `rows=None` falls back to `portfolio_risk._rows()` — the same
  salvage-on-corruption reader `risk_guard.py` and `portfolio_risk.py`
  already share, not a new loader.

This is intentional duplication of *call sequence*, not logic: no
threshold math is reimplemented, only re-called.

## 5. Failure behavior

Every function wrapped here already fails safe on its own:
`news_guard.evaluate()` fails open (`ok=False, blackout=False`) on a
calendar fetch error; `risk_guard.evaluate()` and `portfolio_risk`'s
`_rows()`/`evaluate()` all fail open per their own documented contracts.
`kill_switch.py` adds no new failure surface — it does not catch
exceptions itself because none of the functions it calls are documented
to raise.

## 6. Not wired into the live pipeline

Same posture as `decision_gate.py`: this is a reporting layer, built and
tested standalone, not yet consumed by `alert_signals.py`'s live control
flow. `alert_signals.py` continues to call `news_guard.evaluate()`,
`risk_guard.evaluate()`, and `portfolio_risk.evaluate()` directly, exactly
as before. Wiring a dashboard panel or other consumer on top of
`kill_switch.py` is a separate, future, additive change.

## 7. Explicitly out of scope

- No persisted "engaged" state, activation timestamp, or manual-reset
  recovery flow — see Section 2.
- No new threshold logic — every number reported comes from an existing,
  unmodified function.
- No "owner" or "audit trail" fields from the original debt-register
  item's description — those implied a manual-override workflow that
  doesn't exist anywhere in this platform's design, and inventing one
  wasn't part of the actual gap found.

## 8. Test coverage

`tests/test_kill_switch.py`, 19 tests: `StandDownStatus` construction (1),
`news_blackout_status` (3 — engaged, clear, fail-open), `risk_guard_status`
(2 — locked, clear), `drawdown_status` (8 — clear, day-stop engages,
trailing-drawdown engages, day-stop takes precedence when both would
engage, settings passthrough, config.load() fallback, closed-rows filter,
`_rows()` fallback), `current_stand_downs`/`any_engaged` (4), and one
real-function integration test exercising all three underlying calls
unmocked end-to-end.
