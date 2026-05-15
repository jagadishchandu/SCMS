"""Telegram Bot API sender — completely free, unlimited.

Parents must subscribe by opening the bot in Telegram and sending /start. The bot's
webhook captures their `chat_id` and we store it on the user record. From then on
we can send them messages via `sendMessage`.

Required env:
    TELEGRAM_BOT_TOKEN          — from @BotFather on Telegram
    TELEGRAM_WEBHOOK_SECRET     — optional but recommended: shared secret header

Setup (one-time):
    1. Talk to @BotFather, run /newbot, copy the token.
    2. Set TELEGRAM_BOT_TOKEN in your env.
    3. Hit  POST /api/webhooks/telegram/register-webhook  once to point Telegram at your
       /api/webhooks/telegram endpoint (uses the FRONTEND_URL/BACKEND_URL env vars).
    4. Share https://t.me/<your_bot_username> with parents, ask them to send /start.
"""
import os
import logging
import requests

log = logging.getLogger("scms.telegram")
TELEGRAM_API = "https://api.telegram.org"


def _enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"].strip()


def send_telegram(chat_id: int | str, body: str) -> tuple[bool, str | None]:
    """Returns (sent, message_id_or_error)."""
    if not _enabled():
        return False, None
    if not chat_id:
        return False, "no_chat_id"
    url = f"{TELEGRAM_API}/bot{_token()}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": body[:4096]}, timeout=12)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400 or not data.get("ok"):
            log.warning("Telegram send %s → %s: %s", chat_id, r.status_code, data)
            return False, data.get("description") or f"http_{r.status_code}"
        return True, str(data.get("result", {}).get("message_id", "telegram_ok"))
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False, str(e)


def set_webhook(public_url: str) -> tuple[bool, dict]:
    """Point Telegram at our webhook. `public_url` should be the full https URL
    ending in /api/webhooks/telegram (no trailing slash)."""
    if not _enabled():
        return False, {"error": "not_configured"}
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    payload = {"url": public_url, "allowed_updates": ["message"]}
    if secret:
        payload["secret_token"] = secret
    r = requests.post(f"{TELEGRAM_API}/bot{_token()}/setWebhook", json=payload, timeout=12)
    return r.ok, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text})
