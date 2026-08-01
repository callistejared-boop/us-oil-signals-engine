"""Walk-forward validation — the anti-overfitting harness.

Every proposed probability model is judged ONLY on trades it never saw: we walk
the journal in time order, train on the past, predict the next trade, and score
the out-of-sample (OOS) error. This prevents fitting noise on a small sample.

We compare three probability models OOS by Brier score (lower = better):
  - RAW        : the engine's confidence/100 (what it currently claims)
  - BASE-RATE  : just the historical win rate (the null model - no skill)
  - CALIBRATED : confidence mapped to its empirically-observed win rate

If CALIBRATED beats RAW, the raw score is overconfident and should be replaced.
If neither beats BASE-RATE, the score carries no ranking edge and must NOT drive
sizing - size by fixed-fractional risk instead. Pure, testable, honest.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import store, calibration as cal  # noqa: E402


def _outcome(r):
    return 1.0 if r.get("status") == "win" else 0.0


def _ordered_closed(closed=None):
    if closed is None:
        rows = store.load_array(ROOT / "trades.json")
        closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]
    return sorted(closed, key=lambda r: str(r.get("opened", "")))


def raw_model(trade, train):
    return int(trade.get("confidence", 0)) / 100.0


def base_model(trade, train):
    return (sum(_outcome(t) for t in train) / len(train)) if train else 0.5


def calibrated_model(trade, train):
    cmap = cal.calibrated_map(train, min_n=5)
    return cal.calibrated_probability(trade.get("confidence", 0), cmap, min_n=5)


def rolling_brier(closed, prob_fn, min_train=30):
    seq = _ordered_closed(closed)
    errs = []
    for i in range(min_train, len(seq)):
        p = max(0.0, min(1.0, prob_fn(seq[i], seq[:i])))
        errs.append((p - _outcome(seq[i])) ** 2)
    return (round(sum(errs) / len(errs), 4) if errs else None, len(errs))


def compare(closed=None, min_train=30):
    seq = _ordered_closed(closed)
    out = {}
    for name, fn in (("raw", raw_model), ("base_rate", base_model), ("calibrated", calibrated_model)):
        b, n = rolling_brier(seq, fn, min_train)
        out[name] = {"oos_brier": b, "n_oos": n}
    return out


def report(closed=None, min_train=30):
    c = compare(closed, min_train)
    lines = [f"WALK-FORWARD VALIDATION (out-of-sample, min_train={min_train})",
             f"tested on {c['raw']['n_oos']} out-of-sample trades  (lower Brier = better)"]
    for name in ("raw", "base_rate", "calibrated"):
        lines.append(f"  {name:11s} OOS Brier: {c[name]['oos_brier']}")
    raw, base, calib = c["raw"]["oos_brier"], c["base_rate"]["oos_brier"], c["calibrated"]["oos_brier"]
    if None in (raw, base, calib):
        lines.append("VERDICT: not enough OOS trades yet - keep collecting.")
    elif calib < raw - 0.01:
        verdict = "CALIBRATED beats RAW -> stop using raw confidence as probability; adopt calibrated."
        if calib > base - 0.01:
            verdict += " It matches base-rate, so confidence carries NO ranking edge: do NOT size by it - use fixed-fractional risk."
        lines.append("VERDICT: " + verdict)
    elif raw <= base:
        lines.append("VERDICT: raw already competitive - keep, but keep monitoring.")
    else:
        lines.append("VERDICT: base-rate wins - the score has no OOS skill; size by fixed risk, not confidence.")
    lines.append("Research/education only - not financial advice.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
