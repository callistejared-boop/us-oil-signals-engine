# gold-engine — Testing Coverage & Technical Debt Audit

Read-only audit. No files modified. Evidence-based; every claim below is backed by a grep/read command
run against the repo at
`C:\Users\jared\AppData\Roaming\Claude\local-agent-mode-sessions\1170df9c-db51-4c51-8cae-8f5c7c2d7707\55076882-932b-466d-b9d8-bb15ff97f1df\local_56ff0ed1-1ff2-4c8c-829a-98a0eb7456cc\outputs\gold-engine`.

---

## 1. Test suite run

Command: `python -m pytest --tb=short -q`

```
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
.......................                                                  [100%]
311 passed in 12.50s
```

**311 passed, 0 failed, 0 skipped, 0 errors.** Clean run, no warnings surfaced in the tail output.

Note on scope: the task brief said "27 test files." The actual count in `tests/` today is **39**
`test_*.py` files (`ls tests/test_*.py | wc -l` → 39). The suite has grown since whatever baseline the
"27" figure came from — not a discrepancy in the audit, just flagging that the repo has kept adding
tests. Likewise `engine/` has **58** modules (not ~55) and the repo root has **23** top-level `.py`
scripts (not ~30).

---

## 2. Test coverage map

Method: every `from engine import X`, `from engine.X import ...`, and root-level `import X` statement
in `tests/*.py` was extracted and matched against the 58 `engine/*.py` modules and 23 root `*.py`
scripts. "Indirect" means the module is never imported by name inside a test file, but a module that
*is* imported by a test itself imports it at module scope (so the import executes, and in some cases
shared helper functions get exercised transitively) — this is import-coverage, not necessarily
behavioral test coverage of that module's own functions.

### engine/ modules

| module | dedicated/direct test file(s) | indirect only | NO coverage |
|---|---|---|---|
| backtest.py | — | — | **YES** — only imported by `main.py`, which no test imports |
| balanced_range.py | test_gap3_modules.py | | |
| bias_adjust.py | test_bias_adjust.py, test_journal_news.py, test_journal_regime.py, test_live_integration.py, test_session_edge.py | | |
| breaker_blocks.py | test_gap2_modules.py, test_literature_review_modules.py | | |
| breakout.py | test_mast_layers.py | | |
| calibration.py | test_calibration.py | | |
| candlestick_patterns.py | test_candlestick_patterns.py, test_gap2_modules.py, test_literature_review_modules.py | | |
| chart_patterns.py | test_chart_patterns.py | | |
| config.py | test_config_env_override.py, test_wti_note.py | | |
| confluence.py | test_mast_layers.py | | |
| correlation.py | test_correlation.py | | |
| cot_feed.py | test_extra_confluence_sources.py | | |
| dashboard_publish.py | test_dashboard_publish.py | | |
| data_loader.py | test_engine.py (only `resample`) | `load_csv`, `fetch_live_twelvedata`, `fetch_live_yfinance`, `fetch_live` are **not called by any test** | |
| eia_feed.py | | imported at module scope by `engine/dashboard_publish.py` (tested) and `wti_note.py` (tested) — import-only, no behavior test | |
| elliott_wave.py | test_gap4_modules.py | | |
| fibonacci.py | test_gap3_modules.py, test_literature_review_modules.py | | |
| freshness.py | test_freshness.py | | |
| fundamentals_feed.py | test_fundamentals_feed.py, test_llm_news.py, test_news_bias.py | | |
| grade.py | test_grade.py | | |
| icc.py | test_gap4_modules.py | | |
| ict.py | | imported at module scope via `ict_confluence.py`, `signals.py`, `wyckoff.py` (all tested) — import-only | |
| ict_confluence.py | test_ict_confluence.py | | |
| journal.py | test_journal_news.py, test_journal_regime.py, test_journal_store.py | | |
| ledger.py | test_ledger.py | | |
| liquidity_strength.py | test_gap2_modules.py | | |
| llm_news.py | test_llm_news.py | | |
| ltf.py | | imported at module scope by `alert_signals.py` (tested) — import-only, `ltf.line()`/`ltf.confirm()` never called by a test | |
| markets.py | test_markets_resilient.py | | |
| mean_reversion.py | test_mast_layers.py | | |
| momentum_divergence.py | test_gap_fill_sources.py | | |
| montecarlo.py | | | **YES** — only imported by `engine/report.py`, which is itself only imported by untested `main.py` |
| news_alerts.py | test_news_alerts.py | | |
| news_guard.py | | imported at module scope by `alert_signals.py` (tested) — import-only, `news_guard.evaluate()`/`.line()` never directly unit-tested | |
| pending.py | | imported at module scope by `alert_signals.py` (tested) — import-only | |
| pivots.py | test_gap_fill_sources.py | | |
| price_action.py | test_mast_layers.py | | |
| range_guard.py | test_range_guard.py | | |
| regime.py | test_regime.py | | |
| report.py | | | **YES** — only imported by untested `main.py` |
| risk.py | test_risk.py | | |
| risk_guard.py | test_risk_guard.py | | |
| risk_sentiment.py | test_extra_confluence_sources.py | | |
| seasonality.py | test_extra_confluence_sources.py | | |
| session_edge.py | test_session_edge.py | | |
| session_model.py | test_gap3_modules.py | | |
| signals.py | test_dashboard_publish.py | | |
| spread_feed.py | test_extra_confluence_sources.py | | |
| store.py | test_store.py | | |
| structure.py | test_engine.py, test_gap2_modules.py, test_ict_confluence.py | | |
| symbol_meta.py | test_alert_signals_basis_note.py | | |
| technicals.py | | imported at module scope by `engine/dashboard_publish.py` (tested) — import-only, `technicals.compute()` never directly unit-tested | |
| telegram_alerts.py | | | **YES** — only imported by untested `main.py` |
| trend_quality.py | test_mast_layers.py | | |
| tv_signals.py | test_tv_signals.py | | |
| volume_profile.py | test_mast_layers.py | | |
| walkforward.py | test_walkforward.py | | |
| wyckoff.py | test_mast_layers.py | | |

