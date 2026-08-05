# Gold/US Oil High Probability Platform — Project Summary & Improvement Roadmap
*US Oil · Gold · Bitcoin — prepared 2026-07-20 (renamed 2026-08-03)*

---

## Part 1 — What We Built

This started as a single-market ICT/SMC signal tool and grew into a full institutional-style research and delivery platform. Here's the shape of it, grouped by what each layer actually does.

### 1.1 The core engine (Layer 1 — origination)
Everything starts with ICT/Smart Money Concepts structure reading: multi-timeframe bias (Daily/4H/1H/15m), dealing ranges, equilibrium, OTE (optimal trade entry) zones, fair value gaps, order blocks, liquidity sweeps, displacement, break-of-structure/change-of-character detection, and session/kill-zone timing. This is the **only** layer allowed to originate a trade idea — nothing downstream can invent a setup Layer 1 didn't find. That rule hasn't changed since day one and is the backbone of why the system doesn't chase noise.

### 1.2 The MAST confluence engine (Layer 2 — confirmation only)
Every other methodology confirms, downgrades, or rejects a Layer-1 idea — none of them can originate one. As of today this is **fourteen** independent confirmation sources, each contributing weighted points to a single 0–100 score:

| Layer | What it checks |
|---|---|
| Price action | Candle-close structure vs. the key level |
| Trend quality | EMA stack alignment + ADX + MACD-histogram trend maturity |
| Breakout quality | Was the last structural break real or a false break? |
| Mean reversion | RSI/Bollinger/VWAP-distance — is this move already exhausted? |
| Wyckoff | Spring/upthrust events, sign-of-strength/weakness, absorption |
| Volume profile | POC / value area — is price buying/selling at fair value? |
| Macro (DXY) | Does the dollar trend support or fight this trade? |
| News/fundamentals | Live-scored headline sentiment, negation-aware |
| Session timing | Kill-zone / session-overlap bonus |
| Volatility regime | Range vs. trend, expansion vs. compression classification |
| COT positioning | Managed-money net positioning + percentile-of-year |
| Brent-WTI/crack spreads | Oil-specific leading indicators |
| Seasonality | Calendar-based structural priors (driving season, hurricane season) |
| Cross-asset risk sentiment | VIX/equities regime, with a geopolitical override |
| **RSI momentum divergence** *(new this session)* | Price vs. oscillator shape at swing points — classic exhaustion signal |
| **Daily/weekly pivot confluence** *(new this session)* | Classic floor-trader levels other participants are also watching |
| **Candlestick patterns** *(new this session)* | Engulfing, hammer/shooting star, doji family, marubozu, morning/evening star, three soldiers/crows — scored only when they print fresh on the current bar |

A handful of items are **hard gates** (breakout confirmation, mean-reversion exhaustion, news-risk, minimum R:R, liquidity objective) — fail one and the setup is rejected outright regardless of score. Everything else is scored, not gated, by design: making every item a hard gate would choke the system to near-zero signals.

### 1.3 Risk governance
- **Range guard** — downgrades/caps grade when a trade would chase price into a range-high/low against an adverse dollar trend.
- **Risk guard** — daily loss lock (stops new signals after a bad day) and max-open-positions-per-symbol cap.
- **News blackout guard** — stands aside around high-impact scheduled releases.
- **Calibration** — walk-forward-derived probability, so the published "est. probability" isn't just the raw model confidence, it's adjusted against what actually happened historically.

