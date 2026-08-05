"""Dynamic (rolling) cross-symbol correlation — Day 3 Phase 4.

engine.correlation's USD_SENSITIVITY table is a fixed, hand-set table of each
instrument's sign of correlation with the US Dollar. It is deliberately
static and coarse (a single -1/-0.5 sign, no magnitude, never updated). It
answers "does this trade fight the dollar?" — a different, narrower question
than what portfolio_risk.py needs: "how correlated are the OPEN and
CANDIDATE positions with EACH OTHER, right now, given how the market has
actually been trading recently?"

This module answers that second question with a rolling Pearson correlation
of daily log returns, computed from the same OHLC feed every other module
already uses (engine.markets.fetch_resilient + engine.data_loader.resample),
so it adds no new data source and no new fetch logic. Correlations are
recomputed on demand, disk-cached (same load/max-age pattern as
engine.correlation's macro.json and engine.cot_feed/eia_feed/risk_sentiment),
and fall back to a crude static estimate derived from USD_SENSITIVITY only
when live data is entirely unavailable — never to a bare exception.

Why rolling, not fixed (per Day 3 Phase 4 examples):
  - Gold and Bitcoin can move together during dollar-weakness regimes and
    decouple entirely at other times (BTC is not consistently a "digital
    gold" trade — that relationship is regime-dependent, not structural).
  - Gold and WTI diverge sharply on inflation shocks (both up) vs. pure
    geopolitical supply shocks (oil up, gold flat/down) vs. growth scares
    (both down). A fixed correlation sign cannot capture that switch.
  - Any fixed number is a snapshot of one historical regime; a rolling
    window adapts as regimes change — the same premise engine/regime.py
    already relies on elsewhere in this codebase.

Validation discipline (mirrors engine/calibration.py's min_n=8 rule): a
computed correlation is only trusted outright once at least MIN_SAMPLE_DAYS
of paired daily closes are available. Below that, the computed value is
blended toward the static fallback and tagged "sample": "insufficient" so
callers can see the estimate is thin. This module is read-only analytics
(like the dashboard's use of fetch_resilient) — it never originates or
sizes a trade itself, so degrading to cache/static on an outage is the
correct, safe default, matching fetch_resilient's own documented intent.
"""
from __future__ import annotations

import json
import math
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "correlation_cache.json"

DEFAULT_WINDOW_DAYS = 60
MIN_SAMPLE_DAYS = 20          # below this, computed corr is blended with the static fallback
DEFAULT_MAX_AGE_HOURS = 24


def _log_returns(closes) -> list:
    out = []
    prev = None
    for c in closes:
        if prev is not None and prev > 0 and c > 0:
            out.append(math.log(c / prev))
        prev = c
    return out


