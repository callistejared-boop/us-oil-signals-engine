"""Standalone Telegram test — stdlib only, no pip installs required.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env and sends one
message, then writes the result to diag.txt so it can be confirmed.
"""
import json
import pathlib
import urllib.parse
import urllib.request

root = pathlib.Path(__file__).resolve().parent
cfg = {}
for line in (root / ".env").read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        cfg[k.strip()] = v.strip()

tok = cfg.get("TELEGRAM_BOT_TOKEN", "")
chat = cfg.get("TELEGRAM_CHAT_ID", "")
msg = ("✅ Gold Engine connected. XAUUSD signals will arrive here.\n"
       "You'll only be messaged when a setup clears every filter "
       "(bias + structure + FVG entry + RR≥2 + confluence≥70).")

out = root / "diag.txt"
try:
    data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
    req = urllib.request.urlopen(
        f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
    resp = json.load(req)
    ok = resp.get("ok", False)
    out.write_text(f"sendMessage ok={ok}\n"
                   f"message_id={resp.get('result', {}).get('message_id')}\n")
    print("OK" if ok else f"FAILED: {resp}")
except Exception as exc:  # noqa: BLE001
    out.write_text(f"ERROR: {type(exc).__name__}: {exc}\n")
    print(f"ERROR: {exc}")
