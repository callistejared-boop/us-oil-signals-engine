"""Two-stage setup lifecycle.

A confirmed setup's entry is a limit at an FVG level price has NOT reached
yet. So the moment it forms we announce it ("watching for entry at X, here's
why"), then on later scans we watch for price to tap that level and fire the
actual entry. This removes the 'signal arrives 15 min late' problem: you get
the heads-up first, the trigger second.

State persists in pending.json.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace

import pandas as pd

STORE = pathlib.Path(__file__).resolve().parent.parent / "pending.json"
TOL = 0.0015
MAX_WAIT_BARS = 96          # drop a pending setup if not tapped within ~1 day


@dataclass
class Pending:
    id: str
    symbol: str
    created: str
    direction: str
    entry: float
    stop: float
    target: float
    rr: float
    confidence: int
    prob: int
    reasons: list = field(default_factory=list)
    invalidation: str = ""


def _load() -> list:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(rows: list) -> None:
    STORE.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def exists(sig) -> bool:
    """Already watching an equivalent setup on this symbol?"""
    sym = getattr(sig, "symbol", "XAUUSD")
    for r in _load():
        if r["symbol"] == sym and r["direction"] == sig.direction \
           and abs(r["entry"] - sig.entry) <= max(abs(sig.entry) * TOL, 1e-9):
            return True
    return False


def add(sig, when: pd.Timestamp) -> bool:
    if exists(sig):
        return False
    sym = getattr(sig, "symbol", "XAUUSD")
    rows = _load()
    rows.append(asdict(Pending(
        id=f"{sym}-{str(when).replace(' ', 'T')}", symbol=sym, created=str(when),
        direction=sig.direction, entry=float(sig.entry), stop=float(sig.stop),
        target=float(sig.target), rr=float(sig.rr), confidence=int(sig.confidence),
        prob=int(getattr(sig, "prob", 0)), reasons=list(sig.reasons),
        invalidation=sig.invalidation)))
    _save(rows)
    return True


def update(symbol: str, df: pd.DataFrame) -> list:
    """Advance pending setups for `symbol` against fresh price.

    Returns a list of (event, pending_dict) where event is 'entry'
    (price tapped the level) or 'void' (aged out / stop hit first)."""
    rows = _load()
    events, keep = [], []
    for r in rows:
        if r["symbol"] != symbol:
            keep.append(r)
            continue
        seg = df.loc[df.index > pd.Timestamp(r["created"])]
        if seg.empty:
            keep.append(r)
            continue
        hi, lo = seg["High"].values, seg["Low"].values
        # entry is a limit price hasn't reached; a tap = price reaches it.
        # (For a long the stop is below entry, so price always taps entry
        #  first — there is no 'stop before entry'. If the same bar also
        #  reaches the stop, the journal settles it as a loss.)
        tapped = voided = False
        for j in range(len(seg)):
            if r["direction"] == "long":
                if lo[j] <= r["entry"]:
                    tapped = True; break
            else:
                if hi[j] >= r["entry"]:
                    tapped = True; break
        if not tapped and len(seg) >= MAX_WAIT_BARS:
            voided = True   # never filled within the window
        if tapped:
            events.append(("entry", r))
        elif voided:
            events.append(("void", r))
        else:
            keep.append(r)
    _save(keep)
    return events


def as_signal(r: dict):
    """Rebuild a signal-like object from a pending record (for the journal)."""
    return SimpleNamespace(
        symbol=r["symbol"], direction=r["direction"], entry=r["entry"],
        stop=r["stop"], target=r["target"], rr=r["rr"],
        confidence=r["confidence"], prob=r.get("prob", 0),
        reasons=r.get("reasons", []), invalidation=r.get("invalidation", ""))
