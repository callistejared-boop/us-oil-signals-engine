"""Structured run ledger — append-only JSONL observability trail.

Institutional systems need a decision audit trail: every signal, with its
regime, confidence, calibrated probability, macro read, and action, in a machine-
readable log you can analyze later. Append-only, self-rotating, and fail-safe —
a logging error must never disrupt trading logic.
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "run_ledger.jsonl"
MAX_LINES = 5000


def log(event: dict) -> None:
    try:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **(event or {})}
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass


def _rotate() -> None:
    try:
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            LEDGER.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def tail(n: int = 20) -> list:
    try:
        lines = LEDGER.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []
