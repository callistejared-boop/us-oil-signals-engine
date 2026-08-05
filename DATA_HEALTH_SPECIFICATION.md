# Data Quality & Feed Health Monitoring Framework — Specification

Version 2.1, Day 14. Package: `engine/data_health/`.

## 1. Purpose

This framework's purpose is not to fetch market data. Its purpose is to
determine whether the platform can trust the data it already has. Every
other Day of this platform's build has produced a layer that DOES
something with data (originates signals, scores confluence, estimates
execution cost, tracks a paper account). This Day produces a layer that
watches all of those layers' inputs and says, in plain terms: is this
feed fresh, complete, consistent, and free of obvious anomalies — and if
not, what would an operator need to know to act on it.

The framework observes, validates, classifies, reports, and recommends.
It does not alter trading decisions. It is advisory, structurally proven
so (Sec. 9).

## 2. Package layout

| File | Responsibility |
|---|---|
| `registry.py` | Every data source this platform has, one `FeedSpec` each, with declared dependencies |
| `freshness.py` | 5-state (Fresh/Aging/Stale/Expired/Unknown) sub-day freshness classifier + file/JSON/observation age lookups |
| `completeness.py` | Missing-field, empty-payload, truncated-dataset detection, 4-tier severity |
| `consistency.py` | OHLC validity, duplicate timestamps, negative volume, conflicting-source, symbol-metadata checks |
| `anomaly.py` | Frozen-price, single-bar-outlier (z-score), timeline-gap detection — simple, disclosed statistics, not predictive modeling |
| `provider_status.py` | Combines the four checks above into one 4-state classification per feed + dependency-cascade logic |
| `heartbeat.py` | Process-level liveness: scheduler execution, provider responsiveness, processing latency, queue health, dashboard publishing, journal persistence |
| `health_report.py` | Assembles every module's output into one report object |
| `feed_monitor.py` | The single coordinator — `run_health_check()` / `dashboard_snapshot()` |

Each module has exactly one responsibility, per the mandate's own
structural requirement. No module calls a live data-fetch function from
any other part of this codebase — every check operates on data already
sitting on disk (a cache file's mtime, a cache file's own embedded
timestamp, or a lightweight observation record written by a call site
that was already making a live call for its own reasons).

## 3. Feed registry

18 feeds registered at import time (`registry._register_defaults()`),
covering every data source this platform's Day 1-13 audit surfaced:
market price bars (one per symbol), rates/bonds/inflation, risk
sentiment, dynamic correlation, COT positioning, EIA crude inventory,
WTI crack-spread proxy, curated macro reference data, calendar-driven
seasonality, the ForexFactory news calendar, the derived macro-calendar
view, headline-sentiment (`fundamentals_feed`), trade-journal
persistence, the scan-loop heartbeat, and dashboard publishing.

Each `FeedSpec` declares, per the mandate's required fields: `provider`,
`purpose`, `update_frequency_minutes`, `expected_freshness_minutes`,
`timeout_threshold_seconds`, `failure_behavior`, `fallback_behavior`, and
`dependency_ids`. No hidden dependencies: `registry.validate_registry()`
fails any feed whose declared dependency isn't itself a registered
`feed_id`, and detects circular dependency chains. See
`FEED_REGISTRY_SPECIFICATION.md` for the full per-feed table.

## 4. Freshness — 5 states

Fresh / Aging / Stale / Expired / Unknown, at MINUTE granularity, driven
by each feed's own `expected_freshness_minutes` and two disclosed
multipliers (`AGING_MULTIPLIER = 1.5`, `STALE_MULTIPLIER = 3.0`; beyond
that is Expired). Unknown is distinct from Expired — it means "we cannot
assess," not "we assessed it and it's bad" (e.g. a cache file that has
never been written yet, or a feed with no recorded observation).

**Disambiguation from `engine/freshness.py`**: that module (Day 1-2 era)
is a DAY-granularity, 3-state (fresh/aging/stale) banner for dated
qualitative context (fundamentals commentary, geopolitical narrative
age). It is unchanged by this Day and serves a different purpose — this
package's `freshness.py` is the one used for operational feed-health
monitoring across every data source, market bars included.

