# Day 5 Next-Day Readiness Report

## Remaining risks

1. **The measurement framework is unproven against real data.**
   `measure_contribution()` and `recommend_weight_adjustments()` are fully
   built and pass 47 tests against synthetic data, but have never run
   against a real labeled trade because zero closed trades carry a
   `confluence_score`. The first real-data run of this framework is a
   meaningful unknown — it's possible real data surfaces edge cases (e.g.
   sparse label distributions, sources that never disagree in practice)
   the synthetic tests didn't anticipate. Treat the first several
   real-data runs as validation exercises, not settled output.
2. **Nominal point-value reconstruction could diverge from
   `confluence.py`'s actual per-trade math** for sources with conditional
   sub-weights (trend quality, Wyckoff, volume profile, news). This affects
   `explain()`'s per-source point display and `quality_score()`'s
   diversity/agreement weighting, but NOT `cr.score`/`cr.final_tier`
   themselves (untouched). Risk is cosmetic/analytical, not operational —
   but should be tightened before the contribution-measurement framework's
   output is trusted for a real weighting decision.
3. **`regime_vol` remains invisible in `agree`/`disagree`.** Any future
   attempt to measure its contribution will silently undercount it as
   "neutral/missing" until `confluence.py` is given a small, deliberate
   patch to label it — flagged, not fixed, this session.
4. **The three-echo finding (session timing, Wyckoff/sweep, ICC cluster) is
   structural, not yet outcome-validated.** It is very likely, given how
   directly it's grounded in shared function calls, that these are real
   redundancies — but "shares the same information source" and "adds zero
   incremental expectancy" are not logically identical claims. A duplicate
   mechanism firing on a slightly different subset of cases could still
   have nonzero value. Don't treat §2.2 of the research report as license
   to remove these sources without running them through the sandbox first.

## Open questions for the platform owner

1. Should `journal.py`'s `Trade` dataclass be extended now (small, focused
   change) to persist `confluence_score` and a direct pointer to its
   originating `confluence_history.jsonl` row, removing the
   nearest-timestamp-join approximation entirely? This was deferred as
   out-of-scope for Day 5 ("reuse, don't restructure") but is arguably the
   highest-leverage single change available to accelerate Day 5's own
   measurement framework reaching usable data volume.
2. Should `confluence.py` be given the smallest possible patch to (a) label
   `regime_vol` in `agree`/`disagree` and (b) persist the exact `news_delta`
   value on `ConfluenceRead`? Both are narrow, additive changes that
   wouldn't touch any existing score/gate logic, but they do mean touching
   `confluence.py` for the first time since the audit — worth an explicit
   go-ahead given the mandate's original "the goal is not to replace MAST"
   framing.
3. Given zero real confluence-score data exists yet, is the priority for
   Day 6 (Confidence Engine) to proceed as previewed, or to first let
   Day 4's regime data and Day 5's confluence data accumulate for a few
   weeks before building a third layer that would also want historical
   outcome data to calibrate against? Both Day 4 and Day 5 are now data
   producers with nothing yet to consume; a Confidence Engine is a natural
   third consumer, but it will face the identical "insufficient_data"
   finding on day one unless real trading volume increases first.

## Prerequisites for Day 6 (Confidence Engine)

Per the mandate's own "Strategic Direction" preview: Day 6 should replace
Layer 1's arbitrary-percentage confidence with a calibrated estimate
derived from historical performance. Before that work begins:

- `confluence_history.jsonl` and `regime_history.jsonl` need real
  accumulated rows (currently near-zero, both starting from today) — a
  calibration engine trained on zero examples cannot be meaningfully
  different from an arbitrary percentage.
- The `journal.py` `Trade`-schema gap (item 1 above) should ideally be
  resolved before Day 6, since a Confidence Engine calibrating against
  "did this trade win" needs the SAME clean historical linkage Day 5's
  measurement framework is currently working around via nearest-timestamp
  join — fixing it once benefits both.
- `quality_score()` (Day 5) and the regime quality score (Day 4) are both
  designed as candidate INPUTS to a future calibrated confidence estimate,
  per `CONFLUENCE_SPECIFICATION.md` §8.3 — worth confirming this is still
  the intended architecture before Day 6 starts building.

## Backlog items flagged during Day 5 (not implemented — explicitly deferred with reasoning)

| Item | Reasoning for deferral |
|---|---|
| Persist exact per-source point deltas on `ConfluenceRead` | Requires modifying `confluence.py`; deferred per "reuse, don't restructure" and pending owner go-ahead (open question #2) |
| Label `regime_vol` in `agree`/`disagree` | Same as above |
| Extend `journal.py`'s `Trade` schema with a direct confluence-read foreign key | Same category of "touches an existing, working file outside Day 5's stated scope"; flagged as highest-leverage next step (open question #1) |
| Statistically fit `quality_score()`'s category/formula weights | No labeled outcome data exists yet to fit against — premature by construction |
| Run `measure_contribution()`/`recommend_weight_adjustments()` for real | Blocked on data volume (n≥30 per source), not on code readiness |
| Promote any of the three flagged overlap sources through the sandbox pipeline | Requires real historical/walk-forward/paper-trading evidence that doesn't exist yet; sandbox is ready to receive candidates whenever it does |

## Verification before Day 6 begins

- [x] Full test suite: 437/437 passing, 0 regressions
- [x] `engine/confluence.py` byte-unchanged from pre-Day-5 state (no score/
      gate/weight modified)
- [x] `git status` clean of stray data-file artifacts
- [x] `confluence_sandbox` import-isolation from `confluence.py` verified by
      automated test
- [x] `trades.json` `confluence_score` finding independently re-queried and
      confirmed (0/99 populated) immediately before writing this report
- [ ] Owner decision on the two open `confluence.py`-touching questions
      above, before Day 6 work that would depend on cleaner data begins
