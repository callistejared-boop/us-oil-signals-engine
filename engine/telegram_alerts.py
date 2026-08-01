"""Telegram delivery via the official Bot API (free).

Sends to the private DM and, when TELEGRAM_CHANNEL is set, also to the
public channel that the app reads as its live feed.
"""
from __future__ import annotations

import requests

from .config import Settings
from .signals import Signal


def _post(token: str, chat: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat, "text": text}, timeout=20)
    ok = r.ok and r.json().get("ok", False)
    if not ok:
        print(f"[telegram] send to {chat} failed: {r.status_code} {r.text[:200]}")
    return ok


def send_message(settings: Settings, text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("[telegram] not configured (set TELEGRAM_BOT_TOKEN and "
              "TELEGRAM_CHAT_ID in .env); printing instead:\n" + text)
        return False
    ok = _post(settings.telegram_bot_token, settings.telegram_chat_id, text)
    if settings.telegram_channel:
        _post(settings.telegram_bot_token, settings.telegram_channel, text)
    return ok


def send_signal(settings: Settings, sig: Signal) -> bool:
    return send_message(settings, sig.as_text())
