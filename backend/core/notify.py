"""Notification helper: WhatsApp via Twilio (if configured) + DB log fallback."""
import os
import logging
from .db import get_db
from .utils import new_id, utc_now

log = logging.getLogger("scms.notify")

_twilio_client = None


def _twilio():
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        _twilio_client = Client(sid, token)
        return _twilio_client
    except Exception as e:
        log.warning("Twilio init failed: %s", e)
        return None


def _format_whatsapp_number(phone: str | None) -> str | None:
    if not phone:
        return None
    p = str(phone).strip().replace(" ", "").replace("-", "")
    if not p.startswith("+"):
        # Assume Indian number if 10 digits
        if len(p) == 10 and p.isdigit():
            p = "+91" + p
        else:
            return None
    return f"whatsapp:{p}"


def send_whatsapp(to_phone: str, body: str) -> tuple[bool, str | None, str | None]:
    """Returns (sent, sid_or_error, channel)."""
    client = _twilio()
    if client is None:
        return False, None, None  # not configured, will stay "queued"
    sender = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
    if not sender:
        return False, "TWILIO_WHATSAPP_FROM not set", "whatsapp"
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    to = _format_whatsapp_number(to_phone)
    if not to:
        return False, "invalid_phone", "whatsapp"
    try:
        msg = client.messages.create(from_=sender, body=body, to=to)
        return True, msg.sid, "whatsapp"
    except Exception as e:
        log.warning("Twilio send failed to %s: %s", to, e)
        return False, str(e), "whatsapp"


async def queue_notification(
    school_id: str,
    recipient_type: str,
    recipient_id: str | None,
    phone: str | None,
    channel: str,
    template: str,
    message: str,
    context: dict | None = None,
):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": school_id,
        "recipient_type": recipient_type,
        "recipient_id": recipient_id,
        "phone": phone,
        "channel": channel,
        "template": template,
        "message": message,
        "context": context or {},
        "status": "queued",
        "created_at": utc_now(),
    }

    # Attempt real delivery for whatsapp channel
    if channel == "whatsapp" and phone:
        sent, sid_or_err, _ = send_whatsapp(phone, message)
        if sent:
            doc["status"] = "sent"
            doc["provider_sid"] = sid_or_err
            doc["sent_at"] = utc_now()
        elif sid_or_err is None:
            # Twilio not configured — stay queued (mock log)
            doc["status"] = "queued"
            doc["delivery_note"] = "twilio_not_configured"
        else:
            doc["status"] = "failed"
            doc["delivery_error"] = sid_or_err

    await db.notifications.insert_one(doc)
    return doc
