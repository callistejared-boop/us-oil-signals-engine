# Explainability Engine & Decision Audit System — Specification (Day 8)

## 1. Primary objective and scope

This system does not generate trades. It records, reconstructs, and
explains every decision the platform already made — the literal framing
of the Day 8 mandate. Every live trade, rejected trade, and heads-up
advisory leaves behind a complete, immutable decision record that a future
reviewer can use to reconstruct the platform's reasoning exactly as it
existed at the moment the decision was made.

Three new modules implement this:

- `engine/platform_version.py` — version/configuration traceability
  (Sec.5).
- `engine/explainability_engine.py` — the `DecisionSnapshot` object,
  assembly, the audit graph, data lineage, explanation reports, post-trade
  review, and `replay()` (Sec.2-8).
- `engine/decision_audit_history.py` — immutable, append-only persistence
  (Sec.3).

Everything here is a pure downstream synthesis layer, the same posture as
`confidence_engine.py` (Day 6) and `market_memory.py` (Day 7): every
function takes already-computed upstream objects as parameters and never
re-fetches, re-derives, or re-scores anything. Nothing in this system can
hold, downgrade, reject, or approve a trade — there is no `allow`/`reject`
field anywhere in `DecisionSnapshot`, and every integration point calls
`log_decision_snapshot()` (see Sec.9) strictly AFTER the real gate/approval
decision has already been made, using the same already-computed variables.

## 2. The DecisionSnapshot object

Standardized, immutable decision record — one per opportunity the platform
evaluated, whether it was ultimately approved (entry or heads-up) or
rejected.

| Field | Meaning |
|---|---|
| `decision_id` | Unique per decision, `f"{symbol}-{decision_ts}"` (same format as `journal.make_ref()`/`Trade.id`). Assigned to EVERY decision — approved, heads-up, or rejected. |
| `trade_ref` | `== Trade.id`/`regime_ref`/`confluence_ref`/`confidence_ref` IFF this decision became an actual Stage-2 fill; `""` for a heads-up or a rejection. **Deliberately a different field from `decision_id`** — see Sec.2.1. |
| `symbol`, `direction` | The candidate opportunity's symbol/direction. |
| `created` | ISO8601 UTC, when this snapshot was captured. |
| `stage` | Which `DECISION_STAGES` entry this decision reached (Sec.4). |
| `final_action` | `"approved_entry"` \| `"approved_heads_up"` \| `"rejected"`. |
| `version` | `{"explainability_engine": VERSION, "schema": SCHEMA_VERSION}` — this module's OWN version, distinct from `platform_version` below. |
| `platform_version` | `engine.platform_version.snapshot()` — Sec.5. |
| `config` | `config_snapshot()` — the decision-relevant Settings fields, frozen at decision time (Sec.5). |
| `regime_summary` | `{primary, confidence, quality_score, transition_label, ref}` — denormalized + a ref pointer into `regime_history.jsonl`. |
| `confluence_summary` | `{score, final_tier, agree_count, disagree_count, ref}` — denormalized + a ref pointer into `confluence_history.jsonl`. |
| `confidence_summary` | `{overall_confidence, tier, is_calibrated, ref}` or `{}` if no Confidence Engine assessment was made for this decision. |
| `portfolio_state` | Reused verbatim from `ConfidenceAssessment.portfolio_status` (Day 6) when available. |
| `risk_assessment` | Reused verbatim from `ConfidenceAssessment.risk_status` (Day 6) when available. |
| `historical_context_summary` | `{comparable_count, sufficient_sample, confidence_label, aggregate}` from Market Memory's `historical_context()` (Day 7), or `{}`. |
| `advisory_messages` | `{supporting_rationale, conflicting_rationale, uncertainty_indicators, assumptions}` — reused verbatim from `ConfidenceAssessment`. |
| `supporting_evidence` | `{highest_impact_evidence, lowest_impact_evidence}` — reused verbatim from `ConfidenceAssessment`. |
| `rejection` | `{category, reason}` or `None`. |

### 2.1 Why `decision_id` and `trade_ref` are two different fields

