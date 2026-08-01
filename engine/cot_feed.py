"""COT (Commitment of Traders) positioning — what real money is actually doing.

The CFTC publishes weekly futures positioning every Friday (data as of the
prior Tuesday), free, no key required. This is the one dataset large funds
genuinely watch: non-commercial (speculative) net positioning at a percentile
extreme has historically preceded reversals — a contrarian signal derived
from real capital commitments, not price action.

Source: CFTC public Socrata API, Legacy Futures Only report.
https://publicreporting.cftc.gov/resource/6dca-aqww.json

Multi-symbol (2026-07-28): generalized from WTI-only to also cover gold and
Bitcoin. Market names verified live against the CFTC API before adding them
(same discipline as the original WTI rename note below) — each is the
current, actively-reporting primary futures contract for that instrument,
not a guess:

  * WTIUSD: "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE" (~1.9M contracts OI)
  * XAUUSD: "GOLD - COMMODITY EXCHANGE INC." (COMEX gold, ~383K contracts OI)
  * BTCUSD: "BITCOIN - CHICAGO MERCANTILE EXCHANGE" (CME Bitcoin, ~20.5K
    contracts OI as of 2026-07-21 — genuinely thinner than gold/oil, so
    percentile extremes here are noisier; treat with proportionally less
    weight than the same signal on gold or oil)

NOTE (kept from the original WTI-only version): NYMEX retired the old
market name "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE" after
the 2022-02-01 report. The primary WTI futures contract now reports under
"WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE". If CFTC renames a market
again in the future, `MARKETS` below is the single place to fix it.

Fail-safe throughout: no network / bad response -> None, degrades cleanly.
Weekly data, so cached aggressively (COT only updates once a week). Cache
is one JSON file keyed by symbol (mirrors engine/fundamentals_feed.py's
pattern) so refreshing one symbol never touches another's cached read.
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "cot_cache.json"
URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
EXTREME_HI, EXTREME_LO = 0.85, 0.15   # percentile thresholds for "extreme"

MARKETS = {
    "WTIUSD": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
    "XAUUSD": "GOLD - COMMODITY EXCHANGE INC.",
    "BTCUSD": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
}
# Backward-compatible alias — some older code/tests may still reference the
# single-market WTI constant directly.
MARKET = MARKETS["WTIUSD"]


def fetch(symbol: str = "WTIUSD", weeks: int = 52, timeout: int = 20):
    """Latest `weeks` of speculative net positioning for `symbol`. Returns
    list of {date, spec_net, open_interest} newest-first, or None on
    failure (unknown symbol, no network, empty response)."""
    market = MARKETS.get(symbol)
    if not market:
        return None
    try:
        params = {
            "$where": f"market_and_exchange_names='{market}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": str(weeks),
        }
        url = URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=timeout) as r:
            rows = json.load(r)
        if not rows:
            return None
        out = []
        for row in rows:
            try:
                long_ = float(row.get("noncomm_positions_long_all", 0) or 0)
                short_ = float(row.get("noncomm_positions_short_all", 0) or 0)
                oi = float(row.get("open_interest_all", 0) or 0)
                out.append({"date": row.get("report_date_as_yyyy_mm_dd", "")[:10],
                           "spec_net": long_ - short_, "open_interest": oi})
            except (TypeError, ValueError):
                continue
        return out or None
    except Exception:  # noqa: BLE001
        return None


def percentile_rank(values, x) -> float:
    if not values:
        return 0.5
    return sum(1 for v in values if v <= x) / len(values)


def _load_cache() -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {}
    # Migrate the old single-symbol flat format ({"asof": ..., "spec_net":
    # ...}) into the new per-symbol format, treating it as WTIUSD's entry —
    # preserves any existing cached read instead of silently discarding it.
    if "asof" in data and "spec_net" in data:
        return {"WTIUSD": data}
    return data


def refresh(symbol: str = "WTIUSD"):
    rows = fetch(symbol)
    if not rows:
        return None
    nets = [r["spec_net"] for r in rows]
    cur = nets[0]
    pctl = percentile_rank(list(reversed(nets)), cur)  # rank within trailing history
    out = {"asof": rows[0]["date"], "spec_net": cur, "percentile": round(pctl, 2),
          "open_interest": rows[0]["open_interest"],
          "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        cache = _load_cache()
        cache[symbol] = out
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return out


def read_cached(symbol: str = "WTIUSD", max_age_days: int = 10):
    """COT updates weekly; allow up to 10 days before calling it stale."""
    try:
        cache = _load_cache()
        d = cache.get(symbol)
        if d is None:
            return None
        gen = datetime.fromisoformat(d["generated"])
        if (datetime.now(timezone.utc) - gen).days > max_age_days:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


def read(symbol: str = "WTIUSD", refresh_if_missing=True):
    d = read_cached(symbol)
    if d is None and refresh_if_missing:
        d = refresh(symbol)
    return d


def alignment(direction: str, symbol: str = "WTIUSD", d=None):
    """Does current speculative positioning support or warn against `direction`?
    Returns {supports: True/False/None, extreme: bool, note}."""
    d = d if d is not None else read(symbol)
    if not d:
        return {"supports": None, "extreme": False,
                "note": "COT: no data (needs network / CFTC unavailable)"}
    pctl = d["percentile"]
    extreme_long = pctl >= EXTREME_HI
    extreme_short = pctl <= EXTREME_LO
    if extreme_long and direction == "long":
        return {"supports": False, "extreme": True,
                "note": f"COT WARNING: spec net long at {pctl:.0%} percentile "
                        "(crowded long) — contrarian caution on fresh longs"}
    if extreme_short and direction == "short":
        return {"supports": False, "extreme": True,
                "note": f"COT WARNING: spec net short at {pctl:.0%} percentile "
                        "(crowded short) — contrarian caution on fresh shorts"}
    if extreme_short and direction == "long":
        return {"supports": True, "extreme": True,
                "note": f"COT: spec positioning near {pctl:.0%} percentile "
                        "(crowded short) — contrarian tailwind for longs"}
    if extreme_long and direction == "short":
        return {"supports": True, "extreme": True,
                "note": f"COT: spec positioning near {pctl:.0%} percentile "
                        "(crowded long) — contrarian tailwind for shorts"}
    return {"supports": None, "extreme": False,
            "note": f"COT: spec net positioning at {pctl:.0%} percentile "
                    "(no crowding extreme)"}


def note(symbol: str = "WTIUSD"):
    d = read(symbol)
    if not d:
        return f"COT ({symbol}): unavailable (no network / CFTC feed unreachable this run)"
    thin = " — thin OI, weight lightly" if symbol == "BTCUSD" else ""
    return (f"COT ({symbol}, as of {d['asof']}): spec net {d['spec_net']:+.0f} contracts, "
           f"{d['percentile']:.0%} percentile of trailing year{thin}")


if __name__ == "__main__":
    for sym in MARKETS:
        print(note(sym))
