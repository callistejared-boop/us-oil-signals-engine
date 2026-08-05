"""Watchdog: alerts if the engine's heartbeat has gone stale.

Added 2026-07-28 — this is the "watchdog heartbeat on the scheduler" item
from the roadmap's backlog, made concrete now that the GitHub Actions
migration is code-complete. Sends exactly one Telegram DM if the engine's
heartbeat is older than STALE_MINUTES — the point is to notice the whole
pipeline going silent (GitHub Actions broken, secrets misconfigured, repo
not pushed yet, every symbol's data fetch failing) before the user does,
not to editorialize on trading.

Day 15 fix — read source changed: this used to read alert_heartbeat.txt,
written every scan by alert_signals.py. That file is (correctly)
gitignored, and entry-scan.yml's persist step never committed it, so on
this workflow's own fresh `actions/checkout@v4` it could never actually
be present — heartbeat_age_minutes() always returned None, "not launched
yet", and no alert could ever fire. Confirmed as the root cause of an 11+
day silent gap on Day 15 (see DAY15_IMPLEMENTATION_REPORT.md). Fixed by
reading .cache/heartbeat_status.json instead — the SAME .cache/ directory
entry-scan.yml already round-trips across ephemeral runners via
actions/cache (see that workflow's "Restore last-known-good market data
cache" step), so this rides an existing, already-working persistence
mechanism. This workflow now restores that same cache before running (see
heartbeat-watchdog.yml). alert_heartbeat.txt is still read as a fallback,
purely for local/manual runs where no cache restore step exists.

Deliberately quiet, not alarmist:
  - No status file at all -> treated as "not launched yet", not a fault.
    Logs and exits quietly. This is the expected state before the user has
    pushed this repo to GitHub and configured the Actions secrets (or,
    now, before the cache has been populated by a first entry-scan run).
  - Heartbeat present but stale -> exactly one DM (not a channel post -
    this is an operational health signal for the owner, not a trade idea).
  - Never raises; a bug in the watchdog itself must never look like, or
    cause, a pipeline failure. Every failure mode degrades to a printed
    log line, same fail-safe discipline as the rest of the engine.
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

STALE_MINUTES = 45   # entry-scan.yml runs every 15 min; 45 gives 2 missed runs of slack


def _age_from_scan_status(path):
    """Minutes since .cache/heartbeat_status.json's own "ts" field, or
    None if missing/unreadable. Also returns the parsed record (or None)
    so main() can mention *why* it's stale (e.g. a total data outage),
    not just that it is."""
    path = pathlib.Path(path)
    if not path.exists():
        return None, None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(record["ts"])
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
        return age, record
    except Exception:  # noqa: BLE001
        return None, None


def _age_from_legacy_heartbeat_txt(path):
    """Minutes since alert_heartbeat.txt's own timestamp, or None if the
    file is missing/unreadable. Local/manual-run fallback only — see
    module docstring for why this is no longer the primary source."""
    path = pathlib.Path(path)
    if not path.exists():
        return None
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        ts_str = first_line.split("[")[0].strip()   # strip "[NEWS BLACKOUT]" etc.
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


def heartbeat_age_minutes(path=None):
    """Minutes since alert_heartbeat.txt's (or the given path's) own
    timestamp, or None if missing/unreadable. Unchanged signature/
    behavior from before Day 15 — kept as its own function, still reading
    the plain-text legacy heartbeat format, specifically so callers (and
    the existing tests exercising it directly) that only care about that
    one file don't need to know about the newer, structured status file.
    See scan_status() for the primary, cache-backed check main() now
    uses."""
    hb = path or (ROOT / "alert_heartbeat.txt")
    return _age_from_legacy_heartbeat_txt(hb)


def scan_status(path=None, legacy_path=None):
    """The primary health check as of Day 15: tries the durable
    .cache/heartbeat_status.json first (populated by alert_signals.py,
    round-tripped across ephemeral runners via actions/cache — see module
    docstring), falls back to the legacy alert_heartbeat.txt for local/
    manual runs where no cache restore step exists. Returns
    (age_minutes|None, record|None) — record is only populated from the
    structured status file (None when falling back to the legacy text
    heartbeat, which carries no outage detail)."""
    status_path = path or (ROOT / ".cache" / "heartbeat_status.json")
    age, record = _age_from_scan_status(status_path)
    if age is not None:
        return age, record
    hb = legacy_path or (ROOT / "alert_heartbeat.txt")
    return _age_from_legacy_heartbeat_txt(hb), None


def _send_dm(text: str) -> bool:
    try:
        from engine import config
        s = config.load()
        if not s.telegram_bot_token or not s.telegram_chat_id:
            print("heartbeat_watchdog: stale, but Telegram not configured — cannot alert.")
            return False
        data = urllib.parse.urlencode({"chat_id": s.telegram_chat_id, "text": text}).encode()
        with urllib.request.urlopen(
                "https://api.telegram.org/bot" + s.telegram_bot_token + "/sendMessage",
                data=data, timeout=20):
            pass
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"heartbeat_watchdog: stale, but alert failed to send ({exc})")
        return False


def main():
    age, record = scan_status()
    if age is None:
        print("heartbeat_watchdog: no heartbeat file yet (engine not launched, "
              "or file unreadable) — nothing to check.")
        return
    print(f"heartbeat_watchdog: last heartbeat {age:.0f} min ago (threshold {STALE_MINUTES})")
    # Day 15: a fresh-but-total-outage scan (every symbol failed to fetch
    # data) is itself worth flagging even when age is well within
    # STALE_MINUTES — the scan loop is running on schedule, but producing
    # nothing usable. Same one-DM-per-transition discipline as the
    # staleness check below: only alert here on the CURRENT run's outcome,
    # never repeat every 15 min for an ongoing outage (that's what the
    # workflow's own failed-run status is for; see alert_signals.py).
    if record and record.get("total_data_outage"):
        text = (f"⚠️ Engine scan ran on schedule but every symbol failed to fetch "
                f"market data ({record.get('symbols')}). Check GitHub Actions "
                f"'Entry scan' run logs and TWELVEDATA_API_KEY.")
        ok = _send_dm(text)
        print(f"heartbeat_watchdog: total data outage this scan — alert {'sent' if ok else 'NOT sent'}.")
        return
    if age <= STALE_MINUTES:
        print("heartbeat_watchdog: healthy.")
        return
    text = (f"⚠️ Engine heartbeat is stale: last update {age:.0f} minutes ago "
            f"(expected every ~15 min). Check GitHub Actions runs for failures.")
    ok = _send_dm(text)
    print(f"heartbeat_watchdog: stale — alert {'sent' if ok else 'NOT sent'}.")


if __name__ == "__main__":
    main()
