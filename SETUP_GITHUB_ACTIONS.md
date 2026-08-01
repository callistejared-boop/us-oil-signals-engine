# Moving off the laptop: GitHub Actions setup

This replaces Windows Task Scheduler with six scheduled GitHub Actions
workflows (already added under `.github/workflows/`) that run the exact
same Python scripts, on a server that's on 24/7 — no more "the engine only
runs while your laptop is on and awake."

| Workflow | Replaces | Cadence | Script(s) |
|---|---|---|---|
| `entry-scan.yml` | "XAUUSD Entry Scan 15min" | every 15 min | `alert_signals.py` (already loops every symbol in `SYMBOLS`) |
| `wti-hourly.yml` | "WTI Hourly Analysis" | hourly (:06) | `wti_hourly.py` (also publishes the dashboard snapshot for every symbol) |
| `gold-btc-hourly.yml` | *(new, 2026-07-28)* | hourly (:16) | `gold_btc_hourly.py` — gold + Bitcoin's own hourly note, mirroring `wti_hourly.py` |
| `news-refresh.yml` | "Signals News 5min" | every 5 min | `engine/correlation.py`, `engine/fundamentals_feed.py`, `news_bias.py`, `command_center.py`, `news_watch.py` |
| `fundamentals-daily.yml` | "WTI Fundamentals Refresh" | daily 06:00 UTC | `engine/fundamentals_feed.py` (backstop, redundant with the 5-min job on purpose) |
| `heartbeat-watchdog.yml` | *(new, 2026-07-28)* | every 30 min | `heartbeat_watchdog.py` — one Telegram DM if the pipeline goes silent (see below) |

**Heartbeat watchdog:** reads `alert_heartbeat.txt` (committed by
`entry-scan.yml` every ~15 min) and sends you exactly one Telegram DM if
it's stale for more than 45 minutes — the point is to catch the whole
pipeline going quiet (broken secrets, GitHub Actions itself down, or you
simply haven't finished step 2-3 below yet) before you'd otherwise notice.
It stays silent if no heartbeat file exists at all, since that's the
expected state until you've completed the setup below — not a fault to
alert on.

**Bitcoin's Telegram channel:** per your call, BTC notes fall back to
`TELEGRAM_CHANNEL` (the same channel gold uses) until you create a
dedicated Bitcoin channel. Whenever you do, add a `TELEGRAM_CHANNEL_BTCUSD`
secret (see step 3) and BTC notes automatically switch over — no code
change needed.

State that used to live only on your laptop's disk (`pending.json`,
`trades.json`, `run_ledger.jsonl`, `fundamentals.json`, `macro.json`,
`news_state.json`, the COT/spread/risk-sentiment caches) now gets committed
back to the repo by each workflow run, so dedup, the daily-loss lock, and
the trade journal all survive between runs on a fresh machine every time.
The `.cache/` market-data fallback (Phase 1's resilience layer) is kept
warm via GitHub's Actions cache instead — best-effort, not committed.

I already fixed the two spots that only read secrets from a literal `.env`
file (`engine/config.py`, `engine/dashboard_publish.py`) so they also check
real environment variables first — that's how GitHub Actions secrets get
injected, so this was a real gap, not just plumbing.

## What I can't do for you

I can't enter API keys/tokens into any web form, and I can't push code
using your GitHub credentials — both are things you need to do yourself.
Everything below should take about 10 minutes.

## 1. Repo — already created

Done: **https://github.com/callistejared-boop/us-oil-signals-engine**
(public, no README/license/.gitignore added by GitHub — clean empty repo,
ready for your push below).

## 2. Push the code

This exact folder is already on your computer. Open a terminal there and run:

```bash
cd path/to/gold-engine
git init
git add .
git commit -m "Initial commit: gold-engine trading platform"
git branch -M main
git remote add origin https://github.com/callistejared-boop/us-oil-signals-engine.git
git push -u origin main
```

(If prompted for credentials, use a GitHub Personal Access Token as the
password — GitHub stopped accepting account passwords for git operations.
If you don't have one: Settings → Developer settings → Personal access
tokens → generate one with `repo` scope.)

## 3. Add the secrets

Go to your new repo → **Settings → Secrets and variables → Actions → New
repository secret**, and add each of these (copy the values straight from
your local `.env` file — I'm not printing them here):

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_CHANNEL` (this is gold's channel and BTC's fallback channel)
- `TELEGRAM_CHANNEL_WTIUSD`
- `TELEGRAM_CHANNEL_BTCUSD` — only once you've created a dedicated Bitcoin
  channel; skip it for now and BTC notes keep using `TELEGRAM_CHANNEL`.
- `ANTHROPIC_API_KEY`
- `LLM_MODEL`
- `SYMBOLS` — set to `WTIUSD,XAUUSD,BTCUSD` to match the local `.env`
- `EIA_API_KEY`
- `DASHBOARD_PUBLISH_SECRET`
- `TWELVEDATA_API_KEY` — only if you have one; not currently set locally, so
  the engine will keep using yfinance as it does today if you skip this.

## 4. Turn it on

Nothing else to do — the four workflows will start firing on their own
schedule once the code and secrets are in place (GitHub polls cron jobs
roughly every few minutes, so the first run may take a little while to
kick in). To fire one immediately instead of waiting:

Repo → **Actions** tab → pick a workflow (e.g. "Entry scan (15 min)") →
**Run workflow** → **Run workflow** button. Watch it live, and check the
job log for `[data] live: ... bars` / Telegram send confirmations to
verify it's actually working end to end.

## 5. Retire the laptop scheduler (once you've confirmed GitHub Actions is working)

On the laptop, run `UNREGISTER_STALE_TASK.bat`-style disabling for the four
live tasks (or just open Task Scheduler and disable/delete "XAUUSD Entry
Scan 15min", "WTI Hourly Analysis", "Signals News 5min", "WTI Fundamentals
Refresh"). I'd recommend running both the laptop and GitHub Actions in
parallel for a day or two first and comparing Telegram messages, so you're
not relying on an unverified path for a live signal feed.

## Known trade-offs (so nothing here is a surprise later)

- **5-minute cadence is at GitHub's practical limit.** Expect occasional
  multi-minute delays under GitHub-wide load; this never happened on your
  own laptop's Task Scheduler. If reliability matters more than freshness
  for the news refresh, widen `*/5` to `*/10` in `news-refresh.yml`.
- **State commits add small, frequent commits to the repo.** This is
  intentional (git history doubles as an audit trail of every state
  change) but means the repo will accumulate commits quickly. Nothing to
  do about this — just don't be alarmed by the commit count.
- **Why public:** at this cadence — 96 (15-min scan) + 24 (hourly) + 288
  (5-min news) + 1 (daily) = 409 runs/day ≈ 12,270/month — a private repo
  would run ~6x over the 2,000 free minutes/month, roughly $80/month in
  overage. Public repos get unlimited free Actions minutes, so this is the
  $0/month path. Your secrets are still fully protected either way (GitHub
  Secrets are encrypted and never appear in logs or the repo); only the
  trading-logic source code is visible to the public on this plan.