**Summary: 47 of 58 engine modules have direct dedicated tests. 6 have import-only "indirect" exposure
(eia_feed, ict, ltf, news_guard, pending, technicals) with no test that calls their functions and
asserts on results. 4 have zero coverage of any kind (backtest, montecarlo, report, telegram_alerts) —
notably, all 4 dead-end at `main.py`, which itself is never imported/exercised by the test suite.**

### root-level `*.py` scripts (23 total)

| script | direct test coverage | indirect | NO coverage |
|---|---|---|---|
| alert_signals.py | test_alert_signals_basis_note.py, test_live_integration.py | | |
| heartbeat_watchdog.py | test_heartbeat_watchdog.py | | |
| news_bias.py | test_news_bias.py | | |
| wti_note.py | test_wti_note.py | | |
| analyze_tf.py | | | **YES** |
| analyze_wti.py | | | **YES** |
| chart_wti.py | | | **YES** |
| command_center.py | | | **YES** |
| forward_report.py | | | **YES** |
| gold_btc_hourly.py | | | **YES** |
| hourly_briefing.py | | | **YES** (see §3.5 — this is the important one) |
| main.py | | | **YES** |
| news_watch.py | | | **YES** |
| performance_dashboard.py | | | **YES** |
| post_overview.py | | | **YES** |
| publisher.py | | | **YES** |
| self_review.py | | | **YES** |
| send_test_alert.py | | | **YES** |
| set_channel_title.py | | | **YES** |
| tv_webhook.py | | | **YES** |
| verify_all.py | | | **YES** |
| weekly_audit.py | | | **YES** |
| wti_hourly.py | | | **YES** |

**Summary: only 4 of 23 root scripts (17%) have any test at all.** 19 root scripts — including the
main scheduler entry point (`main.py`), the live-alert-fanout script for gold/oil/BTC
(`gold_btc_hourly.py`), the webhook receiver (`tv_webhook.py`), and every HTML dashboard generator —
have zero test coverage of any kind.

---

## 3. Technical debt scan

### 3.1 TODO / FIXME / XXX / HACK / temporary / deprecated

