# Qualification Diagnostics — engine/qualification_diagnostics.py

**V2.2 Priority 5 extension**, triggered by a live diagnostic finding on
2026-08-15.

## 1. What triggered this

A one-off manual pass over `decision_audit.jsonl` and `run_ledger.jsonl`
found: **79/79 decisions recorded since 2026-08-06 were rejected** — zero
approvals across all 4 symbols in 9+ tracked days, despite the scan loop
actively running every cycle. `pending.json` is empty (nothing being
watched for entry) and `confidence_history.jsonl`/`execution_history.jsonl`
don't exist at all — no candidate has reached those stages in this window.

Breakdown: 65/79 (82%) rejected at `confluence_assessment` (MAST score/
hard-gate filter, category `weak_evidence`), 14/79 (18%) at `portfolio_risk`
(`drawdown_protection`, matching the Day 10 finding from
`RESEARCH_VALIDATION_SPECIFICATION.md` Sec.9.1). Confluence score
distribution: median 60, min 33, max 74 — 33/65 candidates scored within
10 points of the 70-point bar. The single most common disagreeing check
across 84 `confluence_held` ledger events: "liquidity strength" (58/84,
69%), followed by "volume profile" (37/84), "mean reversion" (28/84).
Cross-checked against current regime state: all 4 symbols are in
low-quality, choppy conditions (Range/Distribution/Accumulation, quality
20–56/100) — so some of this may be the platform correctly sitting out
chop, not necessarily miscalibration. That's a call for the platform
owner, not something this module decides.

## 2. What was built

This picture had to be reconstructed by hand — no standing view answered
"why is qualification rate what it is" as a queryable report.
`engine/qualification_diagnostics.py` is that view: read-only, reuses
existing infrastructure exactly as it already exists (no new persistence,
no new scoring, no config change, no production behavior touched):

- `rejection_summary(days=14)` — `decision_audit_history.all_rows()`
  filtered to the window, broken down by final_action / rejection stage /
  rejection category / confluence score distribution.
- `disagree_frequency(top=15)` — every `confluence_held` event
  `ledger.py` currently retains (`ledger.tail(ledger.MAX_LINES)`), ranked
  by which confirmation source disagrees most often. Disclosed limitation:
  `ledger.py` rotates at 5000 lines, so this is "most recent retained
  history," not a full lifetime record.
- `current_regime_snapshot(symbols)` — most recently RECORDED regime read
  per symbol (`regime_history.last_for()`, never a fresh recompute), for
  context on whether a low qualification rate coincides with genuinely
  low-quality market conditions.
- `current_stand_downs()` — `kill_switch.current_stand_downs()`, since a
  `drawdown_protection` stand-down produces the identical symptom (zero
  approvals) as a confluence/threshold issue but needs a completely
  different fix.
- `summary()` — assembles all of the above, wired additively into
  `research_dashboard.build_research_payload()` as a new
  `qualification_diagnostics` key, same per-section `try/except`
  discipline as every other section of that payload.

## 3. Test coverage

`tests/test_qualification_diagnostics.py`: 10 tests — counting/filtering
correctness for each section, time-window exclusion, empty-history
handling, and never-raises guarantees for every section independently
(a `kill_switch` failure, a `ledger` failure, or a per-symbol
`regime_history` failure must not blank the rest of the payload).
`tests/test_research_dashboard.py`: 2 new tests confirming the key is
present and that a failure in this module can't break the overall
research payload.

Full suite: 1583/1583 passing.
