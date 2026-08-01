"""Rename the Telegram channel's DISPLAY TITLE to 'US Oil Signals'.

Uses the bot's setChatTitle (works only if the bot is an admin of the channel
with the 'change info' right). NOTE: the public @handle (@jaredwticrudesignals)
cannot be changed by a bot — that's a manual change in Telegram if you want it.
Fail-safe: prints the result, never throws.
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import config, markets  # noqa: E402

TITLE = "US Oil Signals"
DESC = "Institutional US Oil (WTI) signals — ICT/SMC + live news. Research/education only."


def api(token, method, params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(url, data=data, timeout=25))


def main():
    s = config.load()
    ch = markets.channel_for("WTIUSD", s)
    if not ch:
        print("no channel configured — nothing to rename")
        return
    for method, params in (("setChatTitle", {"chat_id": ch, "title": TITLE}),
                           ("setChatDescription", {"chat_id": ch, "description": DESC})):
        try:
            r = api(s.telegram_bot_token, method, params)
            print(f"{method}: ok={r.get('ok')} {r.get('description', '')}")
        except Exception as exc:  # noqa: BLE001
            print(f"{method}: ERROR {exc}")
    print(f"channel: {ch}  (the @handle itself can only be changed manually in Telegram)")


if __name__ == "__main__":
    main()
