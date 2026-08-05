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


# --- Day 9: generalized expanding-window walk-forward ------------------------
# The functions above (raw_model/base_model/calibrated_model/compare/report)
# are scoped specifically to comparing PROBABILITY models by Brier score —
# built Day 1-2, unchanged and untouched this Day (per the Day 9 mandate:
# "Identify areas for future improvement without changing validated behavior
# unless justified"). The function below GENERALIZES the same walk-forward
# METHODOLOGY (expanding window: train on everything before trade i, evaluate
# on trade i, never look ahead) to ANY metric function, so a future
# experiment (e.g. a new strategy's own expectancy walk-forward) can reuse
# this file's proven look-ahead-safe iteration rather than reimplementing it.
#
# METHODOLOGY NOTE (documented per the mandate's "specify rolling windows,
# evaluation metrics, recalibration policy, reporting standards" requirement
# — see RESEARCH_VALIDATION_SPECIFICATION.md Sec.4 for the full narrative):
# this is an EXPANDING window (train set grows from `min_train` to i-1 for
# each evaluated trade i), not a fixed-size ROLLING window — consistent with
# `compare()`/`rolling_brier()` above, which already use this same
# expanding-window shape. A fixed-size rolling window (e.g. always the last
# 200 trades) is a legitimate alternative methodology NOT implemented here;
# `window_size=None` (default) means expanding, an explicit `window_size=N`
# truncates the train set to the last N trades before i, giving a true
# rolling window when a future experiment wants recency-weighting instead of
# ever-growing history.

def expanding_window_series(metric_fn, closed=None, min_train=30, window_size=None) -> list:
    """Walk the journal in time order (same `_ordered_closed()` this file's
    existing functions use) and, for each trade i beyond `min_train`, call
    `metric_fn(train)` where `train` is every closed trade STRICTLY before i
    (or, if `window_size` is set, only the last `window_size` of them) —
    never including trade i itself or anything after it. Returns a list of
    `{"i": index, "opened": ts, "value": metric_fn(train)}` — an OOS metric
    TIME SERIES, not a single number, so callers (e.g.
    `engine.edge_decay_monitor`) can detect a metric declining over time,
    not just its current level. Never raises; a `metric_fn` error at one
    point is recorded as `"value": None, "error": ...` rather than aborting
    the whole series."""
    seq = _ordered_closed(closed)
    out = []
    for i in range(min_train, len(seq)):
        train = seq[max(0, i - window_size):i] if window_size else seq[:i]
        try:
            value = metric_fn(train)
        except Exception as exc:  # noqa: BLE001
            value = None
            out.append({"i": i, "opened": seq[i].get("opened", ""), "value": value,
                       "error": str(exc)})
            continue
        out.append({"i": i, "opened": seq[i].get("opened", ""), "value": value})
    return out


if __name__ == "__main__":
    print(report())
