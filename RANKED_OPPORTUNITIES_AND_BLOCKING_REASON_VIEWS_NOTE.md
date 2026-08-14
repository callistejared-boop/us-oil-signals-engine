# Ranked Opportunities + Blocking-Reason Dashboard Views

**V2.2 Priority 5, Item 2**

## 1. What the gap matrix flagged

`PHASE0_GAP_MATRIX.md`: "Monitoring/Observability | Yes ... | Missing:
ranked opportunities view, per-candidate blocking-reason view | Extend
after Decision Gate + Opportunity Ranking exist." Both prerequisites
(`engine/decision_gate.py`, Priority 2; `engine/opportunity_ranking.py`,
Priority 3) were already built and are unchanged by this Item — this
landing only wires their existing output into `dashboard_publish.py`'s
payload, plus `why_not.py` (Priority 3) for the blocking-reason side.

## 2. Auditing before building

`opportunity_ranking.py` was deliberately built standalone — its own
docstring: "Wiring this into alert_signals.py's actual publish/suppress
behavior is a separate, later, deliberate decision." Confirmed by a repo
grep: it had zero callers anywhere outside its own tests. It ranks a
*batch of same-cycle candidates*, which meant it needed data from every
symbol at once — `dashboard_publish.py`'s existing `build_payload(symbol)`
is per-symbol and already computes everything a candidate needs
(confidence assessment, confluence score, regime quality) but never
returned those raw values, and its `main()` loop built-and-published each
symbol immediately, one at a time, with no point where all symbols'
candidates existed together.

## 3. What was built

**`engine/opportunity_ranking.py`**: added
`candidate_from_dashboard_payload(symbol, payload)` — a second adapter
alongside the existing `candidate_from_alert_signals_context()`, for
`dashboard_publish.py`'s situation specifically: a separate process that
only ever has its own already-built payload dict in hand, never the raw
`ConfidenceAssessment`/`ConfluenceRead`/`mkt_regime` objects the original
adapter expects. Returns `None` when the payload shows no qualifying setup.

**`engine/dashboard_publish.py`**:
- `build_payload()` gained two additive keys inside `signal_payload`:
  `confluence_score` (the already-computed local `score` var) and
  `regime_quality` (`d_regime.get("quality_score", 0)`). `d_regime` is now
  initialized to `None` before its `try` block specifically so a
  `regime_engine.classify()` failure can't leave it undefined — a real
  `NameError` risk the old code had (untested, since nothing previously
  read `d_regime` outside that `try`), now closed and covered by a
  dedicated regression test.
- `main()` is restructured from "build-then-immediately-publish per
  symbol" into two passes: build every symbol's payload first (same
  per-symbol try/except isolation as before — a failed build is simply
  absent from the batch), THEN compute the ranking across the whole batch
  via the new `_attach_opportunity_views()` helper, THEN publish. A
  symbol's own `payload["opportunity_rank"]` shows its rank/composite
  score relative to every OTHER symbol that qualified this same cycle (or
  `rank: None` if it didn't qualify); `payload["why_not"]` is
  `why_not.why_not_now(symbol)` — the exact live blocking-reason answer
  that module already provides (active stand-down, most recent recorded
  rejection, or "no data yet"), attached to every symbol's payload,
  querying, not recomputing anything.
- No Supabase schema/RPC change: the ranking and blocking-reason views
  are additional keys inside the same per-symbol JSON payload the
  existing `publish_snapshot` RPC already writes — a new cross-symbol
  table/row would be a separate, deliberate schema decision out of scope
  for an additive landing, the same reasoning `opportunity_ranking.py`'s
  own docstring already applied to live publish-gating.

## 4. Test coverage

`tests/test_opportunity_ranking.py`: 6 new tests for
`candidate_from_dashboard_payload()` — returns `None` on no-setup/
missing/garbage payloads, extracts every field correctly, honors
`calibrated_probability` exactly like the original adapter, and feeds
real output into `rank_opportunities()` end-to-end.

`tests/test_dashboard_publish.py`: 6 new tests — `build_payload()` carries
`confluence_score`/`regime_quality` when a setup exists; `regime_quality`
survives a `regime_engine.classify()` failure (the `NameError` regression
guard); `main()` ranks two qualifying symbols relative to each other;
`opportunity_rank` is `None`/`of: 0` when nothing qualifies; a build
failure on one symbol still excludes it from both publish and ranking
(the isolation guarantee, reverified across the two-pass restructure);
and `main()` never raises even if `rank_opportunities()` itself breaks.

Full suite: 1571/1571 passing (1559 prior + 12 new).
