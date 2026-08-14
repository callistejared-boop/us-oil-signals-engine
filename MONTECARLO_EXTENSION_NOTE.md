# Monte Carlo Extension — Recovery Time

**V2.2 Priority 4, Item 1** (`engine/montecarlo.py`)

## 1. What the audit said, and what was actually found

`PHASE0_FORENSIC_AUDIT.md` Section P:

> Monte Carlo depth — `engine/montecarlo.py` exists but is only 51 lines;
> your spec's requirements (median/95th-percentile/tail drawdown,
> probability of ruin, recovery time) need a closer read against what's
> actually implemented before deciding how much is genuinely missing vs.
> just needing extension.

Reading the full 51 lines before writing anything showed four of the five
named requirements already present and correct:

- median / percentile of total return: `total_r_p5` … `total_r_p95`
- tail drawdown: `max_dd_p50`, `max_dd_p95` (the 95th-percentile worst case)
- probability of ruin: `prob_ruin` against a configurable `ruin_r` threshold

**Recovery time was the one genuine gap.** Nothing in the module measured
how many trades a simulated path took to climb back out of its own
drawdown.

## 2. What was built

Two additions to `engine/montecarlo.py`, no changes to any existing
key or existing logic:

- `_recovery_trades(eq)` — given one simulated path's cumulative-R
  equity curve, finds the deepest drawdown, then measures the number of
  trades from the peak that preceded it to the first point the path
  climbs back to that peak level. Returns `0.0` if the path never drew
  down at all, and `None` if the drawdown is still open when the
  simulated path ends (censored — can't report a recovery time for a
  recovery that hasn't happened).
- `simulate()` now aggregates that per-path measurement across all
  `n_paths`: `recovery_trades_p50` / `recovery_trades_p95` (median and
  tail recovery time, in trades, over paths that did recover — `None` if
  no path in the batch ever drew down), and `prob_never_recovered` (the
  fraction of paths whose drawdown was still open at the end of the
  simulated horizon — a real risk signal in its own right, since it means
  the strategy's worst case isn't just "how deep" but "does it come back
  in the time window at all").

`engine/report.py`'s HTML report renders every key in the Monte Carlo
dict generically (`for k, v in mc.items()`), so the new fields appear in
the report with no wiring changes needed.

## 3. Test coverage

`tests/test_montecarlo.py`, 14 tests: six regression tests pinning the
pre-existing behavior (percentiles, ruin probability, determinism under a
fixed seed, all original output keys still present) so this extension
can't silently change the numbers callers already depend on, five tests
on the new recovery fields (all-winners series has no drawdown to
recover from, a series with a real drawdown produces a positive
recovery time with p95 >= p50, an all-losing series never recovers),
and three direct unit tests of the `_recovery_trades` helper covering
the zero/measured/censored cases explicitly.
