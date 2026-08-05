# Day 3 Next-Day Readiness Report

2026-08-03. Remaining risks, open questions, and prerequisites for Day 4
(Market Regime Engine, per the V2 roadmap sequence).

## Remaining risks

1. **`portfolio_equity` is notional, not measured.** No module in this
   codebase reads a live broker balance. The default (`$10,000`) is a
   placeholder. If the operator's real forward-test account size differs,
   every portfolio exposure percentage will be computed against the wrong
   base until `PORTFOLIO_EQUITY` is set in `.env` to match. **Action before
   trusting this in `"block"` mode with real capital:** set this value
   correctly, or the 6% cap could be materially wrong in either direction.

2. **Open-position risk is estimated, not measured** (see
   `RISK_SPECIFICATION.md` §9). If an operator ever manually sizes a
   position away from the platform's stated 1% default, the portfolio
   exposure math will not reflect that override. Low risk today (the
   platform doesn't currently support manual override anywhere in its
   alerting path), but worth fixing before it does.

3. **Correlation data quality depends on live market data access.** This
   sandboxed development environment has no outbound internet access
   (confirmed during Day 1 and reconfirmed during Day 3 testing — see
   `DAY3_VALIDATION_REPORT.md` §3), so `correlation_dynamic.py`'s live path
   has never actually been exercised end-to-end against real Yahoo
   Finance/TwelveData data, only its offline math and fallback paths. It
   should work identically in the GitHub Actions production environment
   (which does have network access, per the existing `entry-scan.yml`
   proven path), but this is a documented gap in what could be verified
   from here: **recommend a manual smoke-test run of `python -m
   engine.correlation_dynamic` in the real production environment before
   fully trusting `"block"` mode on correlation grounds specifically.**

4. **`portfolio_risk_mode="block"` is now live by default.** This is a
   direct, explicit instruction from the platform owner (see Implementation
   Report, decision #1), but it does represent a meaningful behavior change:
   a trade that would have published yesterday could be silently rejected
   today if it breaches a portfolio constraint. **Recommend monitoring
   `run_ledger.jsonl` for `portfolio_held`/`briefing_held` events closely
   for the first several days** to confirm the checks are firing for the
   right reasons and not, e.g., overly conservative due to the estimated
   (not measured) equity/position-size assumptions in risks #1–2 above.

## Open questions for the platform owner

1. Is `$10,000` the right default for `portfolio_equity`, or should it be
   set now via `.env` before the next live run?
2. Is `portfolio_max_directional=2` (max 2 simultaneous same-direction
   positions across all 3 symbols) the right concentration limit, or should
   it start looser (e.g. 3, effectively a warning-only posture until the
   correlation data has more history) given risk #3 above?
3. Should `4_SEND_SIGNAL_NOW.bat`/`run_hourly_silent.bat` eventually be
   renamed to make their research/informational status explicit in the
   filename itself, not just in comments and menu labels? (Not done in Day
   3 — renaming a `.bat` file that may be referenced by an existing Windows
   Scheduled Task would need the task re-registered too, which is outside
   this session's remote reach; flagging as a decision for the operator to
   make on their own machine.)

## Prerequisites for Day 4 (Market Regime Engine)

Per the V2 roadmap sequence, Day 4 focuses on the Market Regime Engine.
Relevant context this session surfaced that Day 4 should account for:

- `engine/regime.py::classify()` already exists and is already called from
  both `alert_signals.py` and `hourly_briefing.py` (pre-Day-3, unchanged) —
  Day 4 is a redesign/extension of something already wired in, not a
  from-scratch integration, which is a materially different (likely lower
  net-new-integration-risk) shape of work than Day 3 was.
- `portfolio_risk.py`'s `session_overlap_factor()` is currently a crude,
  informational-only stand-in (see Known Limitation #2 in the Validation
  Report) — Day 4's regime work may produce a more principled session/regime
  classification that this function should eventually be replaced by
  reusing, rather than left as a parallel, cruder implementation.
- `range_guard.py`'s `SUPPRESS_MODE=False` and its documented "flip to True
  only after the evidence is in" precedent is the same standard Day 3's
  `portfolio_risk_mode` deliberately followed. Day 4 should continue that
  same discipline for any new regime-based blocking behavior.

## Backlog items flagged during Day 3 (not implemented — explicitly deferred with reasoning)

| Item | Why deferred | Where documented |
|---|---|---|
| Add `risk_cash`/`units` fields to `journal.py`'s `Trade` dataclass so portfolio exposure is measured, not estimated | Would require a `journal.py` schema change and migration of existing `trades.json` rows — out of scope for an "integration, not a redesign" day; needs its own reviewed change | `RISK_SPECIFICATION.md` §9 |
| Correlation-adjusted (not just correlation-blocked) position sizing | No backtest evidence yet; needs a research-branch comparison against the current fixed-% baseline before promotion, per the Additional Instruction's production/research separation | `RISK_SPECIFICATION.md` §8 |
| Promote `session_overlap_factor()` from informational to a blocking check | No forward-test evidence yet that session overlap predicts anything actionable | `RISK_SPECIFICATION.md` §4, §8 |
| Rename `hourly_briefing.py`'s launchers for clarity | Needs to happen on the operator's own machine if a Scheduled Task references the filename | Open question #3 above |

## Verification before Day 4 begins

- [x] Full test suite green (348/348)
- [x] No regressions in the pre-existing 311
- [x] No stray files/network calls left behind by the new test suite
- [x] `RISK_SPECIFICATION.md`, `ARCHITECTURE_SPECIFICATION.md`, and
      `PROJECT_SUMMARY_AND_ROADMAP.md` all reflect the final, as-shipped code
- [ ] **Operator action still needed:** confirm `portfolio_equity` and
      `portfolio_max_directional` defaults (open questions #1–2) before the
      next live GitHub Actions run, since `portfolio_risk_mode="block"` is
      now live by default and will act on whatever these are set to.
