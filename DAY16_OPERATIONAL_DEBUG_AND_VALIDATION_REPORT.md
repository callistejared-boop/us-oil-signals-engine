# Day 16 — Operational Debug and Validation Report

Closes out the Day 16 live-verification cycle. Supersedes the "leading
hypothesis" in `DAY16_LIVE_VERIFICATION_REPORT.md` (the empty-`SYMBOLS`
theory), which was tested against real authenticated Actions logs and
directly disproven. This report documents what actually happened, how it
was found, the two fixes applied, and the evidence that closes the
investigation.

## 1. Starting finding: infrastructure healthy, evidence layer dead

Initial live verification (~4h15m after the Day 15 push) found every
scheduled workflow green — `entry-scan.yml` and `heartbeat-watchdog.yml`
both running clean, on the latest code, on schedule. But `run_ledger.jsonl`
had not grown in 17 successful `entry-scan.yml` runs, `trades.json` and
`pending.json` were untouched, and all 14 Day 4–14 research/evidence files
still didn't exist on `origin/main`. A platform that looks fully green in
CI while producing zero evidence is a worse failure mode than a red build —
nothing in the Actions UI would ever surface it.

## 2. Investigation discipline

Rather than guess, the investigation moved in strictly evidence-gated
steps, each one only taken after the previous hypothesis was confirmed or
ruled out from real logs:

1. **Scheduler / deployment** — confirmed healthy (correct commit, on
   schedule, no red runs).
2. **Scan pipeline** — obtained authenticated step-level Actions logs
   (unauthenticated fetches only show run metadata, not step output) and
   confirmed all 4 symbols processed every run with live, varying
   confluence scores. This disproved the initial "empty `SYMBOLS` secret /
   zero symbols processed" hypothesis outright.
3. **Ledger writer** — instrumented `engine/ledger.py`'s `log()` with two
   temporary `print()` statements (before the write, and replacing the
   silent `except: pass` with a typed error message), scoped to that one
   function only. A live run (`#57`, commit `7cbfdd2`) showed 7 clean
   writes with zero exceptions — `ledger.log()` was never the problem.
4. **Persistence step** — instrumented the "Persist engine state" step in
   `entry-scan.yml` with `ls -l`, `git check-ignore -v`, `git status
   --short` before/after `git add`, and `git diff --cached --stat`, and
   removed the `2>/dev/null` suppression on `git add` so any hidden error
   would surface (commit `4838a2f`). Run `#58` immediately revealed the
   root cause.

## 3. Root cause #1 — atomic `git add` failure

```
fatal: pathspec 'confidence_history.jsonl' did not match any files
git add exited non-zero: 128
```

The persist step called `git add` once with a fixed list of 17 paths.
Several of those files (`confidence_history.jsonl`, the four `broker_*`
stores, `experiment_registry.jsonl`, `correlation_cache.json`) are
legitimately absent until their first real trigger — a confirmed/executed
trade, a registered research experiment — which had never happened in
production. When `git add` is given multiple pathspecs, a single
unmatched path makes it fail **atomically**: nothing is staged at all,
not even files that changed and did match. `run_ledger.jsonl` showed as
genuinely modified in `git status` both before and after the `git add`
call, because the add itself staged nothing. The old `2>/dev/null || true`
had been silently discarding this exact error on every run since Day 15
expanded the file list.

**Fix (commit `880e8c5`):** build the `git add` argument list from only
the paths that currently exist on disk. An as-yet-unborn optional history
file is normal, expected state, not an error.

## 4. Root cause #2 — dirty tree blocking `git pull --rebase`

Run `#59` (commit `880e8c5`) proved fix #1: `git add` succeeded, a local
commit was created (`c339559`, 5 files, 22 insertions). But the push still
failed all 5 retries:

```
error: cannot pull with rebase: You have unstaged changes.
error: Please commit or stash them.
```

`cot_cache.json`, `risk_sentiment_cache.json`, and `spread_cache.json` are
tracked files that change every run but are intentionally excluded from
the persisted-state list. Left dirty after the commit, they blocked `git
pull --rebase`, which refuses to run against a dirty working tree. This
bug had always existed but was unreachable until fix #1 let the workflow
get as far as attempting a commit. Confirmed independently: `origin/main`'s
`run_ledger.jsonl` was still 41 lines (original commit) after run `#59`.

**Fix (commit `2fd1e21`):** discard those leftover unstaged diffs with
`git checkout -- .` immediately after the commit, before attempting the
pull/rebase.

## 5. Verification

Run `#60` (commit `2fd1e21`) was the first run in the platform's history
where the persist step completed a full add → commit → checkout → rebase
→ push cycle successfully:

- `git add` exit code 0
- `git status --short` after add: 4 new files staged (`A`), `run_ledger.jsonl`
  modified (`M`)
- `git diff --cached --stat`: 5 files changed, 22 insertions(+)
- Local commit `3ab0da3` created
- Pull/rebase: "Current branch main is up to date" (clean tree)
- Push: `2fd1e21..3ab0da3 HEAD -> main` — succeeded

Confirmed independently via direct GitHub blob fetch (not log output):
`run_ledger.jsonl` grew from 41 to 45 lines, commit `3ab0da3` by
`gold-engine-bot`. `regime_history.jsonl`, `data_health_history.jsonl`,
`data_health_heartbeat_history.jsonl`, and `data_health_observations.jsonl`
all now exist on `origin/main` for the first time in the project's history.

## 6. Cleanup

Per standing practice of not leaving ad hoc debug output in production:

- `engine/ledger.py` reverted to its original silent `except: pass` form
  (commit `47da625`) — the temporary print statements are gone.
- `entry-scan.yml`'s persist step stripped of the `ls -l` / `check-ignore`
  / status / diff-stat diagnostic lines (commit `7343bb4`), keeping only
  the two permanent fixes: the existence-check loop before `git add`, and
  the post-commit `git checkout -- .` before the rebase.
- Re-verified on fully clean code with zero instrumentation: run `#61`
  pushed commit `b173acc`, taking `run_ledger.jsonl` to 49 lines.

## 7. Commit trail

| Commit | Purpose |
|---|---|
| `7cbfdd2` | Temp: instrument `ledger.log()` |
| `4838a2f` | Temp: instrument persist step (reveals root cause #1) |
| `880e8c5` | **Fix #1**: existence-check before `git add` |
| `2fd1e21` | **Fix #2**: discard dirty tree before `pull --rebase` |
| `3ab0da3` | First successful automated state commit (bot) |
| `47da625` | Cleanup: revert `ledger.py` instrumentation |
| `7343bb4` | Cleanup: remove persist-step diagnostics |
| `b173acc` | Verification: clean-code push (bot) |

## 8. Verdict

All four framing questions from the original runbook, now answered
affirmatively with direct evidence rather than log inference:

1. **Is the platform healthy?** Yes — infrastructure and evidence layer
   both confirmed operational.
2. **Is the evidence pipeline working?** Yes — `run_ledger.jsonl` and
   4 previously-orphaned research files are persisting to `origin/main`
   on every run.
3. **Is every subsystem persisting correctly?** The persistence mechanism
   itself is now correct and generalizes to any future file added to
   `STATE_FILES` — it will never again silently discard everything
   because one optional file hasn't been created yet.
4. **Is the platform ready to accumulate statistically meaningful
   paper-trading data?** Yes.

**Version status:**
- **V2.0 — Architecture: Complete.**
- **V2.1 — Operations: Operationally validated.**

The hold on Day 17 / V2.2 is lifted. Next work begins on the Strategy
Framework (Swing / Day / Scalping) as the first V2.2 milestone.
