"""Day 12 — Institutional Execution Simulator & Transaction Cost Model.

This package answers a question the platform has never asked itself
before: "what would execution have actually looked like in the real
market?" Days 1-11 built a decision engine (when to trade, why, whether
risk is acceptable). None of that models the gap between a signal price
and a filled price. This package closes that gap — for RESEARCH and
DISCLOSURE purposes only.

GOVERNING PRINCIPLE (mirrors every prior advisory system's own framing):
this package never originates a trade, never blocks a trade, never
changes a stop/target/size. It answers "how good was/would execution
have been?" — never "should this trade be taken?"

HONESTY NOTE, stated once here and repeated in every module's docstring:
this platform has no live broker connection (that is explicitly Day 13's
job — "Live Broker Abstraction Layer"). Every "actual entry"/"actual
exit"/"execution cost" figure this package produces is a MODELED
ESTIMATE built from disclosed, documented assumptions (typical retail
spreads, session liquidity patterns, latency benchmarks) — never a
truly observed fill from a real broker. Every function and every report
this package produces says so explicitly, the same "disclose, don't
overclaim" discipline applied to the Confidence Engine's
`probability_label` (Day 6) and the Macro Engine's proxies (Day 11).

Modules:
    spread_model.py     - session/volatility/symbol/news-dependent spread estimate
    slippage_model.py   - normal/adverse/favorable slippage, liquidity shocks, partial fills
    latency_model.py    - signal->execution delay estimate, separate timestamps
    fill_model.py        - order-type-aware fill simulation (market/limit/stop)
    execution_report.py - per-trade fill-quality report + descriptive execution score
    comparison.py        - Raw Strategy -> Ideal -> Realistic -> Observed research bridge
    replay.py             - reproducible historical replay under configurable assumptions

Package isolation is deliberate (per the Day 12 mandate's own
recommendation): execution modeling will keep growing (broker-specific
profiles at Day 13, more order types, more liquidity scenarios) and
keeping it in its own package now avoids a future refactor.
"""