`grep -rniE "TODO|FIXME|XXX|HACK|temporary|deprecated"` across `*.py`, `*.md`, `*.bat`, `*.pine`,
`*.html` (excluding `__pycache__`, `.pytest_cache`, `.git`):

```
./engine/fundamentals_feed.py:87:  "bear": {"crackdown": 4, "ban": 3, "banned": 3, "hack": 4, "exploit": 3, "outflow": 3, ...
./tests/test_news_bias.py:22:def test_btc_hack_is_bearish():
./tests/test_news_bias.py:23:    bias, s = ff.score_title("Major exchange hack triggers crypto selloff and liquidation", ...
```

**No real TODO/FIXME/XXX/HACK/deprecated markers exist anywhere in the codebase.** The 3 hits above are
false positives — `"hack"` is a bearish-sentiment keyword in the news-scoring dictionary (crypto
exchange hacks move BTC price), not a code comment. This is a genuinely clean signal: either the team
resolves debt immediately rather than marking it, or (more likely, given the volume of other findings
below) debt isn't being tracked with markers at all — it just accumulates silently as duplicated code
and untested scripts instead.

### 3.2 Duplicate function/class names across files

Scanned every `def X` / `class X` (including indented/method-level) across the whole repo. **763 total
definitions, 50 names duplicated across 2+ files.** Full list generated; the ones worth flagging:

- **`class Trade`** defined independently in both `engine/backtest.py` and `engine/journal.py` —
  two unrelated `Trade` representations with the same name in the same package. Naming-collision risk
  for anyone doing `from engine import *` or refactoring imports; worth an audit to confirm they don't
  drift into representing the same concept differently.
- **Dashboard/reporting helpers duplicated near-identically across `command_center.py`,
  `performance_dashboard.py`, `self_review.py`, `weekly_audit.py`**: `equity_svg`/`_equity_svg`,
  `pct`, `pf_fmt`, `session_of`, `conf_bucket`, `tbl`, `seg`, `block`. Four root scripts each
  reimplement the same equity-curve SVG renderer, percentage formatter, and session/confidence
  bucketing logic instead of sharing one module. `engine/dashboard_publish.py` already proves this
  logic *can* live in `engine/` and be unit-tested (`test_dashboard_publish.py`) — these four scripts
  don't follow that precedent, so the same formatting logic exists in ~4 untested copies that can
  silently drift out of sync with each other.
- **Caching helpers duplicated across `engine/cot_feed.py`, `engine/eia_feed.py`,
  `engine/risk_sentiment.py`, `engine/spread_feed.py`**: `_load_cache`, `read_cached`, `refresh`,
  `note`. Same pattern — a shared "fetch external feed, cache to disk, fall back to stale cache on
  error" pattern reimplemented four times rather than factored into one cache helper.
- `main` is (expectedly) defined in ~15 files — that's the standard CLI-entrypoint convention, not a
  concern.

### 3.3 Files with no docstring / module-level comment