### 1.4 Delivery
- **Telegram** — two-stage alerts (heads-up when a setup forms, entry trigger when price taps it), hourly institutional note, weekly self-audit.
- **Live mobile/desktop dashboard** (Vercel-hosted PWA) — signal card, custom-rendered markup chart (real candles + EMAs + entry/stop/target/OTE/dealing-range, since the free TradingView widget can't be scripted to draw custom levels), recent signals table, forward-test track record, institutional positioning block. Installable to a phone home screen.
- **TradingView** — a custom Pine Script indicator (SMC + Kill Zones) plus webhook bridge, and manual markup sessions driven directly on your live chart.

### 1.5 Verification discipline
201 automated tests (all offline/deterministic, zero live-network dependency), every new module compile-checked and test-run before being wired into the live pipeline, and every change this session was live-verified against a real scheduled pipeline run before being reported as done — including catching and confirming a genuine weekend futures-close data gap wasn't a bug.

### 1.6 Current operational status
WTI is the only symbol actively running end-to-end (scheduled hourly + 15-minute scans, live Telegram, live dashboard). Forward-test (paper) track record as of today: 16 closed trades, +0.26R expectancy, +4.1R net — still a small sample, more on that below.

---

## Part 2 — Honest Architecture Assessment

**Strong:** the Layer-1/Layer-2 separation is the right call — it's what keeps the confluence layers from ever talking the system into a trade Layer 1 didn't already see. The hard-gate/soft-score split is a deliberate, documented trade-off, not an oversight. Fail-safe design (every module degrades to "neutral, no crash" rather than raising) has held up under real weekend-gap conditions. Test coverage is genuinely good for what exists.

**Weak, and this is the main finding from today's audit:** the system was built oil-first, and several pieces are still hardcoded to oil even though multi-instrument support was scaffolded early on (`markets.py` already knows about XAUUSD/EURUSD/BTCUSD). You just told me the actual product scope is US Oil + Gold + Bitcoin — here's exactly what's not ready for that yet.

---

## Part 3 — Improvement Roadmap

### Tier 1 — Do first (multi-instrument parity: Oil, Gold, Bitcoin)

This is the highest-leverage work because you just defined the actual product scope and the engine currently only really runs one of the three.

| Gap | Current state | What's needed |
|---|---|---|
| Active symbol list | `.env` has `SYMBOLS=WTIUSD` only | Add XAUUSD, BTCUSD |
| Institutional note generator | `wti_note.py` is oil-specific (oil-flavored language, oil news sources) | Generalize into one asset-aware note builder, or per-asset variants |
| Live dashboard | `dashboard_publish.py` hardcodes `SYMBOL = "WTIUSD"`, single-row payload | Multi-symbol payload + a symbol switcher/tabs on the dashboard |
| Telegram delivery | Only a WTI channel configured | Separate channels (or clearly asset-tagged messages in one channel) for gold and bitcoin |
| COT positioning | `cot_feed.py` is hardcoded to one CFTC market name | Parametrize by symbol — CFTC publishes COT for gold (COMEX) and now CME Bitcoin futures too |
| Brent-WTI/crack spreads | Fundamentally oil-only, can't apply to gold or Bitcoin as-is | Needs asset-appropriate substitutes: real yields/TIPS or gold-silver ratio for gold; futures basis/funding-rate for Bitcoin. Not a drop-in reuse — genuinely different modules |
| Seasonality | Oil-specific table (driving season, hurricane season) | Build a gold seasonality table (Sept–Nov wedding/Diwali demand, Lunar New Year); Bitcoin has no credible seasonal edge yet — honest move is to leave it neutral rather than invent one |
| **Daily loss lock (risk_guard)** | **Confirmed today: sums `result_r` across ALL symbols, not per-symbol** | This is a real bug risk once multiple assets are live — a bad gold day would silently lock out oil and Bitcoin signals too. Needs to scope the loss lock per-symbol (position cap already is) |
| Test coverage | Fixtures are almost entirely WTI-shaped | Add gold/Bitcoin data-path fixtures so a regression there isn't invisible |

Momentum divergence, pivots, and candlestick patterns (all three added today) are already fully symbol-agnostic — pure OHLC math, zero rework needed to run them on gold or Bitcoin.

### Tier 2 — Signal quality / probability improvements

- **EIA inventory data is sitting unused.** The note output literally says *"EIA inventory: not configured — get a free key at eia.gov/opendata/register.php."* This is a five-minute win that's been available the whole time and directly matters for oil.
- **Kelly-informed position sizing.** Right now sizing lines are flat % of account. The engine already produces a calibrated probability and a letter grade — using both to size (bigger on A+/A, smaller on C+) would likely do more for actual profitability than any new confirmation layer, since it changes how much is risked on the setups already known to be better.
- **Automate the recalibration cadence.** Calibration is walk-forward-derived but I don't see it re-running on a schedule as new forward-test trades close. As the sample grows past today's 16 trades, stale calibration becomes a real risk — worth a scheduled job.
- **Futures term structure (contango/backwardation).** Flagged as a deliberate omission in an earlier pass — no reliable free data source without adding a fragile dependency. Worth revisiting if a paid feed ever enters the picture; it's a genuine oil-specific institutional signal this system doesn't have.

### Tier 3 — Functional robustness

- **Watchdog on the scheduler itself.** If the laptop sleeps, loses network, or Task Scheduler silently fails, is anything telling you? Right now the answer looks like "no" — a simple daily heartbeat check ("last successful run was X hours ago") closes that blind spot.
- **Secondary data-feed fallback.** Currently yfinance-only (or TwelveData if a key is set). This session's weekend price freeze was correct behavior, not a bug, but a fallback source would reduce blind spots during genuine outages.
- **Use `self_review.py`'s factor-attribution** to actually measure whether the four new Tier-2 layers (divergence, pivots, candlesticks, and the earlier COT/spread/seasonality/risk-sentiment batch) are pulling their weight once enough forward-test trades accumulate — the infrastructure to answer "is this feature actually helping" already exists, it just needs to be pointed at the growing trade log periodically.

### On sample size, said plainly
16 closed forward-test trades is not enough to say the system "works" in a statistically meaningful sense yet — it's enough to say it hasn't blown up, which is the right bar for this stage. The most profitable thing on this whole list, ahead of any new indicator, is probably just letting the track record grow long enough for the calibration and factor-attribution loops to have something real to learn from.

---

## Bottom line — suggested order of attack

1. ~~Fix the cross-symbol daily-loss-lock bug before gold/Bitcoin go live~~ **DONE 2026-07-28.**
2. ~~Turn on gold and Bitcoin at the `.env` level and get their note/dashboard/Telegram delivery working end-to-end~~ **DONE 2026-07-28.**
3. ~~Turn on the free EIA key.~~ **User action still required — see below.**
4. ~~Build gold-specific COT + seasonality; build a Bitcoin-appropriate substitute for the spread layer.~~ **DONE 2026-07-28.**
5. Move to Kelly-informed sizing once there's enough forward-test history per grade to trust it. **Not started — deliberately: still ~16 closed forward-test trades, not enough to fit a sizing model against without fooling ourselves. Revisit once the sample size grows.**

---

## Status update — 2026-07-28

Items 1–2 above are complete, plus most of the GitHub Actions migration
that was queued after them. Recap for the permanent record (per the
"documentation over memory" rule — future sessions should trust this over
re-deriving it):

**1. risk_guard cross-symbol bug — fixed.** `today_realized_r()` now takes
a `symbol` argument and only sums that symbol's closed trades; `evaluate()`
passes it through. Regression test `test_daily_loss_lock_is_per_symbol` in
`tests/test_risk_guard.py` locks this in. A bad day on gold can no longer
lock out oil or Bitcoin.

**2. Gold + Bitcoin end-to-end — turned on.**
- `.env`'s `SYMBOLS` is now `WTIUSD,XAUUSD,BTCUSD` (was `WTIUSD` only).
- New `engine/symbol_meta.py` is the single source of truth for per-symbol
  display names, basis notes, short labels, Telegram-channel labels, and
  the trade note's "what voids this" risk bullets — both
  `engine/dashboard_publish.py` and `wti_note.py` now read from it instead
  of each hardcoding their own oil-only copy.
- `engine/dashboard_publish.py`: `build_payload()`/`publish()` are fully
  symbol-parametrized; `main()` loops every symbol in `SYMBOLS` with
  per-symbol try/except isolation. Also fixed a second bug found during
  this work: `_fundamentals()` used to call `ff.load_feed()` with no
  argument, which defaults to WTIUSD — so gold/BTC dashboard payloads were
  silently showing oil's fundamentals feed. Now scoped per symbol.
- The Supabase `dashboard_snapshot` table was migrated from a single
  fixed row to one row per symbol (unique on `symbol`); the pre-existing
  oil row was preserved untouched. The `publish_snapshot` RPC now takes a
  `p_symbol` argument.
- `webapp/index.html` (the live dashboard) got a symbol switcher (US
  Oil / Gold / Bitcoin tabs, persisted in `localStorage`), its Supabase
  query now filters by `symbol=eq.<X>` instead of the old fixed `id=eq.1`,
  and the embedded TradingView chart + all display text re-render per
  symbol. Deployed to production at `us-oil-signals.vercel.app`.
- `wti_note.py`: `build()` and `main()` are now symbol-parametrized the
  same way (same `_fundamentals` bug fixed here too, with WTI's existing
  curated static fallback preserved unchanged and other symbols getting an
  honest "no feed yet" line instead of a fabricated bias). `main()` still
  defaults to `WTIUSD` and writes `wti_note.txt` exactly as before — zero
  risk to the existing hourly automation — and only writes to
  `note_<symbol>.txt` when a different symbol is requested.
- New `gold_btc_hourly.py` — the gold/BTC twin of `wti_hourly.py` — refreshes
  each symbol's news slice and sends its Telegram note hourly.
- Test coverage added: `tests/test_dashboard_publish.py` (9 tests),
  `tests/test_wti_note.py` (7 tests). Full suite: **288 passing** (was 272).

**Open decision, already made:** Bitcoin has no dedicated Telegram channel
yet. Per your instruction, its notes fall back to `TELEGRAM_CHANNEL` (the
same channel gold uses) via the existing per-symbol fallback in
`engine/markets.channel_for()`. Whenever a dedicated Bitcoin channel
exists, set `TELEGRAM_CHANNEL_BTCUSD` and BTC notes switch over
automatically — no code change needed.

**3. GitHub Actions migration — code-complete, needs your push+secrets.**
Added `.github/workflows/gold-btc-hourly.yml` (runs `gold_btc_hourly.py`
hourly at :16) alongside the four existing workflows. Confirmed
`entry-scan.yml`, `news-refresh.yml`, and `fundamentals-daily.yml` already
run against whichever symbols are in the `SYMBOLS` secret/env var with no
code changes needed — `alert_signals.py` and `engine/fundamentals_feed.py`
were already written to loop over `config.load().symbols`. All 5 workflow
YAML files parse cleanly. What's left is entirely on your side (documented
in `SETUP_GITHUB_ACTIONS.md`): push this repo to GitHub, and add/update the
repo's Actions secrets — especially `SYMBOLS=WTIUSD,XAUUSD,BTCUSD` — since
I can't push code with your credentials or enter secrets into GitHub's UI
for you.

**4. EIA key — not started, needs your action.** Free signup at
https://www.eia.gov/opendata/register.php (~2 minutes) gets you an API key
for `EIA_API_KEY` in `.env` (and the `EIA_API_KEY` GitHub secret once
pushed). I can't create the account or fill in the signup form on your
behalf — creating accounts and entering personal data into forms are both
things I'm required to leave to you.

