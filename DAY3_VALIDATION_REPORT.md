# Day 3 Validation Report — Production Risk Engine Integration

2026-08-03. Tests performed, results, and regressions found/fixed.

## 1. Full suite results

```
Baseline (before Day 3 changes):  311 passed
After Day 3 changes:               348 passed   (+37 new, 0 regressions, 0 failures)
```

Ran with `python3 -m pytest -q` from the repo root, three times across this
session (once as a pre-change baseline, once immediately after the new test
files were added, once as a final clean re-run after fixing the issue in
§3). All three runs: 100% pass rate, no flaky results.

## 2. New tests, by file

| File | Tests | What's covered |
|---|---|---|
| `tests/test_portfolio_risk.py` | 17 | Config/risk-module cap sync guard; clean book allow; exposure-cap breach block; warn-mode flags-without-blocking; directional concentration block + exact-boundary allow; correlation-too-high block; low-correlation allow; opposite-direction skip; portfolio day-stop block + "not today" exclusion; trailing 30-trade drawdown block; fail-open on malformed input; `line()` formatting for both clear and rejected verdicts. |
| `tests/test_correlation_dynamic.py` | 15 | Identity short-circuit; Pearson correlation (perfect positive/negative, insufficient-N, zero-variance); log-return math (including the non-positive-price skip case); static fallback (same-sign vs. unknown-symbol); cache read (fresh, reverse-key, stale-rejected, missing-file); outage fallback with no live data source (network explicitly disabled via monkeypatch, not skipped); `line()` formatting. |
| `tests/test_hourly_briefing_risk_gate.py` | 7 | Non-confirmed/None signals pass through untouched; news-blackout suppression (pre-existing behavior, confirmed unchanged); risk_guard-lock suppression; portfolio-risk-rejection suppression; warn-mode shows-but-logs; clean pass shows the signal. |

## 3. Regression found and fixed during validation

**Finding:** `tests/test_portfolio_risk.py::test_directional_concentration_at_exact_cap_allows`,
as first written, did not monkeypatch `correlation_dynamic.get_correlation`.
Because that test's directional check passes (falls through to the
correlation check), running it made a REAL live call through
`markets.fetch_resilient` → `yfinance`/TwelveData for both symbols, and
`correlation_dynamic.refresh()` wrote a real `correlation_cache.json` to the
repo root as a side effect.

This was caught by inspecting `git status` and file mtimes after the first
full test run, per this report's own "no stray artifacts" check — not by a
test failure (the test still passed; the yfinance call apparently
succeeded, so the fallback path wasn't even exercised, which made the
problem easy to miss without an explicit disk/network hygiene check).

**Fix:** the test now monkeypatches `pr.corr_dyn.get_correlation` to a fixed
neutral value, consistent with every other test in the file that reaches
the correlation check. `correlation_cache.json` was deleted from the repo
root (it is not tracked by design — no test should be writing production
cache files). Re-ran the full suite after the fix: 348/348 passing, `git
status` confirms zero new/modified data files from the test run.

**Why this matters beyond "a test was flaky":** this is exactly the kind of
outbound network call the codebase's own prior investigation flagged as
unavailable from this sandboxed environment (`PROJECT_SUMMARY_AND_ROADMAP.md`:
"the sandbox this session runs in has no general outbound internet access
(confirmed — direct requests to Yahoo Finance and Supabase's REST host both
failed to connect)"). In an environment where the call fails slowly (DNS
timeout) rather than failing fast, an untested code path like this could
have made the test suite slow or flaky in CI. All correlation-reaching test
paths are now explicitly offline.

## 4. Manual verification

- `ast.parse()` on every changed/new Python file (`alert_signals.py`,
  `hourly_briefing.py`, `engine/portfolio_risk.py`,
  `engine/correlation_dynamic.py`, `engine/config.py`) — all parse cleanly.
- Read-through of the final `alert_signals.py` diff at both insertion points
  to confirm the portfolio gate runs AFTER `risk_guard`/MAST-confluence and
  BEFORE `_send()`/`pending.add()`, matching the documented hierarchy.
- Confirmed `hourly_briefing.py`'s `apply_risk_gate()` preserves the
  pre-existing news-blackout behavior byte-for-byte (same held-note text,
  same `sig=None` result) via
  `test_news_blackout_suppresses_confirmed_signal`.
- Confirmed no test touches the real `trades.json`/journal files: every
  `portfolio_risk` test passes `rows=` explicitly rather than letting
  `evaluate()` fall through to `store.load_array(TRADES_PATH)`.

## 5. Final Validation checklist (per the Day 3 mandate)

| Item | Status | Evidence |
|---|---|---|
| No existing trading logic changed unnecessarily | ✅ | Only `config.py`'s casting helper was touched in pre-existing code, and only because the new fields required it (see Implementation Report §"Explicit decisions", item 4/the `_coerce` change). No gate's own internal logic (`risk_guard.py`, `range_guard.py`, `confluence.py`, `signals.py`, `regime.py`) was modified. |
| No regression introduced | ✅ | 311/311 pre-existing tests still pass, unchanged. |
| No duplicate risk logic remains | ✅ | `portfolio_risk.py` imports and reuses `engine.risk`, `engine.risk_guard.today_realized_r`, `forward_report.drawdown_r` rather than reimplementing any of them; the module docstring explicitly lists the five rejection categories it deliberately does NOT reimplement because an existing gate already owns them. |
| Risk decisions are explainable | ✅ | Every `evaluate()` call returns a `detail` dict (equity, cap_pct, open_risk_pct, portfolio_heat, risk_budget_remaining_pct, directional_exposure, candidate_risk_cash, session_overlap_factor, and the specific violation's own numbers) whether or not it blocked — not just a pass/fail flag. |
| Portfolio controls function correctly | ✅ | 17 dedicated tests, each isolating one of the five checks and its boundary condition. |
| Testing passes | ✅ | 348/348, see §1. |
| Documentation matches implementation | ✅ | `RISK_SPECIFICATION.md` was written directly against the final code (function names, field names, and default values copy-checked against the actual files, not from memory). |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. Open-position risk is estimated from the platform's stated default (1%),
   not measured, because `journal.py` doesn't persist actual position size.
   See `RISK_SPECIFICATION.md` §9.
2. `session_overlap_factor()` is informational only (logged, not blocking) —
   no forward-test evidence yet to justify blocking on it. See
   `RISK_SPECIFICATION.md` §4 row 2/§8.
3. Correlation estimates below `MIN_SAMPLE_DAYS=20` are blended toward the
   static fallback rather than fully trusted — by design, mirroring
   `calibration.py`'s `min_n=8` precedent, but this means early correlation
   readings for a newly-added symbol will be conservative/uncertain until
   enough daily history accumulates.
