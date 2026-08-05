"""Feed registry — every data source this platform has, one place.

"No hidden dependencies": every `FeedSpec.dependency_ids` entry must
itself be a registered `feed_id`, or `validate_registry()` reports it as
an error. This is the single source of truth `provider_status.py`'s
dependency-cascade logic and `health_report.py`'s dependency map both
read from — neither module hard-codes a second copy of this graph.

Each `FeedSpec` declares, per the mandate's own required fields:
provider name, purpose, update frequency, expected freshness, timeout
threshold, failure behavior, fallback behavior, and dependency list.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional, Tuple

# Freshness kinds, distinguishing feeds that decay with clock time from
# feeds that don't. Mirrors `engine/macro_providers.py`'s three-way split
# (`_freshness_from_iso` / `_freshness_reference` / `_freshness_computed`)
# — reused as the precedent for this table, not reinvented.
TIME_DECAYED = "time_decayed"    # ages against update_frequency/expected_freshness
REFERENCE = "reference_data"     # curated, operator-updated, no decay clock
COMPUTED = "computed"            # pure calculation, always available if code runs
OBSERVED = "observed"            # no cache file; freshness comes from a recorded
                                  # observation of a call the platform already made


@dataclasses.dataclass(frozen=True)
class FeedSpec:
    feed_id: str
    provider: str                       # human-readable provider/module name
    purpose: str
    category: str                       # market_data | macro | news | infrastructure | computed
    freshness_kind: str = TIME_DECAYED  # one of the four constants above
    update_frequency_minutes: Optional[float] = None   # expected cadence, disclosed
    expected_freshness_minutes: Optional[float] = None  # age at which "Aging" begins
    timeout_threshold_seconds: Optional[float] = None  # disclosed estimate; this
                                                         # package does not itself
                                                         # instrument live call
                                                         # duration for every feed
    failure_behavior: str = ""          # what the SOURCE module does on failure
    fallback_behavior: str = ""         # what the SOURCE module falls back to
    dependency_ids: Tuple[str, ...] = ()
    configured_check: Optional[Callable[[object], bool]] = None  # (settings) -> bool
    probe_kind: str = "none"            # "file_mtime" | "json_field" | "heartbeat" | "observed" | "computed" | "none"
    probe_target: Optional[str] = None  # path template or json field name, interpreted by freshness.py


class RegistryError(Exception):
    pass


_REGISTRY: dict = {}


def register(spec: FeedSpec) -> None:
    """Register (or replace) a FeedSpec. Never raises — a bad registration
    is caught by validate_registry(), not by crashing whatever imported
    this module at process start."""
    try:
        _REGISTRY[spec.feed_id] = spec
    except Exception:  # noqa: BLE001
        pass


def get(feed_id: str) -> Optional[FeedSpec]:
    return _REGISTRY.get(feed_id)


def all_feeds() -> Tuple[FeedSpec, ...]:
    return tuple(_REGISTRY.values())


def feed_ids() -> Tuple[str, ...]:
    return tuple(_REGISTRY.keys())


def dependents_of(feed_id: str) -> Tuple[str, ...]:
    """Feeds that declare feed_id as one of their dependencies — the
    'what breaks if this goes down' view."""
    return tuple(f.feed_id for f in _REGISTRY.values() if feed_id in f.dependency_ids)


def dependency_chain(feed_id: str, _seen: Optional[set] = None) -> Tuple[str, ...]:
    """Full transitive dependency closure for one feed, cycle-safe."""
    seen = _seen if _seen is not None else set()
    spec = _REGISTRY.get(feed_id)
    if spec is None or feed_id in seen:
        return ()
    seen.add(feed_id)
    out = []
    for dep in spec.dependency_ids:
        if dep not in out:
            out.append(dep)
        out.extend(x for x in dependency_chain(dep, seen) if x not in out)
    return tuple(out)


def validate_registry() -> dict:
    """Structural validation only — no network, no filesystem probing.
    Returns {"ok": bool, "errors": [...], "feed_count": int}."""
    errors = []
    try:
        for spec in _REGISTRY.values():
            for dep in spec.dependency_ids:
                if dep not in _REGISTRY:
                    errors.append(
                        f"{spec.feed_id}: dependency '{dep}' is not a registered feed_id"
                    )
            if not spec.provider:
                errors.append(f"{spec.feed_id}: missing provider name")
            if not spec.purpose:
                errors.append(f"{spec.feed_id}: missing purpose")
        # cycle detection
        for feed_id in _REGISTRY:
            chain = dependency_chain(feed_id)
            if feed_id in chain:
                errors.append(f"{feed_id}: circular dependency detected ({chain})")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"validate_registry internal error: {exc}")
    return {"ok": len(errors) == 0, "errors": errors, "feed_count": len(_REGISTRY)}


def reset() -> None:
    """Test-only helper — clears the module-level registry dict."""
    _REGISTRY.clear()


def _configured(feed_id: str, settings) -> Optional[bool]:
    """Runs a feed's configured_check(settings) if present. Returns None
    (unknown, not a fault) if the feed has no check or the check itself
    raises."""
    spec = _REGISTRY.get(feed_id)
    if spec is None or spec.configured_check is None:
        return None
    try:
        return bool(spec.configured_check(settings))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Default registration — every real data source this platform has, per the
# Day 14 Phase 1 audit. Registered at import time so `feed_monitor.py` has a
# populated registry with zero setup required by callers.
# ---------------------------------------------------------------------------

def _register_defaults() -> None:
    from engine.markets import MARKETS

    for symbol in MARKETS:
        register(FeedSpec(
            feed_id=f"market_data:{symbol}",
            provider="engine.markets.fetch_resilient",
            purpose=f"OHLC price bars for {symbol} signal generation",
            category="market_data",
            freshness_kind=TIME_DECAYED,
            update_frequency_minutes=15,
            expected_freshness_minutes=20,
            timeout_threshold_seconds=30,
            failure_behavior=(
                "raises only if no live source AND no local cache exists; "
                "otherwise falls back to the last cached bar set"
            ),
            fallback_behavior=f"serves .cache/{symbol.upper()}.pkl, flagged stale=True with age",
            dependency_ids=(),
            probe_kind="file_mtime",
            probe_target=f".cache/{symbol.upper()}.pkl",
        ))

    register(FeedSpec(
        feed_id="rates_feed",
        provider="engine.rates_feed (rates/bonds/inflation_expectation_proxy)",
        purpose="Interest-rate, sovereign-bond, and inflation-expectation macro context",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=20 * 60,
        failure_behavior="never raises; returns an 'unavailable' shaped result",
        fallback_behavior="serves rates_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="rates_cache.json",
    ))

    register(FeedSpec(
        feed_id="risk_sentiment",
        provider="engine.risk_sentiment",
        purpose="Cross-asset risk-on/risk-off sentiment proxy",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=20 * 60,
        failure_behavior="never raises; returns an 'unavailable' shaped result",
        fallback_behavior="serves risk_sentiment_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="risk_sentiment_cache.json",
    ))

    register(FeedSpec(
        feed_id="correlation_dynamic",
        provider="engine.correlation_dynamic",
        purpose="Rolling cross-symbol correlation for portfolio-risk aggregation",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=48 * 60,
        failure_behavior="never raises; returns an 'unavailable' shaped result",
        fallback_behavior="serves correlation_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="correlation_cache.json",
    ))

    register(FeedSpec(
        feed_id="cot_feed",
        provider="engine.cot_feed",
        purpose="CFTC Commitment of Traders positioning context",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=24 * 10 * 60,
        failure_behavior="never raises; returns an 'unavailable' shaped result",
        fallback_behavior="serves cot_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="cot_cache.json",
    ))

    register(FeedSpec(
        feed_id="eia_feed",
        provider="engine.eia_feed",
        purpose="EIA crude-oil inventory data (WTI fundamentals)",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=24 * 8 * 60,
        failure_behavior="never raises; returns a 'not_configured' or 'unavailable' shaped result",
        fallback_behavior="serves eia_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        configured_check=lambda settings: bool(getattr(settings, "eia_api_key", "")),
        probe_kind="file_mtime",
        probe_target="eia_cache.json",
    ))

    register(FeedSpec(
        feed_id="spread_feed",
        provider="engine.spread_feed",
        purpose="WTI crack-spread proxy context",
        category="macro",
        freshness_kind=TIME_DECAYED,
        expected_freshness_minutes=20 * 60,
        failure_behavior="never raises; returns an 'unavailable' shaped result",
        fallback_behavior="serves spread_cache.json beyond max_age with disclosed staleness",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="spread_cache.json",
    ))

    register(FeedSpec(
        feed_id="macro_reference",
        provider="engine.macro_reference",
        purpose="Curated central-bank/geopolitical reference assessments",
        category="macro",
        freshness_kind=REFERENCE,
        failure_behavior="never raises; returns a clearly-labeled 'not configured' result",
        fallback_behavior="none — this is operator-curated data, not fetched",
        dependency_ids=(),
        probe_kind="none",
    ))

    register(FeedSpec(
        feed_id="seasonality",
        provider="engine.seasonality",
        purpose="Calendar-driven structural seasonal priors",
        category="computed",
        freshness_kind=COMPUTED,
        failure_behavior="pure computation; failure would be a code defect, not a data-availability issue",
        fallback_behavior="none needed — no external dependency",
        dependency_ids=(),
        probe_kind="computed",
    ))

    register(FeedSpec(
        feed_id="news_calendar",
        provider="engine.news_guard (ForexFactory feed)",
        purpose="High-impact USD economic calendar + news-blackout window logic",
        category="news",
        freshness_kind=OBSERVED,
        update_frequency_minutes=15,
        expected_freshness_minutes=20,
        timeout_threshold_seconds=15,
        failure_behavior="fails OPEN — evaluate() returns ok:False rather than raising or blocking",
        fallback_behavior="none — no local cache; next scan retries the live fetch",
        dependency_ids=(),
        probe_kind="observed",
        probe_target="news_calendar",
    ))

    register(FeedSpec(
        feed_id="macro_calendar",
        provider="engine.macro_calendar",
        purpose="Standardized, classified view of news_guard's event list",
        category="news",
        freshness_kind=OBSERVED,
        failure_behavior="derived module; inherits news_guard's own fail-open behavior",
        fallback_behavior="none — re-derived from news_guard on every call, no independent fetch",
        dependency_ids=("news_calendar",),
        probe_kind="observed",
        probe_target="news_calendar",
    ))

    register(FeedSpec(
        feed_id="fundamentals_feed",
        provider="engine.fundamentals_feed (Google News RSS headline sentiment)",
        purpose="Per-symbol headline-sentiment heuristic (BUY/SELL/NEUTRAL bias)",
        category="news",
        freshness_kind=TIME_DECAYED,  # writes fundamentals.json each run — a
                                       # real cache file to inspect, unlike
                                       # news_guard/macro_calendar below
        update_frequency_minutes=5,
        expected_freshness_minutes=15,
        timeout_threshold_seconds=20,
        failure_behavior="best-effort per-query; a failed query is simply excluded from the aggregate",
        fallback_behavior="serves fundamentals.json (last successful write) if the current run fails",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="fundamentals.json",
    ))

    register(FeedSpec(
        feed_id="journal_persistence",
        provider="engine.journal (trades.json)",
        purpose="Trade record persistence — the platform's core decision/outcome ledger",
        category="infrastructure",
        freshness_kind=TIME_DECAYED,
        update_frequency_minutes=15,
        expected_freshness_minutes=180,
        failure_behavior="atomic write via temp-file + os.replace; a mid-write crash leaves the prior file intact",
        fallback_behavior="STORE.bak exists as a manual-recovery copy; not auto-restored",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="trades.json",
    ))

    register(FeedSpec(
        feed_id="scan_loop_heartbeat",
        provider="alert_signals.main() via .github/workflows/entry-scan.yml (cron */15 * * * *)",
        purpose="Liveness of the primary signal-generation scan loop",
        category="infrastructure",
        freshness_kind=TIME_DECAYED,
        update_frequency_minutes=15,
        expected_freshness_minutes=45,  # matches heartbeat_watchdog.STALE_MINUTES
        failure_behavior="a missing/stale heartbeat file does not raise; heartbeat_watchdog DMs once",
        fallback_behavior="none — a stale scan loop is itself the fault being reported",
        dependency_ids=(),
        probe_kind="heartbeat",
        probe_target="alert_heartbeat.txt",
    ))

    register(FeedSpec(
        feed_id="dashboard_publish",
        provider="engine.dashboard_publish.build_payload/publish",
        purpose="Publishes the platform's read-only dashboard payload",
        category="infrastructure",
        freshness_kind=TIME_DECAYED,
        update_frequency_minutes=15,
        expected_freshness_minutes=45,
        failure_behavior="each payload section is wrapped in _safe_note(); one section failing does not block the rest",
        fallback_behavior="last successfully published payload remains live until the next successful publish",
        dependency_ids=(),
        probe_kind="file_mtime",
        probe_target="dashboard_publish_heartbeat.json",
    ))


_register_defaults()
