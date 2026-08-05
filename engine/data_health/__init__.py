"""Data Quality & Feed Health Monitoring Framework (Day 14).

GOVERNING PRINCIPLE: this package's purpose is not to fetch market data.
Its purpose is to determine whether the platform can trust the data it
ALREADY has. Every module in here observes, validates, classifies,
reports, and recommends — never originates a live network call of its
own. Where a feed already writes a cache file (rates_cache.json,
spread_cache.json, cot_cache.json, eia_cache.json,
risk_sentiment_cache.json, correlation_cache.json, the `.cache/*.pkl`
price bars, `trades.json`, `alert_heartbeat.txt`), this package reads
that file's own embedded timestamp or filesystem mtime — a local,
zero-network inspection of data the platform already fetched for its own
reasons. Where a feed has no persisted cache (news_guard's calendar,
fundamentals_feed's headline sentiment), this package never calls the
feed itself; it only reads a lightweight OBSERVATION record that the
existing call site writes via `record_observation()` after a call it was
already making anyway (see `alert_signals.py` integration, Phase 8).

ADVISORY ONLY, STRUCTURALLY. Nothing in `engine/data_health/` is
imported by any gating module (`risk_guard.py`, `confluence.py`,
`confidence_engine.py`, `bias_adjust.py`, `signals.py`,
`portfolio_risk.py`, `regime_engine.py`). A health report can say a feed
is UNAVAILABLE and no trade will be blocked as a direct structural
consequence of that fact alone — see DATA_HEALTH_SPECIFICATION.md for
the grep-verified proof, mirroring the same proof pattern every prior
Day's advisory layer has carried since Day 8.

NAMING DISAMBIGUATION — two modules named "freshness" now exist in this
codebase and they are NOT the same thing:

- `engine/freshness.py` (Day 1-2 era): a DAY-granularity, 3-state
  (fresh/aging/stale) banner used for dated qualitative context —
  fundamentals commentary, geopolitical narrative age. Unchanged by this
  Day.
- `engine/data_health/freshness.py` (this package): a MINUTE-granularity,
  5-state (Fresh/Aging/Stale/Expired/Unknown) classifier used for
  operational feed-health monitoring across every data source this
  platform has, market bars included. A different tool for a different
  question — "is this specific feed's data recent enough to act on"
  versus "is this dated narrative getting old."

Suggested reading order for a new module: `registry.py` (what's being
watched) -> `freshness.py`/`completeness.py`/`consistency.py`/
`anomaly.py` (the four independent checks) -> `provider_status.py`
(combines the four checks + dependency graph into one classification per
provider) -> `heartbeat.py` (process-level liveness, distinct from
per-feed data freshness) -> `health_report.py` (assembles everything into
one report) -> `feed_monitor.py` (the single coordinator every external
caller should use).
"""
