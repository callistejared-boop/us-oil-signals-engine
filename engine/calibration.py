"""Confidence calibration — is the engine's probability score honest?

The prompt's rule: every probability must be measurable, testable, and calibrated
against realized performance. This reads the live journal and compares the
PREDICTED probability (the engine's confidence /100) to the REALIZED win rate,
per confidence bucket. It reports a reliability table, the Brier score (lower =
better-calibrated), and an empirical calibrated-probability map you can trust
once each bucket has enough trades. Transparent; never fabricates certainty.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import store  # noqa: E402

BUCKETS = [("<70", 0, 70, 65), ("70-79", 70, 80, 75),
           ("80-89", 80, 90, 85), ("90-100", 90, 101, 95)]


def _closed():
    rows = store.load_array(ROOT / "trades.json")
    return [r for r in rows if r.get("status") in ("win", "loss", "scratch")]


def _outcome(r):
    return 1.0 if r.get("status") == "win" else 0.0


def reliability(closed=None):
    closed = _closed() if closed is None else closed
    out = []
    for name, lo, hi, mid in BUCKETS:
        grp = [r for r in closed if lo <= int(r.get("confidence", 0)) < hi]
        n = len(grp)
        if not n:
            continue
        wr = sum(_outcome(r) for r in grp) / n
        out.append({"bucket": name, "predicted": mid / 100.0, "realized": round(wr, 3),
                    "n": n, "gap": round(wr - mid / 100.0, 3)})
    return out


def brier(closed=None):
    closed = _closed() if closed is None else closed
    if not closed:
        return None
    s = sum((int(r.get("confidence", 0)) / 100.0 - _outcome(r)) ** 2 for r in closed)
    return round(s / len(closed), 4)


def calibrated_map(closed=None, min_n=8):
    """Empirical win rate per bucket where n>=min_n (else None => trust raw)."""
    return {b["bucket"]: b["realized"] for b in reliability(closed) if b["n"] >= min_n}


def calibrated_probability(confidence, cmap=None, min_n=8):
    """Map a raw confidence to the empirically-observed win rate for its bucket.
    Falls back to raw/100 when there isn't enough history to be trustworthy."""
    cmap = calibrated_map(min_n=min_n) if cmap is None else cmap
    c = int(confidence or 0)
    for name, lo, hi, _ in BUCKETS:
        if lo <= c < hi:
            return cmap.get(name, c / 100.0)
    return c / 100.0


def report():
    closed = _closed()
    rel = reliability(closed)
    b = brier(closed)
    lines = [f"CONFIDENCE CALIBRATION ({len(closed)} closed trades)",
             f"Brier score: {b}  (0=perfect, lower is better; 0.25 = coin flip)"]
    lines.append("bucket   predicted  realized   n   gap")
    for r in rel:
        flag = "" if r["n"] >= 8 else "  (thin - not yet trustworthy)"
        lines.append(f"{r['bucket']:7s}  {r['predicted']*100:5.0f}%    {r['realized']*100:5.0f}%   "
                     f"{r['n']:2d}  {r['gap']*100:+4.0f}pt{flag}")
    if rel:
        worst = max(rel, key=lambda x: abs(x["gap"]))
        if abs(worst["gap"]) > 0.15 and worst["n"] >= 8:
            lines.append(f"NOTE: '{worst['bucket']}' is mis-calibrated by {worst['gap']*100:+.0f}pt "
                         "- use the calibrated map, not the raw score, when sizing.")
        else:
            lines.append("NOTE: calibration within noise for the current sample - keep collecting.")
    lines.append("Research/education only - not financial advice.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
