# Why-Not Engine — Completeness Check + Small Extension

**V2.2 Priority 3, Item 3** (`engine/why_not.py`)

## 1. What the audit said, and what was actually found

`PHASE0_FORENSIC_AUDIT.md`:

> Why-not / rejection explanation — `explainability_engine.py::explain_rejection()`
> and `_hypothetical_rejection_causes()` already exist (Day 8 Phase 4). Needs
> a read against your Section 10 example format to judge completeness, but
> the concept and a working implementation both already exist.

Two checks followed directly from that, in order:

**Is `explain_rejection()` itself complete?** Reading the full module
(625 lines) confirmed yes. `explain_rejection(row)` returns rejection
category/reason, stage reached, evidence at rejection, what would have
allowed it (`_hypothetical_approval_requirements()`), historical context,
assumptions, and disclosed limitations — a genuinely comprehensive,
already-tested (51 tests across five files, per
`EXPLAINABILITY_SPECIFICATION.md` Sec.11) implementation. Nothing here
needed rebuilding.

**Does "Section 10" check out?** The audit's own reference turned out to
be `EXPLAINABILITY_SPECIFICATION.md` Sec.10 ("Dashboard integration"),
not a separate document. Reading it against `engine/dashboard_publish.py`
confirmed the two match exactly: a `decision_audit` payload key built
from `decision_audit_history.tail(5, symbol=symbol)`, each row paired
with `build_audit_graph()` + `explain_rejection()`/`explain_approval()`.
No gap there either.

## 2. The actual gap

`EXPLAINABILITY_SPECIFICATION.md` Sec.9.1 / Sec.12 item 1 already
disclose it directly: two account-level gates — the platform-wide news
blackout and the per-symbol `risk_guard` day-stop lock checked *before*
Layer 1 origination runs — are, by deliberate design, never turned into a
`DecisionSnapshot`. There is no specific candidate direction yet at the
point either one fires, so recording one would misrepresent what "a
decision" means. That reasoning is sound and is left unchanged here.

But it leaves a real hole: if someone asks *"why wasn't I alerted on
XAUUSD just now"* during a news blackout or a Stage-1 risk lock,
`decision_audit_history` has nothing to find. `explain_rejection()` can't
explain a decision that, correctly, was never recorded — and there was no
existing tool that answered this question for that case.

## 3. What was built

`engine/why_not.py::why_not_now(symbol, *, settings=None, rows=None, now=None)`
— a live QUERY, not a new recording mechanism:

1. Checks `engine.kill_switch.current_stand_downs(symbol=...)` (V2.2
   Priority 2, already built and tested this cycle) — the exact live
   truth the two un-snapshotted gates represent. If anything is engaged,
   that *is* the answer.
2. Only if nothing is currently standing the platform down does it fall
   back to the most recent PERSISTED decision for that symbol
   (`decision_audit_history.tail(1, symbol=symbol)`), reusing
   `explain_rejection()` verbatim if it was a rejection.
3. If neither applies, says so plainly — most likely reading being "no
   qualifying setup has been identified yet this session."

No new explanation-generation logic, no new persistence, no change to
`DecisionSnapshot`'s scope. Not wired into `alert_signals.py` or any
dashboard/alert output in this landing — same posture as every other
Priority 2/3 module this cycle.

## 4. Test coverage

`tests/test_why_not.py`, 12 tests: engaged-stand-down reporting (3,
including multi-stand-down and precedence-over-recorded-decision),
fallback to recorded rejection (3, including most-recent-wins and
symbol-scoping), recorded-approval case (1), no-data case (1), fail-open
contract (2), and two end-to-end tests exercising the real
`kill_switch` → `news_guard`/`risk_guard`/`portfolio_risk` chain plus real
`decision_audit_history` wiring (isolated to `tmp_path`), proving the
pieces actually connect rather than just asserting `why_not.py`'s
internal logic in isolation.
