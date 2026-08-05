# RISK SPECIFICATION — Gold/US Oil High Probability Platform

**Day 3 deliverable.** Covers the Production Risk Engine integration completed
2026-08-03: `engine/portfolio_risk.py`, `engine/correlation_dynamic.py`, the
`alert_signals.py`/`hourly_briefing.py` wiring, and the failure-recovery
design for every new dependency this introduces. Companion to
`DAY3_PHASE1_EXECUTION_PATH.md` (pre-integration baseline trace),
`ARCHITECTURE_SPECIFICATION.md` (Day 1 audit), and `RISK_RULES.md` (the
plain-language rules this formalizes).

---

## 1. Scope and non-goals

This is an **integration**, not a redesign. Every piece of math (position
sizing, portfolio exposure %, drawdown) already existed in `engine/risk.py`
and `forward_report.py`, fully unit-tested, before Day 3 — it was simply
never called from the live path. Day 3 adds exactly one new decision layer
(`engine/portfolio_risk.py`) that aggregates the open book across symbols
and one new data layer (`engine/correlation_dynamic.py`) that estimates how
correlated that book is, and wires both into the two places a trade can
currently be published (`alert_signals.py`'s Stage-1/Stage-2 paths,
`hourly_briefing.py`'s confirmed-signal section). No existing per-symbol gate
(`risk_guard.py`, `range_guard.py`, MAST confluence) was modified in its own
logic — only called earlier in the same way it already was.

## 2. Post-integration execution path

```
... [unchanged: session/regime/strategy/confluence/risk_guard, see
    DAY3_PHASE1_EXECUTION_PATH.md Sec.1] ...
                    |
                    v
        engine/portfolio_risk.py :: evaluate(symbol, direction, entry, stop, ...)
                    |
        allow=True? ----No----> log HELD, ledger.log(portfolio_held / briefing_held), STOP
                    |
                   Yes
                    |
                    v
              _send() / Telegram publish  (alert_signals.py)
              OR confirmed-signal section shown (hourly_briefing.py)
```

Two call sites in `alert_signals.py::main()` (Stage-1 HEADS-UP, immediately
before `pending.add()`/`_send()`; Stage-2 ENTRY, immediately before `_send()`
in the pending-record loop) and one in `hourly_briefing.py` (via the new
`apply_risk_gate()` helper, called right after `signals.analyze()`). All
three call the exact same `engine.portfolio_risk.evaluate()` function — one
centralized engine, three integration points, not three implementations.

## 3. Why the portfolio gate had to run at BOTH alert stages

Stage-1 (HEADS-UP) is not itself a fill, but it seeds `pending.json`, and
Stage-2 (ENTRY) fires automatically off that pending record with **no**
further portfolio check of its own in between — Stage-2 only re-checks
`risk_guard` (per-symbol). If the portfolio gate only ran at Stage-2, a
HEADS-UP could be announced publicly ("watching for entry at X") for a trade
that would already be portfolio-rejected today; then, if the portfolio state
changed favorably before price tapped the level, Stage-2 would fire without
ever having represented the HEADS-UP's own portfolio context to begin with.
Running the check at both stages means: (a) a portfolio-blocked setup is
never announced in the first place, and (b) if it were announced before
today's book existed, the ENTRY fill is independently re-validated against
the book *at fill time*, which is the state that actually matters for risk.

## 4. Portfolio Risk Engine — what it checks, in order, and why

`engine/portfolio_risk.py::evaluate()` runs five checks in this order. Each
one returns immediately on the first violation found (short-circuit), so the
returned `category`/`reason` always names the FIRST constraint that failed,
not necessarily the only one.

| # | Check | Reuses | Category | Rationale for this position in the order |
|---|---|---|---|---|
| 1 | Portfolio exposure cap (aggregate risk % of equity, including this candidate) | `engine.risk.portfolio_exposure` | `portfolio_exposure_exceeded` | Cheapest, most fundamental constraint — if the book is already full, nothing else matters. |
| 2 | Simultaneous directional exposure (max same-direction positions across all symbols) | new (`directional_exposure`) | `trade_frequency_control` | A distinct failure mode from #1: three *small* same-direction trades can each be individually small yet represent one concentrated market bet. |
| 3 | Correlation concentration (same-direction + correlated open position) | `engine.correlation_dynamic.get_correlation` | `correlation_too_high` | Requires a network-backed lookup (cached), so it runs after the two purely-local checks above to avoid unnecessary correlation lookups when the trade would already be rejected on cheaper grounds. |
| 4 | Portfolio-wide daily loss stop | `engine.risk_guard.today_realized_r(rows, symbol=None)` | `drawdown_protection` | Time-sensitive circuit breaker — checked before the slower-moving 30-trade drawdown check. |
| 5 | Trailing 30-trade portfolio drawdown cap | `forward_report.drawdown_r` | `drawdown_protection` | Last line of defense: a structural capital-preservation stand-down, independent of today specifically. |

If all five clear, `evaluate()` returns `allow=True, category=None` and the
full explainability payload (`detail`) is still returned — every call is
logged with its inputs and outputs (`portfolio_heat`, `risk_budget_remaining_pct`,
`directional_exposure`, `open_risk_pct`, etc.) whether or not it blocked,
satisfying the Phase 3/7 requirement that portfolio state be visible, not
just pass/fail.

### 4.1 Categories this module deliberately does NOT implement

Per the Day 3 mandate's own guiding principle ("avoid parallel
implementations"), five of the ten Phase 7 rejection categories are owned by
existing, already-tested gates and are not reproduced here:

| Category | Owned by |
|---|---|
| `session_restriction` | `ict.py` session logic |
| `market_regime_unsuitable` | `engine/regime.py` + `engine/range_guard.py` |
| `confidence_below_threshold` | `signals.py` / `engine/confluence.py` thresholds |
| `liquidity_conditions` | `engine/range_guard.py`'s chase/extreme-severity checks |
| `duplicate_opportunity` (same symbol) | `engine/risk_guard.py`'s per-symbol position cap |

`portfolio_risk.py` defines all ten category constants (so every layer of
the pipeline can log under one shared vocabulary) but only ever *returns*
the five it owns.

## 5. Reconciling RISK_RULES.md's account-wide day-stop with risk_guard.py's per-symbol implementation

`RISK_RULES.md` rule #2 reads: *"Day stop: −2R. After −2R of closed losses
in a day the engine locks and publishes no new signals until tomorrow
(UTC)."* Read literally, this is an **account-wide** rule. The shipped
`engine/risk_guard.py`, however, deliberately scopes the day-stop **per
symbol** (2026-07-28 fix, `test_daily_loss_lock_is_per_symbol`) specifically
so that a bad gold day cannot silently lock out oil or Bitcoin signals too.
That was the right call for a single-symbol day-stop, but it left a real gap
between the written rule and the code: nothing was checking the account-wide
number the document actually promises.

`portfolio_risk.evaluate()`'s check #4 closes that gap without touching
`risk_guard.py`: it calls `risk_guard.today_realized_r(rows, symbol=None)` —
the exact same function, with `symbol=None`, which sums every symbol's
closed trades for today "for free" (the function only filters by symbol when
one is explicitly passed). `Settings.portfolio_day_stop_r` (default `2.0`,
matching the document literally) governs the threshold; it is configurable
independently of `risk_guard`'s own per-symbol `max_daily_loss_r`, so an
operator running two or three symbols simultaneously can widen the
account-wide number without touching the per-symbol protection that was
fixed for a specific, tested reason.

## 6. `hourly_briefing.py` — Phase 8 classification decision

**Decision: keep, do not retire or redirect — but close the gap with
defense-in-depth gating.**

Reasoning: `hourly_briefing.py` never calls `journal.log_signal()` (verified
by direct read) — it cannot itself create a tracked "open position," so it
is not a position-origination path in the same sense `alert_signals.py` is.
It also serves a distinct, real purpose the two-stage alerter does not: an
always-available, on-demand full Smart-Money + technicals read for every
configured symbol, not gated on a fresh setup having just formed. Retiring
it would remove a working, useful tool for no risk-reduction benefit.
Redirecting its launchers to `alert_signals.py` instead would silently
change their behavior (`alert_signals.py` is pending-state-driven, not an
instant full-read tool) and violates the guiding principle "existing trading
logic remains unchanged unless required to integrate risk controls."

It DOES, however, publish a `*** CONFIRMED SIGNAL ***` section to Telegram
that a human could act on manually — so it is not exempt from risk
governance. Day 3 adds `hourly_briefing.apply_risk_gate()` (extracted as an
independently unit-tested function — see
`tests/test_hourly_briefing_risk_gate.py`), which mirrors
`alert_signals.py`'s gates in the same order: news blackout (pre-existing,
unchanged) → `risk_guard.evaluate()` → `portfolio_risk.evaluate()`. A
suppressed signal becomes a structured HELD note in the briefing text,
exactly like the pre-existing news-blackout suppression it was modeled on.