Checked every root `.py` and every `engine/*.py` file (excluding tests) via `ast.get_docstring()`.
**Zero files lack a module docstring.** This is a genuine strength — every module, including one-off
scripts like `post_overview.py`, opens with an explanatory docstring, several of which (e.g.
`risk_guard.py`, `wti_note.py`, `wti_hourly.py`, `gold_btc_hourly.py`) go further and document *why*
a design decision was made and when it changed (dated notes like "Bug fix (2026-07-28)" and "Added
2026-07-28"). Documentation hygiene at the module level is good; it's test coverage and duplication
that lag behind it.

### 3.4 Bare `except:` / silent `except Exception:` blocks

`grep -rn "except:"` → **zero bare excepts** anywhere in the repo.

`grep -rn "except Exception"` → **165 occurrences**, all tagged `# noqa: BLE001` (a deliberate
Ruff/flake8-bugbear lint suppression — this is a project-wide convention, not 165 separate oversights).
Most return an explicit fallback value or include the exception text in a returned/printed message
(e.g. `engine/dashboard_publish.py:307` prints `f"publish failed ({exc}) — dashboard will show stale
data, pipeline continues"`).

However, **15 of the 165 are truly silent** — `except Exception: pass` with no log line, no print, no
returned error context:

```
engine/correlation.py:52
engine/cot_feed.py:125
engine/eia_feed.py:56
engine/fundamentals_feed.py:219
engine/journal.py:133   <- inside _save(), swallows failure to write the trades.json.bak rolling backup
engine/ledger.py:23
engine/ledger.py:32
engine/llm_news.py:86
engine/markets.py:83
engine/markets.py:96    <- explicitly commented "caching is best-effort — never let it break a live fetch"
engine/pivots.py:48
engine/pivots.py:56
engine/risk_sentiment.py:73
engine/spread_feed.py:169
alert_signals.py:54
```

Most of these are in caching/best-effort paths where silent failure is arguably the right call
(`markets.py:96` even says so in a comment). `journal.py:133` is the one worth a second look — a
failed backup write during `_save()` is swallowed with no signal at all, so a broken backup mechanism
in the trade journal could go unnoticed indefinitely.

**The most important finding in this whole scan is `engine/risk_guard.py:97`** — see §3.5.

### 3.5 THE key finding: the live-alert entry point that bypasses the risk guard

`engine/risk_guard.py` is the account's circuit breaker (daily loss lock + position cap). Its own
module docstring states the design explicitly:

> "Fail-safe: any error evaluating the rules returns 'unlocked' so a bug can never silently kill the
> pipeline — but errors are reported in the reason string."

```python
# engine/risk_guard.py:97-99
except Exception as exc:  # noqa: BLE001
    return {"locked": False, "day_r": 0.0, "open_n": 0,
            "reason": f"risk-guard error ({exc}) — failing open"}
```

That's a **documented, deliberate fail-open policy on a risk circuit breaker in a live trading
system**: if the risk-guard's own logic throws (bad trades.json, bad config, whatever), the guard
returns "not locked" and the pipeline is free to publish another signal. This is defensible as an
availability trade-off, but it means the one thing standing between the account and unbounded
daily loss is designed to disable itself under error conditions, and there is no counter, alert, or
log aggregation anywhere in the repo that would notice if this fail-open path started firing
repeatedly in production — the only trace is a string embedded in a Telegram-bound "reason" field.

That risk is compounded by a second, independently-confirmed fact: **`engine/risk_guard.py` and
`engine/range_guard.py` are not even wired into every live signal path.**

- `alert_signals.py` (the modern, tested entry point) *does* call both:
  `alert_signals.py:30` imports `range_guard as rgd, ... risk_guard`; calls `risk_guard.evaluate(sym)`
  at lines 148 and 181.
- `hourly_briefing.py` (an older entry point, **zero test coverage**, see §2) imports
  `news_guard, ict, markets, bias_adjust` but **never imports or calls `risk_guard` or `range_guard`
  at all**, and computes its own ad-hoc "grade" via `bias_adjust.grade_from()` rather than
  `engine/grade.py`. It builds and sends "CONFIRMED SIGNAL" Telegram messages with no daily-loss-lock
  or position-cap check whatsoever.
- The repo itself already flags this. `UNREGISTER_STALE_TASK.bat` disables the old
  `"XAUUSD Signal 90min"` scheduled task with this exact comment written to its own output file:
  > "Disabling stale 'XAUUSD Signal 90min' task (runs hourly_briefing.py, which predates the MAST
  > confluence engine and bypasses range_guard/risk_guard/grade.py)"

So the team already identified and disabled *one* scheduled trigger for `hourly_briefing.py`. But the
script itself is still present, still untested, and **`4_SEND_SIGNAL_NOW.bat` still calls it directly**
(`where py >nul 2>nul && (py hourly_briefing.py) || (python hourly_briefing.py)`), and
`START_HERE.bat` — the main interactive menu — still wires option **"3  Send a signal now"** straight
to `4_SEND_SIGNAL_NOW.bat` → `hourly_briefing.py`. `run_hourly_silent.bat` (used by the disabled
scheduled task) also still calls it. Anyone running the primary documented entry point by hand still
reaches a signal path with no risk-guard, no range-guard, and no test coverage, in direct contradiction
of the repo's own internal note about why that path was supposed to be retired.

