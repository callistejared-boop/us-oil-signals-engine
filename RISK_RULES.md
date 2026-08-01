# RISK RULES — non-negotiable (print this)

**The account survives first. The edge gets proven second. Scaling comes third.
Never in a different order.**

## Hard rules (the engine enforces #2 and #3 automatically)

1. **Risk per trade: 0.5–1% of equity. Fixed.** No "sure thing" exceptions —
   the walk-forward test proved confidence doesn't predict winners yet.
2. **Day stop: −2R.** After −2R of closed losses in a day the engine locks and
   publishes no new signals until tomorrow (UTC). Do not override it manually.
3. **One open US Oil position, max.** No stacking, no averaging down.
4. **No trading through red-news windows** (EIA, FOMC, Hormuz headlines) — the
   news blackout stands aside for a reason; spreads blow out and stops gap.
5. **Forward test before real size: 30 closed trades in paper mode.** The
   scoreboard (`forward_report.py`) gives the verdict — the numbers decide,
   not feelings, not one good week.

## The scoreboard that matters

- **Expectancy (avg R/trade)** — the only number that pays. Target > +0.15R.
- **Max drawdown (R)** — keep under 6R per 30-trade window.
- Win-rate is a *vanity* metric on its own: 45% at 2.5R average winners is a
  professional, profitable system; 80% with −3R losers is ruin.

## Scale-up ladder (only after a VALIDATED window)

0.5% risk → 30 more trades still positive → 0.75% → repeat → 1.0% cap.
Any −6R window at any rung: drop one rung and re-validate.

## Known gap to respect

Engine levels come from WTI **futures** (CL=F). Your broker's **USOIL** CFD
can sit $0.1–0.4 away (basis). Always sanity-check the level on YOUR platform
before placing the order; skip fills that would need chasing.

*Research/education only — not financial advice.*
