# Day 8 Validation Report — Explainability Engine & Decision Audit System

## 1. Full suite results

```
cd gold-engine && python3 -m pytest -q
........................................................................ [ 11%]
........................................................................ [ 23%]
........................................................................ [ 34%]
........................................................................ [ 46%]
........................................................................ [ 58%]
........................................................................ [ 69%]
........................................................................ [ 81%]
........................................................................ [ 92%]
............................................                             [100%]
620 passed in 39.57s
```

569 baseline (post-Day-7) + 51 new = 620. **Zero failures, zero
regressions.**

## 2. New tests, by file

| File | Tests | Covers |
|---|---|---|
| `tests/test_platform_version.py` | 5 | `snapshot()`'s platform/architecture version fields, `component_versions()` reporting real declared versions, honest `"unversioned"` disclosure for a module without one, never-raises on a bad module name |
| `tests/test_decision_audit_history.py` | 15 | record/tail/rotation/fail-safety, dict-vs-dataclass input, `find_by_ref()`/`find_by_trade_ref()`, structural no-mutator-function proof, `record_correction()`'s original-untouched guarantee, `history_for_ref()`'s original-plus-corrections ordering |
| `tests/test_explainability_engine.py` | 19 | `config_snapshot()` field coverage and honest `None` reporting, `DecisionSnapshot` assembly (full context, minimal/rejected context, garbage-input safety), `decision_id`/`trade_ref` distinctness, audit graph node/edge construction (approved and rejected), data lineage map coverage and per-snapshot annotation, `explain_approval()`/`explain_rejection()` answering every mandate-required question, a 500-snapshot graph+explain performance benchmark |
| `tests/test_replay.py` | 5 | missing-decision_id safety, deterministic replay of an approved decision, deterministic replay of a rejected decision, corrections surfaced in replay output, two different decisions not confused with each other |
| `tests/test_post_trade_review.py` | 7 | no-snapshot-found, heads-up-never-filled, still-open trade, closed win, closed loss (uncertainty-indicator heuristic listing), never-raises on garbage, structural proof that `trades.json` is never modified by a review call |

Isolated run (Day 8 files only): `51 passed`.

## 3. Regression check

The pre-existing 569 tests (Day 1-7) were re-run unmodified as part of the
full 620-test suite above — no pre-existing test file's assertions were
changed this Day (same as Day 7; unlike Day 6, which had to update one
Day 5 test for an approved behavior change). The four `VERSION`-constant
additions (`signals.py`, `regime_engine.py`, `confluence.py`,
`portfolio_risk.py`) are pure additive metadata and required no test
changes anywhere in the pre-existing suite — confirmed by all 569
pre-existing tests passing unmodified.

## 4. Manual verification

- **`git status --porcelain`** reviewed directly: every `M`/`??` entry
  corresponds to a file this session has legitimately touched (no commits
  made mid-session, so modifications accumulate by design); no stray data
  files (`.jsonl`, `.pyc`, cache directories) appear — in particular, no
  stray `decision_audit.jsonl` was left in the repo root (every test
  points `HISTORY_PATH` at `tmp_path` via monkeypatch, same discipline as
  every prior Day).
- **`ast.parse()` on every modified/new Python file**
  (`engine/platform_version.py`, `engine/explainability_engine.py`,
  `engine/decision_audit_history.py`, `engine/signals.py`,
  `engine/regime_engine.py`, `engine/confluence.py`,
  `engine/portfolio_risk.py`, `alert_signals.py`,
  `engine/dashboard_publish.py`) confirmed all parse cleanly.
- **Confirmed `replay()`'s determinism directly**, not just via the test
  suite: built a rejected `DecisionSnapshot`, recorded it, called
  `replay()` twice, and compared `json.dumps(..., sort_keys=True,
  default=str)` output for exact string equality — `True`, matching the
  automated test's own assertion.
- **Confirmed no mutator function exists** in
  `decision_audit_history.py` by direct inspection of the module's
  function list (`record`, `record_correction`, `tail`, `all_rows`,
  `find_by_ref`, `find_by_trade_ref`, `history_for_ref`, plus three
  private helpers) — none named update/delete/overwrite/edit/modify/
  remove/patch.