Three freshness mechanisms, matched to how each feed actually persists
data:

1. **File mtime** (`age_minutes_from_mtime`) — for feeds with a
   filesystem cache (`.cache/{SYMBOL}.pkl`, `rates_cache.json`,
   `spread_cache.json`, `cot_cache.json`, `eia_cache.json`,
   `risk_sentiment_cache.json`, `correlation_cache.json`,
   `fundamentals.json`, `trades.json`).
2. **JSON embedded field** (`age_minutes_from_json_field`) — reads a
   cache file's own `"generated"`/`"published_at"` field rather than
   filesystem mtime, when available.
3. **Observation** (`record_observation`/`age_minutes_from_observation`)
   — for feeds with NO persisted cache (`news_guard`'s live calendar
   fetch). The call site that was already making that live call for its
   own reasons (`alert_signals.py`'s Stage-2 flow) reports the outcome to
   `data_health_observations.jsonl`. This package never triggers the
   call itself.

`REFERENCE` (curated, operator-maintained, e.g. `macro_reference`) and
`COMPUTED` (pure calculation, e.g. `seasonality`) feeds are treated as
always-current for status purposes — they don't decay against a clock
the way time-decayed feeds do.

## 5. Completeness

`completeness.check_dict()` / `check_dataframe()` classify missing
fields, empty payloads, and truncated datasets into
none/minor/major/critical severity. A payload that is `None`, the wrong
type, or an empty container is `critical`. Missing some-but-not-all
required fields is `major`; missing only optional fields is `minor`.

## 6. Consistency

`consistency.check_ohlc()` validates high>=low, high>=open, high>=close,
low<=open, low<=close, non-positive prices, and negative volume, row by
row, reporting violation counts and a severity proportional to the
violation ratio. `check_duplicate_timestamps()` flags repeated
index/timestamp entries. `check_conflicting_sources()` compares the same
fact reported by multiple providers against a disclosed tolerance
percentage. `check_symbol_metadata()` confirms a symbol's entry in
`engine.markets.MARKETS` is complete.

## 7. Anomaly detection

Explicitly NOT predictive modeling — pure operational statistics, same
"disclosed engineering judgment, not a fitted model" posture as every
other qualitative constant in this codebase (Day 6's confidence tiers,
Day 9's `EXPECTANCY_DECLINE_R`).

- `check_frozen_price()` — flags N consecutive identical closes
  (default threshold 6 bars) as a stuck/frozen-feed signature.
- `check_price_jump()` — flags a single bar-to-bar change with a
  z-score >= 6.0 against the series' own recent bar-to-bar volatility.
- `check_timeline_gaps()` — flags gaps in a bar timeline materially
  larger (3x by default) than the feed's own expected sampling interval.

## 8. Health scoring — 4 states, not a single number

Per the mandate's explicit instruction, health is a classification, not
a score:

- **Operational** — fresh (or reference/computed as designed), no
  completeness/consistency/anomaly issue worse than minor.
- **Degraded** — usable but imperfect (aging freshness, or an isolated
  minor/major issue). Worth watching, no action required yet.
- **Partial** — meaningfully compromised (stale freshness, or a major
  finding). Usable with real caution; investigate.
- **Unavailable** — expired freshness, a critical finding, or a feed
  whose `configured_check` reports it isn't configured at all. Do not
  rely on this feed's current data.

Each classification also carries a **confidence** in the assessment
itself (high/medium/low — separate from the status: an Unknown
freshness state with no other signal gets low confidence regardless of
what status results), the **affected subsystems** (every feed that
transitively depends on this one, per the registry's dependency graph),
and a **recommended action**.

## 9. Advisory only — structural proof

Nothing in `engine/data_health/` is imported by `engine/risk_guard.py`,
`engine/confluence.py`, `engine/confidence_engine.py`,
`engine/bias_adjust.py`, `engine/signals.py`,
`engine/portfolio_risk.py`, or `engine/regime_engine.py`:

```
$ grep -n "data_health" engine/risk_guard.py engine/confluence.py \
    engine/confidence_engine.py engine/bias_adjust.py engine/signals.py \
    engine/portfolio_risk.py engine/regime_engine.py
(no output — zero matches)
```

`alert_signals.py`'s integration (Sec. 10) calls the health check strictly
AFTER every symbol in a scan has already been fully processed — the
health check is an observation OF the scan that just happened, never a
precondition for it.

## 10. Advisory integration

- `alert_signals.py`: `log_data_health(settings, elapsed_seconds,
  symbol_count)` runs once per scan (not once per symbol), after the
  per-symbol loop completes, and appends a one-line summary
  (`data health: <status> (<counts>)`) to the same heartbeat log
  `alert_heartbeat.txt` already carries. It also records an observation
  for the `news_calendar` feed immediately after `news_guard.evaluate()`
  — the same call the news-blackout check already makes, never a second
  fetch.
- `engine/dashboard_publish.py`: a `"data_health"` payload key,
  symbol-agnostic (one platform-wide report, identical across every
  symbol's payload — same precedent as `"paper_trading"`), read via
  `feed_monitor.dashboard_snapshot()`. `dashboard_publish.main()` also
  writes `dashboard_publish_heartbeat.json` (`{"published_at": ...,
  "symbols_published": [...]}`) on any successful publish — a "last
  successful publish" timestamp that did not exist before this Day (a
  gap identified during Phase 1 audit).

**Read vs. write separation**: `feed_monitor.run_health_check(persist=
True)` (the default, used by `log_data_health()`) both computes the
report AND writes a heartbeat record + failure-philosophy event trail.
`feed_monitor.dashboard_snapshot()` calls `run_health_check(persist=
False)` — a dashboard page load (called once per symbol, potentially
several times per scan) must never itself count as a scan-level "beat"
or inflate the research history. Both paths compute the identical report
shape; only persistence differs.

## 11. Failure philosophy — no silent failures

Every scan-level health check (`persist=True`) appends one `run_summary`
event to `data_health_history.jsonl`, plus a dedicated `provider_issue`
event for every feed that is Degraded-or-worse, plus a dedicated
`recovery` event for any feed that transitions FROM a non-Operational
status back to Operational (detected by re-deriving the previous run's
statuses from the persisted history itself, not from in-process memory —
the same `rebuild_from_history()` discipline Day 13 established, needed
because this platform's scan loop is a fresh process each invocation).
So a failure becomes: an event (`data_health_history.jsonl`), a log line
(`alert_heartbeat.txt`'s "data health: ..." line), a dashboard
notification (the `"data_health"` payload key), and a research record
(the same JSONL, readable by any future research script).

## 12. Testing

149 new tests across 10 files (Sec. below in
`DAY14_VALIDATION_REPORT.md`), covering every item on the mandate's own
testing list: missing feeds, delayed feeds, malformed data, duplicate
updates, frozen prices, dependency-cascade failures, restart/recovery
detection, registry validation (missing dependency, missing
provider/purpose, circular dependency), and full-suite regression
against the Day 13 baseline (1,204 tests; 1,353 after this Day, zero
regressions).

## 13. Known limitations (disclosed, not hidden)

- **Quality checks (completeness/consistency/anomaly) only run against
  feeds this package can cheaply inspect on disk** — market-data
  pickles (full OHLC/consistency/anomaly checks) and JSON caches
  (a generic non-empty-payload check only, not per-field schema
  validation for each individual feed's internal shape). Deeper,
  feed-specific field validation is a disclosed backlog item, not
  silently assumed to already exist.
- **`timeout_threshold_seconds` is a disclosed estimate per feed, not
  measured live** — this package does not instrument the actual
  duration of every underlying fetch call; it is not itself doing any
  fetching to measure.
- **`processing_latency_seconds`/`queue_depth` in the heartbeat are only
  as good as what `alert_signals.py` supplies** — this platform has no
  message queue in the traditional sense; `queue_depth` is best
  understood as "symbols processed this scan pass" when supplied.
- **`dashboard_snapshot()` recomputes the full health check on every
  call** (once per symbol per scan, from `dashboard_publish.py`) —
  cheap (local file I/O only, no network), but not cached across those
  repeated calls within one scan. Mirrors the same precedent already
  accepted for `paper_trading`'s `dashboard_snapshot()`.
