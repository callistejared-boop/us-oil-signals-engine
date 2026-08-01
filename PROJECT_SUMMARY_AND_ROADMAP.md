# Signal Engine — Project Summary & Improvement Roadmap
*US Oil · Gold · Bitcoin — prepared 2026-07-20*

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
