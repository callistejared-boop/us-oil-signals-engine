# Day 3 — Phase 1: Live Execution Path Trace (Pre-Integration Baseline)

Captured 2026-08-03, from direct source reads (not from memory of the Day 1
audit). This is the state of the system **before** any Day 3 code changes.
Post-integration path is documented in `RISK_SPECIFICATION.md` §2.

## 1. The one proven production path: `alert_signals.py` (via `entry-scan.yml`, `*/15 * * * *`)

```
GitHub Actions cron (*/15 * * * *)
  -> alert_signals.py :: main()
       for sym in markets.symbols(s):                       # XAUUSD / WTIUSD / BTCUSD
         1. markets.fetch(sym, s)                            -> pd.DataFrame (OHLC, raises on failure)
         2. journal.settle(df, symbol=sym)                    -> mutates journal.jsonl (closes matured trades)
         3. pending.update(sym, df)                           -> yields ("entry", rec) | ("void", rec)

         STAGE-2 (ENTRY) branch, per pending record:
           4. risk_guard.evaluate(sym)                        -> {locked, reason, day_r, open_n}
              if locked -> log "entry HELD", ledger.log(entry_held), continue   [existing gate]
           5. ltf.confirm(direction)            (XAUUSD only)  -> lower-timeframe confirmation dict
           6. regime.classify(resample(df,"4h"))                -> regime dict (trend/vol)
           7. _guard_for(sym, direction, df)
                -> ict.read(df) -> r
                -> regime.classify(resample(df,"4h")) -> reg
                -> correlation.read_macro()           -> macro (cached DXY trend)
                -> range_guard.evaluate(sym, direction, r['pos'], dxy, reg) -> guard verdict
           8. confluence.analyze(df.tail(12000), symbol=sym, min_score=s.confluence_min_score) -> cr (MAST result)
           9. build_entry(rec, lt, confluence=cr)              -> formatted Telegram text
          10. _send(s, text, channel=markets.channel_for(sym,s)) -> Telegram publish   *** NO PORTFOLIO CHECK ***
          11. journal.log_signal(...)                          -> appended Trade row
          12. ledger.log({"event":"entry", ...})                -> observability trail

         STAGE-1 (HEADS-UP) branch, once per symbol per scan (if not blackout):
           4. risk_guard.evaluate(sym)                          [existing gate, same as above]
           5. signals.analyze(df.tail(12000), min_conf=PUBLISH_THRESHOLD, symbol=sym) -> sig | None
              (Layer 1 origination: ICT/SMC engine)
           6. pending.exists(sig) / journal.is_open(...)         -> dedup guard
           7. confluence.analyze(...) -> cr                      (Layer 2: MAST, confirm/downgrade/reject only)
              if cr.final_tier != "confirmed": log "MAST held", ledger.log(confluence_held), continue
           8. ict.read(df) -> r
           9. _guard_for(sym, sig.direction, df) -> guard         (Layer 3: range/dollar-headwind guard)
          10. pending.add(sig, timestamp)                        -> persisted to pending.json
          11. build_prealert(sig, r, guard, confluence=cr)       -> formatted Telegram text
          12. _send(s, text, channel=...)                        -> Telegram publish   *** NO PORTFOLIO CHECK ***
          13. ledger.log({"event":"heads_up", ...})

       (ii) dashboard_publish.main()  — refresh mobile dashboard from journal state every scan
```

**Objects passed between modules:** `pd.DataFrame` (OHLC, indexed by UTC timestamp) from
`markets.fetch` flows into every downstream call; `Signal` objects (from `signals.py`/`pending.py`)
carry `symbol, direction, entry, stop, target, rr, confidence, reasons, tier`; `ConfluenceResult`
objects (`cr`) carry `score, final_tier, agree[], disagree[]`; guard verdicts are plain dicts
(`action, penalty, grade_cap, size_factor, severity, macro_headwind, reasons, note`); `risk_guard`
verdicts are plain dicts (`locked, reason, day_r, open_n`). None of these objects, and no step in
either branch, currently carries or checks **portfolio-level** state — every decision is scoped to
the single symbol being evaluated in that loop iteration.

## 2. Where production risk validation is currently missing

