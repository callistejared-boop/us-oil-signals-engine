"""Watchdog: alerts if the engine's heartbeat has gone stale.

Added 2026-07-28 — this is the "watchdog heartbeat on the scheduler" item
from the roadmap's backlog, made concrete now that the GitHub Actions
migration is code-complete. Reads alert_heartbeat.txt (written every ~15
minutes by alert_signals.py's entry-scan job, the most frequent job in the
pipeline) and sends exactly one Telegram DM if it's older than
STALE_MINUTES — the point is to notice the whole pipeline going silent
(GitHub Actions broken, secrets misconfigured, repo not pushed yet) before
the user does, not to editorialize on trading.

Deliberately quiet, not alarmist:
  - No heartbeat file at all -> treated as "not launched yet", not a fault.
    Logs and exits quietly. This is the expected state before the user has
    pushed this repo to GitHub and configured the Actions secrets.
  - Heartbeat present but stale -> exactly one DM (not a channel post -
    this is an operational health signal for the owner, not a trade idea).
  - Never raises; a bug in the watchdog itself must never look like, or
    cause, a pipeline failure. Every failure mode degrades to a printed
    log line, same fail-safe discipline as the rest of the engine.
"""
import pathlib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

STALE_MINUTES = 45   # entry-scan.yml runs every 15 min; 45 gives 2 missed runs of slack


def heartbeat_age_minutes(path=None):
    """Minutes since alert_heartbeat.txt's own timestamp, or None if the
    file is missing/unreadable (treated as 'not launched yet', not stale)."""
    hb = path or (ROOT / "alert_heartbeat.txt")
    hb = pathlib.Path(hb)
    if not hb.exists():
        return None
    try:
        first_line = hb.read_text(encoding="utf-8").splitlines()[0]
        ts_str = first_line.split("[")[0].strip()   # strip "[NEWS BLACKOUT]" etc.
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


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
    age = heartbeat_age_minutes()
    if age is None:
        print("heartbeat_watchdog: no heartbeat file yet (engine not launched, "
              "or file unreadable) — nothing to check.")
        return
    print(f"heartbeat_watchdog: last heartbeat {age:.0f} min ago (threshold {STALE_MINUTES})")
    if age <= STALE_MINUTES:
        print("heartbeat_watchdog: healthy.")
        return
    text = (f"⚠️ Engine heartbeat is stale: last update {age:.0f} minutes ago "
            f"(expected every ~15 min). Check GitHub Actions runs for failures.")
    ok = _send_dm(text)
    print(f"heartbeat_watchdog: stale — alert {'sent' if ok else 'NOT sent'}.")


if __name__ == "__main__":
    main()
