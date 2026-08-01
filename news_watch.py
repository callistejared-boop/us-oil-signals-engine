"""5-minute watcher: reads the freshly-written feed and fires bias-flip alerts
to your Telegram DM. Runs after fundamentals_feed in the scheduled job. Reads
the feed file (no refetch) so it is cheap and fail-safe.
"""
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import config, fundamentals_feed as ff, news_alerts  # noqa: E402


def _send(s, text):
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return
    data = urllib.parse.urlencode({"chat_id": s.telegram_chat_id, "text": text}).encode()
    urllib.request.urlopen(
        "https://api.telegram.org/bot" + s.telegram_bot_token + "/sendMessage",
        data=data, timeout=25)


def main():
    data = ff.read_feed_raw()
    if not data or "symbols" not in data or not data["symbols"]:
        print("news_watch: no live feed yet - nothing to check.")
        return
    s = config.load()
    fired = news_alerts.run(data, lambda t: _send(s, t))
    if fired:
        for c in fired:
            print(f"ALERT: {c['sym']} {c['old']} -> {c['new']} [{c['strength']}]")
    else:
        print("news_watch: no bias flips this cycle.")


if __name__ == "__main__":
    main()