def _pearson(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return None
    a = a[-n:]
    b = b[-n:]
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    r = cov / ((va ** 0.5) * (vb ** 0.5))
    return max(-1.0, min(1.0, r))


def _daily_closes(symbol, settings, bars=3000):
    """Reuses the exact fetch + resample path the rest of the platform
    already relies on: engine.markets.fetch_resilient (read-only,
    fail-open-to-cache — the intended use per its own docstring) +
    engine.data_loader.resample. Returns a pandas Series of daily closes,
    or None on total failure (no live source AND no cache)."""
    try:
        from . import markets
        from .data_loader import resample
        df = markets.fetch_resilient(symbol, settings, bars=bars)
        daily = resample(df, "1d")
        return daily["Close"].dropna()
    except Exception:  # noqa: BLE001
        return None


def _static_fallback(symbol_a, symbol_b) -> float:
    """Crude sign-only estimate from engine.correlation.USD_SENSITIVITY,
    used ONLY when live data for the pair is unavailable. Same-sign USD
    sensitivity -> loosely positive (~0.4); opposite sign -> loosely
    negative (~-0.4); either symbol missing from the table -> 0.0 (no
    assumed relationship — the conservative choice when we have no basis
    for one)."""
    from . import correlation as co
    sa = co.USD_SENSITIVITY.get(symbol_a)
    sb = co.USD_SENSITIVITY.get(symbol_b)
    if sa is None or sb is None:
        return 0.0
    same_sign = (sa > 0) == (sb > 0)
    return 0.4 if same_sign else -0.4


def compute_pair(symbol_a, symbol_b, settings, window_days=DEFAULT_WINDOW_DAYS) -> dict:
    """Compute one pair's rolling correlation. Returns
    {corr, n, sample, method}. Never raises."""
    if symbol_a == symbol_b:
        return {"corr": 1.0, "n": None, "sample": "trivial", "method": "identity"}
    try:
        ca = _daily_closes(symbol_a, settings)
        cb = _daily_closes(symbol_b, settings)
        if ca is None or cb is None:
            return {"corr": _static_fallback(symbol_a, symbol_b), "n": 0,
                    "sample": "no_data", "method": "static_fallback"}
        import pandas as pd
        joined = pd.concat([ca, cb], axis=1, join="inner").tail(window_days + 1)
        ra = _log_returns(list(joined.iloc[:, 0]))
        rb = _log_returns(list(joined.iloc[:, 1]))
        n = min(len(ra), len(rb))
        r = _pearson(ra, rb)
        if r is None:
            return {"corr": _static_fallback(symbol_a, symbol_b), "n": n,
                    "sample": "degenerate", "method": "static_fallback"}
        sample = "ok" if n >= MIN_SAMPLE_DAYS else "insufficient"
        if sample == "insufficient":
            fb = _static_fallback(symbol_a, symbol_b)
            r = (r + fb) / 2.0
        return {"corr": round(r, 4), "n": n, "sample": sample, "method": "rolling_pearson"}
    except Exception as exc:  # noqa: BLE001
        return {"corr": _static_fallback(symbol_a, symbol_b), "n": 0,
                "sample": f"error: {exc}", "method": "static_fallback"}


def refresh(settings, symbols=None, window_days=None) -> dict:
    """Recompute the full pairwise matrix and cache it to disk. Fail-open:
    any single pair's failure degrades to its own static fallback (see
    compute_pair) rather than aborting the whole refresh."""
    from . import markets
    window_days = window_days or int(getattr(settings, "correlation_window_days",
                                              DEFAULT_WINDOW_DAYS) or DEFAULT_WINDOW_DAYS)
    syms = symbols or markets.symbols(settings)
    matrix = {}
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            matrix[f"{a}|{b}"] = compute_pair(a, b, settings, window_days)
    payload = {"asof": date.today().isoformat(),
               "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "window_days": window_days, "matrix": matrix}
    try:
        CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return payload


def read_cache(max_age_hours=DEFAULT_MAX_AGE_HOURS):
    try:
        payload = json.loads(CACHE_PATH.read_text())
        gen = datetime.fromisoformat(payload["generated"])
        age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600.0
        if age_h > max_age_hours:
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None


def get_correlation(symbol_a, symbol_b, settings=None,
                    max_age_hours=DEFAULT_MAX_AGE_HOURS) -> dict:
    """Main entry point. Returns {corr, n, sample, method, source}.
    Tries the disk cache first (fast, no network); refreshes on a cache
    miss/stale cache; falls back to the static USD_SENSITIVITY estimate if
    the live refresh itself fails. Never raises — this is read directly
    inside the live alert-publication path (portfolio_risk.py), which must
    never be broken by a correlation-service outage."""
    if symbol_a == symbol_b:
        return {"corr": 1.0, "n": None, "sample": "trivial",
                "method": "identity", "source": "identity"}
    key, key_rev = f"{symbol_a}|{symbol_b}", f"{symbol_b}|{symbol_a}"
    cache = read_cache(max_age_hours)
    if cache:
        hit = cache["matrix"].get(key) or cache["matrix"].get(key_rev)
        if hit:
            hit = dict(hit)
            hit["source"] = "cache"
            return hit
    try:
        if settings is None:
            from . import config
            settings = config.load()
        payload = refresh(settings, symbols=[symbol_a, symbol_b])
        hit = payload["matrix"].get(key) or payload["matrix"].get(key_rev)
        if hit:
            hit = dict(hit)
            hit["source"] = "fresh"
            return hit
    except Exception:  # noqa: BLE001
        pass
    return {"corr": _static_fallback(symbol_a, symbol_b), "n": 0,
            "sample": "unavailable", "method": "static_fallback", "source": "fallback"}


def line(symbol_a, symbol_b, result) -> str:
    tag = {"insufficient": " (thin sample)", "no_data": " (no data - static est.)",
           "unavailable": " (unavailable - static est.)",
           "degenerate": " (flat data - static est.)"}.get(result.get("sample"), "")
    return f"{symbol_a}/{symbol_b} corr {result['corr']:+.2f}{tag}"


if __name__ == "__main__":
    from . import config as _config
    s = _config.load()
    out = refresh(s)
    print(f"correlation_cache.json updated: {len(out['matrix'])} pairs, "
          f"window {out['window_days']}d")
    for k, v in out["matrix"].items():
        a, b = k.split("|")
        print(" ", line(a, b, v))