The unified trade ID pattern (Day 6/7) only ever applied to decisions that
became actual filled trades. Day 8 extends the "one identifier per
lifecycle" idea to EVERY decision the platform makes, including ones that
never became a trade at all — a rejected setup, or a Stage-1 heads-up that
never triggered. `decision_id` is that broader identifier, computed the
same way (`journal.make_ref(symbol, when)`) but assigned regardless of
outcome. `trade_ref` remains the narrower, Day 6/7 concept: non-empty only
when this decision corresponds 1:1 to a Stage-2 fill, at which point
`trade_ref == decision_id == Trade.id == regime_ref == confluence_ref ==
confidence_ref` by construction (same equality guarantee Day 6/7 already
established, now with one more member).

## 3. Storage design — why a new store, and what it does NOT duplicate

No existing log captured a REJECTED decision at all before Day 8 —
`regime_history`/`confluence_history`/`confidence_history` each record a
classification or a read, never "what happened to this opportunity and
why." `decision_audit.jsonl` (via `engine/decision_audit_history.py`) is
the first durable record of a held/rejected signal beyond a single-line
ledger event.

This is NOT a duplicate database in the sense the mandate warns against.
`DecisionSnapshot` stores:

1. **Ref pointers** into the three existing history logs (`regime_ref`
   inside `regime_summary`, etc.) — the actual per-source detail (full
   `agree`/`disagree` lists, full regime `evidence`/`conflicting_evidence`)
   remains ONLY in those logs, reachable via the ref.
2. **A small, denormalized SUMMARY** of each — frozen at decision time. This
   is the same trade-off `engine/journal.py`'s `Trade` dataclass already
   makes for `regime_trend`/`regime_vol`/`confluence_score`/
   `confluence_agree` (Day 1-2), not a new pattern. It is necessary, not
   redundant: `regime_history.last_for()` and similar reads can change over
   time (a symbol's most recent regime classification moves forward every
   scan), but a decision record must stay historically accurate to the
   moment the decision was actually made — reading `last_for()` again
   later would silently rewrite history.
3. **Genuinely new fields** nothing else captures: `final_action`,
   `rejection`, `platform_version`, `config` — the state that produced
   THIS decision, not a re-derivable read of an engine's current output.

### 3.1 Immutability