**Recommendation for whoever picks this up:** either delete/retire `hourly_briefing.py` and repoint
`4_SEND_SIGNAL_NOW.bat`/`START_HERE.bat` option 3 at `alert_signals.py`, or add the same
`risk_guard`/`range_guard`/`grade.py` calls to `hourly_briefing.py` and write tests for it. Leaving it
as-is means the platform has two live-signal code paths with different risk enforcement, and the safer
one is not the one the main menu points to.

### 3.6 Root-level script duplication / near-duplicates

Read every root script's header docstring. Verdict: **these are genuinely distinct tools, not
copy-paste leftovers** — each has a specific, documented purpose (`analyze_tf.py` = multi-timeframe
top-down ICT read → `analysis_tf.txt`, no Telegram; `analyze_wti.py` = on-demand full WTI
analysis → `wti_report.txt`; `chart_wti.py` = renders an HTML chart only). `wti_hourly.py` and
`gold_btc_hourly.py` are explicitly self-documented as intentional "twins" (`gold_btc_hourly.py`
docstring: "the gold/BTC twin of wti_hourly.py... Added 2026-07-28 as part of turning gold and Bitcoin
on end-to-end"), a deliberate per-symbol pipeline split rather than accidental duplication.

The real duplication isn't at the *tool* level (each script's *purpose* is distinct and well
documented) — it's at the *implementation* level inside the dashboard-generating cluster
(`command_center.py`, `performance_dashboard.py`, `self_review.py`, `weekly_audit.py`), already
covered in §3.2.

### 3.7 `.bat` launcher audit (35 files)

Every `.bat` file was grepped for `python `/`py ` invocations. **All `.py` files referenced by every
`.bat` launcher exist in the repo — no launcher points at a missing script.** Full call map:

| .bat | runs |
|---|---|
| 0_SETUP_AND_VERIFY.bat | pip install -r requirements.txt; `main.py scan --live` (writes setup_log.txt) |
| 1_TEST_ALERT.bat | send_test_alert.py |
| 2_INSTALL.bat | pip install -r requirements.txt |
| 3_START_SIGNALS.bat | main.py run |
| 4_SEND_SIGNAL_NOW.bat | **hourly_briefing.py** (see §3.5) |
| 5_SCHEDULE_HOURLY.bat | schtasks only → run_hourly_silent.bat |
| 6_FIX_BATTERY.bat | powershell only (task settings) |
| 7_VERIFY_ALL.bat | verify_all.py |
| 8_SCHEDULE_15MIN.bat | schtasks only → run_hourly_silent.bat |
| 9_POST_OVERVIEW.bat | post_overview.py |
| A_SCHEDULE_90MIN.bat | schtasks only → run_hourly_silent.bat |
| B_SCHEDULE_ENTRY_SCAN.bat | schtasks only → run_alert_silent.bat (alert_signals.py) |
| C_TEST_ALERT_NOW.bat | alert_signals.py |
| D_ANALYZE_WTI.bat | analyze_wti.py |
| E_DRAW_WTI_CHART.bat | pip install plotly; chart_wti.py |
| F_DASHBOARD.bat | performance_dashboard.py |
| G_WTI_NOTE.bat | engine/fundamentals_feed.py; wti_note.py --send |
| H_SELF_REVIEW.bat | self_review.py |
| I_COMMAND_CENTER.bat | self_review.py; performance_dashboard.py; command_center.py |
| J_WEEKLY_AUDIT.bat | weekly_audit.py --send |
| K_REFRESH_FUNDAMENTALS.bat | engine/fundamentals_feed.py |
| L_SCHEDULE_FUNDAMENTALS.bat | schtasks only → run_fundamentals_silent.bat |
| M_SCHEDULE_NEWS_5MIN.bat | schtasks only → run_news_silent.bat |
| N_NEWS_INTERFACE.bat | engine/fundamentals_feed.py; news_bias.py |
| O_START_TV_WEBHOOK.bat | tv_webhook.py |
| P_ANALYZE_TF.bat | analyze_tf.py WTIUSD |
| Q_TEST_LLM.bat | engine/llm_news.py |
| RUN_GAP_TESTS.bat | py_compile check; pytest tests/; wti_note.py (writes gap_test_output.txt) |
| R_CALIBRATION.bat | python -m engine.calibration |
| START_HERE.bat | interactive menu; calls 2_INSTALL/7_VERIFY_ALL/4_SEND_SIGNAL_NOW/G_WTI_NOTE/I_COMMAND_CENTER/F_DASHBOARD/N_NEWS_INTERFACE/H_SELF_REVIEW/J_WEEKLY_AUDIT/K_REFRESH_FUNDAMENTALS/A_SCHEDULE_90MIN/M_SCHEDULE_NEWS_5MIN/B_SCHEDULE_ENTRY_SCAN/O_START_TV_WEBHOOK/6_FIX_BATTERY |
| S_WALKFORWARD.bat | python -m engine.walkforward |
| TASK_AUDIT.bat | schtasks /Query only (no python) |
| UNREGISTER_STALE_TASK.bat | schtasks only — disables the "XAUUSD Signal 90min" task and documents why (see §3.5) |
| U_SCHEDULE_HOURLY.bat | schtasks only → run_alert_silent.bat |
| V_ANALYZE_WTI.bat | engine/fundamentals_feed.py; wti_note.py |
| W_HOURLY_WTI.bat | wti_hourly.py (writes wti_hourly.log) |
| X_SCHEDULE_WTI_HOURLY.bat | schtasks /Create → W_HOURLY_WTI.bat, then calls it immediately |
| Y_REBRAND_AND_ANALYZE.bat | set_channel_title.py; wti_hourly.py (writes rebrand_log.txt) |
| Z_FORWARD_REPORT.bat | forward_report.py --send |
| check_hb.bat | py -c ast-parse checks on hourly_briefing.py and engine/news_guard.py |
| run_alert_silent.bat | alert_signals.py |
| run_fundamentals_silent.bat | engine/fundamentals_feed.py |
| run_hourly_silent.bat | **hourly_briefing.py** |
| run_news_silent.bat | engine/correlation.py; engine/fundamentals_feed.py; news_bias.py; command_center.py; news_watch.py |
| verify2.bat | import smoke test; `data_loader.load_csv` + `signals.analyze`; pytest tests/ |
| verify3.bat | `data_loader.fetch_live` live smoke test |

