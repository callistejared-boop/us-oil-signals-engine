# Gold Engine v0.2 — Phase 1 of the AI Trading Intelligence Platform

A rule-based, multi-timeframe XAUUSD analysis engine built on institutional
concepts (market structure, BOS/CHoCH, Fair Value Gaps, premium/discount,
kill zones), with a cost-aware walk-forward backtester, Monte Carlo risk
simulation, HTML performance reports, Telegram alerts, and a TradingView
Pine Script indicator.

## What it does

Every scan, the engine:

1. Reads Daily / 4H / 1H structure and votes a weighted directional bias.
2. Requires 15m structure to agree (no counter-trend entries).
3. Requires price in discount (longs) / premium (shorts) of the 1H dealing range.
4. Finds the nearest unfilled 15m Fair Value Gap in the bias direction.
5. Builds the trade: limit entry at the gap midpoint, stop beyond the gap
   (ATR-padded), target at nearest opposing liquidity, RR between 2 and 4.
6. **Rejects any setup whose stop is tighter than 10× the spread** — costs
   would eat the edge (this filter alone turned the worst regime from
   −22R into +1.3R).
7. Scores confluence 0–100 and rejects everything below 70.
8. Explains every published setup, including the invalidation level.

Risk gates: one position at a time, 4-hour cooldown after a stop-out,
stand down for the day after 2 losses.

## Verified results — WITH transaction costs ($0.30 spread+slippage/trade)

Walk-forward, no lookahead, pessimistic fills (stop wins ties).

| Period | Trades | Win rate | Profit factor | Total R | Max DD |
|---|---|---|---|---|---|
| May–Jun 2025 | 25 | 40% | 2.19 | +19.1R | −4.3R |
| Nov–Dec 2024 | 6 | 17% | 0.43 | −3.1R | −3.3R |
| Sep–Oct 2024 | 4 | 50% | 2.17 | +2.5R | −1.1R |
| Mar–Apr 2023 | 4 | 50% | 1.98 | +2.1R | −2.1R |
| Jun–Jul 2022 | 3 | 33% | 1.62 | +1.3R | −1.1R |
| **Aggregate** | **42** | **36%** | **~1.9** | **+21.9R** | worst window −3.3R |

**Read this honestly:**
- The engine is *selective*: 2–12 trades per month depending on regime.
  In low-volatility periods it mostly stands aside — by design, because
  tight-stop trades lose to the spread.
- 4 of 5 windows positive; the losing window cost −3.1R. No blow-ups.
- Per-window samples are small; the aggregate is the meaningful number.
- R multiples are position-size agnostic. At 1% risk per trade,
  +21.9R ≈ +22% across those 10 months of windows.
- One instrument, five windows, rules iterated against this same data.
  **Forward-test on live data before risking money.** Nothing here
  predicts markets; it finds rule-based confluence and controls risk.

## Setup (10 minutes, no coding needed)

1. **Install Python 3.10+** from https://python.org (tick "Add to PATH").
2. Terminal in this folder: `pip install -r requirements.txt`
3. **Live data (free):** get an API key at https://twelvedata.com, copy
   `.env.example` to `.env`, paste the key. Falls back to Yahoo (GC=F)
   without it.
4. **Telegram alerts:** message **@BotFather** → `/newbot`, copy the token
   into `.env`. Message your new bot once, open
   `https://api.telegram.org/bot<TOKEN>/getUpdates`, copy the
   `"chat":{"id":...}` number into `.env`. Verify:
   `python main.py test-telegram`

## Usage

```
python main.py scan --live                              # one-off analysis now
python main.py run                                      # continuous scanning + Telegram alerts
python main.py backtest --start 2025-01-01 --end 2025-06-30
python main.py report --start 2025-05-01 --end 2025-06-30   # HTML dashboard
python -m pytest tests/                                 # 9 unit tests
```

`scan` says "no qualifying setup" most of the time. **That is the product
working** — rejection is the job.

## TradingView

`tradingview/gold_engine_structure.pine` mirrors the engine on charts:
BOS/CHoCH labels, live unfilled FVG boxes, kill-zone shading, trend readout.
Pine Editor → New indicator → paste → Add to chart.

## Project structure

```
gold-engine/
├── main.py                    # CLI: scan / run / backtest / report / test-telegram
├── engine/
│   ├── data_loader.py         # CSV history + TwelveData/yfinance live
│   ├── structure.py           # swings, BOS/CHoCH, FVGs, ATR, ranges, kill zones
│   ├── signals.py             # multi-TF confluence + cost-aware signal build
│   ├── backtest.py            # walk-forward sim, costs, risk gates, R stats
│   ├── montecarlo.py          # bootstrap: DD distribution, P(ruin)
│   ├── report.py              # self-contained HTML dashboard
│   ├── telegram_alerts.py     # Bot API delivery
│   └── config.py              # .env settings
├── tests/test_engine.py       # unit tests (9)
├── tradingview/gold_engine_structure.pine
├── data/XAU_15m_data.csv      # 480k bars 15m XAUUSD 2004–2025 (MIT)
├── sample_report_2025-05_06.html
├── requirements.txt
└── .env.example
```

## Roadmap

- **Phase 2** — web dashboard + Supabase auth (signals, journal, equity)
- **Phase 3** — walk-forward optimizer, regime detection (the Nov–Dec 2024
  miss suggests a volatility-regime switch for the risk floor)
- **Phase 4** — Stripe billing, tiers, TradingView webhooks, Forex/BTC
- **Phase 5** — mobile app, AI coach, research reports

## Legal note

Research and education only; not investment advice. Selling signals
commercially is a regulated activity in many jurisdictions — get proper
advice before charging users.
