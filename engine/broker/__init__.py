"""Day 13 — Broker Abstraction Layer (BAL).

Governing principle: the decision engine (`signals.py`, `confluence.py`,
`confidence_engine.py`, `risk_guard.py`, `portfolio_risk.py`, `bias_adjust.py`)
NEVER imports anything from this package and NEVER talks to a broker
directly. The dependency runs one way only:

    Decision Engine  ->  (approved trade)  ->  alert_signals.py
                                                     |
                                                     v
                                      Broker Abstraction Layer (this package)
                                                     |
                              -----------------------------------------
                              |                |                |
                        Paper Broker      Live Broker       Replay Broker
                        (Day 13, this)   (future adapter)   (drives Paper
                                                              Broker from
                                                              historical
                                                              trades)

Every provider implements the same `contract.BrokerInterface` — a
versioned "Execution API v1" contract (see `contract.py`'s module
docstring). A future live adapter (MetaTrader/IBKR/OANDA/etc.) conforms
to the identical interface; nothing above this layer needs to change
when a live adapter is added.

Honesty note, carried forward from Day 12: this platform still has no
live broker connection. The Paper Broker is a REALISTIC SIMULATION —
built on Day 12's disclosed spread/slippage/latency assumption models
(`engine.execution.fill_model`) — not a live account. Every balance,
fill, and P&L figure this package produces is clearly labeled
`is_estimate: True` and traceable to the assumption model that produced
it. See PAPER_BROKER_SPECIFICATION.md Sec.2 for the full disclosure.

Advisory posture, unchanged from every prior Day 4-12 subsystem: this
package is called by `alert_signals.py` only AFTER a trade has already
been approved by every upstream gate (regime -> confluence -> risk_guard
-> portfolio_risk). Nothing in this package can hold, downgrade, resize,
or reject a signal that has already been approved — a broker-layer
rejection (e.g. simulated insufficient buying power) is recorded for
research/observability, never fed back into the gating pipeline. This is
verified structurally (grep) in DAY13_VALIDATION_REPORT.md, exactly like
every prior Day's advisory-only proof.

Naming disambiguation (read before assuming a collision):
  - `config.paper_mode` (Day 1-2): a boolean flag that tags Telegram
    alerts "FORWARD TEST (paper)" — pure messaging, no execution model.
  - `engine.paper_trading_review.py` (Day 9): a decision-audit SYNTHESIS
    layer over Day 8's DecisionSnapshot trail — compares proposed vs.
    executed, surfaces operational issues. It does not simulate an
    account or fills.
  - `engine.broker.paper_broker.PaperBroker` (Day 13, THIS package): a
    full execution provider — order lifecycle, positions, account
    balances, realistic fills. The first genuine "broker" this platform
    has ever had, even though it is not connected to real money.
  These three are unrelated and never call each other.

Modules:
  - `contract.py`      — Execution API v1: `BrokerInterface` ABC +
                          `OrderRequest`/`Order`/`Fill`/`PositionSnapshot`/
                          `AccountSnapshot` dataclasses + enums.
  - `order_state.py`   — order lifecycle state machine (Created ->
                          Accepted -> Working -> PartiallyFilled/Filled/
                          Cancelled/Expired/Rejected), immutable
                          transitions.
  - `events.py`        — standardized execution event taxonomy + emit().
  - `broker_history.py`— append-only JSONL persistence for orders,
                          fills, events, and account equity snapshots.
  - `position_engine.py` — centralized, symbol-aggregate position
                          tracking (avg entry, exposure, realized/
                          unrealized P&L, fees, execution costs, risk
                          utilization).
  - `account.py`       — `PaperAccount` + `AccountRegistry`: starting
                          capital, leverage, margin, buying power, equity
                          curve, multi-account support.
  - `paper_broker.py`  — `PaperBroker`, the first true execution
                          provider: implements `contract.BrokerInterface`
                          on top of Day 12's execution simulator.
  - `replay_broker.py` — drives `PaperBroker` from historical trades
                          exactly as live signals would, reproducibly.
  - `research_bridge.py` — keeps simulated / paper / (future) live
                          execution evidence separately labeled and
                          never merged, per the Day 13 mandate.
"""

VERSION = "1.0.0"
