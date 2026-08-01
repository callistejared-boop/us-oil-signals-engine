"""Resilient JSON-array loader shared by every trade-data consumer.

A truncated/corrupt read (partial write, sync glitch) must never crash a
dashboard or, worse, be mistaken for an empty history. This salvages a
truncated JSON array of objects back to its last complete record. Stdlib-only,
so lightweight readers (self-review, dashboards) don't need pandas.
"""
import json
import pathlib


def salvage(text):
    """Recover a truncated JSON array of objects; drop only a partial tail."""
    depth = in_str = esc = 0
    last_close = -1
    for i, ch in enumerate(text):
        if esc:
            esc = 0
            continue
        if in_str:
            if ch == "\\":
                esc = 1
            elif ch == '"':
                in_str = 0
            continue
        if ch == '"':
            in_str = 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_close = i
    if last_close < 0:
        return []
    candidate = text[:last_close + 1].rstrip()
    if not candidate.endswith("]"):
        candidate += "]"
    try:
        rows = json.loads(candidate)
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def load_array(path):
    """Load a JSON array from path, salvaging on corruption. Never raises."""
    p = pathlib.Path(path)
    if not p.exists():
        return []
    try:
        text = p.read_text()
    except Exception:  # noqa: BLE001
        return []
    try:
        rows = json.loads(text)
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return salvage(text)
