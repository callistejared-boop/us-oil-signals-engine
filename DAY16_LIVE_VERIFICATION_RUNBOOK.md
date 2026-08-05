# Day 16 — Live Operational Verification Runbook

Not a coding day. This is the checklist for confirming the Day 15 fixes
actually work once pushed and given real time to run. Every check below
is written as something concrete to look at or a command to run — no
step should require re-deriving methodology from scratch.

**Prerequisite**: the 18 local commits are pushed to `origin/main`
(`DAY15_GIT_HYGIENE_REPORT.md` / the prior session's summary has the
detail). Nothing below is meaningful until that's done and at least one
full scheduled cycle of every workflow has had a chance to run (allow at
least 1-2 hours for the fastest cadences, up to 24h to see
`fundamentals-daily.yml` and to get a clean read on `heartbeat-
watchdog.yml`'s 30-min cadence relative to `entry-scan.yml`'s 15-min one).

## 1. GitHub Actions — every workflow starts, completes, exits successfully

Check: `https://github.com/callistejared-boop/us-oil-signals-engine/actions`
(public, no sign-in needed to see run list/status/duration; sign-in
needed to see step-level logs).

- [ ] `entry-scan.yml` — runs show **Status Success** (not just
      "completed" — a total-outage now exits non-zero, so a red run here
      means the fix is working and there's a real problem to look at,
      not that something broke).
- [ ] `heartbeat-watchdog.yml` — same check, plus confirm it's actually
      finding the cache (see Sec.2).
- [ ] `gold-btc-hourly.yml`, `wti-hourly.yml`, `news-refresh.yml`,
      `fundamentals-daily.yml` — unchanged this cycle, should be
      continuing their existing pattern; spot-check they're still green.
- [ ] If ANY `entry-scan.yml` run is red: click into it, it now means a
      total data-fetch failure (or another uncaught condition) actually
      happened — check `TWELVEDATA_API_KEY` in repo Settings > Secrets
      first, per Day 15's leading hypothesis.

## 2. Heartbeat — advances after every run, watchdog reacts correctly

- [ ] `git log --oneline -- .cache` won't show anything (`.cache/` is
      gitignored by design — this is expected, not a bug; the heartbeat
      status rides GitHub's Actions cache, not git).
