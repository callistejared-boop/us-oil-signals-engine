"""Consistency checks — duplicate timestamps, impossible prices, negative
volumes, invalid OHLC relationships, conflicting provider outputs,
inconsistent symbol metadata. Pure functions over already-fetched data;
no I/O, no network.

Uses the same severity scale as `completeness.py`
(none/minor/major/critical) so `provider_status.py` can combine both
checks' outputs with one shared `worst_severity()` reducer.
"""
from __future__ import annotations

from .completeness import NONE_, MINOR, MAJOR, CRITICAL, worst_severity  # noqa: F401


def check_ohlc(df) -> dict:
    """Validates OHLC relationships row-by-row: high >= low, high >= open,
    high >= close, low <= open, low <= close, and no negative/zero prices
    or negative volume. Returns counts, not row-level detail (the health
    report is operational, not a forensic dump)."""
    try:
        if df is None or len(df) == 0:
            return {"severity": NONE_, "checked_rows": 0, "violations": {}, "detail": "no rows to check"}
        cols = {c.lower(): c for c in df.columns}
        needed = ("open", "high", "low", "close")
        if not all(k in cols for k in needed):
            return {"severity": NONE_, "checked_rows": len(df), "violations": {},
                     "detail": "OHLC columns not present — not a price dataframe, skipped"}
        o, h, l, c = (df[cols[k]] for k in needed)
        violations = {
            "high_lt_low": int((h < l).sum()),
            "high_lt_open": int((h < o).sum()),
            "high_lt_close": int((h < c).sum()),
            "low_gt_open": int((l > o).sum()),
            "low_gt_close": int((l > c).sum()),
            "non_positive_price": int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum()),
        }
        if "volume" in cols:
            violations["negative_volume"] = int((df[cols["volume"]] < 0).sum())
        total = sum(violations.values())
        n = len(df)
        if total == 0:
            severity = NONE_
        elif total / max(n, 1) < 0.01:
            severity = MINOR
        elif total / max(n, 1) < 0.05:
            severity = MAJOR
        else:
            severity = CRITICAL
        return {"severity": severity, "checked_rows": n, "violations": violations, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "checked_rows": None, "violations": {}, "detail": f"consistency check error: {exc}"}


def check_duplicate_timestamps(df, ts_column: str = None) -> dict:
    """Detects duplicate index/timestamp entries — a common resampling or
    double-write artifact that can silently double-count a bar."""
    try:
        if df is None or len(df) == 0:
            return {"severity": NONE_, "duplicate_count": 0, "detail": "no rows to check"}
        if ts_column and ts_column in getattr(df, "columns", []):
            series = df[ts_column]
        else:
            series = df.index
        dup_count = int(len(series) - len(set(series)))
        if dup_count == 0:
            severity = NONE_
        elif dup_count / max(len(series), 1) < 0.01:
            severity = MINOR
        else:
            severity = MAJOR
        return {"severity": severity, "duplicate_count": dup_count, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "duplicate_count": None, "detail": f"consistency check error: {exc}"}


def check_conflicting_sources(values: dict, tolerance_pct: float = 5.0) -> dict:
    """Compares the same fact reported by multiple providers (e.g. two
    independent gold-price observations). `values` is {source_name: number}.
    Flags when the spread between max and min exceeds tolerance_pct of the
    mean. Fewer than 2 usable values -> NONE_ (nothing to conflict)."""
    try:
        usable = {k: v for k, v in (values or {}).items() if isinstance(v, (int, float))}
        if len(usable) < 2:
            return {"severity": NONE_, "sources_compared": len(usable), "spread_pct": None, "detail": None}
        lo, hi = min(usable.values()), max(usable.values())
        mean = sum(usable.values()) / len(usable)
        spread_pct = abs(hi - lo) / abs(mean) * 100 if mean else float("inf")
        if spread_pct <= tolerance_pct:
            severity = NONE_
        elif spread_pct <= tolerance_pct * 3:
            severity = MINOR
        elif spread_pct <= tolerance_pct * 6:
            severity = MAJOR
        else:
            severity = CRITICAL
        return {"severity": severity, "sources_compared": len(usable),
                "spread_pct": round(spread_pct, 2), "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "sources_compared": None, "spread_pct": None,
                 "detail": f"consistency check error: {exc}"}


def check_symbol_metadata(symbol: str, markets_table: dict) -> dict:
    """Confirms a symbol has a complete, non-conflicting entry in the
    platform's own MARKETS table (mult/label/dp all present)."""
    try:
        entry = (markets_table or {}).get(symbol)
        if entry is None:
            return {"severity": CRITICAL, "detail": f"'{symbol}' has no MARKETS entry"}
        missing = [k for k in ("mult", "label", "dp") if k not in entry or entry.get(k) is None]
        if missing:
            return {"severity": MAJOR, "detail": f"'{symbol}' MARKETS entry missing {missing}"}
        return {"severity": NONE_, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "detail": f"consistency check error: {exc}"}
