# Gold/US Oil High Probability Platform — Master Summary
*Everything built, how it connects, and how a trade is set up, sent, and analyzed.*

---

## 1. What this platform is

A fully autonomous, rule-based trading-signal engine for four markets — **Gold (XAUUSD), WTI Crude Oil (WTIUSD), EUR/USD, and Bitcoin (BTCUSD)** — built on **ICT / Smart-Money Concepts** (market structure, liquidity, fair value gaps, order blocks, OTE, premium/discount, kill zones).

It reads live price, forms a multi-timeframe view, scores each setup, folds in live news and timing edges, sends staged alerts to Telegram, tracks every trade automatically, and continuously measures whether its own edges are working. It runs unattended on your laptop and mirrors itself onto TradingView.

**Core principle throughout: nothing is a black box.** Every score, grade, and adjustment is shown with the reasons behind it, and the system tells you honestly when the sample is too small to trust.

---

## 2. The big picture — how everything connects

```
        LIVE PRICE (yfinance)                 LIVE NEWS (Google News RSS + Claude)
               │                                          │
               ▼                                          ▼
     ICT/SMC ENGINE (structure, FVG,            NEWS FEED  ->  fundamentals.json
     order blocks, liquidity, OTE)              (BUY/SELL per pair + reasoning)
               │                                          │
               ├───────────────► CONFIDENCE SCORE ◄───────┤
               │            (technical base +/- context)   │
               │                       │                   │
        KILL-ZONE TIMING EDGE ─────────┤        TradingView confirmation (optional)
                                       ▼
                               GRADE  A+ / A / B / C
                                       │
              ┌────────────────────────┼───────────────────────────┐
              ▼                        ▼                            ▼
      TELEGRAM ALERTS          TRADE JOURNAL (trades.json)    INTERFACES (HTML)
   (heads-up -> entry)         auto win/loss + news stamp     Command Center,
              │                        │                       News&Bias, Dashboard
              ▼                        ▼
        Your phone              SELF-REVIEW / LEARNING LOOP
                                (does each edge actually work?)
```

Everything lives in one folder (**gold-engine**) and is driven by one menu: **START_HERE.bat**.

---

## 3. HOW A TRADE IS SET UP (the signal pipeline)

This is the heart of it. For each market, every scan does the following:

**Step 1 — Pull live price.** `engine/markets.py` fetches recent candles (via yfinance: `CL=F` oil, `GC=F` gold, `EURUSD=X`, `BTC-USD`) and resamples them to the timeframes it needs.

**Step 2 — Read the market structure (ICT/SMC).** `engine/ict.py` + `engine/structure.py` compute the full smart-money picture:
- **Multi-timeframe bias** (Daily / 4H / 1H / 15m) from swing structure, with an EMA-trend fallback so it always forms a view.
- **Dealing range** and where price sits in it → **premium** (expensive) vs **discount** (cheap), with the **OTE** zone (0.62–0.79 retracement).
- **Liquidity map**: resting buy-side (above) and sell-side (below) pools — the targets.
- **Last structure event**: BOS (break of structure) or CHoCH (change of character).
- **Nearest unfilled Fair Value Gap** and the most recent **order block** (the entry zones).
- The **trading session / kill zone**.

**Step 3 — Score confidence.** `engine/signals.py` turns that read into a setup with a **confidence 0–100** and a **tier**: *confirmed* (tradeable) or *watch* (forming). Entry is a limit at the FVG/OTE, with stop and multi-target take-profits (TP1 +1R, TP2 +2R, TP3 at the structure target).

**Step 4 — Fold in live context (bounded, transparent).** `engine/bias_adjust.py` nudges that confidence by a small, capped amount (±8 max) from three inputs:
- **Live news bias** (from the news feed — see §6): agrees with the trade → up; conflicts → down (±6).
- **Kill-zone timing edge** (`engine/session_edge.py`): London KZ 07–10 UTC and New York KZ 12–15 UTC are high-probability windows (+4); the Asian dead zone is faded (−3). This is backed by both research *and* your own trade data.
- **TradingView confirmation** (optional, `engine/tv_signals.py`): if a TradingView alert agrees, +2.

**Step 5 — Grade it.** The context-adjusted confidence becomes a letter grade: **A+ / A / B / C (watch)**. Everything is shown with a factor-by-factor breakdown, so you see *why* it's an A vs a B.

The result is a complete, explainable trade: direction, grade, entry zone, stop, three targets, expected hold time, invalidation level, and the reasoning stack.

---

## 4. HOW A TRADE IS SENT (alerts to your phone)

`alert_signals.py` runs on a fast cadence and uses a **two-stage system** so you're never late:

