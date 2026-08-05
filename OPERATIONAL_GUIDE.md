# Data Health — Operational Guide

Version 2.1, Day 14. For the platform owner / operator, not a developer
reference (see `DATA_HEALTH_SPECIFICATION.md` for that).

## 1. Where to look

- **Telegram/heartbeat log** (`alert_heartbeat.txt`) — the last line of
  every scan now reads `data health: <status> (<counts>)`, e.g.
  `data health: operational ({'operational': 16, 'degraded': 2, ...})`.
  This is the fastest single-glance check.
- **Dashboard** — the `"data_health"` payload key on every symbol's
  dashboard row (identical across symbols — one platform-wide report).
  Shows per-provider status, reasons, recommended action, the dependency
  map, and the last 10 research-history events.
- **`data_health_history.jsonl`** (repo root) — the full append-only
  research trail: one `run_summary` per scan, plus a `provider_issue`
  event for anything degraded-or-worse and a `recovery` event when a
  feed comes back. Read with `feed_monitor.history_tail(n)`.
- **`data_health_heartbeat_history.jsonl`** — process-level liveness
  over time (scheduler/dashboard-publish/journal-persistence age,
  processing latency). Read with `heartbeat.tail(n)`.

## 2. Reading a status

| Status | What it means | What to do |
|---|---|---|
| Operational | Feed is fresh, complete, consistent | Nothing |
| Degraded | Aging, or an isolated minor/major issue | Watch; usually resolves next scan |
| Partial | Stale, or a major finding | Investigate the underlying provider/cache — usable with caution |
| Unavailable | Expired, a critical finding, or not configured | Don't rely on this feed's current data; check connectivity/API key |

Every status also carries a **confidence** in the assessment (a Low
confidence with an otherwise-fine status usually means "we genuinely
don't have a freshness signal for this feed yet," not "something is
wrong").

## 3. Common situations

**"A feed shows Unknown/Degraded and I've never seen it fetch
anything."** Check whether its cache file has ever been written — many
caches (rates_cache.json, spread_cache.json, etc.) don't exist until the
first successful live pull. This is expected on a fresh checkout or
right after a reset, not a fault.

**"`eia_feed` always shows Unavailable."** Check `EIA_API_KEY` is set —
`eia_feed` is the one registered feed with a `configured_check`; an
empty key reports Unavailable regardless of anything else.

**"`macro_calendar` went Unavailable right after `news_calendar` did."**
Expected — this is the one real dependency edge in the registry
(Sec. 3 of `FEED_REGISTRY_SPECIFICATION.md`). Fix `news_calendar`
first; `macro_calendar` recovers automatically on the next scan once its
dependency does.

**"The overall status says degraded but nothing looks broken."** The
overall rollup is intentionally sensitive — ANY feed worse than
Operational moves the platform-wide status to `degraded`. Check the
`degraded_or_worse` list in the report for exactly which feed(s) and
why, rather than reading `overall_status` alone as a verdict.

## 4. What this framework will never do

It will never delay, block, or resize a trade, and it will never change
a confluence score, confidence score, or macro label. It is
structurally incapable of this — see `DATA_HEALTH_SPECIFICATION.md`
Sec. 9 for the grep-verified proof. If a feed is Unavailable and a trade
still fires, that is not a bug in this framework; the framework's job
ends at reporting, by design, per this Day's mandate.

## 5. Extending monitoring to a new data source

See `FEED_REGISTRY_SPECIFICATION.md` Sec. 5. In short: register a
`FeedSpec` in `engine/data_health/registry.py`, give it a
`probe_kind`/`probe_target` pointing at wherever that feed already
persists data (or an `observed` probe if it doesn't persist anything),
and it is picked up automatically by the next `run_health_check()` —
no change needed to `feed_monitor.py`, `dashboard_publish.py`, or
`alert_signals.py`.

## 6. Troubleshooting the framework itself

Every module in `engine/data_health/` is fail-safe by construction — a
bug in one check should degrade that one feed's assessment, not crash
the scan. If `data health:` disappears from the heartbeat log entirely,
check `log_data_health()`'s return — `als.log_data_health()` catches
everything from `feed_monitor.run_health_check()` and falls back to an
`unavailable`/error-noted report rather than raising, so the scan itself
is never at risk. `registry_validation.errors` in any report will
surface a bad `FeedSpec` registration immediately.