**5. Gold COT + seasonality, Bitcoin spread substitute — done, plus two
real bugs found and fixed along the way.**
- `engine/cot_feed.py` generalized from WTI-only to all three symbols.
  Market names verified live against the CFTC API before adding them (not
  guessed): `GOLD - COMMODITY EXCHANGE INC.` for gold, `BITCOIN - CHICAGO
  MERCANTILE EXCHANGE` for Bitcoin (note: BTC's CME open interest is only
  ~20.5K contracts vs gold's ~383K and oil's ~1.9M — genuinely thinner, so
  its COT percentile read is noisier and should be weighted accordingly,
  which the module's own docstring now says explicitly).
- `engine/spread_feed.py` gets asset-appropriate substitutes instead of
  reusing Brent-WTI/crack: gold uses the gold/silver ratio (GC=F/SI=F,
  rising = gold-specific defensive demand), Bitcoin uses CME futures basis
  (BTC=F vs BTC-USD spot, widening = bullish futures positioning). Both
  tickers verified live via Yahoo Finance before use.
- `engine/seasonality.py` gets a real gold table built on documented
  physical-demand cycles (Chinese New Year, Akshaya Tritiya, the Indian
  wedding season/Diwali run-up that the World Gold Council's own reporting
  flags as India's heaviest demand quarter). Bitcoin was deliberately left
  with NO monthly table and an honest "no documented seasonal pattern"
  neutral read — inventing one just to have a number would be fabricating
  a signal, which the project's own rules rule out.
- **Bug found #1:** `engine/confluence.py`'s `analyze()` was calling
  `cot.alignment(direction)`, `sp.alignment(direction)`, and
  `sea.alignment(direction)` with no `symbol` argument — every one of those
  defaults to WTIUSD, so gold and Bitcoin signals were being scored against
  OIL's COT positioning, oil's Brent-WTI spread, and oil's seasonality
  table this whole time, just displayed under generic-looking chip labels
  ("COT positioning", "seasonality") that gave no hint it was oil's data.
  Only `risk_sentiment`'s call was already passing `symbol` correctly. Now
  all four pass `symbol` through.
- **Bug found #2:** `engine/risk_sentiment.py` had the opposite kind of
  bug — it DID accept a `symbol` argument, but its interpretation of the
  VIX/SPX regime was hardcoded to oil's logic (risk-on is bullish) for
  every symbol. Gold is a safe haven: risk-off is normally BULLISH for
  gold, the exact opposite of oil. Before this fix, a gold signal in a
  risk-off regime would have been scored as a headwind when it should have
  been a tailwind — a real, backwards signal, not just a missing feature.
  Fixed with a per-symbol `_BULLISH_REGIME` mapping; oil keeps its existing
  geopolitical-supply-shock decoupling override (gold doesn't need one,
  since risk-off already supports it; Bitcoin doesn't get one either,
  since it has no comparable physical-supply-shock story).
- EIA weekly crude inventory data is inherently oil-only — it no longer
  appears on gold/BTC's dashboard panel or note (it used to print a
  meaningless "EIA inventory: not configured" line on every symbol).
- 11 new regression tests added to `tests/test_extra_confluence_sources.py`
  covering all of the above, including one that specifically monkeypatches
  `confluence.analyze()`'s four alignment calls to catch the exact
  wrong-symbol bug if it ever regresses.

**6. Watchdog heartbeat on the scheduler — done.** New `heartbeat_watchdog.py`
+ `.github/workflows/heartbeat-watchdog.yml` (every 30 min): reads
`alert_heartbeat.txt` (committed every ~15 min by `entry-scan.yml`) and
sends exactly one Telegram DM if it's gone stale for 45+ minutes — a way to
notice the whole pipeline going silent (broken secrets, GitHub Actions
itself down, or the repo not pushed yet) before you'd otherwise notice.
Stays quiet if no heartbeat file exists at all yet (expected pre-launch
state, not a fault). 8 new tests in `tests/test_heartbeat_watchdog.py`.

Full suite as of this update: **307 passing** (was 272 at the start of
this session).

**Investigated but not built: a third (non-yfinance/TwelveData) intraday
data-feed fallback.** Free, keyless sources like Stooq only offer DAILY
historical bars, not the 15-minute intraday bars this engine trades on -
adding one wouldn't actually restore live signal generation during an
outage, just create the appearance of redundancy. The existing behavior
(stand aside when both TwelveData and yfinance are unreachable, per
`fetch()`'s fail-safe design) is the honest, already-correct choice here,
not a gap to rush a fix for. Revisit if a genuine intraday-capable free
source turns up.

---

## Status update — 2026-07-31: autonomous audit pass

The laptop was offline for a stretch mid-session; the `us-oil-signals-engine`
GitHub push was staged (commands + a pre-generated PAT-scope link on the
clipboard/browser) but had not completed yet, so GitHub Actions still
wasn't live. While that remained blocked on the user, I used the time for a
self-directed correctness audit of the rest of the codebase — the same kind
of check that had already caught the `confluence.py` and `risk_sentiment.py`
symbol-scoping bugs earlier this session — rather than sitting idle.

**7. Found and fixed a third instance of the same bug class: `alert_signals.py`
hardcoded WTI's basis note for every symbol.** The live ENTRY Telegram alert
(`build_entry()`) quoted a module-level `BASIS_NOTE` constant —
`"levels from WTI futures (CL=F); broker USOIL may differ..."` — regardless
of which symbol triggered the alert. A live gold or Bitcoin entry would have
told the reader to check the wrong futures contract's price. `symbol_meta.py`
(built earlier this session) already had the correct per-symbol basis notes
for `dashboard_publish.py` and `wti_note.py`; `alert_signals.py` was simply
never wired to the same source of truth. Fixed by importing `symbol_meta`
and calling `sm.basis_note(rec["symbol"])` in place of the constant; the
constant itself is removed (not just unused) so it can't silently drift back
in. 4 new regression tests in `tests/test_alert_signals_basis_note.py`,
including one that asserts the old constant no longer exists on the module.

**Audited and confirmed clean (no fix needed):** `correlation.py` (USD
sensitivity already keyed per-symbol, all four current symbols correct),
`fundamentals_feed.py` (dedicated news lexicon per symbol, already
generalized), `risk_guard.py` (the daily-loss-lock fix from earlier this
session verified still correct), `bias_adjust.py` / `apply_context()`
(threads `symbol` through to fundamentals, session-edge, and TradingView
confirmation correctly), `range_guard.py` (passes `symbol` through to
`correlation.macro_alignment()`, and since WTIUSD/XAUUSD/BTCUSD all share
the same USD-inverse sign today there's no directional bug — flagged below
as a latent risk, not a live one), `tv_signals.py`, `session_edge.py`,
`calibration.py`, `grade.py`, `volume_profile.py`, `eia_feed.py` (correctly
WTI-only by design — US crude inventories have no gold/BTC equivalent),
`config.py`.

**Found and deliberately NOT changed — flagged for a product decision, not
a bug fix:** `publisher.py` and `forward_report.py` both hard-lock to
`FOCUS_SYMBOL = "WTIUSD"` with an explicit comment that the public track
record page and forward-test scoreboard are WTI-only "by design," dating to
before this session's gold+Bitcoin rollout. Whether the public-facing track
record should now include gold/BTC trades is a branding/product call (it
changes what a page literally titled "US Oil Signals" shows), not a
correctness bug — so I left it as-is and am surfacing it here rather than
changing it unilaterally. Same for `set_channel_title.py` (renames the
Telegram channel display title to "US Oil Signals") and `command_center.py`
(a pre-multi-symbol local `.bat`-launched dashboard that still only reads
`wti_note.txt`) — both are one-off/local tools outside the live Telegram +
GitHub Actions pipeline, not part of the automated signal path, and lower
priority than anything that touches a live alert.

**Found and deliberately NOT changed — a scope gap, not a bug:**
`engine/ltf.py` (1m/5m lower-timeframe entry-confirmation gate) hardcodes
`yf.download("GC=F", ...)` — gold's own futures ticker — and is only ever
called for `sym == "XAUUSD"` in `alert_signals.py` (`lt = ltf.confirm(...)
if sym == "XAUUSD" else {}`). That gating happens to make today's hardcoded
ticker correct by coincidence, but it also means WTI and Bitcoin entries get
*no* lower-timeframe confirmation at all — an entire confirmation layer that
silently doesn't apply to two of the three traded symbols. Extending it
would be a new-feature/scope decision (does LTF confirmation even help on
oil/BTC's tickers? no evidence either way yet), not a mechanical fix like
the basis-note bug, so it's logged here rather than done autonomously.

**Also verified, not fixed (nothing broken, just recorded as evidence):**
- All 6 GitHub Actions workflow YAML files parse cleanly (`yaml.safe_load`)
  and their cron schedules don't collide (WTI hourly at :06, gold+BTC hourly
  at :16, entry-scan every 15 min, heartbeat every 30 min).
- `us-oil-signals.vercel.app` is live and correctly multi-symbol-branded
  ("Live institutional-grade trading signals for US Oil (WTI), Gold (XAUUSD)
  and Bitcoin").
- The Supabase `dashboard_snapshot` table currently holds exactly **one**
  row — `WTIUSD`, last updated 2026-07-24 (7 days stale at the time of this
  check) — with **no XAUUSD or BTCUSD row at all**. This is expected, not a
  new bug: the laptop was offline and GitHub Actions isn't live yet (push
  still pending), so nothing has run the updated multi-symbol
  `dashboard_publish.py` since gold/BTC were wired up. It's recorded here as
  concrete evidence of why finishing the GitHub Actions push matters — the
  public dashboard is currently showing a week-old, oil-only snapshot to any
  visitor. I could not refresh it myself: the sandbox this session runs in
  has no general outbound internet access (confirmed — direct requests to
  Yahoo Finance and Supabase's REST host both failed to connect), so I
  cannot run the live data pipeline from here; only the scoped Supabase
  management API and the workspace's own fetch tool are reachable.

Full suite as of this update: **311 passing** (was 307 before this pass; +4
from the `alert_signals.py` basis-note regression tests).

**Next real unblock is still the same one:** the `us-oil-signals-engine`
GitHub push. Everything code-side that can be done without laptop/credential
access is done. The EIA key signup is the other outstanding user-only item.

---

## Day 3 (2026-08-03) — Production Risk Engine Integration

Implemented the Version 2 Risk Engine: `engine/portfolio_risk.py` (new) and
`engine/correlation_dynamic.py` (new), wired into `alert_signals.py` (both
alert stages) and `hourly_briefing.py` (defense-in-depth). A live trade is
now rejected before publication if it would breach aggregate portfolio
exposure, same-direction concentration, correlated-position concentration,
the account-wide daily loss stop, or the trailing 30-trade drawdown cap —
enforced by default (`portfolio_risk_mode="block"`), configurable to
shadow-mode (`"warn"`) via `.env`. Full detail: `RISK_SPECIFICATION.md`,
`DAY3_PHASE1_EXECUTION_PATH.md`, `DAY3_IMPLEMENTATION_REPORT.md`,
`DAY3_VALIDATION_REPORT.md`, `DAY3_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **348 passing** (was 311 before this pass;
+37 new: `test_portfolio_risk.py`, `test_correlation_dynamic.py`,
`test_hourly_briefing_risk_gate.py`). Zero regressions in the pre-existing
311.

---

## Day 4 (2026-08-03) — Market Regime Engine

Implemented the Version 2 Market Regime Engine: `engine/regime_engine.py`
(new, multi-timeframe classification into a finer taxonomy with a strategy
compatibility matrix and quality score) and `engine/regime_history.py` (new,
persists every classification). Runs as the first analytical stage on every
scan in both `alert_signals.py` and `hourly_briefing.py`. Ships in
`"advisory"` mode (logged, non-blocking) by default — see
`RESEARCH_REGIME_ENGINE.md` for why: only 10 of 99 closed trades in
`trades.json` carry any regime tag at all, and all 10 share the same
`regime_trend` label, so there is not yet enough data to prove filtering
helps. `"block"` mode is fully implemented and tested for when that evidence
exists. Full detail: `MARKET_REGIME_SPECIFICATION.md`,
`RESEARCH_REGIME_ENGINE.md`, `DAY4_IMPLEMENTATION_REPORT.md`,
`DAY4_VALIDATION_REPORT.md`, `DAY4_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **390 passing** (was 348 before this pass;
+42 new: `test_regime_engine.py`, `test_regime_history.py`,
`test_alert_signals_regime_gate.py`). Zero regressions in the pre-existing
348.

## Day 5 (2026-08-03) — Adaptive Confluence Engine & Evidence Independence

Investigated the Day 1 audit's finding that ~45% of the MAST confluence
score is Layer 1 confidence echoed through other layers. Built
`engine/confluence_analysis.py` (new — five-tier independence
classification of all 26 confirmation sources, per-trade explainability,
Confluence Quality Score, conflict-pattern detection, and a
contribution-measurement/adaptive-weighting framework), `engine/
confluence_history.py` (new — persists every confluence read), and
`engine/confluence_sandbox.py` (new — five-stage governed pipeline for
future candidate sources, with zero import coupling to `confluence.py`,
enforced by test). `engine/confluence.py` itself was **not modified** — no
score, weight, or gate changed. Integration is purely additive via
`alert_signals.log_confluence_explainability()`, wired at both alert
stages.

Finding: the true picture is more nuanced than a flat 45% — 13 of 26
sources (50%) are genuinely independent (Primary). The overlap is
concentrated in three named, code-verified mechanisms: the kill-zone
timing boolean scored three times (Layer 1, `confluence.py` directly,
`session_model.py`), Wyckoff's Spring/Upthrust reusing Layer 1's own
sweep-detection call, and `icc.py` as the weakest of a three-way
swing-pattern cluster with `elliott_wave.py`/`chart_patterns.py`. As with
Day 4, zero closed trades in `trades.json` currently carry a populated
`confluence_score`, so the contribution-measurement framework is built and
tested but has no real outcome data yet — see `RESEARCH_CONFLUENCE_ENGINE.md`
for the full accounting and rollout roadmap. Full detail:
`CONFLUENCE_SPECIFICATION.md`, `RESEARCH_CONFLUENCE_ENGINE.md`,
`DAY5_IMPLEMENTATION_REPORT.md`, `DAY5_VALIDATION_REPORT.md`,
`DAY5_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **437 passing** (was 390 before this pass;
+47 new: `test_confluence_analysis.py`, `test_confluence_history.py`,
`test_confluence_sandbox.py`). Zero regressions in the pre-existing 390.

## Day 6 (2026-08-03) — Confidence Engine (Calibrated Decision Quality)

Built `engine/confidence_engine.py` (new — the `ConfidenceAssessment`
object: overall confidence, five decision tiers, evidence/market/regime/
confluence sub-scores, uncertainty engine, explainability; runs LAST in
the pipeline, after every other gate, and cannot itself hold/reject a
trade), `engine/confidence_history.py` (new — persists every assessment,
immutable records), and `engine/confidence_calibration.py` (new — mirrors
the pre-existing `calibration.py`'s reliability/Brier methodology to
calibrate the new composite score against real outcomes; advisory-only
`recommend_recalibration()`, never automatic).

Closed a real schema gap Day 4/5 both flagged: `journal.py` gained
`make_ref()` and `Trade.confluence_ref`/`confidence_ref` fields, giving
every new trade a direct, exact link to its confluence and confidence
history rows instead of Day 4/5's nearest-timestamp approximation
(`trade.id == confluence_ref == confidence_ref` by construction). Both
`confluence_analysis.join_trades_with_confluence()` and the new
`confidence_calibration.join_trades_with_confidence()` prefer this direct
match, falling back to the original timestamp join for pre-Day-6 rows.

Two small, disclosed, additive fixes landed in `engine/confluence.py`
itself (approved backlog items from `RESEARCH_CONFLUENCE_ENGINE.md`):
`regime_vol`'s contribution is now labeled in `agree`/`disagree` (was
previously invisible), and the exact news point delta is now persisted on
`ConfluenceRead` (`news_delta` field) instead of being discarded after use.
Neither changes any score or gate — confirmed by the full regression suite.

`overall_confidence` is explicitly labeled an uncalibrated internal
decision-quality estimate on every assessment made today —
`confidence_history.jsonl` starts empty at this deployment, so
`is_calibrated=False` for every read until real matched trades accumulate
(≥30 per bucket). See `RESEARCH_CONFIDENCE_ENGINE.md` for the full honest
accounting. Full detail: `CONFIDENCE_ENGINE_SPECIFICATION.md`,
`RESEARCH_CONFIDENCE_ENGINE.md`, `DAY6_IMPLEMENTATION_REPORT.md`,
`DAY6_VALIDATION_REPORT.md`, `DAY6_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **513 passing** (was 437 before this pass;
+76 new: `test_confidence_engine.py`, `test_confidence_history.py`,
`test_confidence_calibration.py`, `test_journal_confidence.py`,
`test_alert_signals_confidence.py`). Zero regressions in the pre-existing 437.

## Day 7 (2026-08-03) — Market Memory Engine & Trade Intelligence System

Built `engine/market_memory.py` (new — the `MemoryRecord` object and its
full assembly/similarity/look-ahead-protection/analytics surface). No new
persistent database was created: every `MemoryRecord` is joined at read
time from `trades.json` plus the existing `regime_history`/
`confluence_history`/`confidence_history` logs, directly satisfying the
mandate's "reuse existing journals, avoid duplicate storage" principle.

Extended the unified-trade-ID pattern (started Day 6 for confluence/
confidence) to regime history: `regime_history.record()` gained an
optional `ref` parameter and `find_by_ref()`, and `Trade` gained a
matching `regime_ref` field, so `trade.id == regime_ref == confluence_ref
== confidence_ref` by construction for every trade logged from today
forward. This was the platform owner's explicit Day 6 closing decision
("I would standardize the entire platform around a single immutable trace
ID").

Built a seven-dimension similarity framework (regime, confluence profile,
session, volatility, macro alignment, portfolio state, direction —
disclosed, not fitted weights) and a single look-ahead-protection choke
point (`_look_ahead_safe()`, requires closed status AND `closed` strictly
before the query's `as_of`) that every comparison routes through.
`historical_context()` reports sample size, aggregate outcomes, and an
explicit sufficiency label, never inferring confidence from a small
sample (`MIN_N_FOR_CONTEXT=5`, `MIN_N_FOR_TRUST=30` — same trust bar as
Day 5/6).

Integrated as advisory-only context: `confidence_engine.assess()` gained
a `memory_context` parameter consumed only after `overall_confidence` is
already finalized (proven by a dedicated identical-score test, not just
asserted), and `alert_signals.py`/`dashboard_publish.py` were extended to
compute and surface it (`market_memory_advisory`, a sibling key to
`signal` on the dashboard payload) without touching any gating logic.

Added `confidence_calibration.raw_vs_composite_comparison()` per the
platform owner's second Day 6 decision ("design now, activate later") —
built and tested, but not wired into `report()` or any live surface;
self-gates on `n>=30` matched trades (0 today).

Full detail: `MARKET_MEMORY_SPECIFICATION.md`, `RESEARCH_MARKET_MEMORY.md`,
`DAY7_IMPLEMENTATION_REPORT.md`, `DAY7_VALIDATION_REPORT.md`,
`DAY7_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **569 passing** (was 513 before this pass;
+56 new: `test_regime_history_ref.py` (6), `test_market_memory_lookahead.py`
(8), `test_market_memory.py` (33), `test_calibration_comparison.py` (4),
plus 5 appended to `test_confidence_engine.py`). Zero regressions in the
pre-existing 513.

Per the platform owner's strategic guidance closing Day 7: the core
decision architecture (origination → regime → confluence → risk/portfolio
→ confidence → market memory) is now complete. Day 8 is designated to
pause feature expansion for one milestone and focus on **Explainability &
Decision Audit** — ensuring every decision the platform makes can be
reconstructed, understood, and audited end-to-end before further
intelligence layers are added.

## Day 8 (2026-08-03) — Explainability Engine & Decision Audit System

Built `engine/platform_version.py` (new — single source of truth for
version/configuration traceability; `component_versions()` reads each
decision-path module's own `VERSION`, reporting `"unversioned"` honestly
for the ones that don't declare one), `engine/explainability_engine.py`
(new — the `DecisionSnapshot` object, `build_audit_graph()`,
`lineage_for_snapshot()`, `explain_approval()`/`explain_rejection()`,
`post_trade_review()`, `replay()`), and `engine/decision_audit_history.py`
(new — immutable append-only persistence to `decision_audit.jsonl`,
structurally proven to expose no update/delete function).

Closed a real version-traceability gap: four core decision-path modules
(`signals.py`, `regime_engine.py`, `confluence.py`, `portfolio_risk.py`)
had no explicit `VERSION` constant before today — added retroactively as
purely additive metadata, zero logic changes, confirmed by the unchanged
full regression suite.

`DecisionSnapshot` is the first durable record of a REJECTED opportunity
this codebase has ever kept — every prior history log
(regime/confluence/confidence) only ever recorded a classification or
read, never "what happened to this opportunity and why." Storage design
follows `engine/journal.py`'s own established precedent: ref pointers into
the three existing history logs plus a small denormalized summary, not a
new duplicate database. `replay(decision_id)` reconstructs a full
explanation purely from persisted evidence and is proven deterministic —
calling it twice returns byte-identical output — which is the literal
meaning of the mandate's "historical explanations must remain
reproducible."

Integrated into `alert_signals.py` at every point where a specific
candidate opportunity is already known (both Stage-1 and Stage-2, approved
and rejected paths), using already-computed variables and wrapped
fail-safe — cannot influence whether anything publishes. Two account-level
gates that run before any specific opportunity exists (news blackout,
pre-origination risk lock) are explicitly NOT snapshotted — a disclosed
scope boundary. `dashboard_publish.py` gained a new `decision_audit`
top-level payload key surfacing recent snapshots with their audit graph
and explanation, kept separate from `signal`.

Full detail: `EXPLAINABILITY_SPECIFICATION.md`, `RESEARCH_EXPLAINABILITY.md`,
`DAY8_IMPLEMENTATION_REPORT.md`, `DAY8_VALIDATION_REPORT.md`,
`DAY8_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **620 passing** (was 569 before this pass;
+51 new: `test_platform_version.py` (5), `test_decision_audit_history.py`
(15), `test_explainability_engine.py` (19), `test_replay.py` (5),
`test_post_trade_review.py` (7)). Zero regressions in the pre-existing 569.

`decision_audit.jsonl` starts empty at this deployment — per the same
honest-disclosure pattern as every prior Day's newly-introduced store,
`RESEARCH_EXPLAINABILITY.md` states plainly that every finding in this
Day's research report is about engine correctness, not accumulated
decision data, because none exists yet.

## Day 9 (2026-08-03) — Research & Statistical Validation Framework

Per the platform owner's explicit re-sequencing decision (Macro
Intelligence moved from Day 9 to Day 10 in favor of building research
governance first — "governance becomes a competitive advantage" once the
architecture is this mature): built the platform's permanent Research &
Statistical Validation Framework, seven new modules, zero production
files touched (only one pre-existing file, `walkforward.py`, gained one
additive function).

`engine/research_stats.py` (standardized metrics: expectancy, profit
factor, win rate, max drawdown, Sharpe/Sortino/Calmar-like, recovery
factor, stability-over-time — every one documented with why it matters,
when it misleads, and a minimum-sample caveat) and
`engine/evidence_tiers.py` (the mandate's five-tier, deliberately
non-rigid sample-size policy — representativeness and within-sample
consistency can downgrade a large sample, never upgrade a small one) give
every future experiment a shared statistical vocabulary.

`engine/experiment_registry.py` implements the mandate's eleven-stage
research lifecycle and `Hypothesis` template, persisted immutably
(mirrors Day 8's `decision_audit_history.py` exactly — append-only,
structurally proven no update/delete function exists). Rejected
experiments stay permanently queryable: "failed experiments are valuable
knowledge."

`engine/edge_decay_monitor.py` compares recent vs. prior trade performance
and flags decline — every recommendation is literally "investigate — do
not change production automatically." Run against the real, live
`trades.json` this Day, it found four real, current conditions worth the
platform owner's attention (expectancy +1.22R -> -0.01R over the last 30
vs. prior 69 trades, profit factor 3.47 -> 0.99, drawdown -5.0R -> -12.0R,
inconsistent recent sub-segments) — reported, not acted on; see
`DAY9_NEXT_DAY_READINESS_REPORT.md`.

`engine/paper_trading_review.py` is the mandate's proposed/executed/
expected/realized/deviations/operational-issues bridge, built by reusing
Day 8's `post_trade_review()` rather than duplicating it — and honestly
discloses a real gap (no ref yet links a Stage-1 heads-up to the Stage-2
entry it may trigger) rather than papering over it with a fragile
heuristic.

`engine/research_dashboard.py` is a standalone, symbol-agnostic payload
(never imported into `dashboard_publish.py` or `alert_signals.py`) —
"keep research clearly separated from production," true by construction,
not just by convention.

Full detail: `RESEARCH_VALIDATION_SPECIFICATION.md` (includes the full
backtest-quality review of `engine/backtest.py`, the walk-forward
methodology writeup, and the real edge-decay finding above),
`DAY9_IMPLEMENTATION_REPORT.md`, `DAY9_VALIDATION_REPORT.md`,
`DAY9_NEXT_DAY_READINESS_REPORT.md`.

Full suite as of this update: **703 passing** (was 620 before this pass;
+83 new: `test_research_stats.py` (26), `test_evidence_tiers.py` (10),
`test_experiment_registry.py` (19), `test_walkforward_expanding_window.py`
(5), `test_edge_decay_monitor.py` (8), `test_paper_trading_review.py` (8),
`test_research_dashboard.py` (7)). Zero regressions in the pre-existing
620.

Per the platform owner's own words closing this mandate: "No future
feature should be accepted because it is interesting, popular, or
theoretically appealing. Every feature must earn its place through
reproducible evidence, measured performance, and disciplined validation."
Macro Intelligence — originally Day 9 — is now Day 10, and will be the
first capability actually required to pass through this framework.

---

## Day 10 (2026-08-03) — Edge Investigation & Performance Recovery (Experiment #0001)

The platform owner re-sequenced the roadmap a second time: "Do not
proceed directly to Macro Intelligence. Insert a new milestone: Day 10 —
Edge Investigation & Performance Recovery... Your own framework says:
investigate first. Follow it." Macro Intelligence moves to Day 11.

Day 10 opened the platform's first formal research investigation —
**Experiment #0001: "Observed Edge Deterioration Investigation"** —
managed entirely through `engine/experiment_registry.py` (Day 9), in
direct response to Day 9's own `edge_decay_monitor.check()` finding.
**No new production capability was added this Day; no production file was
modified.** Full narrative: `PERFORMANCE_INVESTIGATION_0001.md`. Full
detail on what was built and how it was verified:
`DAY10_IMPLEMENTATION_REPORT.md`, `DAY10_VALIDATION_REPORT.md`,
`DAY10_NEXT_DAY_READINESS_REPORT.md`.

**The headline finding:** the apparent deterioration is real (independently
re-verified — expectancy +1.22R -> -0.01R, profit factor 3.47 -> 0.99, win
rate 49.3% -> 26.7%, drawdown -5.0R -> -12.0R) but is only ~25-30%
explained by a genuine data-quality issue discovered during this
investigation: a settlement-methodology drift in `engine/journal.py`
(the platform's win-crediting rule changed from a legacy "full target or
bust" formula to the current breakeven/partial-banking formula mid-way
through the prior comparison window, and was never retroactively
reapplied). Restated to one consistent methodology, prior expectancy is
+0.91R (PF 2.85) against a recent window still flat-to-losing (-0.01R,
PF 0.99) — most of the decline is NOT a measurement artifact. Concrete,
concentrated evidence exists for session effects (Asian/London
degradation); two of the eight named root-cause hypotheses (Regime Shift,
Risk Controls) are inconclusive due to genuine metadata-completeness gaps,
not because they were tested and ruled out. A statistical-variance
permutation test makes chance-alone unlikely (p≈0.01-0.03) but not
impossible, with a disclosed post-hoc-selection caveat. **Overall
classification: Research Further** — not Monitor, not Reject, not a
graduation to production. See `PERFORMANCE_INVESTIGATION_0001.md` Sec.8
for the full, per-finding recommendation table.

`engine/edge_investigation.py` (new) is entirely read-only against
`trades.json`, reuses `engine.research_stats`/`engine.evidence_tiers`
(Day 9) for every core metric, and adds two metrics this platform's
statistics vocabulary didn't have yet (average holding time, average
stop/target size) as pure functions of already-persisted `Trade` fields —
no new storage.

Full suite as of this update: **732 passing** (was 703 before this pass;
+29 new: `test_edge_investigation.py`). Zero regressions in the
pre-existing 703.

### A permanent process rule, adopted this Day

Per the platform owner's explicit request closing this mandate: **every 10
implementation days, one dedicated Research & Validation day is scheduled
before any new production capability is added.** Day 9 (Research &
Statistical Validation Framework) and Day 10 (this investigation) both
count toward that cadence — Day 9 built the mechanism, Day 10 was its
first real use. The next scheduled Research & Validation day (absent an
earlier signal, exactly as happened here, that pulls one forward) falls
around Day 20. Rationale, in the platform owner's own words: "That cadence
keeps engineering and scientific validation in balance, reducing the risk
that the platform becomes more complex faster than it becomes more
reliable." This rule is now standing project policy, not a one-time
decision — any future roadmap planning should check against it before
scheduling ten consecutive days of new-capability work.

## Day 11 (2026-08-03) — Institutional Macro Intelligence Engine

The platform owner resumed feature development after Day 10's clean
investigation baseline, then, mid-mandate, tightened the remaining scope
with an explicit 5-phase build order and two new design requirements
("Macro Confidence is not the trading Confidence Engine" and "every
provider reports Data Freshness"), plus an explicit prohibition: "Do not
create another weighted scoring engine." Full detail on what was built
and how it was verified: `DAY11_IMPLEMENTATION_REPORT.md`,
`DAY11_VALIDATION_REPORT.md`, `DAY11_NEXT_DAY_READINESS_REPORT.md`. Full
specification and research note: `MACRO_ENGINE_SPECIFICATION.md`,
`RESEARCH_MACRO_ENGINE.md`.

**What shipped, in the mandated order:** `engine/macro_providers.py` —
the single abstraction layer every downstream module goes through (grep-
verified: zero direct imports of the underlying feed modules anywhere
else). Ten mandate providers plus two supplementary wrappers, all
returning a standardized shape with a `freshness` field (fresh/stale/
reference_data/computed/missing). Two new feeds back it:
`engine/rates_feed.py` (live Treasury yields, curve shape, TLT, TIP/IEF
inflation-expectations proxy) and `engine/macro_reference.py`
(operator-curated central-bank stances, geopolitical flags, economic
prints — disclosed, not fabricated). `engine/macro_calendar.py` and
`engine/macro_cross_asset.py` (11 named relationships) round out the
provider layer. `engine/macro_regime.py` classifies eight
non-mutually-exclusive descriptive labels (Inflationary, Disinflationary,
Tightening, Easing, Risk-On, Risk-Off, Neutral, Mixed) from simple
disclosed count-based rules — explicitly not a third scoring engine
alongside `confluence.py`/`confidence_engine.py` — and carries the two
required-distinct fields, `macro_confidence` and `evidence_quality`.
`engine/macro_history.py` persists normalized, immutable assessments
(never raw facts, per the platform's standing anti-duplication
discipline). `engine/macro_engine.py` orchestrates
`Providers -> Macro Regime -> Cross-Asset Context -> Macro Assessment ->
Explainability` and performs no calculations of its own. Advisory
integration (only after all four prior phases were complete, per the
mandate): `alert_signals.py` logs one assessment per Stage-2 entry and
optionally appends an informational `macro:` line to the entry alert;
`engine/journal.py` gained `Trade.macro_ref`, extending the platform's
unified-ID invariant to `id == regime_ref == confluence_ref ==
confidence_ref == macro_ref`; `engine/dashboard_publish.py` surfaces the
last recorded assessment as `"macro_advisory"`.

**A real bug was found and fixed during Day 11's own testing** (not a
pre-existing issue carried from an earlier Day): `dashboard_publish.py`'s
`build_payload()` had a local variable named `macro`
(`macro = co.read_macro()`, pre-existing DXY guard logic) in the same
function scope as the new `macro_advisory` lambda, shadowing the
module-level `macro_engine` import and raising `UnboundLocalError` on any
code path that reached the dashboard payload before that local
assignment ran. Caught immediately by the new dashboard tests written for
this feature; fixed by renaming the local variable to `dxy_macro`. Zero
collateral impact on the 9 pre-existing `test_dashboard_publish.py` tests.

**Structural proof this engine never gates a trade** (the same discipline
applied to every advisory system since Day 4): `grep -n "macro_engine\|
macro_regime\|macro_providers\|macro_history" engine/risk_guard.py
engine/confluence.py engine/confidence_engine.py engine/bias_adjust.py
engine/signals.py` returns zero matches across all five modules capable
of rejecting, resizing, or scoring a trade. (`confluence.py` and
`confidence_engine.py` do contain the standalone word "macro" — that is
the pre-existing, Day-1-era DXY-correlation-alignment confluence factor,
unrelated to and predating this engine; the precise grep above targets
the four Day 11 module names specifically.)

Full suite as of this update: **890 passing** (was 732 before this pass;
+158 new across 10 test files: `test_rates_feed.py` (14),
`test_macro_reference.py` (11), `test_macro_calendar.py` (18),
`test_macro_cross_asset.py` (21), `test_macro_providers.py` (23),
`test_macro_regime.py` (23), `test_macro_history.py` (20),
`test_macro_engine.py` (12), `test_journal_macro.py` (4),
`test_alert_signals_macro.py` (9), plus 3 new tests added to the existing
`test_dashboard_publish.py`). Zero regressions in the pre-existing 732.

### Version 2.0 Architecture Complete

Per the platform owner's own closing recommendation from the original Day
11 mandate — "Once the Macro Intelligence Engine is complete, I would
consider Days 1 through 11 as: **Version 2.0 Architecture Complete**" —
this milestone is now formally declared. Days 1-11 together built the
platform's full advisory-architecture layer around the original ICT/SMC
origination + MAST confluence core: Risk Governance (Day 3), Market
Regime (Day 4), Confluence Independence & Adaptive Weighting (Day 5),
Confidence Engine (Day 6), Market Memory (Day 7), Decision Explainability
(Day 8), Research & Statistical Validation (Day 9), Edge Investigation
(Day 10), and Macro Intelligence (Day 11). Every one of these nine
systems is structurally advisory-only — verified at each Day's own close
via grep against the production trade-selection path — and none has yet
been promoted to production-gating status through the Day 9 promotion
pipeline. Per the platform owner's own framing, future days should now
shift emphasis from adding major architectural pillars toward refining,
validating, and extending what exists, with the Day 9/10 research cadence
(one dedicated Research & Validation day every 10 implementation days,
adopted as standing policy at Day 10's close) remaining the mechanism for
that shift.

## Day 12 (2026-08-03) — Institutional Execution Simulator & Transaction Cost Model (Version 2.1 opens)

The platform owner opened Version 2.1 with an explicit strategic shift:
"The first 11 days built a sophisticated decision engine. The next stage
should focus on making the platform institutionally reliable." Day 12's
mandate identified a real gap — every R-multiple in `trades.json` has
always implicitly assumed a perfect, zero-cost fill, which "can easily
distort research conclusions." Full detail on what was built and how it
was verified: `DAY12_IMPLEMENTATION_REPORT.md`, `DAY12_VALIDATION_
REPORT.md`, `DAY12_NEXT_DAY_READINESS_REPORT.md`. Full specification and
research note: `EXECUTION_SIMULATOR_SPECIFICATION.md`,
`RESEARCH_EXECUTION_MODEL.md`.

**What shipped**, in a new isolated package per the mandate's own
architectural recommendation — `engine/execution/` (8 files, 1,146
lines) rather than a single growing file: `spread_model.py`
(session/volatility/symbol/news-dependent spread estimate, reusing
`engine.regime.atr_percentile()` and the existing `news_guard` blackout
flag rather than adding new upstream computation), `slippage_model.py`
(normal/adverse/favorable slippage with a disclosed, capped liquidity-
shock probability model and partial-fill support), `latency_model.py`
(five named delay stages including `human_reaction` — the dominant,
most uncertain one, included because this platform is Telegram-alert-
based, not auto-trading), `fill_model.py` (order-type-aware fills for
market/limit/stop, with structural support for all six mandate-named
stress conditions: zero liquidity, missing data, stale prices, high
volatility, delayed fills, partial fills), `execution_report.py`
(per-trade fill-quality report + a descriptive Excellent/Good/Average/
Poor/Failed execution score that measures FILL quality, not STRATEGY
quality — a losing trade can score Excellent), `execution_history.py`
(immutable persistence, the fourth-generation instance of Day 4's
`regime_history.py` pattern), `replay.py` (reproducible historical
replay under named assumption profiles — the mandate's own "WTI, London
session, typical spread/slippage/latency" example runs directly), and
`comparison.py` (the Raw Strategy -> Ideal Execution -> Realistic
Execution -> Observed Performance research bridge, reusing Day 9's
`research_stats.full_report()`).

**A critical honesty finding surfaced by this Day's own research
framing, not a bug**: Raw Strategy and Observed Performance are
numerically IDENTICAL in the four-layer comparison today, because
`trades.json`'s `result_r` has never had execution cost subtracted from
it — there is no live broker connection yet (explicitly Day 13's job),
so nothing has ever actually been "observed" through a real fill. Only
Realistic Execution (this Day's new modeled layer) introduces a
genuinely different number. `RESEARCH_EXECUTION_MODEL.md` treats this as
the single most important caveat in the whole research note, to prevent
a future reader from misreading "no gap today" as "execution costs don't
matter."

**Advisory integration, additive only**: `alert_signals.py`'s
`log_execution_context()` simulates one entry-leg fill per Stage-2
entry and `build_entry()` optionally appends an `est. execution:` line;
`engine/journal.py` gained `Trade.execution_ref`, extending the
platform's unified-ID invariant to `id == regime_ref == confluence_ref
== confidence_ref == macro_ref == execution_ref` (entry/stop/target
themselves are never overwritten with a simulated price);
`engine/dashboard_publish.py` surfaces the last recorded report as
`"execution_summary"`.

**Structural proof this package never gates a trade**: `grep -n
"execution" engine/risk_guard.py engine/confluence.py engine/
confidence_engine.py engine/bias_adjust.py engine/signals.py` returns
zero matches — the bare word "execution" does not appear anywhere in
those five files, so unlike Day 11's "macro" naming collision with a
pre-existing DXY-alignment feature, there was no ambiguity to
disambiguate this time.

Full suite as of this update: **1,049 passing** (was 890 before this
pass; +159 new across 12 test files, including a dedicated
`test_execution_stress.py` covering the mandate's six named stress
scenarios explicitly). Zero regressions in the pre-existing 890.

### Version 2.1 roadmap (adopted this Day)

| Day | Objective |
|---|---|
| 12 | Execution Simulation & Transaction Cost Modeling (this Day) |
| 13 | Live Broker Abstraction Layer (paper trading first, live-ready architecture) |
| 14 | Data Quality & Feed Health Monitoring |
| 15 | Advanced Backtesting 2.0 (walk-forward + Monte Carlo + execution modeling) |
| 16 | AI Research Assistant (interprets data, proposes hypotheses, summarizes experiments — never changes production automatically) |
| 17 | Optional ML Research Sandbox (strictly research mode, never production) |
| 18 | Portfolio Optimization & Dynamic Capital Allocation Research |
| 19 | Observability, Monitoring & System Health Dashboard |
| 20 | Version 2.1 Validation, Cleanup & Technical Debt Review |

### A new standing rule, adopted this Day

Per the platform owner's explicit request: **every new feature must
either improve realism, improve measurement, improve reliability, or
improve statistical confidence.** Indicators or scoring systems should
not be added unless they pass through the Day 9 research framework and
demonstrate measurable value — this discipline is expected to contribute
more to long-term performance than expanding the number of signals. This
rule sits alongside (does not replace) the Day 10 "one Research &
Validation day every 10 implementation days" cadence — both are now
standing project policy, checked before scheduling future work.

## Day 13 (2026-08-04) — Broker Abstraction Layer (Paper Trading First)

Version 2.1's second implementation day. Built `engine/broker/` (10
files, 1,988 lines) — a versioned, broker-neutral Execution API v1
(`contract.py`'s `BrokerInterface`), an order lifecycle state machine
(`order_state.py`), standardized events + append-only JSONL persistence
(`events.py`/`broker_history.py`), a centralized symbol-aggregate
position engine (`position_engine.py`), a multi-account virtual account
model (`account.py`), and the platform's first true execution provider —
`PaperBroker` (`paper_broker.py`) — built entirely on top of Day 12's
`fill_model`, never reimplementing it.

**What shipped**: full order lifecycle (Created -> Accepted -> Working
-> Filled/PartiallyFilled/Cancelled/Expired/Rejected, every transition
persisted, never mutated in place); MARKET/STOP orders resolve
immediately, LIMIT orders without a price path rest as genuine WORKING
orders (cancellable, modifiable, resolvable later); seven documented,
retry-safe failure modes; symbol-aggregate positions with weighted-
average entry and lifetime-accumulated realized P&L; a virtual account
(disclosed $10,000/30x-leverage/1%-risk defaults, all overridable,
multiple independent accounts supported); a replay driver that pushes
historical trades through the SAME `submit_order()`/`close_position()`
calls the live scan loop makes; and a research bridge that keeps
simulated (Day 12) and paper (Day 13) evidence permanently separate.

**Critical correctness finding from this Day's own testing**: this
platform's scan loop is a FRESH PROCESS roughly every 15 minutes, not a
long-lived daemon — an earlier draft of `PaperBroker` held all state
purely in memory, which would have silently reset every account to
`flat`/starting-capital on every scan. Fixed by adding
`rebuild_from_history()` to both `PositionEngine` and `AccountRegistry`,
called once per `PaperBroker.__init__()`, replaying `broker_history
.jsonl`'s immutable fill trail to reconstruct correct state — verified
by a dedicated test comparing a same-process balance against one
rebuilt from a simulated process restart.

**Advisory integration**: `alert_signals.py` gained
`log_paper_broker_submission()` (Stage-2 entry, same placement as Day
12's execution logging) and `sync_paper_broker_closures()` (called
immediately after `journal.settle()`, closing the Paper Broker's
position for any trade that scan just closed). `build_entry()` gained a
`paper broker:` line. `journal.py` gained `Trade.broker_ref`, completing
the unified-ID invariant through six fields. `dashboard_publish.py`
gained a `"paper_trading"` payload key.

**Structural proof this package never gates a trade**: `grep -n
"broker" engine/risk_guard.py engine/confluence.py
engine/confidence_engine.py engine/bias_adjust.py engine/signals.py
engine/portfolio_risk.py engine/regime_engine.py` returns zero matches —
the decision engine has no dependency on this package.

Full suite as of this update: **1,204 passing** (was 1,049 before this
pass; +155 new across 12 test files). Zero regressions in the
pre-existing 1,049. First `tests/conftest.py` in this codebase (a
shared `broker_paths` fixture — justified by `broker_history.py`'s four
JSONL paths vs. every prior history module's one).

New documentation this Day: `BROKER_ABSTRACTION_SPECIFICATION.md`,
`PAPER_BROKER_SPECIFICATION.md`, `EXECUTION_API_DOCUMENTATION.md`,
`DEVELOPER_GUIDE.md`, `TESTING_GUIDE.md`.

Backlog opened for a future Day: no commission/fee schedule modeled yet
(spread+slippage is the only transaction cost); no margin-call/
liquidation mechanics; resting limit orders have no time-based auto-
expiry (`time_in_force` accepted by the contract, not yet enforced by a
clock). None of these block Day 14.

## Day 14 (2026-08-04) — Data Quality & Feed Health Monitoring Framework

Built `engine/data_health/` — a 9-module, ~1,600-line package whose job
is to determine whether the platform can trust the data it already has,
never to fetch anything new. Registered all 18 real data sources this
platform has (`registry.py`), each with a disclosed provider/purpose/
update-frequency/expected-freshness/timeout/failure-behavior/fallback-
behavior/dependency list — validated structurally, no hidden
dependencies possible.

**Four independent checks**: `freshness.py` (a new 5-state, minute-
granularity classifier, explicitly disambiguated from the pre-existing
day-granularity `engine/freshness.py` banner), `completeness.py`,
`consistency.py` (OHLC validity, duplicate timestamps, conflicting
sources), `anomaly.py` (frozen prices, z-score outliers, timeline gaps —
disclosed operational statistics, not predictive modeling).

**Health scoring** (`provider_status.py`): 4-state classification
(Operational/Degraded/Partial/Unavailable) per the mandate's own
instruction — not a single number — plus confidence, affected
subsystems (via the registry's dependency graph), and a recommended
action. Dependency cascade propagates a bad status downstream (concrete
example: `macro_calendar` inherits `news_calendar`'s status).

**Heartbeat** (`heartbeat.py`): reuses `heartbeat_watchdog.
heartbeat_age_minutes()` directly, adds dashboard-publish and journal-
persistence tracking. Required adding a NEW `dashboard_publish_
heartbeat.json` write to `dashboard_publish.py` — no persisted publish
timestamp existed before this Day, found during this Day's own audit.

**Coordinator** (`feed_monitor.py`): `run_health_check(persist=True|
False)`. `persist=True` (`alert_signals.py`, once per scan, after every
symbol is processed) writes a heartbeat record and a failure-philosophy
event trail (`data_health_history.jsonl`: `run_summary` + `provider_
issue` + `recovery` events). `persist=False` (`dashboard_snapshot()`)
computes the identical report read-only — a dashboard page load must
never itself count as a heartbeat.

**Advisory integration**: `log_data_health()` in `alert_signals.py`
(once per scan, appends a `data health: <status> (<counts>)` line to
`alert_heartbeat.txt`) and a `record_observation()` call for the
`news_calendar` feed right after the pre-existing `news_guard.evaluate()`
call. `dashboard_publish.py` gained a `"data_health"` payload key,
symbol-agnostic like `"paper_trading"`.

**Structural proof this package never gates a trade**: `grep -n
"data_health" engine/risk_guard.py engine/confluence.py
engine/confidence_engine.py engine/bias_adjust.py engine/signals.py
engine/portfolio_risk.py engine/regime_engine.py` returns zero matches.

Full suite as of this update: **1,353 passing** (was 1,204 before this
pass; +149 new across 10 dedicated `data_health` test files + 5
appended to `test_dashboard_publish.py`). Zero regressions in the
pre-existing 1,204 (one transient parallel-worker flake in a pre-
existing Day 12 test reproduced 0/5 in isolation — not a regression,
see `DAY14_VALIDATION_REPORT.md`).

New documentation this Day: `DATA_HEALTH_SPECIFICATION.md`,
`FEED_REGISTRY_SPECIFICATION.md`, `OPERATIONAL_GUIDE.md`.

Per the user's own stated Version 2.1 policy (one Research & Validation
Day every ten implementation days), this closes the block of Days 5-14
as institutional decision architecture + institutional execution
architecture + institutional operational monitoring. The next session
is a Research & Validation Day, not Day 15 — see
`DAY14_NEXT_DAY_READINESS_REPORT.md`.
