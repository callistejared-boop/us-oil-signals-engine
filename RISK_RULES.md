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
- **Max drawdown (R)** — keep under 6R per 30-trade window (also capped
  to the trailing 30 calendar days — see "Drawdown stand-down recovery"
  below).
- Win-rate is a *vanity* metric on its own: 45% at 2.5R average winners is a
  professional, profitable system; 80% with −3R losers is ruin.

## Scale-up ladder (only after a VALIDATED window)

0.5% risk → 30 more trades still positive → 0.75% → repeat → 1.0% cap.
Any −6R window at any rung: drop one rung and re-validate.

## Drawdown stand-down recovery (V2.2)

If the trailing 30-trade drawdown hits the 6R cap, the engine enters
`DRAWDOWN_PROTECTION` and blocks every new signal — by design, this is the
account's last line of defense. That stand-down now clears two ways:

1. **A new trade closes** and rolls the 30-trade window (the original
   design) — normal path when trading is active.
2. **30 calendar days pass** since a losing trade in the window closed —
   that trade ages out of the drawdown calculation even with zero new
   trades. This is the fix for a real deadlock found 2026-08-10: with no
   open positions and the stand-down blocking every new entry, the
   trade-count window could never advance on its own, so the stand-down
   had no possible way to ever self-clear. See
   `engine/portfolio_risk.py::portfolio_drawdown_r()` and
   `RISK_SPECIFICATION.md` for the full mechanism
   (`portfolio_drawdown_max_age_days`, default 30, tunable via
   `engine/config.py`).

Do not manually clear the stand-down. Let it expire on one of the two paths
above — that's the whole point of a capital-preservation control.

## Known gap to respect

Engine levels come from WTI **futures** (CL=F). Your broker's **USOIL** CFD
can sit $0.1–0.4 away (basis). Always sanity-check the level on YOUR platform
before placing the order; skip fills that would need chasing.

*Research/education only — not financial advice.*
