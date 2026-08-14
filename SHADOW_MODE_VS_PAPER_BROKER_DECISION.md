# Shadow-Mode vs. Paper Broker — Architecture Decision

**V2.2 Priority 4, Item 2**

## 1. What the audit flagged

`PHASE0_FORENSIC_AUDIT.md` Section R, Priority 4:

> Extend `montecarlo.py` (review its current 51 lines first). Decide the
> Shadow-mode-vs-Paper-Broker question with you before building anything
> there.

No further detail was given in that document — it names the question
without spelling out the two options, so resolving it required reading
what each term actually means elsewhere in this codebase before a call
could be made.

## 2. What each term actually means here

Two genuinely different things share the word "shadow" in this
repository, and conflating them would have produced a wrong decision:

**"Shadow-mode" as it already exists** (`config.portfolio_risk_mode =
"warn"`, documented in `RISK_SPECIFICATION.md` and `engine/config.py`):
a per-gate escape hatch. A specific check runs, logs what it would have
done, but does not block — "prove it before it gets teeth," the same
precedent `range_guard.py`'s `SUPPRESS_MODE` established. This is
narrow and already built; nothing about it needed a decision.

**"Shadow-mode" as a strategy-validation architecture** (what the audit
line is actually asking about): the open question of how a *new,
unproven strategy* gets evaluated against live market data before it's
trusted — do you build a live-observing "shadow" path that watches real
ticks and logs hypothetical signals with no account/position state, or
do you route new strategies through something that simulates an actual
account?

That second, real question is what needed deciding.

## 3. What already exists that bears on this

Reading `engine/broker/` (Day 13, `PAPER_BROKER_SPECIFICATION.md`) and
`engine/broker/research_bridge.py` (Day 13's evidence-source
separation) before deciding showed the second option already has a
mature, tested implementation:

- `PaperBroker` (`engine/broker/paper_broker.py`) is a full
  `BrokerInterface` implementation — order lifecycle, an aggregate
  per-symbol position engine, a virtual account with starting capital/
  leverage/margin, and every fill priced through the same
  `fill_model.simulate_fill()` the Day 12 execution simulator uses. No
  duplicated spread/slippage/latency assumptions.
- `research_bridge.py` already formalizes THREE distinct evidence
  tiers and is explicit that they must never be merged: **simulated**
  (Day 12's retrospective, per-trade, no-account comparison),
  **paper** (`PaperBroker` driven sequentially through real trades,
  Day 13), and **live** (reserved, `None` today, "a future Day's live
  adapter has an obvious place to plug in without changing this
  function's shape").

That third slot is the key fact: the evidence-source architecture this
platform already committed to is a three-tier ladder — simulated →
paper → live — not a fourth "shadow" tier bolted alongside paper. A
live-observing shadow path that logs hypothetical signals against real
ticks with no account/position modeling would functionally duplicate
what "simulated" already does (per-trade, no account state), just with
a live rather than historical data source — and would NOT be a step
toward "live," since it still wouldn't exercise position-netting,
margin, or sequencing.

## 4. The decision

**New/unproven strategies get validated by running them through the
existing `PaperBroker`, not through a new shadow-mode observation
system.** No new module is being built for this Item.

Rationale, in order of weight:

1. **Extract-and-reuse discipline.** This has been the standing rule
   for every Priority 2/3 item this cycle (`kill_switch.py` reusing
   `news_guard`/`risk_guard`, `why_not.py` reusing `explain_rejection`,
   `regime_transitions_report.py` reusing `regime_history.record()`).
   `PaperBroker` already does everything a shadow-mode system would
   need to do — and does it with account/position state a pure
   observation layer would lack.
2. **The evidence-tier ladder is already designed and documented.**
   `research_bridge.py`'s simulated → paper → live structure, with an
   explicit reserved slot for live, is the intended promotion path. A
   new strategy is either evaluated retrospectively (simulated,
   already exists) or run forward through `PaperBroker` (paper,
   already exists) before a live adapter is ever built. There is no
   gap in that ladder for a fourth tier to fill.
3. **A shadow-observation path would be strictly weaker evidence, not
   complementary evidence.** Since it wouldn't model an account,
   position-netting, or margin, any "shadow" signal it produced would
   already be a subset of what `PaperBroker`, run on the same forward
   window, produces — plus `PaperBroker`'s output is directly
   comparable to the paper tier other strategies are already measured
   against.

## 5. What this unblocks

This decision was a prerequisite the audit explicitly called out before
any promotion-pipeline enforcement work could safely proceed (Priority
4/5 territory: gating a strategy from reaching production without
passing through research → experiment → backtest → walk-forward →
paper, per `STRATEGY_RESEARCH_FRAMEWORK.md`). That future work can now
assume "paper" in that pipeline means `PaperBroker`, with no separate
shadow-mode concept to reconcile against it. Nothing is being built or
wired in this landing — this Item is the decision itself, made explicit
and recorded so it doesn't need re-litigating later.