### 6.1 Every launcher, classified

| Launcher | Decision | Why |
|---|---|---|
| `4_SEND_SIGNAL_NOW.bat` | **Keep**, now risk-gated via `hourly_briefing.py` itself | Manual on-demand read; menu/echo text updated to say so. |
| `run_hourly_silent.bat` | **Keep**, now risk-gated via `hourly_briefing.py` itself | Same script, silent variant for scheduling. |
| `START_HERE.bat` option 3 ("Send a signal now") | **Keep**, relabeled `[research read, risk-gated]` | Calls `4_SEND_SIGNAL_NOW.bat`; no logic change needed, just visibility. |
| `START_HERE.bat` option 11 ("Schedule 90-min briefings") | **Keep**, relabeled `[research read, risk-gated]` | See 6.2 below — this was the most severe finding. |
| `A_SCHEDULE_90MIN.bat` | **Keep**, comment added | Registers the Windows Scheduled Task that runs `run_hourly_silent.bat` every 90 min; the gating lives in `hourly_briefing.py` itself so this needed no code change, only a documentation comment. |
| `check_hb.bat` | **No change — out of scope** | Static `ast.parse()` syntax check only; never calls `main()`, never publishes anything. Confirmed by direct read. |
| `entry-scan.yml` (GitHub Actions, `alert_signals.py`) | **No change needed** | Already the production path; Day 3's gates were added directly inside it. |

