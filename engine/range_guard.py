"""Range-extension / dollar-headwind guard — stop the engine chasing.

The failure mode this fixes: the engine prints a high-grade LONG while price
is pinned to the TOP of an established dealing range (premium), in a RANGE
regime, while the US dollar is trending up. That is not a high-probability
trade — it is a chase into resistance against a macro headwind. (Shorts are
the mirror: a SHORT into the range LOW / discount with the dollar falling.)

Design principles (deliberately conservative, anti-overfit):

  * REGIME-AWARE, not blind. A premium long is only a *chase* inside a range.
    In a confirmed trend (or a real volatility expansion / breakout) the same
    premium long is *continuation* and must NOT be penalised. So the guard's
    weight is scaled down to zero when structure says "trend", and halved on a
    fresh expansion. This is the single most important guard against it
    strangling legitimate momentum trades.

  * DOWNGRADE by default, SUPPRESS only when explicitly enabled. We do not yet
    have out-of-sample proof that guard-flagged trades lose. Until the journal
    proves it (self_review joins guard_action to realised R), the guard caps
    the grade and cuts suggested size but still lets the trade through, so we
    keep collecting the data needed to validate it. Flip SUPPRESS_MODE = True
    only after the evidence is in.

  * FAIL-SAFE. Any bad/missing input degrades to "allow" (no effect). It can
    never crash a live scan.

Pure function — no I/O, no network — so it is trivially unit-testable.
"""
from __future__ import annotations

# --- tunables (kept explicit so changes are deliberate and auditable) --------
PREMIUM_FLOOR = 0.60     # range position where "premium/discount" begins
BREAKOUT_POS = 1.05      # beyond the range edge = breakout, NOT a chase → allow
EXTREME_SEV = 0.85       # effective severity that qualifies as an extreme chase
MAX_PENALTY = 15         # hard floor on confidence points removed
SUPPRESS_MODE = False    # False = downgrade+flag only (validate before trusting)

# Covers both the legacy confidence-only grades (A+/A/B) and the MAST
# confluence-score grades (A+/A/B+/B/C+/C/NO TRADE) — cap_grade is used with
# whichever scheme the caller passes, so both must rank sensibly together.
_GRADE_RANK = {"A+": 7, "A": 6, "B+": 5, "B": 4, "C+": 3, "C": 2, "NO TRADE": 0}


def _rank(grade: str) -> int:
    return _GRADE_RANK.get(str(grade).strip(), 1)  # unrecognized → 1 (near-lowest)


def cap_grade(grade: str, cap: str | None) -> str:
    """Return the MORE conservative of the engine grade and the guard's cap."""
    if not cap:
        return grade
    return grade if _rank(grade) <= _rank(cap) else cap


def _position_severity(direction: str, pos: float) -> tuple[float, str]:
    """How far price is into the adverse end of the range, 0..1.

    long  → adverse end is the range HIGH (premium).
    short → adverse end is the range LOW (discount).
    A clean breakout beyond the edge (pos>BREAKOUT_POS / <-.05) is momentum,
    not a chase, so severity collapses to 0.
    """
    span = 1.0 - PREMIUM_FLOOR
    if direction == "long":
        if pos > BREAKOUT_POS:
            return 0.0, "breakout above range (momentum)"
        sev = (min(pos, 1.0) - PREMIUM_FLOOR) / span
        return max(0.0, min(1.0, sev)), "range-high (premium)"
    if direction == "short":
        if pos < (1.0 - BREAKOUT_POS):
            return 0.0, "breakdown below range (momentum)"
        # mirror of the long case: discount severity grows as pos → 0.
        # discount band is [0, 1-PREMIUM_FLOOR]; sev = 1 at pos 0, 0 at the band top.
        discount_top = 1.0 - PREMIUM_FLOOR
        sev = (discount_top - min(max(pos, 0.0), discount_top)) / span
        return max(0.0, min(1.0, sev)), "range-low (discount)"
    return 0.0, "no direction"


