# Day 3 Implementation Report — Production Risk Engine Integration

2026-08-03. What changed and why, in the order it was built.

## New files

| File | Purpose |
|---|---|
| `engine/portfolio_risk.py` | Centralized portfolio-level risk gate. Reuses `engine.risk` (position sizing, exposure math), `engine.risk_guard.today_realized_r` (portfolio-wide daily R), `forward_report.drawdown_r` (trailing drawdown), and `engine.correlation_dynamic` (concentration). Five checks, short-circuit on first violation, fail-open on internal error. |
| `engine/correlation_dynamic.py` | Rolling Pearson correlation of daily log returns, computed from the same `markets.fetch_resilient` + `data_loader.resample` path every other module uses. Disk-cached (`correlation_cache.json`, 24h default max age). Falls back to a crude static estimate derived from `engine.correlation.USD_SENSITIVITY` when live data is unavailable. |
| `tests/test_portfolio_risk.py` | 17 offline tests covering all five checks, block/warn modes, and fail-open behavior. |
| `tests/test_correlation_dynamic.py` | 15 offline tests covering the math, cache logic, and outage fallback — no network calls. |
| `tests/test_hourly_briefing_risk_gate.py` | 7 offline tests for the new `apply_risk_gate()` helper. |
| `DAY3_PHASE1_EXECUTION_PATH.md` | Pre-integration baseline trace of the full live execution path, and every launcher that can reach `hourly_briefing.py`. |
| `RISK_SPECIFICATION.md` | The master Day 3 reference: post-integration execution path, per-check rationale, the RISK_RULES.md/risk_guard.py day-stop reconciliation, the `hourly_briefing.py` classification decision, failure-recovery table, position-sizing review, and interface reference. |

## Modified files

| File | Change | Why |
|---|---|---|
| `engine/config.py` | Added 8 new `Settings` fields (`portfolio_equity`, `portfolio_risk_mode`, `portfolio_max_risk_pct`, `portfolio_day_stop_r`, `portfolio_max_drawdown_r`, `portfolio_max_directional`, `correlation_high_threshold`, `correlation_window_days`). Extracted the inline `int(val) if isinstance(cur, int) else val` casting into a `_coerce()` function that also handles `float` and `bool` correctly. | The new fields needed `.env`/env-var overridability; the original inline cast would have silently left every float field as an uncast string. This is the only pre-existing logic this Day 3 work modified, and it was required to integrate the new risk controls. |
| `alert_signals.py` | Added `portfolio_risk as pr` import. Inserted `pr.evaluate(...)` calls at both publication points: Stage-2 ENTRY (before `_send(build_entry(...))`) and Stage-1 HEADS-UP (before `pending.add()`/`_send(build_prealert(...))`). A violation logs a HELD line + `ledger.log({"event": "portfolio_held", ...})` and `continue`s (skips publication); a warn-mode violation logs `portfolio_warn` but still publishes. | This is THE integration point per the Day 3 mandate: "risk must be evaluated before any trade can be published." Both stages needed it — see `RISK_SPECIFICATION.md` §3 for why Stage-1 alone is insufficient. |
| `hourly_briefing.py` | Added `risk_guard`, `portfolio_risk as pr`, `ledger` imports. Extracted a new `apply_risk_gate(sym, raw, s, guard)` function (independently unit-tested) that mirrors `alert_signals.py`'s gates — news blackout (pre-existing, unchanged) → `risk_guard.evaluate()` → `pr.evaluate()` — and returns a HELD note instead of showing a confirmed signal on violation. `main()` now calls this helper instead of inlining the old blackout-only check. Module docstring updated with the Phase 8 classification decision. | Closes Finding F01 (the Day 1 audit's top finding): this script could previously publish a "CONFIRMED SIGNAL" to Telegram with zero risk_guard/range_guard/portfolio awareness. |
| `4_SEND_SIGNAL_NOW.bat` | Echo text updated to note it's now risk-gated. | Visibility only — the actual gating lives in `hourly_briefing.py`. |
| `run_hourly_silent.bat` | Comment block added explaining the Day 3 gating and why the scheduled-task path (`A_SCHEDULE_90MIN.bat`) is no longer a silent bypass. | Same reasoning — no code change needed since the fix is centralized in `hourly_briefing.py`. |
| `START_HERE.bat` | Menu labels for options 3 and 11 updated to `[research read, risk-gated]`. | Visibility for the operator; no logic change. |
| `ARCHITECTURE_SPECIFICATION.md` | Added §13 noting P0-1 and P0-3 from the original roadmap are now resolved, with a pointer to `RISK_SPECIFICATION.md`. | Keeps the Day 1 audit's own roadmap accurate. |
| `PROJECT_SUMMARY_AND_ROADMAP.md` | Added a "Day 3" section summarizing the change and the new test count (311 → 348). | Standing project log, consistent with every prior day's entry. |

## Explicit decisions made (per the mandate's own instruction to resolve ambiguity transparently rather than silently)

1. **`portfolio_risk_mode` defaults to `"block"`, not `"warn"`.** The Day 3 mandate is explicit ("the trade must be rejected before publication") and this is the core Day 3 deliverable, not an "uncertain enhancement" the Additional Instruction's research-first clause was written to gate. `"warn"` remains available as a configuration override for an operator who wants a shadow-mode evidence-gathering period before trusting a newly-added check — the same posture `range_guard.py`'s `SUPPRESS_MODE` already established as precedent in this codebase.

2. **`hourly_briefing.py` was re-guarded, not retired or redirected.** It never writes to the trade journal (verified by direct read), so it cannot itself create a tracked position; it also serves a genuinely different purpose (full on-demand read vs. two-stage pending-tracked alerts). Retiring or blanket-redirecting it would have violated "existing trading logic remains unchanged unless required to integrate risk controls." Defense-in-depth gating closes the actual risk (a human acting on an ungated "CONFIRMED SIGNAL") without changing its working behavior. Full reasoning: `RISK_SPECIFICATION.md` §6.

3. **Correlation-adjusted position SIZING was not implemented**, only correlation-based blocking. A sizing formula has no backtest evidence yet; a binary block/warn decision is auditable and reversible in a way an ad-hoc shrink formula is not. Flagged as a Day 4+ research-branch candidate. Full reasoning: `RISK_SPECIFICATION.md` §8.

4. **`portfolio_max_risk_pct` (6.0) duplicates `engine.risk.MAX_PORTFOLIO_RISK_PCT` (6.0) as a literal**, rather than importing `engine.risk` into the low-level `config.py` module. Mitigated with `test_config_cap_matches_risk_module`, which fails loudly if the two ever drift apart. A single-constant duplication with a regression test guarding it was judged safer than adding a new import dependency to the platform's most foundational module.

5. **Open-position risk is estimated, not measured**, because `journal.py`'s `Trade` dataclass has no `risk_cash`/`units` field. Documented explicitly as a known limitation (`RISK_SPECIFICATION.md` §9) rather than silently assumed — flagged for Day 4+.

## What was explicitly NOT touched

- `engine/risk_guard.py`, `engine/range_guard.py`, `engine/confluence.py`, `signals.py`, `engine/regime.py`, `engine/ict.py` — zero changes. Their existing gates were called in the same places and same order they already were; only a new gate was added downstream of them.
- `journal.py`, `pending.py`, `ledger.py`, `store.py` — zero changes; reused as-is.
- The GitHub Actions workflow (`entry-scan.yml`) — no change needed; it already calls `alert_signals.py`, which now includes the new gate internally.