### 6.2 Most severe Phase 1/8 finding

`START_HERE.bat` option 11 does not run `hourly_briefing.py` once — it calls
`schtasks /Create ... "run_hourly_silent.bat" /SC MINUTE /MO 90`, registering
a **standing, unattended Windows Scheduled Task** that would have run every
90 minutes indefinitely, with zero risk_guard/range_guard/portfolio
awareness, until manually unregistered. This is exactly the kind of
execution path the Day 3 mandate's Phase 8 was written to find. Because the
fix lives inside `hourly_briefing.py` itself (via `apply_risk_gate()`) rather
than in any one launcher, this scheduled task — and any future launcher that
might call `hourly_briefing.py` — is covered automatically without having to
track down and edit every entry point individually.

## 7. Failure recovery (Phase 9)

Every new dependency `portfolio_risk.py`/`correlation_dynamic.py` introduces,
and its designed failure behavior:

| Dependency | Failure mode | Retry | Fallback | Safe shutdown | Notification |
|---|---|---|---|---|---|
| `engine.portfolio_risk` module itself (bug/exception) | Any uncaught exception inside `evaluate()` | None — single evaluation, not worth retrying mid-scan | **Fail OPEN**: returns `allow=True, mode="fail-open"` with the exception text in `reason` | N/A — the enclosing `alert_signals.py`/`hourly_briefing.py` scan loop continues to the next symbol regardless (existing per-symbol `try/except` in both `main()` loops, unchanged) | `reason` string is included in the returned dict; callers that log it (both integration points do) surface it in `alert_heartbeat.txt` / `last_briefing.txt` and the ledger |
| Trade journal / `trades.json` unreadable or corrupt | `store.load_array()` hits a parse error | None | `store.load_array` salvages a truncated file back to its last complete record; total failure returns `[]` (empty book) — never raises | N/A | Silent by design (matches `risk_guard.py`'s existing use of the same reader) — an empty book means every portfolio check evaluates as if no positions were open, which is conservative in the direction of NOT falsely blocking, but is documented here as a real limitation: a genuinely corrupt journal could under-count real exposure. Flagged in `DAY3_NEXT_DAY_READINESS_REPORT.md`. |
| Correlation data source (yfinance/TwelveData) unavailable | `markets.fetch_resilient()` raises (no live source AND no local cache) | None at the correlation layer — `markets.fetch_resilient` already retries live-then-cache internally | `correlation_dynamic._daily_closes()` catches the exception, returns `None`; `compute_pair()` degrades to `_static_fallback()` (crude sign-only estimate from `engine.correlation.USD_SENSITIVITY`) | N/A | `sample` field in the returned dict is tagged `"no_data"` so it is visible in logs/ledger, not silently indistinguishable from a real computed value |
| Correlation cache file (`correlation_cache.json`) unreadable/stale | `read_cache()` hits a parse error or age > `max_age_hours` | None | Returns `None`, caller (`get_correlation`) falls through to a fresh `refresh()` attempt, which itself degrades to the static fallback per-pair on further failure | N/A | N/A (best-effort cache, same posture as `engine.correlation`'s `macro.json`) |
| Database — **N/A for this platform** | This codebase has no database (confirmed by Day 1 audit: file-based `trades.json`/`journal.jsonl` storage throughout) | — | — | — | — |
| Telegram API unavailable | `_post()`/`send()` raise or return `ok=False` | None (both `alert_signals.py` and `hourly_briefing.py` already wrap the whole per-symbol iteration in `try/except`, pre-existing, unchanged) | The scan continues to the next symbol; the failed publish is recorded in `alert_heartbeat.txt`/`last_briefing.txt` as `ERROR ...` (pre-existing behavior) | N/A | The heartbeat/briefing-log file itself is the notification channel already in use platform-wide |
| Ledger (`run_ledger.jsonl`) unwritable | `ledger.log()`'s blanket `try/except: pass` | None | Silent no-op (pre-existing design, unchanged) — losing an observability entry must never block a risk decision or a publish | N/A | None — this is an accepted, pre-existing trade-off (observability is best-effort, risk-blocking is not) |

**Design principle applied throughout:** every NEW Day 3 dependency
(`portfolio_risk`, `correlation_dynamic`) fails open on internal error,
exactly matching `risk_guard.py` and `range_guard.py`'s existing posture — a
bug in newly-added risk code must never be able to silently halt the entire
alert pipeline. The one place Day 3 intentionally fails **closed** is a
genuine, successfully-computed constraint violation under
`portfolio_risk_mode="block"` — that is not a failure, it is the check doing
its job, per the explicit Day 3 mandate.

## 8. Position sizing (Phase 6)

Current chain, unchanged by Day 3 except for where it is now READ from:

`engine.risk.position_size(equity, risk_pct, entry, stop)` — fixed
percentage risk (`DEFAULT_RISK_PCT=1.0`), volatility-adjustable via
`vol_adjusted_risk()` (`VOL_SCALE` table), used today only for the
*display-only* `sizing_lines()` shown in Telegram messages (illustrative
$1k/$5k/$10k accounts) — this was already true before Day 3 and is
unchanged.

**New in Day 3:** `portfolio_risk.py` uses the SAME `risk.position_size()`
function to estimate each open position's `risk_cash` for portfolio
aggregation purposes (see §9 below for the documented limitation this
implies), and to size the CANDIDATE trade identically, so the exposure math
in §4 is internally consistent with the platform's own stated default risk.

**Not implemented in Day 3, and why:** correlation-adjusted or
portfolio-adjusted position SIZE (shrinking a trade's size rather than
binary-blocking it) was considered and explicitly deferred. The Day 3
mandate's Additional Instruction requires uncertain enhancements to prove
themselves with statistical evidence before reaching production; a
sizing-adjustment formula has no such evidence yet (the 42-trade backtest
underlying the platform's confidence assessment predates any correlation- or
portfolio-aware sizing). Binary block/warn is auditable, explainable, and
reversible in a way an ad-hoc size-shrink formula is not. **Recommended Day
4+ backlog item:** build a research-branch backtest that replays the
existing 42-trade + ongoing forward-test history with a candidate
correlation-adjusted sizing formula and compares expectancy/drawdown against
the current fixed-% baseline before promoting it to production — see
`DAY3_NEXT_DAY_READINESS_REPORT.md`.

## 9. Known, documented limitation: estimated vs. measured position risk

`engine/journal.py`'s `Trade` dataclass does not persist the actual
`risk_cash`/`units` a position was sized at when it was opened (verified by
direct read of the dataclass fields — no such field exists). Until that
field is added, `portfolio_risk.open_positions_snapshot()` conservatively
treats every open position as sized at the platform's own stated default
risk (`engine.risk.DEFAULT_RISK_PCT`, 1%) for aggregation purposes. This is
a documented approximation, not a measurement. It is conservative in the
sense that it matches the platform's own stated risk discipline, but if an
operator ever manually overrides position size away from the stated
default, the portfolio exposure numbers in this engine will not reflect
that override. Flagged as a Day 4+ backlog item in
`DAY3_NEXT_DAY_READINESS_REPORT.md`.

## 10. New configuration surface (`engine/config.py`)

| Field | Default | Purpose |
|---|---|---|
| `portfolio_equity` | `10000.0` | Notional account size for portfolio-risk % math. No live-broker-balance reader exists anywhere in this codebase; operators must override to match their real forward-test account. |
| `portfolio_risk_mode` | `"block"` | `"block"` enforces rejections (default, per the explicit Day 3 mandate); `"warn"` is a shadow-mode evidence-gathering escape hatch. |
| `portfolio_max_risk_pct` | `6.0` | Mirrors `engine.risk.MAX_PORTFOLIO_RISK_PCT`; kept in sync by `test_config_cap_matches_risk_module`. |
| `portfolio_day_stop_r` | `2.0` | Account-wide daily loss stop (see §5). |
| `portfolio_max_drawdown_r` | `6.0` | Trailing 30-trade portfolio drawdown cap, matching `RISK_RULES.md`. |
| `portfolio_max_directional` | `2` | Max simultaneous same-direction open positions across all symbols. |
| `correlation_high_threshold` | `0.6` | \|correlation\| above which two symbols are treated as concentrated risk. |
| `correlation_window_days` | `60` | Rolling window for `correlation_dynamic`. |

All are `.env`/environment-variable overridable, exactly like every existing
`Settings` field. `engine/config.py::_coerce()` was extracted (from
previously-inline casting logic) to correctly parse the new float-typed
fields — the original inline cast only handled `int`/`str`, which would have
silently left every new float field as an uncast string. This is the one
piece of genuinely pre-existing code this Day 3 work modified, and it was
required to integrate the new risk controls, per the guiding principle.

## 11. Testing summary

See `DAY3_VALIDATION_REPORT.md` for full pass/fail results. New test files:
`tests/test_portfolio_risk.py` (17 tests), `tests/test_correlation_dynamic.py`
(15 tests), `tests/test_hourly_briefing_risk_gate.py` (7 tests) — all
offline/deterministic, no live network calls, no disk pollution (rows are
injected directly, matching the existing `test_risk_guard.py` pattern; where
a code path could reach a real network call, it is explicitly monkeypatched
— see the "correlation_cache.json pollution" fix documented in the
Validation Report).

## 12. Interfaces reference

```python
# engine/portfolio_risk.py
evaluate(symbol, direction, entry, stop, settings=None, rows=None,
        session_label=None) -> dict
    # {allow, would_block, mode, category, reason, detail, generated}

open_positions_snapshot(open_rows, equity, base_risk_pct=None) -> list[dict]
directional_exposure(open_rows) -> dict            # {"long": n, "short": n}
portfolio_drawdown_r(closed_rows, window=30) -> float
portfolio_heat(open_risk_pct, cap_pct) -> float
risk_budget_remaining_pct(open_risk_pct, cap_pct) -> float
session_overlap_factor(session_label) -> float      # informational only
line(verdict) -> str

# engine/correlation_dynamic.py
get_correlation(symbol_a, symbol_b, settings=None, max_age_hours=24) -> dict
    # {corr, n, sample, method, source}
compute_pair(symbol_a, symbol_b, settings, window_days=60) -> dict
refresh(settings, symbols=None, window_days=None) -> dict
read_cache(max_age_hours=24) -> dict | None
line(symbol_a, symbol_b, result) -> str

# hourly_briefing.py
apply_risk_gate(sym, raw, s, guard) -> (sig_or_None, held_note, ledger_event_or_None)
```