- **Manually traced every `log_decision_snapshot()` call site** in
  `alert_signals.py` (seven total: Stage-2 risk-lock hold, Stage-2
  portfolio hold, Stage-2 approved entry, Stage-1 regime-blocked, Stage-1
  confluence-held, Stage-1 portfolio-held, Stage-1 approved heads-up) and
  confirmed each one is placed strictly AFTER the corresponding
  `log.append()`/`ledger.log()` call for that same event — i.e. after the
  real gate/approval decision has already been made, never before or
  interleaved with it.
- **Confirmed `post_trade_review()` never writes to `trades.json`** via a
  direct before/after byte comparison in
  `test_post_trade_review_does_not_modify_production_data`, and
  independently by inspecting the function's source for any `write`/
  `_save` call — there is none; it only reads via
  `engine.store.load_array()`.
- **Re-queried the real repo directly** immediately before writing this
  report: `decision_audit.jsonl` does not exist yet (confirms
  `RESEARCH_EXPLAINABILITY.md`'s central finding), and
  `component_versions()` run against the live codebase reports six
  modules with real version strings and reports would report
  `"unversioned"` for any other module — spot-checked with
  `engine.store` (not in `COMPONENT_MODULES`, confirmed unversioned).

## 5. Final Validation checklist (per the Day 8 mandate)

| Success criterion | Status |
|---|---|
| Every production decision has a complete immutable audit trail | Done for every decision reaching Stage-1 origination or later (both approved and rejected paths); two account-level pre-origination gates are an explicit, disclosed exception — see Sec.9.1 of the spec |
| Approved and rejected decisions are both explainable | Done — `explain_approval()`/`explain_rejection()`, both answering every question the mandate lists verbatim |
| Unified identifiers connect all stages of the decision lifecycle | Done for regime/confluence/confidence history (Day 6/7) plus, new this Day, EVERY decision (including rejections) via `decision_id`; NOT yet extended to risk/portfolio/Telegram/dashboard persisted storage (none of those persist a per-decision row to link to) — disclosed, not silently claimed complete |
| Historical replay can reconstruct decisions accurately | Done — `replay()`, proven deterministic by direct test assertion |
| Configuration and version traceability are recorded | Done — `config_snapshot()`/`platform_version.snapshot()` on every `DecisionSnapshot` |
| Data lineage is documented | Done — `DATA_LINEAGE_MAP` + `lineage_for_snapshot()` |
| Automated tests pass with zero regressions | Done — 620/620 passing |
| Documentation is complete | Done — `EXPLAINABILITY_SPECIFICATION.md`, `RESEARCH_EXPLAINABILITY.md`, `ARCHITECTURE_SPECIFICATION.md` §18, `PROJECT_SUMMARY_AND_ROADMAP.md` |
| The Explainability Engine remains observational and does not alter production decision-making | Done — no `allow`/`reject` field exists anywhere in `DecisionSnapshot`; every integration call site runs after the real decision; `log_decision_snapshot()` is wrapped fail-safe |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. **Two account-level gates are not snapshotted** (news blackout,
   pre-origination risk lock) — disclosed scope boundary, not a gap
   discovered after the fact. See `EXPLAINABILITY_SPECIFICATION.md`
   Sec.9.1.
2. **`decision_audit.jsonl` contains zero real rows today** — this store
   starts empty at this deployment; every claim in
   `RESEARCH_EXPLAINABILITY.md` is about engine correctness, not
   accumulated decision data, because none exists yet.
3. **`post_trade_review()` is a disclosed heuristic, not a causal
   attribution model** — every output carries a `heuristic_disclosure`
   string saying so explicitly.
4. **Only six modules carry an explicit `VERSION` constant** — the rest
   of the ~40-module engine package reports `"unversioned"` honestly via
   `component_versions()`, not silently omitted or fabricated.
5. **`find_by_ref()`/`find_by_trade_ref()` are O(n) linear scans** — fine
   at zero-to-low-thousands of rows; flagged as worth monitoring sooner
   than Day 7's equivalent note, since `decision_audit.jsonl` will grow
   faster than `trades.json` (it records every heads-up and rejection,
   not just fills).
6. **The unified trade ID is still not extended to risk/portfolio/
   Telegram/dashboard persisted storage** — none of those persist a
   per-decision row today, so there is nothing yet to link a ref to; same
   open item carried forward from Day 7's readiness report.
