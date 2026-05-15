"""Meta WhatsApp Business Cloud API sender.

Free tier: 1000 conversations / month.
Docs: https://developers.facebook.com/docs/whatsapp/cloud-api

Required env:
    META_WHATSAPP_PHONE_ID      — numeric phone number id (from Meta App Dashboard → WhatsApp → API Setup)
    META_WHATSAPP_ACCESS_TOKEN  — long-lived system user token
    META_WHATSAPP_VERIFY_TOKEN  — arbitrary secret string for webhook handshake (you pick this)
    META_WHATSAPP_API_VERSION   — optional, defaults to v21.0
"""
import os
import logging
import requests

log = logging.getLogger("scms.meta_whatsapp")


def _enabled() -> bool:
    return bool(os.environ.get("META_WHATSAPP_PHONE_ID", "").strip()
                and os.environ.get("META_WHATSAPP_ACCESS_TOKEN", "").strip())


def send_whatsapp(phone_e164: str, body: str) -> tuple[bool, str | None, dict | None]:
    """Returns (sent, message_id_or_error, raw_response)."""
    if not _enabled():
        return False, None, None
    if not phone_e164:
        return False, "invalid_recipient", None
    phone_id = os.environ["META_WHATSAPP_PHONE_ID"].strip()
    token = os.environ["META_WHATSAPP_ACCESS_TOKEN"].strip()
    api_ver = os.environ.get("META_WHATSAPP_API_VERSION", "v21.0").strip() or "v21.0"
    # Strip "whatsapp:" prefix if present (Twilio-style), keep +sign optional
    to = phone_e164.replace("whatsapp:", "").lstrip("+").strip()
    url = f"https://graph.facebook.com/{api_ver}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4096]},  # WhatsApp body cap
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        data = {}
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            log.warning("Meta WhatsApp %s → %s: %s", to, r.status_code, data)
            return False, f"http_{r.status_code}: {data.get('error', {}).get('message') or data}", data
        msg_id = ""
        if isinstance(data.get("messages"), list) and data["messages"]:
            msg_id = data["messages"][0].get("id", "")
        return True, msg_id or "meta_ok", data
    except Exception as e:
        log.warning("Meta WhatsApp send failed: %s", e)
        return False, str(e), None


def verify_webhook(mode: str, verify_token: str, challenge: str) -> str | None:
    """Returns the challenge to echo back when handshake is valid; else None."""
    expected = os.environ.get("META_WHATSAPP_VERIFY_TOKEN", "").strip()
    if mode == "subscribe" and expected and verify_token == expected:
        return challenge
    return None
