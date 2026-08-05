# Feed Registry Specification

Version 2.1, Day 14. Source of truth: `engine/data_health/registry.py`.

Every real data source this platform has, registered as a `FeedSpec`.
"No hidden dependencies" is a structural guarantee, not a convention:
`registry.validate_registry()` fails any feed whose declared
`dependency_ids` entry is not itself a registered `feed_id`, and detects
circular chains.

## 1. `FeedSpec` schema

| Field | Meaning |
|---|---|
| `feed_id` | Unique registry key |
| `provider` | Human-readable module/provider name |
| `purpose` | One-line description of what this feed is for |
| `category` | `market_data` \| `macro` \| `news` \| `infrastructure` \| `computed` |
| `freshness_kind` | `time_decayed` \| `reference_data` \| `computed` \| `observed` |
| `update_frequency_minutes` | Disclosed expected cadence |
| `expected_freshness_minutes` | Age at which state moves past Fresh |
| `timeout_threshold_seconds` | Disclosed estimate (not live-measured) |
| `failure_behavior` | What the SOURCE module does on failure |
| `fallback_behavior` | What the SOURCE module falls back to |
| `dependency_ids` | Other registered `feed_id`s this feed depends on |
| `configured_check` | Optional `(settings) -> bool`, for feeds needing an API key |
| `probe_kind` | `file_mtime` \| `json_field` \| `observed` \| `heartbeat` \| `computed` \| `none` |
| `probe_target` | Path/field/feed_id interpreted by `probe_kind` |

## 2. Registered feeds

| feed_id | Category | Provider | Expected freshness | Dependencies |
|---|---|---|---|---|
| `market_data:XAUUSD` | market_data | `markets.fetch_resilient` | 20 min | — |
| `market_data:WTIUSD` | market_data | `markets.fetch_resilient` | 20 min | — |
| `market_data:BTCUSD` | market_data | `markets.fetch_resilient` | 20 min | — |
| `market_data:EURUSD` | market_data | `markets.fetch_resilient` | 20 min | — |
| `rates_feed` | macro | `engine.rates_feed` | 20 h | — |
| `risk_sentiment` | macro | `engine.risk_sentiment` | 20 h | — |
| `correlation_dynamic` | macro | `engine.correlation_dynamic` | 48 h | — |
| `cot_feed` | macro | `engine.cot_feed` | 10 d | — |
| `eia_feed` | macro | `engine.eia_feed` | 8 d | — (gated on `settings.eia_api_key`) |
| `spread_feed` | macro | `engine.spread_feed` | 20 h | — |
| `macro_reference` | macro | `engine.macro_reference` | reference data (no clock decay) | — |
| `seasonality` | computed | `engine.seasonality` | computed (no clock decay) | — |
| `news_calendar` | news | `engine.news_guard` (ForexFactory) | 20 min | — |
| `macro_calendar` | news | `engine.macro_calendar` | derived | `news_calendar` |
| `fundamentals_feed` | news | `engine.fundamentals_feed` (Google News RSS) | 15 min | — |
| `journal_persistence` | infrastructure | `engine.journal` (`trades.json`) | 3 h | — |
| `scan_loop_heartbeat` | infrastructure | `alert_signals.main()` via `entry-scan.yml` | 45 min | — |
| `dashboard_publish` | infrastructure | `engine.dashboard_publish` | 45 min | — |

18 feeds total (4 market-data symbols + 14 macro/news/infrastructure).

## 3. Dependency graph

Only one real dependency edge exists today: `macro_calendar` depends on
`news_calendar` (it is a derived, re-classified VIEW of
`news_guard.fetch_events()`'s own output, not an independent fetch — see
`engine/macro_calendar.py`'s own "REUSE, NOT DUPLICATION" docstring).
Per the mandate's own cascading-failure example ("Macro Engine -> Rates
Feed -> Yahoo"), if `news_calendar` degrades to Partial/Unavailable,
`provider_status.apply_dependency_cascade()` propagates that status onto
`macro_calendar` — `macro_calendar` can never show healthier than the
feed it's derived from.

Every other registered feed is currently a leaf (no declared
dependency) — this platform's macro/news/market-data providers are each
independently sourced, per Day 11's `macro_providers.py` single-
abstraction-layer design (no provider function calls another provider
function's underlying feed module directly).

## 4. Configured-gated feeds

Only `eia_feed` has a `configured_check` today (`settings.eia_api_key`
non-empty) — the one feed in this codebase that already required
optional operator configuration before Day 14 (see
`engine/eia_feed.py`'s pre-existing "not configured" shape). A feed with
`configured_check` returning `False` is classified `Unavailable`
regardless of its freshness state.

## 5. Extending the registry

To register a new feed, add one `FeedSpec` to
`registry._register_defaults()` (or call `registry.register()` from
anywhere else at import time). Required: `feed_id`, `provider`,
`purpose`, `category`. Strongly recommended: `expected_freshness_minutes`
and a `probe_kind`/`probe_target` pair so `feed_monitor.py` can actually
assess it — a feed with `probe_kind="none"` will always report Unknown
freshness (not a fault, just nothing to check). Run
`registry.validate_registry()` (or the full `tests/test_data_health_
registry.py` suite) after any change — it will catch a typo'd
`dependency_ids` entry before it reaches production.
