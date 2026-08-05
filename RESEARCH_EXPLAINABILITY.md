# RESEARCH REPORT — Explainability Engine & Decision Audit System (Day 8)

Companion to `EXPLAINABILITY_SPECIFICATION.md`. Follows the same honesty
convention established Day 4-7: where data are insufficient, this report
states that explicitly rather than drawing unsupported conclusions.

## 1. What the real data actually contains today

`decision_audit.jsonl` does not exist in the repo yet — this is a NEW
store, introduced this Day, and starts empty at this deployment. Every
number in this report is therefore about the ENGINE's structural
correctness (does it assemble/persist/explain/replay correctly), not about
any accumulated decision history, because none exists yet.

This is the same pattern as every prior Day's research report at its own
introduction point (Day 4's `regime_history.jsonl`, Day 5's
`confluence_history.jsonl`, Day 6's `confidence_history.jsonl`, Day 7's
market-memory analytics over `trades.json`) — the tooling is built and
tested first; the data accumulates from this point forward.

## 2. Explainability architecture

The core design choice — a small, denormalized `DecisionSnapshot` plus ref
pointers into the three existing history logs, rather than either (a) a
full duplicate of every upstream object, or (b) storing nothing and
relying on live re-computation — was made for two reasons, both testable
independently of any accumulated data:

1. **Storage discipline**: verified structurally.
   `test_no_mutator_besides_record_exists` and the "reuse, ref-pointer,
   denormalized-summary" pattern match `engine/journal.py`'s own existing
   `Trade` dataclass precedent exactly — this is not a new idea introduced
   for Day 8, it is the SAME idea, applied one level up.
2. **Reproducibility**: verified structurally, not statistically.
   `replay()` reconstructing byte-identical output from a persisted row
   twice in a row (`test_replay_approved_decision_is_deterministic`) is a
   proof about the CODE, not about any particular decision's content — it
   would hold on day one with zero decisions recorded and will continue to
   hold once thousands are.

## 3. Audit methodology

The audit graph (`build_audit_graph()`) and lineage annotation
(`lineage_for_snapshot()`) are both PURE FUNCTIONS of a persisted row —
no live re-fetch. This was a deliberate methodological choice: an audit
tool whose output depends on the CURRENT state of other engines (rather
than the state recorded at decision time) would not actually be auditing
the original decision, it would be re-evaluating it with today's data and
calling the result "explanation." The look-ahead-protection discipline
Day 7 established for Market Memory comparisons (`_look_ahead_safe()`)
and this Day's "replay from persisted evidence only" are the same
underlying principle applied to two different problems: don't let
information from AFTER a decision point leak into an explanation OF that
decision point.

## 4. Replay capability

`replay(decision_id)` is fully implemented and tested against synthetic
decisions (approved-entry, approved-heads-up, rejected, with and without
corrections). It has NOT been exercised against real accumulated decision
history, because none exists yet (Sec.1). The one thing this report can
say with confidence: the function's behavior does not depend on the
CONTENT of the row, only its SHAPE (a dict with the documented
`DecisionSnapshot` fields) — `test_replay_two_different_decisions_are_not_confused`
confirms two structurally-different rows (approved vs. rejected) both
replay correctly and independently.

## 5. Traceability guarantees

Version traceability (`platform_version.snapshot()`) and configuration
traceability (`config_snapshot()`) are both point-in-time captures with no
dependency on accumulated history — they are correct from the very first
decision recorded. The one honest gap: six of the engine's ~40 modules
carry an explicit `VERSION` constant (`COMPONENT_MODULES` — Sec.5 of the
spec); the rest report `"unversioned"`. This is disclosed, not silently
narrowed — a future day wanting fuller version coverage would need to
decide whether every module warrants its own version number or whether
the current "decision-path modules only" scoping is sufficient
indefinitely (see `DAY8_NEXT_DAY_READINESS_REPORT.md`'s open questions).

## 6. Post-trade review — an explicit methodological caveat

`post_trade_review()`'s "assumptions that may have held/failed" heuristic
deserves its own research note, not just a code disclosure (already
present in `EXPLAINABILITY_SPECIFICATION.md` Sec.8.4 and the function's
docstring): matching a recorded `uncertainty_indicator` string against a
losing trade's outcome is a CORRELATION-agnostic listing, not even a
correlation claim yet — it is one data point. The recommendation
functions (`_review_recommendations()`) explicitly say so
("worth including in any future review... once enough closed trades
accumulate," "one data point, not a pattern"). A methodologically sound
future pass would NOT read individual `post_trade_review()` outputs as
findings; it would aggregate `uncertainty_indicators` across many closed,
`decision_id`-linked trades and check whether trades carrying a SPECIFIC
indicator (e.g. "conflicting evidence") lose at a materially different
rate than trades without it — exactly the kind of aggregate,
sample-size-gated analysis `market_memory.py`'s `performance_by_*`
functions (Day 7) already do for OTHER dimensions, and the natural
extension once `decision_audit.jsonl` accumulates real volume.

## 7. Expected limitations

1. **Zero real decision history exists yet** — every claim in this report
   is about code correctness, not about any pattern in actual decisions
   (Sec.1).
2. **Two account-level gates are not snapshotted** (news blackout,
   pre-origination risk lock — `EXPLAINABILITY_SPECIFICATION.md` Sec.9.1)
   — a future reviewer looking for 100% decision coverage should know
   these two categories remain ledger-only.
3. **`post_trade_review()` is a heuristic, not a causal model** (Sec.6) —
   should never be read as "this uncertainty indicator caused this loss."
4. **Version coverage is six modules, not all of them** (Sec.5).
5. **`find_by_ref()`/`find_by_trade_ref()` are O(n) scans** — fine at zero
   to low thousands of rows; revisit if `decision_audit.jsonl` grows an
   order of magnitude beyond `trades.json`'s current ~100-row scale (this
   store will actually grow FASTER than `trades.json`, since it records
   every heads-up and rejection too, not just fills — worth monitoring
   sooner than Day 7's equivalent note about `market_memory.py`).

## 8. Future enhancements

- Once `decision_audit.jsonl` accumulates real volume, run the aggregate
  uncertainty-indicator analysis described in Sec.6 (natural extension of
  Day 7's `performance_by_*` pattern).
- Extend the unified identifier pattern to the two remaining branches of
  the platform owner's original Day 6 diagram not yet covered by ANY
  persisted log: Telegram alerts and dashboard entries are still ephemeral
  (a message send, a JSON payload build), not persisted history — see
  `DAY7_NEXT_DAY_READINESS_REPORT.md`'s open question #3, still open.
- Consider whether `dashboard`/`research` lineage presence (Sec.7 of the
  spec — currently `None`, "not determinable") could be made determinable
  by having the dashboard/research code itself write a lightweight
  "consumed decision_id X" breadcrumb; not attempted this Day, flagged as
  a possible future enhancement rather than a gap needing urgent closure.
- Revisit whether every engine module should carry a `VERSION` constant,
  or whether the current six-module decision-path scoping is the right
  permanent boundary (Sec.5).

## 9. Explicit statement on insufficient data

Per the mandate's own instruction: where data are insufficient, this
report states that explicitly. `decision_audit.jsonl` contains zero rows
today (Sec.1) — every finding in this report is about the CORRECTNESS of
the engine (proven by 51 new tests, deterministic replay, structural
immutability), not about any pattern in accumulated decisions, because
none exist yet. This mirrors Day 7's own honest finding at its
introduction ("every existing trade predates the unified trade ID") —
Day 8's tooling is, similarly, ready before the data that would make it
maximally useful has accumulated.