`decision_audit_history.py` exposes no update/delete function of any kind
— only `record()` (append), `record_correction()` (append a NEW,
explicitly-linked row), and read-only lookups
(`find_by_ref`/`find_by_trade_ref`/`history_for_ref`/`tail`/`all_rows`).
`test_no_mutator_besides_record_exists` proves this structurally (greps
the module's own function names for anything update/delete/overwrite-like)
rather than relying on it staying true by convention. A correction is its
own row (`record_type="correction"`, `corrects_ref=<decision_id>`) —
`history_for_ref()` returns the original plus every correction in write
order, so a reviewer always sees the full trail, never a silently-altered
original.

### 3.2 Performance

`find_by_ref()`/`find_by_trade_ref()` are O(n) linear scans of the JSONL
file — the same disclosed trade-off every other `find_by_ref()` in this
codebase makes (Day 6/7 precedent), fine at current data volumes
(benchmarked to <5s for 500 synthetic snapshots' worth of graph+explanation
generation in `test_large_history_graph_and_explain_performance`), not a
strict contract.

## 4. Decision timeline (`DECISION_STAGES`)

```
market_data_received
  -> market_regime_assessment
  -> ict_smc_origination
  -> confluence_assessment
  -> portfolio_risk
  -> confidence_assessment
  -> market_memory
  -> approval_or_rejection
  -> publication
  -> execution
  -> trade_outcome
  -> post_trade_review
  -> calibration
```

Every `DecisionSnapshot` records `stage` — the LAST stage it reached, not
necessarily every stage in between (a rejection stops the timeline early;
a heads-up stops before `execution`). `build_audit_graph()` (Sec.6) reads
this single field to reconstruct which stages ran.

## 5. Version and configuration traceability

`engine/platform_version.py` is the single source of truth. Before Day 8,
only two modules (`confidence_engine.py`, `market_memory.py`) carried an
explicit `VERSION` constant — every other engine module was, honestly,
unversioned. Day 8 retroactively assigned `VERSION` to four more
decision-path modules (`signals.py`="1.0.0", `regime_engine.py`="2.0.0"
matching its own "V2" docstring label, `confluence.py`="1.0.0",
`portfolio_risk.py`="1.0.0") — purely additive metadata, zero logic
changes, confirmed by the unchanged full regression suite.

`component_versions()` reports `"unversioned"` HONESTLY for any module
without a `VERSION` constant rather than fabricating one —
`test_component_versions_reports_unversioned_honestly` proves this with a
real example (`engine.store`).

`PLATFORM_VERSION`/`ARCHITECTURE_VERSION` (both `"0.8.0"` today) are
bumped BY CONVENTION each Day a major capability lands, mirroring
`ARCHITECTURE_SPECIFICATION.md`'s own §-per-Day numbering — disclosed
explicitly as an internal traceability marker, NOT a claim of strict
SemVer discipline against a public API (there isn't one).

`config_snapshot()` captures the decision-relevant subset of `Settings` —
eighteen fields covering risk/portfolio/regime/confidence thresholds and
modes — frozen at the moment of the decision. Deliberately excludes
credentials/connection settings (Telegram tokens, API keys, Supabase
secrets): those affect delivery, not the decision, and have no place in a
record meant to be reviewed or shared.

## 6. Audit graph

`build_audit_graph(row)` reconstructs the decision graph purely from a
PERSISTED `decision_audit` row — no live re-fetch, no re-computation. This
is what makes `replay()` (Sec.8.3) deterministic: the graph is a pure,
structural reshaping of data already in the row.

- **Nodes**: one per `DECISION_STAGES` entry, `status` in
  `{"completed", "rejected", "not_reached"}`.
- **Edges**: `{from, to, reason}` for every stage the decision actually
  progressed through; the terminal edge into a rejected decision carries
  `reason = "<category>: <reason text>"`.

## 7. Data lineage

`DATA_LINEAGE_MAP` is a static, documented map of the pipeline's data flow
(the mandate's own diagram: market data → regime → origination →
confluence → portfolio risk → confidence → market memory → decision
snapshot → journal → dashboard/research). It is NOT recomputed per
decision. `lineage_for_snapshot(row)` annotates it per decision using only
fields already on the row (e.g. `journal: bool(row["trade_ref"])`) —
`dashboard`/`research` presence is explicitly reported as `None`
("not determinable from a stored row") rather than guessed.

## 8. Explanation reports

### 8.1 `explain_approval(row)`

Answers, verbatim, the mandate's nine questions: why considered, why
approved, most/least contributing evidence, conflicting evidence,
assumptions, uncertainty, what would have caused rejection, historical
context, limitations. Operates purely on a PERSISTED row (dict) — the same
shape whether called live right after `build_decision_snapshot()` or later
via `replay()`.

`what_would_have_caused_rejection` is a plain-language readout of the
SAME thresholds `config_snapshot()` already recorded (e.g. "MAST
confluence score below {confluence_min_score}") — not a counterfactual
re-run of any gate.

### 8.2 `explain_rejection(row)`

Answers: rejection category/reason, stage reached, evidence at rejection,
what would have allowed it (the inverse of 8.1's question, keyed off the
recorded `rejection.category`), historical context, assumptions,
limitations.

### 8.3 `replay(decision_id)`

Reconstructs the full explanation (`snapshot`, `graph`, `lineage`,
`explanation`, `corrections`) PURELY from persisted evidence. Calling this
twice for the same `decision_id` returns byte-identical output —
`test_replay_approved_decision_is_deterministic`/
`test_replay_rejected_decision_is_deterministic` prove this directly
(`json.dumps(..., sort_keys=True) == json.dumps(..., sort_keys=True)`
across two calls), which is the literal meaning of "historical
explanations must remain reproducible."

### 8.4 `post_trade_review(decision_id_or_trade_ref)`

**Honesty disclosure, stated once here and repeated in the function's own
docstring**: this is a LIGHTWEIGHT, disclosed HEURISTIC comparison, NOT a
causal attribution model. It matches the `DecisionSnapshot`'s recorded
`uncertainty_indicators`/`conflicting_rationale` text against the realized
win/loss/scratch outcome and lists them under
`assumptions_that_may_have_failed` for a losing/scratch trade — this does
NOT mean those specific indicators caused the loss, only that they were
present at decision time and worth surfacing for a future reviewer doing
aggregate research (see `RESEARCH_EXPLAINABILITY.md` Sec.4 for why
per-trade causal attribution isn't attempted). Every output includes a
`heuristic_disclosure` string making this explicit, not just a doc
comment a reader might miss. Never modifies `trades.json` or any
production data — `test_post_trade_review_does_not_modify_production_data`
proves this via a before/after byte comparison.

## 9. Integration (observational only)

`alert_signals.py` gained one new helper, `log_decision_snapshot()`,
called at every point where a SPECIFIC candidate direction/opportunity is
already known:

- Stage-2 fill approved (after every gate, right before `_send()`).
- Stage-2 held: risk lock, portfolio violation.
- Stage-1 heads-up approved (after every gate, right before `pending.add()`).
- Stage-1 held: regime block, MAST confluence hold, portfolio violation.

Every call site passes ALREADY-COMPUTED variables (the same `mkt_regime`,
`cr`, `e_pr`/`pr_verdict`, `e_assessment`/`assessment` the existing
`ledger.log()` call right next to it already uses) — zero new
computation, zero new external fetch. `log_decision_snapshot()` itself is
wrapped in a single `try/except` returning `None` on any failure, matching
every other `log_*` helper's fail-safe posture in this file
(`log_confluence_explainability`, `log_confidence_assessment`,
`log_market_memory_context`).

### 9.1 Explicit scope boundary: what is NOT snapshotted

Two account-level gates run BEFORE any specific candidate
direction/opportunity exists: the news blackout check and the
symbol-wide `risk_guard` lock checked prior to Layer 1 origination
(`sig = signals.analyze(...)` hasn't run yet at that point). Recording a
`DecisionSnapshot` with an empty/unknown direction for "nothing was being
evaluated yet" would misrepresent what a decision snapshot means — so
these two remain single-line ledger events only, exactly as before Day 8.
This is a disclosed scope decision, not a silent gap — see
`DAY8_IMPLEMENTATION_REPORT.md`'s explicit-decisions log.

## 10. Dashboard integration

`dashboard_publish.py` gained a new top-level `decision_audit` payload key
(a sibling of `signal` and `market_memory_advisory`, deliberately NOT
nested inside either — matching Day 7's "clearly separated from live
trade recommendations" pattern). It surfaces the five most recent
PERSISTED decision snapshots for the symbol, each with its audit graph and
explanation, computed via `decision_audit_history.tail(5, symbol=symbol)`
— a read of already-persisted history, never a live re-evaluation.

## 11. Testing

51 new tests across five files: `test_platform_version.py` (5),
`test_decision_audit_history.py` (15), `test_explainability_engine.py`
(19), `test_replay.py` (5), `test_post_trade_review.py` (7). Covers unit
assembly, immutability (structural, not just documented), missing-data
graceful degradation, garbage-input safety, replay determinism, and a
500-snapshot performance benchmark. See `DAY8_VALIDATION_REPORT.md` for
the full breakdown and regression results.

## 12. Known limitations

1. Two account-level gates (news blackout, pre-origination risk lock) are
   not snapshotted — Sec.9.1.
2. `post_trade_review()`'s assumption-matching is a disclosed heuristic,
   not causal attribution — Sec.8.4.
3. `dashboard`/`research` lineage presence is not determinable from a
   stored row and is reported as `None`, not guessed — Sec.7.
4. `find_by_ref()`/`find_by_trade_ref()` are O(n) scans — Sec.3.2.
5. Only six modules carry an explicit `VERSION` today
   (`COMPONENT_MODULES`); every other engine module remains
   "unversioned," disclosed rather than hidden — Sec.5.
6. No historical `decision_audit.jsonl` data exists yet (this store starts
   empty at this deployment) — see `RESEARCH_EXPLAINABILITY.md` for the
   honest current-data assessment.