Two existing gates run today, both **per-symbol, not portfolio-wide**:
- `risk_guard.evaluate(sym)` — per-symbol day-stop (−2R) and per-symbol position cap (max 1 open).
- `range_guard.evaluate(...)` — per-signal chase/dollar-headwind downgrade (`SUPPRESS_MODE=False`,
  so it can only downgrade/annotate, never block, by explicit design pending forward-test evidence).

**Nothing currently aggregates across symbols.** A -1.5R day on gold plus a -1.5R day on oil (a
-3R portfolio day, worse than the documented -2R account-wide rule in `RISK_RULES.md` rule #2) is
invisible to both gates. Simultaneous same-direction exposure across correlated symbols (e.g. long
gold + long BTC during a dollar-weakness regime) is never evaluated. `engine/risk.py`
(`position_size`, `portfolio_exposure`, `MAX_PORTFOLIO_RISK_PCT=6.0`) implements exactly this kind
of math but is **never imported** by `alert_signals.py` or `hourly_briefing.py` — only by
`tests/test_risk.py`. This confirms the Day 1 audit finding: institutional-grade portfolio logic
exists, fully tested in isolation, wired into nothing.

**Correct insertion point (per Phase 5 hierarchy, see `RISK_SPECIFICATION.md` §3):** after the
existing per-symbol `risk_guard`/`range_guard`/MAST-confluence gates have all passed, immediately
before `_send()` in both branches. This is the last point before an irreversible action
(Telegram publish) and the first point where all the inputs a portfolio check needs — confirmed
direction, confirmed symbol, the full open-book from `journal` — are all available.

## 3. The bypass path: `hourly_briefing.py`

Confirmed by fresh read: **no import of `risk_guard`, `range_guard`, `engine.risk`, or
`engine.portfolio_risk`(pre-Day-3) anywhere in `hourly_briefing.py`.** Its only suppression is a
news-blackout check (lines ~109-113). It calls `signals.analyze()` directly and publishes via its
own local `_post`/`send` — a fully parallel, independent implementation of the publish step that
does not share `alert_signals.py`'s gates.

**Every reachable entry point into `hourly_briefing.py`, confirmed by direct read/grep of the repo:**

| Launcher | Invokes | Trigger | Risk gates applied today |
|---|---|---|---|
| `4_SEND_SIGNAL_NOW.bat` | `hourly_briefing.py` directly | Manual double-click | News blackout only |
| `run_hourly_silent.bat` | `hourly_briefing.py` directly (via `pyw`/`pythonw`/`py` fallback) | Manual or scheduled | News blackout only |
| `START_HERE.bat` option 3 ("Send a signal now") | → `4_SEND_SIGNAL_NOW.bat` → `hourly_briefing.py` | Manual, from the main menu | News blackout only |
| `START_HERE.bat` option 11 ("Schedule 90-min briefings") | → `A_SCHEDULE_90MIN.bat` → `schtasks /Create ... "run_hourly_silent.bat" /SC MINUTE /MO 90` | **Standing Windows Scheduled Task, runs unattended every 90 minutes indefinitely once set up** | News blackout only |
| `check_hb.bat` | Static `ast.parse()` syntax check of `hourly_briefing.py` — does **not** execute `main()` or publish anything | N/A | N/A — not a publication path, excluded from Phase 8 scope |

**Most severe finding of Phase 1/8:** option 11 is not a one-off manual bypass — it is a
**silent, unattended, recurring** bypass. If ever activated, it runs `hourly_briefing.py`
every 90 minutes indefinitely with no risk_guard, no range_guard, and (until this change) no
portfolio check, until manually unregistered. This is addressed in Phase 8
(`RISK_SPECIFICATION.md` §6) by adding the same defense-in-depth gate directly inside
`hourly_briefing.py` itself, so *every* invocation path — known or future, manual or scheduled —
is covered without having to track down and edit every launcher individually.

## 4. Dashboard / journal (read side, no risk decisions made here)

`journal.py::stats()` / `track_record_lines()` and `dashboard_publish.py` only read already-settled
`journal.jsonl` rows; they make no publication decisions and are out of scope for this phase's risk
gating (they cannot themselves cause a trade to be sent).
