"""Alerts. Sends a Telegram message if TELEGRAM_TOKEN + TELEGRAM_CHAT_ID are set;
otherwise logs to stdout. Never a hard dependency, never crashes the bot."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import CONFIG


def alert(message: str) -> None:
    print(f"[alert] {message}")
    if not (CONFIG.telegram_token and CONFIG.telegram_chat_id):
        return
    try:
        url = f"https://api.telegram.org/bot{CONFIG.telegram_token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": CONFIG.telegram_chat_id, "text": message}
        ).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as e:  # noqa: BLE001 - alerts must never take the bot down
        print(f"[alert] Telegram send failed (non-fatal): {e}")
