"""Post a market overview / announcement to the DM and public channel.
Reads credentials from .env (the program uses its own config)."""
import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
cfg = {}
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        cfg[k.strip()] = v.strip()

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
msg = (
    "📌 XAUUSD SIGNALS — MARKET OVERVIEW\n"
    f"{now}\n\n"
    "Big session today. High-impact USD news is on the calendar, so we are "
    "stepping up coverage:\n\n"
    "• Briefings now every 15 MINUTES (up from hourly).\n"
    "• The engine automatically STANDS ASIDE inside news blackout windows "
    "(~20 min before to ~15 min after high-impact releases) to protect the "
    "track record.\n"
    "• Signals still fire ONLY when confluence >= 70 and risk:reward >= 2 — "
    "quality over quantity.\n\n"
    "Expect frequent structure + technical updates through the session. Trade "
    "your own plan and manage your risk.\n\n"
    "Research/education only — not financial advice."
)

tok = cfg.get("TELEGRAM_BOT_TOKEN", "")
results = {}
for label, chat in (("dm", cfg.get("TELEGRAM_CHAT_ID", "")),
                    ("channel", cfg.get("TELEGRAM_CHANNEL", ""))):
    if not chat:
        continue
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
        r = urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
        results[label] = json.load(r).get("ok", False)
    except Exception as exc:  # noqa: BLE001
        results[label] = f"ERROR: {exc}"

(ROOT / "overview_result.txt").write_text(str(results), encoding="utf-8")
print(results)