- [ ] Confirm the cache mechanism itself worked: open a recent
      `heartbeat-watchdog.yml` run's log (needs sign-in) and check for
      either "Cache restored from key: market-cache-..." or a clear
      cache-miss message on the "Restore latest scan status from cache"
      step. A miss on the very first run after deploy is expected (no
      cache exists yet); a miss on the SECOND+ run is a problem worth
      investigating (the cache round-trip isn't working as designed).
- [ ] Confirm `heartbeat_watchdog.py`'s own log line in that same run:
      `heartbeat_watchdog: last heartbeat N min ago` — N should be small
      (under 15-20) if `entry-scan.yml` has run recently.
- [ ] To test the alert path deliberately: temporarily break
      `TWELVEDATA_API_KEY` (or wait for a real outage), confirm exactly
      one Telegram DM arrives, not one every 30 minutes thereafter.

## 3. Data pipeline — fetch, fallback, cache, snapshot persistence

- [ ] In a recent `entry-scan.yml` run's log: no "ERROR yfinance empty"
      or "ERROR ProxyError" lines for any symbol. If TwelveData is
      working, yfinance should never even be tried (see
      `engine/markets.py::fetch()` — TwelveData first, yfinance only on
      TwelveData failure).
- [ ] `git log --oneline -5 -- trades.json pending.json run_ledger.jsonl`
      on `origin/main` — should show fresh `state: entry-scan update`
      commits with recent timestamps, not just the historical
      `fundamentals-daily` ones from before this fix.
- [ ] Dashboard (wherever `dashboard_publish.py`'s live output is hosted)
      shows a recent "as of" timestamp, not a stale one.

## 4. Research histories — persist across runs, nothing disappears

This is the Day 15 fix with the least direct precedent to check against
(these files have never been tracked before), so verify carefully:

- [ ] `git log --oneline -5 -- regime_history.jsonl confluence_history.jsonl confidence_history.jsonl decision_audit.jsonl macro_history.jsonl execution_history.jsonl broker_orders.jsonl broker_fills.jsonl broker_events.jsonl broker_accounts.jsonl data_health_history.jsonl data_health_heartbeat_history.jsonl data_health_observations.jsonl experiment_registry.jsonl`
      on `origin/main` — every one of these should now show commit
      history where before Day 15 it showed none.
- [ ] Pick any 2-3 consecutive `entry-scan update` commits and confirm
      each of these files' line count strictly increases run over run
      (`git show <sha>:regime_history.jsonl | wc -l`) — growing, not
      reset to empty, confirms the persistence (not just the first write)
      is working.
- [ ] Market Memory specifically doesn't have its own dedicated history
      file (it reads from `trades.json` + `regime_history.jsonl`
      directly per `engine/market_memory.py`) — verify via those two
      files instead of looking for a separate memory file.

## 5. Paper Broker — reconstruction survives a restart

- [ ] Confirm `broker_accounts.jsonl`, `broker_orders.jsonl`,
      `broker_fills.jsonl`, `broker_events.jsonl` are all growing (Sec.4).
- [ ] `PaperBroker.__init__()` rebuilds from history on every fresh
      process (every `entry-scan.yml` run IS a fresh process, per
      `alert_signals.py`'s own `_BROKER_CACHE` comment) — so every
      successful run that shows a sensible, continuous equity/position
      figure (not reset to the account's starting balance each time) is
      itself the "restart doesn't reset anything" proof, no special test
      needed. Check the dashboard's paper-trading section or
      `broker_accounts.jsonl`'s latest row for a plausible, continuous
      balance.

## 6. First real trade — verify, don't force

- [ ] Do not adjust confluence thresholds, position limits, or any
      other gate to "help" a trade through. The point is to observe
      genuine behavior.
- [ ] Once `trades.json` gains a new row past this point (`git log -1 --
      trades.json` on origin, check the date), pull that row's `id` and
      grep for it exactly the way DAY15_PIPELINE_TRACE_AND_TRADE_ID_
      VALIDATION.md did:
      ```
      git show HEAD:trades.json | python3 -c "import json,sys; print(json.load(sys.stdin)[-1])"
      for f in regime_history.jsonl confluence_history.jsonl confidence_history.jsonl decision_audit.jsonl macro_history.jsonl execution_history.jsonl broker_orders.jsonl broker_events.jsonl run_ledger.jsonl; do
        echo "$f: $(git show HEAD:$f | grep -c '<the trade id>')"
      done
      ```
- [ ] Confirm all six `*_ref` fields on the new row equal its own `id`
      (Day 15's synthetic trace proved the code does this correctly —
      this step confirms it holds on a REAL trade, which is the one
      thing the synthetic trace couldn't prove).
- [ ] If several days pass with zero new trades: that's not automatically
      a failure. Check `git log -- run_ledger.jsonl` on origin — if it's
      growing with `regime`/`no setup`/`entry HELD` type events every 15
      minutes, the pipeline is running and simply not finding qualifying
      setups (a legitimate, documentable outcome). If `run_ledger.jsonl`
      is NOT growing, that's the real problem to chase.

## 7. Statistics — the first trade's downstream effects

Once Sec.6 confirms one trade, no separate check needed beyond what
Sec.4/6 already covered — `journal.stats()` reads `trades.json` directly,
so a correctly-written row (confirmed in Sec.6) already means the trade
journal, and everything joined to it, is correct.

## Success criteria checklist (mirrors the mandate)

- [ ] GitHub Actions running the new code (commit SHA on `origin/main`
      matches what's in the workflow run's "Triggered via schedule ...
      main" line).
- [ ] Heartbeat updates normally (Sec.2).
- [ ] Histories persist between runs (Sec.4, growing not resetting).
- [ ] No silent failures (every red run in Sec.1 was actually
      investigated, not ignored).
- [ ] One complete paper trade traversed the full chain (Sec.6), OR a
      documented explanation (via `run_ledger.jsonl` growth showing
      active-but-non-qualifying scans) for why not yet.

Only once every box above is checked should Day 17 (Strategy Framework)
begin.