No launcher references a missing file. The only structural issue is the one already covered:
`4_SEND_SIGNAL_NOW.bat` and `run_hourly_silent.bat` both still point at the script the team's own
`UNREGISTER_STALE_TASK.bat` comment says should have been retired.

### 3.8 Generated/output artifacts sitting in the repo, and what's actually tracked in git

`.gitignore` exists and covers: `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.cache/`,
`*.json.bak`, `*.json.tmp`, `*_result.txt`, `hb_check.txt`, `alert_heartbeat.txt`, `last_briefing.txt`,
`*.log`, `task_audit_output.txt`, `unregister_output.txt`. That's reasonably thoughtful, but it's
incomplete — `git status` and `git ls-files` show these generated/output artifacts are **actually
committed to version control**:

- **State/cache JSON** (mutates every run, not source): `cot_cache.json`, `fundamentals.json`,
  `macro.json`, `pending.json`, `risk_sentiment_cache.json`, `spread_cache.json`, `trades.json`,
  `run_ledger.jsonl`, `news_state.json`
- **Generated HTML reports** (rebuilt by scripts on every run): `command_center.html`,
  `dashboard.html`, `news_bias.html`, `track_record.html`, `wti_chart.html`, `self_review.html`,
  `XAUUSD_Signals_App.html`, `sample_report_2025-05_06.html`
- **Generated .txt output** (also not covered by the `*_result.txt` glob): `analysis_tf.txt`,
  `diag.txt`, `forward_report.txt`, `fresh_note.txt`, `gap_test_output.txt`, `llm_diag.txt`,
  `llm_wire_err.txt`, `rebrand_log.txt`, `setup_log.txt`, `verify_all.txt`, `wti_note.txt`,
  `wti_report.txt`, `wti_send_status.txt`
- `webapp/index.html`, `webapp/manifest.json` are also tracked (may be legitimate static site source
  rather than generated output — worth confirming with whoever owns `webapp/`).