def _regime_factor(regime: dict | None) -> tuple[float, str]:
    """Scale the chase penalty by structure. Trend → 0 (continuation, allow)."""
    reg = regime or {}
    trend = str(reg.get("trend", "")).lower()
    vol = str(reg.get("vol", "")).lower()
    phase = str(reg.get("phase", "")).lower()
    if trend == "trend":
        return 0.0, "confirmed trend → continuation, guard stands down"
    if vol == "expansion":
        rf, why = 0.5, "volatility expansion → possible breakout, half weight"
    else:
        rf, why = 1.0, "range regime → full chase weight"
    if "distribution" in phase:
        rf *= 1.15
        why += " + distribution phase"
    return rf, why


def evaluate(symbol, direction, range_pos, dxy_trend, regime=None,
             macro_aligned=None):
    """Assess whether a signal is a range-extreme chase into a macro headwind.

    Parameters
    ----------
    symbol, direction : the trade ("long"/"short").
    range_pos : ICT range position (0=low, 1=high; can exceed on breakouts).
    dxy_trend : "up" | "down" | "flat" | None (short-term dollar trend).
    regime    : regime.classify(...) dict (trend/vol/phase).
    macro_aligned : optional pre-computed correlation.macro_alignment result
                    (dict with "aligned"); if None, computed from dxy_trend.

    Returns a verdict dict (see module docstring). Fail-safe → allow.
    """
    allow = {"action": "allow", "penalty": 0, "grade_cap": None,
             "size_factor": 1.0, "severity": 0.0, "raw_ext": 0.0,
             "macro_headwind": False, "regime_factor": 0.0,
             "reasons": ["not a range-extreme chase"],
             "note": "clear — no range-extreme / dollar-headwind flag"}
    try:
        if range_pos is None or direction not in ("long", "short"):
            return allow

        raw, pos_label = _position_severity(direction, float(range_pos))
        rf, rf_why = _regime_factor(regime)
        sev_eff = max(0.0, min(1.2, raw * rf))

        # macro headwind: is the trade fighting the dollar?
        headwind = False
        macro_why = ""
        try:
            if macro_aligned is None:
                from engine import correlation as _co
                macro_aligned = _co.macro_alignment(symbol, direction, dxy_trend)
            aligned = (macro_aligned or {}).get("aligned")
            headwind = aligned is False
            macro_why = (macro_aligned or {}).get("note", "")
        except Exception:  # noqa: BLE001
            headwind = False

        base_pen = round(sev_eff * 12)
        macro_pen = round(raw * 4) if (headwind and sev_eff > 0.05) else 0
        p = min(base_pen + macro_pen, MAX_PENALTY)

        if p <= 0:
            v = dict(allow)
            v["reasons"] = [f"{pos_label}; {rf_why}"]
            if rf == 0.0 and raw > 0:
                v["note"] = "premium but structure = continuation — allowed"
            return v

        cap = "A" if p <= 5 else "B" if p <= 10 else "C (chase)"
        sf = 0.75 if p <= 5 else 0.5 if p <= 10 else 0.35

        suppress = (sev_eff >= EXTREME_SEV and rf >= 1.0 and headwind
                    and SUPPRESS_MODE)
        action = "suppress" if suppress else "downgrade"
        if suppress:
            sf = 0.0

        reasons = [f"{direction.upper()} into {pos_label} (pos {float(range_pos):.2f})",
                   rf_why]
        if headwind:
            reasons.append("fighting the dollar" + (f": {macro_why}" if macro_why else ""))

        verb = "SKIP" if suppress else "downgrade"
        note = (f"{verb}: {direction} chasing {pos_label} in a range"
                + (" against a rising/adverse dollar" if headwind else "")
                + f" → grade capped {cap}, size x{sf:.2f}")

        return {"action": action, "penalty": -p, "grade_cap": cap,
                "size_factor": sf, "severity": round(sev_eff, 3),
                "raw_ext": round(raw, 3), "macro_headwind": headwind,
                "regime_factor": rf, "reasons": reasons, "note": note}
    except Exception:  # noqa: BLE001
        return allow


def line(verdict: dict) -> str:
    """One-line display string for notes/alerts."""
    if not verdict or verdict.get("action") == "allow":
        return "RANGE GUARD: clear (not a range-extreme chase)"
    tag = "SKIP" if verdict["action"] == "suppress" else "DOWNGRADE"
    return (f"RANGE GUARD [{tag}]: {verdict['note']} | "
            f"conf {verdict['penalty']:+d}")
