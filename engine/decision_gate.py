"""V2.2 Priority 2 — Master Decision Gate.

A single, named, independently-testable module giving the platform's
per-candidate gate sequence an explicit return contract:

    {ENTER, WAIT, HOLD, REJECT, BLOCKED, STAND_DOWN}

Scope and honesty about what this is (read before trusting this module
for anything): this WRAPS the existing, already-tested gate functions
(`risk_guard.evaluate()`, `portfolio_risk.evaluate()`,
`alert_signals.apply_regime_gate()`) and the existing rejection-category
vocabulary already unified in `explainability_engine.py`
(`REJECTION_CATEGORIES`) — it does not reimplement a single line of their
decision logic, and it does not change what any of them decide. It exists
to give the SAME sequence of decisions alert_signals.py already makes
inline a callable, testable, named surface, per
PHASE0_FORENSIC_AUDIT.md Section P/R ("Master Decision Gate... does not
exist [as a callable]... extract, wrapping existing calls, not rewriting
their logic").

Deliberately NOT wired into alert_signals.py's live control flow in this
landing. `alert_signals.py::main()` continues to make its own inline
decisions exactly as before — this module is not yet load-bearing in
production. Swapping the live pipeline over to call through here instead
of its own inline checks is a real, separate follow-up that needs its own
careful review (a live trading pipeline is not the place to land an
architecture change and a behavior-risk change in the same commit); this
module is the safe, test-proven first half of that work. See
TECHNICAL_DEBT_REGISTER.md / VERSION_2.2_ROADMAP.md for tracking.

Deliberately OUT OF SCOPE (do not extend this module to cover these
without a fresh, explicit design pass — they are not binary
gate/no-gate decisions and folding them in would misrepresent what a
"gate" is):
  - `_guard_for()` / range_guard's allow/downgrade/suppress verdict —
    this can downgrade a signal's confidence or suppress it, but it is
    not currently a hard `continue` point in either pipeline stage's
    control flow the way the gates below are. Wrapping it here would
    imply a binary pass/fail this module can't honestly claim.
  - Confidence Engine, Market Memory, Macro Engine, Execution Simulator,
    Paper Broker submission — all advisory-only by explicit design
    (see their own module docstrings); none of them can block a trade,
    so none of them belong in a BLOCK/REJECT/STAND_DOWN contract.

Two stages, two narrower gate sets — mirrors alert_signals.py exactly,
not a single merged pipeline (Stage-2 does not re-check regime/confluence
because Stage-1 already qualified them before the pending setup existed):

  Stage-1 (`evaluate_origination_gate`): news blackout -> risk_guard
  (per-symbol day-stop/position lock) -> regime gate (advisory by
  default, see `apply_regime_gate`) -> MAST confluence tier -> portfolio
  risk (five-gate sequence in `portfolio_risk.evaluate()`) -> WAIT.

  Stage-2 (`evaluate_entry_gate`): news blackout -> risk_guard ->
  portfolio risk -> ENTER.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import risk_guard
from . import portfolio_risk as pr
from . import explainability_engine as expl

# --- The six-action contract ------------------------------------------------
ENTER = "enter"            # Stage-2: fill approved, trade to be logged/published
WAIT = "wait"               # Stage-1: heads-up approved, watching for entry trigger
HOLD = "hold"               # a specific candidate is held (regime/confluence quality) —
                            # softer than REJECT: the setup may still qualify later on
                            # a fresh read, nothing about the symbol/account is locked
REJECT = "reject"           # portfolio_risk rejected this specific candidate
                            # (exposure/correlation/session/confidence/etc.)
BLOCKED = "blocked"         # account/symbol-wide condition that pre-empts evaluating
                            # ANY candidate at all (news blackout, risk_guard lock) —
                            # matches PHASE0_FORENSIC_AUDIT.md's "account-level gates
                            # that run before any specific opportunity exists"
STAND_DOWN = "stand_down"   # portfolio-wide protective stand-down specifically
                            # (drawdown protection / trade-frequency control) —
                            # a REJECT category that represents the platform pulling
                            # back generally, not a per-candidate risk judgment

ACTIONS = {ENTER, WAIT, HOLD, REJECT, BLOCKED, STAND_DOWN}

# Which of portfolio_risk's existing rejection categories represent a
# platform-wide protective stand-down rather than a per-candidate risk
# judgment. Reused directly from portfolio_risk.py's own category
# constants — not a new taxonomy.
#
# DRAWDOWN_PROTECTION only: verified against portfolio_risk.py's actual
# evaluate() body (checks #4 "portfolio-wide daily loss stop" and #5
# "trailing 30-trade drawdown cap") -- both are pure functions of
# portfolio-wide state (today's realized R across every symbol; the
# trailing closed-trade drawdown), with NO dependency on the specific
# candidate's own direction/entry/stop. Every other candidate evaluated
# in the same moment would get the identical rejection -- a genuine
# platform-wide stand-down.
#
# TRADE_FREQUENCY_CONTROL deliberately excluded despite its name sounding
# stand-down-like: it's actually check #2, "simultaneous directional
# exposure" -- `dirs[direction] + 1 > max_dir` -- which depends on THIS
# candidate's own `direction`. A same-symbol candidate proposed in the
# OPPOSITE direction at the same instant would NOT get this rejection,
# so it is a per-candidate REJECT, not a platform-wide STAND_DOWN. (The
# category name not matching its actual check is an existing naming
# quirk in portfolio_risk.py, not something to "fix" here -- the string
# is a live schema value other modules pattern-match on; renaming it
# would be a breaking change out of scope for this module.)
STAND_DOWN_CATEGORIES = {pr.DRAWDOWN_PROTECTION}


@dataclass
class GateVerdict:
    """One gate decision. `category` is one of
    `explainability_engine.REJECTION_CATEGORIES` (or None for ENTER/WAIT).
    `details` carries the raw, already-computed sub-verdict(s) this
    GateVerdict was classified from — for debugging/audit, never for
    re-deriving the decision (the decision is already made by the time
    this object exists)."""
    action: str
    stage: str
    category: "str | None" = None
    reason: str = ""
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise ValueError(f"GateVerdict: unknown action {self.action!r}")

    @property
    def passed(self) -> bool:
        """True only for ENTER/WAIT — every other action means this
        candidate did not proceed. Convenience for callers that just
        want a boolean without inspecting `action` themselves."""
        return self.action in (ENTER, WAIT)


def _stand_down_or_reject(category: "str | None") -> str:
    return STAND_DOWN if category in STAND_DOWN_CATEGORIES else REJECT


def evaluate_origination_gate(symbol: str, direction: str, entry: float, stop: float, *,
                              mkt_regime: dict, cr=None, news_state: "dict | None" = None,
                              settings=None, session_label: "str | None" = None,
                              regime_mode: str = "advisory",
                              regime_min_quality: int = 30) -> GateVerdict:
    """Stage-1 heads-up origination gate. Mirrors
    alert_signals.py::main()'s Stage-1 sequence exactly (see module
    docstring) — same functions, same order, same short-circuit
    semantics, just given a name and a return contract instead of an
    inline `continue`. Never raises: every wrapped call already fails
    safe on its own (risk_guard/portfolio_risk's own fail-open
    disclosure, apply_regime_gate's advisory default); this function
    adds no new failure surface on top of them."""
    blackout = bool((news_state or {}).get("blackout", False))
    if blackout:
        return GateVerdict(BLOCKED, "origination", expl.NEWS_BLACKOUT,
                           "news blackout active", {"news_state": news_state})

    rk = risk_guard.evaluate(symbol)
    if rk.get("locked"):
        return GateVerdict(BLOCKED, "origination", expl.RISK_LOCK,
                           rk.get("reason", ""), {"risk_guard": rk})

    # Deferred import: apply_regime_gate lives in alert_signals.py, which
    # does not (and, to avoid a circular import, must not) import this
    # module at top level. Reusing the exact function rather than
    # reimplementing its (intentionally simple) advisory-vs-block logic.
    from alert_signals import apply_regime_gate
    regime_blocked, regime_note = apply_regime_gate(
        mkt_regime or {}, regime_mode, regime_min_quality)
    if regime_blocked:
        return GateVerdict(HOLD, "origination", pr.MARKET_REGIME_UNSUITABLE,
                           regime_note, {"mkt_regime": mkt_regime})

    final_tier = getattr(cr, "final_tier", None) if cr is not None else None
    if final_tier != "confirmed":
        score = getattr(cr, "score", None) if cr is not None else None
        disagree = getattr(cr, "disagree", None) if cr is not None else None
        return GateVerdict(HOLD, "origination", expl.WEAK_EVIDENCE,
                           f"MAST {final_tier} (score {score})",
                           {"cr_score": score, "cr_final_tier": final_tier,
                            "cr_disagree": disagree})

    pr_verdict = pr.evaluate(symbol, direction, entry, stop,
                             settings=settings, session_label=session_label)
    if not pr_verdict["allow"]:
        category = pr_verdict.get("category")
        return GateVerdict(_stand_down_or_reject(category), "origination", category,
                           pr_verdict.get("reason", ""), {"portfolio_risk": pr_verdict})

    return GateVerdict(WAIT, "origination", None, "heads-up approved",
                       {"portfolio_risk": pr_verdict})


def evaluate_entry_gate(symbol: str, direction: str, entry: float, stop: float, *,
                        news_state: "dict | None" = None, settings=None,
                        session_label: "str | None" = None) -> GateVerdict:
    """Stage-2 fill/entry gate. Mirrors alert_signals.py::main()'s
    Stage-2 sequence exactly — deliberately narrower than Stage-1: no
    regime or confluence re-check here, because Stage-1 already
    qualified both before this candidate ever became a pending setup
    (see module docstring "Two stages, two narrower gate sets"). Never
    raises, for the same reason as evaluate_origination_gate above."""
    blackout = bool((news_state or {}).get("blackout", False))
    if blackout:
        return GateVerdict(BLOCKED, "entry", expl.NEWS_BLACKOUT,
                           "news blackout active", {"news_state": news_state})

    erk = risk_guard.evaluate(symbol)
    if erk.get("locked"):
        return GateVerdict(BLOCKED, "entry", expl.RISK_LOCK,
                           erk.get("reason", ""), {"risk_guard": erk})

    pr_verdict = pr.evaluate(symbol, direction, entry, stop,
                             settings=settings, session_label=session_label)
    if not pr_verdict["allow"]:
        category = pr_verdict.get("category")
        return GateVerdict(_stand_down_or_reject(category), "entry", category,
                           pr_verdict.get("reason", ""), {"portfolio_risk": pr_verdict})

    return GateVerdict(ENTER, "entry", None, "entry approved",
                       {"portfolio_risk": pr_verdict})