`git status --short` at audit time also shows `fundamentals.json`, `news_state.json`,
`command_center.html`, `news_bias.html` as currently modified-but-uncommitted — i.e., this isn't a
one-time accident, these files churn and get diffed on every commit cycle. `trades.json` (the actual
live trade ledger — the source of truth risk_guard reads to decide whether to lock trading) being
committed to git is a special case: it's arguably *not* pure build output, since it's the account's
real trading history and losing it would be bad, but it also means every trade produces a git diff,
and the `.gitignore` explicitly ignores `*.json.bak`/`*.json.tmp` (the *backup* of trades.json) while
tracking the live file itself — an inconsistent policy either way you look at it (back up what you
don't track, or track what you back up, not a mix).

---

## 4. Naming and structural consistency

The `engine/` vs. root-script split largely follows one implicit rule, consistently applied:
**`engine/` holds pure, offline-testable domain logic** (signal generation, structure/ICT detection,
confluence sources, risk rules, persistence, config) that's imported as a library and has no
side-effecting network/Telegram/file-writing "main". Every module in `engine/` that this audit read
has a module docstring, several explicitly say things like "Pure logic + a thin journal reader, so it
is unit-testable offline" (`risk_guard.py`). **Root-level scripts are the executable glue** — CLI
entry points and scheduled-task targets that wire `engine/` modules together with I/O side effects
(Telegram posting, HTML file writes, `.txt` report generation).

That rule holds for the majority of the repo, but there is one clear, repeated violation: **reporting
logic that computes derived statistics (equity curves, percentage formatting, session/confidence
bucketing) lives at the root, copy-pasted across `command_center.py`, `performance_dashboard.py`,
`self_review.py`, and `weekly_audit.py`, instead of in `engine/`.** This is genuinely business logic
(it decides what "win rate" or "expectancy" means, not just how to draw it), not I/O glue, so by the
repo's own apparent rule it belongs in `engine/` where it would get a shared implementation and unit
tests — the same way `engine/dashboard_publish.py` already does for the JSON dashboard payload path
(and is tested via `test_dashboard_publish.py`). The four root scripts don't follow the precedent set
by their own sibling module, which is the clearest structural inconsistency in the repo.

A secondary, smaller inconsistency: `engine/report.py`, `engine/backtest.py`, and
`engine/telegram_alerts.py` live in `engine/` (suggesting testable library code) but are only ever
imported by `main.py`, itself untested and seemingly a legacy/alternate entry point separate from the
`alert_signals.py` / `wti_hourly.py` / `gold_btc_hourly.py` pipelines that the `.bat` launchers and
`START_HERE.bat` menu actually drive day-to-day. It's unclear from the repo alone whether `main.py`
is still a live entry point or a leftover from an earlier architecture — worth confirming with whoever
owns deployment, since if it's dead, `backtest.py`/`report.py`/`telegram_alerts.py`/`montecarlo.py`
(4 of the 6 fully-uncovered `engine/` modules) are dead code, not undertested code.

---

## Evidence index (commands run)

- `python -m pytest --tb=short -q` — full suite
- `grep -n "^import\|^from" tests/*.py` — full import inventory used for §2
- `grep -rn "import <module>"` per untested engine module, to check for indirect (transitive) import coverage
- `grep -rniE "TODO|FIXME|XXX|HACK|temporary|deprecated"` across the whole repo
- Custom `def`/`class` scanner (763 definitions) → duplicate-name detector
- `ast.get_docstring()` scanner over every root and `engine/*.py` file
- `grep -rn "except:"` / `grep -rn "except Exception"` + a swallow-detector that inspects the line
  immediately following each `except` for a bare `pass`
- Manual read of `engine/risk_guard.py`, `alert_signals.py`, `hourly_briefing.py`,
  `UNREGISTER_STALE_TASK.bat`, `4_SEND_SIGNAL_NOW.bat`, `run_hourly_silent.bat`, `START_HERE.bat`
- `grep -n "python "` inside every `*.bat` file, cross-checked against `ls *.py engine/*.py`
- `git status --short` / `git ls-files | grep -E "\.(json|txt|html|log|jsonl)$"` against `.gitignore`
