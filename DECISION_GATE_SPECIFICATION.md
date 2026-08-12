# Master Decision Gate Specification (V2.2 Priority 2)

## 1. What this is

`engine/decision_gate.py` gives the platform's existing, already-working
gate sequence a single named, callable, independently-testable surface
with an explicit six-action contract:

    ENTER | WAIT | HOLD | REJECT | BLOCKED | STAND_DOWN

This satisfies the gap `PHASE0_FORENSIC_AUDIT.md` Section P identified:
*"Master Decision Gate as a single named, callable, independently-testable
module... does not exist. The gate logic exists, correctly sequenced, but
inline in `alert_signals.py::main()`."*

## 2. What this is NOT

This module **wraps** `risk_guard.evaluate()`, `portfolio_risk.evaluate()`,
and `alert_signals.apply_regime_gate()` — it does not reimplement a single
line of their decision logic, and it cannot change what any of them
decide. It is not a rewrite of the gate sequence, and it does not (yet)
drive `alert_signals.py`'s live control flow — see Section 5.

## 3. The six-action contract

| Action | Meaning | Stage(s) |
|---|---|---|
| `ENTER` | Fill approved — trade proceeds to journal/publish | Stage-2 only |
| `WAIT` | Heads-up approved — watching for the entry trigger | Stage-1 only |
| `HOLD` | This specific candidate is held (regime quality or MAST confluence tier) — softer than `REJECT`: nothing about the account/symbol is locked, a fresh read may qualify later | Stage-1 only |
| `REJECT` | `portfolio_risk.evaluate()` rejected this specific candidate on a per-trade category (exposure, correlation, session, confidence, liquidity, duplicate) | Both |
| `BLOCKED` | An account/symbol-wide condition pre-empts evaluating ANY candidate — news blackout or `risk_guard` lock | Both |
| `STAND_DOWN` | A `portfolio_risk` rejection specifically in `DRAWDOWN_PROTECTION` (portfolio-wide day-stop or trailing drawdown cap — both direction-independent) — the platform pulling back generally, not a per-candidate judgment. `TRADE_FREQUENCY_CONTROL` deliberately excluded despite its name: it's the directional-concentration cap, which depends on THIS candidate's own direction (`dirs[direction] + 1 > max_dir`), so it maps to `REJECT` — see the `STAND_DOWN_CATEGORIES` comment in `engine/decision_gate.py` for the full verification trail. | Both |

`REJECT` vs. `STAND_DOWN` are both `portfolio_risk.evaluate()` rejections;
the split exists so a future kill-switch abstraction (`TECHNICAL_DEBT_
REGISTER.md` gap, `VERSION_2.2_ROADMAP.md` Priority 2) can distinguish
"this one trade doesn't qualify" from "the platform itself is standing
down" without another consumer having to know portfolio_risk's category
strings by heart.

Rejection categories are NOT a new vocabulary — every `category` value
this module returns is one of `explainability_engine.REJECTION_CATEGORIES`
(itself built from `portfolio_risk.py`'s existing ten categories plus
`WEAK_EVIDENCE`/`RISK_LOCK`/`NEWS_BLACKOUT`), reused directly.

## 4. Two stages, two narrower gate sets

Mirrors `alert_signals.py::main()` exactly — this is not a merged,
single pipeline:

- **`evaluate_origination_gate()`** (Stage-1): news blackout →
  `risk_guard` → regime gate (advisory by default) → MAST confluence
  tier → `portfolio_risk` → `WAIT`.
- **`evaluate_entry_gate()`** (Stage-2): news blackout → `risk_guard` →
  `portfolio_risk` → `ENTER`. Deliberately does NOT re-check regime or
  confluence — Stage-1 already qualified both before this candidate
  became a pending setup; re-checking would misrepresent when in the
  pipeline the platform actually re-evaluates. `evaluate_entry_gate()`'s
  signature has no `mkt_regime`/`cr` parameters at all, enforced by
  `test_entry_gate_does_not_reference_regime_or_confluence_at_all`.

## 5. Not yet wired into the live pipeline — deliberately

`alert_signals.py::main()` continues to make its own inline decisions
exactly as before this landing. This module is not yet load-bearing in
production. Swapping the live scan loop over to call through here instead
of its own inline checks is real, valuable follow-up work — but it is a
separate change requiring its own careful review, not something to land
in the same commit as a new architecture surface on a live trading
pipeline. The safe half of the work (a proven-equivalent, independently
tested gate classifier) is what this landing delivers.

## 6. Explicitly out of scope

Do not extend this module to cover the following without a fresh design
pass — they are not binary gate/no-gate decisions, and folding them into
a `{ENTER,WAIT,HOLD,REJECT,BLOCKED,STAND_DOWN}` contract would
misrepresent what they actually do:

- `_guard_for()` / range_guard's `allow`/`downgrade`/`suppress` verdict
  — can downgrade confidence or suppress a signal, but is not currently
  a hard `continue` point in either stage's control flow.
- Confidence Engine, Market Memory, Macro Engine, Execution Simulator,
  Paper Broker submission — all advisory-only by explicit design (see
  each module's own docstring); none can block a trade, so none belong
  in a block/reject contract.

## 7. Test coverage

`tests/test_decision_gate.py` — 20 tests. Every branch of both gate
functions is covered by monkeypatching the SAME functions
`alert_signals.py` itself calls (`risk_guard.evaluate`, `portfolio_risk.
evaluate`), matching the mocking pattern already established in
`test_hourly_briefing_risk_gate.py` and `test_portfolio_risk.py` — this
proves the classification matches the live pipeline's actual behavior,
not just internal self-consistency. One test (`test_entry_gate_real_
risk_guard_lock_end_to_end`) calls the REAL, unmocked `risk_guard.
evaluate()` with engineered rows to prove the wiring reaches the actual
production function, not a mock-friendly stand-in.
