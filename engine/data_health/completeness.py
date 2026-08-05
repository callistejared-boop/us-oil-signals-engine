"""Completeness checks — missing fields, incomplete responses, truncated
datasets, empty payloads, unavailable providers. Pure functions over
already-fetched data; no I/O, no network.

Severity scale (shared with consistency.py, same 4-tier convention every
other qualitative table in this codebase uses — low/medium/high plus a
disclosed floor, e.g. Day 6's confidence tiers, Day 11's event
categories):

- none     — nothing wrong
- minor    — cosmetic/optional fields missing; usable as-is
- major    — required fields missing or data materially truncated;
             usable with caution, should be flagged
- critical — empty/unusable payload; treat as unavailable
"""
from __future__ import annotations

NONE_ = "none"
MINOR = "minor"
MAJOR = "major"
CRITICAL = "critical"

SEVERITY_ORDER = {NONE_: 0, MINOR: 1, MAJOR: 2, CRITICAL: 3}


def check_dict(payload, required_fields=(), optional_fields=()) -> dict:
    """Checks a dict-shaped payload (the common provider-function return
    shape in this codebase) for missing required/optional fields.

    Never raises: a non-dict payload (None, exception object, etc.) is
    itself reported as CRITICAL/"payload is not a dict", not a crash."""
    try:
        if payload is None:
            return {"severity": CRITICAL, "missing_required": list(required_fields),
                     "missing_optional": list(optional_fields), "detail": "payload is None"}
        if not isinstance(payload, dict):
            return {"severity": CRITICAL, "missing_required": list(required_fields),
                     "missing_optional": list(optional_fields),
                     "detail": f"payload is not a dict (got {type(payload).__name__})"}
        if not payload:
            return {"severity": CRITICAL, "missing_required": list(required_fields),
                     "missing_optional": list(optional_fields), "detail": "payload is an empty dict"}

        missing_required = [f for f in required_fields if f not in payload or payload.get(f) is None]
        missing_optional = [f for f in optional_fields if f not in payload or payload.get(f) is None]

        if missing_required:
            severity = CRITICAL if len(missing_required) == len(required_fields) and required_fields else MAJOR
        elif missing_optional:
            severity = MINOR
        else:
            severity = NONE_

        return {"severity": severity, "missing_required": missing_required,
                "missing_optional": missing_optional, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "missing_required": list(required_fields),
                "missing_optional": list(optional_fields), "detail": f"completeness check error: {exc}"}


def check_dataframe(df, min_rows: int = 1, required_columns=()) -> dict:
    """Checks a pandas-DataFrame-shaped payload (the market-bars shape)
    for emptiness, truncation, and missing columns. Accepts df=None or a
    non-DataFrame gracefully."""
    try:
        if df is None:
            return {"severity": CRITICAL, "row_count": 0, "missing_columns": list(required_columns),
                     "detail": "dataframe is None"}
        n = len(df)
        missing_cols = [c for c in required_columns if c not in getattr(df, "columns", [])]
        if n == 0:
            return {"severity": CRITICAL, "row_count": 0, "missing_columns": missing_cols,
                     "detail": "empty payload (0 rows)"}
        if missing_cols:
            return {"severity": CRITICAL if len(missing_cols) == len(required_columns) else MAJOR,
                     "row_count": n, "missing_columns": missing_cols, "detail": "required column(s) absent"}
        if n < min_rows:
            return {"severity": MAJOR, "row_count": n, "missing_columns": [],
                     "detail": f"truncated: {n} rows < expected minimum {min_rows}"}
        return {"severity": NONE_, "row_count": n, "missing_columns": [], "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"severity": CRITICAL, "row_count": None, "missing_columns": list(required_columns),
                "detail": f"completeness check error: {exc}"}


def worst_severity(*severities) -> str:
    """Reduces multiple severity strings to the single worst one. Unknown
    strings are treated as CRITICAL (fail loud, not silent)."""
    worst = NONE_
    for s in severities:
        rank = SEVERITY_ORDER.get(s, SEVERITY_ORDER[CRITICAL])
        if rank > SEVERITY_ORDER[worst]:
            worst = s if s in SEVERITY_ORDER else CRITICAL
    return worst