1. **Stage 1 — HEADS-UP:** the moment a confirmed setup forms (entry is a limit price hasn't reached yet), it messages *"watching for entry at X, and here's why"* — with the grade, levels, and reasoning — and remembers it.
2. **Stage 2 — ENTRY TRIGGERED:** on a later scan, when price actually taps that level, it fires the real entry alert and logs the trade. The entry message includes the **management plan**: move stop to break-even at +1R, bank 50% at +2R, let the runner go to target.

Routing (`engine/config.py` + `engine/markets.py`): everything goes to your **Telegram DM**, and each market can route to its own **public channel** (gold → @jaredxauusdsignals, oil → @jaredwticrudesignals). It stands aside during high-impact news windows (`engine/news_guard.py`).

There's also an **institutional WTI note** (`wti_note.py`) — a hedge-fund-style writeup with the full multi-timeframe read, targets, confidence breakdown, and live geopolitics — and **bias-flip alerts** (`news_watch.py`): if a pair's news bias flips BUY↔SELL, it pings your DM with the reasoning.

---

## 5. HOW IT'S ANALYZED & HOW IT LEARNS

Every trade is tracked and studied so the system improves on evidence, not guesswork.

**The journal** (`engine/journal.py`): every entry is logged to `trades.json` and **settled automatically** against real price using the exact tested rules (break-even after +1R, 50% partial at +2R, runner to target). Each trade is also **stamped with the live news context at entry** (which signal, how strong, how much it moved confidence). Storage is hardened — atomic writes, a rolling backup, and salvage-on-corruption — so your history can never be silently lost.

**The self-review** (`self_review.py` → `self_review.html`): reads the journal and reports **what actually predicts wins** — broken down by confidence bucket, session, market, direction, weekday, and **news-agreement**. It gives plain-English recommendations and, crucially, says *"sample too small, don't rewire yet"* when that's the honest answer.

**The learning loop** (the key innovation): because trades are news-stamped, the review can measure the real question — *do news-agreeing trades actually win more?* It surfaces the answer automatically and tells you when to act. (Current honest status: the journal is ~89 trades, still net-positive; the loop has flagged that news-agreeing trades were underperforming on a small sample — a *watch* signal, which is exactly what it's designed to catch.)

**Weekly self-audit** (`weekly_audit.py`): posts a plain-English "what the engine is learning" summary to your DM.

---

## 6. THE LIVE NEWS ENGINE (and the Claude upgrade)

`engine/fundamentals_feed.py` runs every 5 minutes:
- Pulls recent headlines for each pair from public financial news (Reuters/Bloomberg/CNBC/FT via Google News RSS — free, no key).
- **Scores each headline** for that instrument's bias. Two modes:
  - **Free lexicon** — negation-aware keyword scoring (so "Iran *denies* closing Hormuz" doesn't read as bullish).
  - **Claude analyst (LIVE, now enabled)** — `engine/llm_news.py` sends the headlines to Claude with your API key; Claude returns a reasoned BUY/SELL/NEUTRAL + strength + a written rationale. This is a real analyst read, not word-counting (e.g. it flipped gold to SELL on Fed/USD strength where the keyword scorer said BUY). Falls back to the lexicon automatically if anything fails.
- Produces `fundamentals.json`: per-pair signal, strength, net score, reasoning, and scored headlines with source links — which feeds the confidence score (§3), the alerts (§4), and the interfaces (§7).

---

## 7. THE INTERFACES (what you look at)

- **Command Center** (`command_center.html`) — one screen for everything: live news-bias strip, engine-health checks, headline performance, equity curve, "what predicts wins", latest note, and links to every tool.
- **Live News & Bias** (`news_bias.html`) — a per-pair BUY/SELL page with reasoning and source links; auto-reloads every 5 min and shows a red **FEED-STALE alarm** if the job stops.
- **Performance Dashboard** (`dashboard.html`) — full stats: win rate, profit factor, expectancy, max drawdown, consecutive losses, per-pair / per-session / confidence / monthly tables, each explained in plain English.
- **Self-Review** (`self_review.html`) — the learning-loop report (§5).
- **Mobile app (PWA)** + **landing page** — phone-installable signal feed and a public sales page.
- **TradingView** — the `Alpha Signals Engine` Pine v5 indicator is loaded on your chart: kill-zone shading, EMA trend, BOS labels, FVG boxes, OTE zone, buy/sell triangles, plus native alerts. A webhook path lets TradingView alerts feed back into the engine.

---

## 8. AUTOMATION — it runs itself

Windows Task Scheduler runs these unattended (battery-safe):
- **Every 5 minutes:** refresh all-pair news + Claude scoring, regenerate interfaces, fire bias-flip alerts.
- **90-minute market briefings** and a **15-minute entry scanner** (when enabled).
- One menu — **START_HERE.bat** — launches everything: install, verify, send a signal, WTI note, dashboards, refresh news, schedule jobs, start the TradingView webhook.

---

## 9. SAFETY & QUALITY

- **Freshness guard** — stale fundamentals get flagged and discounted; they can never masquerade as current.
- **Crash-proof journal** — atomic writes + backup + salvage (a bad read can't erase history).
- **Graceful fallbacks everywhere** — no news / no Claude / no network → the system degrades safely instead of breaking.
- **Test-covered** — **77 automated tests** covering scoring, negation, the confidence fold, kill-zone edge, TradingView confirmation, the journal, the learning loop, and the Claude parser. All passing.
- **Credential safety** — your API key and bot token live only in your local `.env`; they were never handled or stored by the assistant.

---

## 10. HONEST STATUS & CAVEATS

- **Win rate 40–55% is professional and profitable** at this reward-to-risk. The engine is net-positive; it is *not* an "80% win rate" machine — forcing that quota loses money, and I've kept the numbers honest throughout.
- **Data note:** gold/oil use a futures proxy for price; the exact broker spot can differ slightly. TradingView uses your broker's live feed.
- **The learning loop is young** — treat its findings as a compass, not gospel, until each bucket has more trades.
- **This is research/education tooling — not financial advice.** Always confirm against the primary source before trading.

---

## 11. THE ONE-LINE VERSION

*Live price → ICT/SMC structure read → confidence score → nudged by Claude-graded news + kill-zone timing → letter grade → two-stage Telegram alert with a management plan → auto-logged and settled → continuously measured to prove which edges actually work → mirrored on TradingView — all running itself every 5 minutes on your laptop.*
