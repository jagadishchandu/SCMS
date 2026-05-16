"""Notification helper: WhatsApp via Meta Cloud API or Twilio (Meta preferred when
configured) + Email via SMTP + Telegram bot + DB log fallback.

Channel selection inside `queue_notification`:
- channel="whatsapp" → tries Meta Cloud API first, then Twilio, else stays queued.
- channel="email"    → SMTP send.
- channel="telegram" → requires recipient_user.telegram_chat_id; Telegram Bot API.
"""
import os
import logging
from .db import get_db
from .utils import new_id, utc_now
from .email_sender import send_email
from . import meta_whatsapp as meta_wa
from . import telegram_sender as tg

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
    """Returns (sent, sid_or_error, provider).
    Tries Meta Cloud API first (free 1000/month), then falls back to Twilio.
    """
    # 1. Meta WhatsApp Cloud API (free tier)
    if meta_wa._enabled():
        sent, sid_or_err, _raw = meta_wa.send_whatsapp(to_phone, body)
        if sent:
            return True, sid_or_err, "meta_whatsapp"
        # if Meta fails with a clear error, log and try Twilio as backup
        log.info("Meta WhatsApp returned error, trying Twilio: %s", sid_or_err)

    # 2. Twilio (paid, backup)
    client = _twilio()
    if client is None:
        return False, None, None  # neither provider configured → stay "queued"
    sender = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
    if not sender:
        return False, "TWILIO_WHATSAPP_FROM not set", "twilio_whatsapp"
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    to = _format_whatsapp_number(to_phone)
    if not to:
        return False, "invalid_phone", "twilio_whatsapp"
    try:
        msg = client.messages.create(from_=sender, body=body, to=to)
        return True, msg.sid, "twilio_whatsapp"
    except Exception as e:
        log.warning("Twilio send failed to %s: %s", to, e)
        return False, str(e), "twilio_whatsapp"


async def queue_notification(
    school_id: str,
    recipient_type: str,
    recipient_id: str | None,
    phone: str | None,
    channel: str,
    template: str,
    message: str,
    context: dict | None = None,
    email: str | None = None,
    subject: str | None = None,
    telegram_chat_id: int | str | None = None,
):
    db = get_db()
    # Auto-resolve telegram_chat_id from the recipient's user record if not supplied.
    # This lets callers (e.g. fee_invoice / attendance / exam) trigger fallback
    # delivery via Telegram without each call-site having to look it up.
    if not telegram_chat_id and recipient_id:
        try:
            u = await db.users.find_one({"id": recipient_id}, {"_id": 0, "telegram_chat_id": 1})
            if u and u.get("telegram_chat_id"):
                telegram_chat_id = u["telegram_chat_id"]
        except Exception:
            pass
    doc = {
        "id": new_id(),
        "school_id": school_id,
        "recipient_type": recipient_type,
        "recipient_id": recipient_id,
        "phone": phone,
        "email": email,
        "telegram_chat_id": telegram_chat_id,
        "subject": subject,
        "channel": channel,
        "template": template,
        "message": message,
        "context": context or {},
        "status": "queued",
        "created_at": utc_now(),
    }

    # WhatsApp — Meta → Twilio → queued; falls back to Telegram if recipient is linked.
    if channel == "whatsapp" and phone:
        sent, sid_or_err, provider = send_whatsapp(phone, message)
        if sent:
            doc["status"] = "sent"
            doc["provider_sid"] = sid_or_err
            doc["provider"] = provider
            doc["sent_at"] = utc_now()
        elif provider is None:
            doc["status"] = "queued"
            doc["delivery_note"] = "whatsapp_not_configured"
        else:
            doc["status"] = "failed"
            doc["provider"] = provider
            doc["delivery_error"] = sid_or_err
        # Fallback: if WhatsApp didn't actually send and the recipient has a
        # linked Telegram chat, deliver the same message via Telegram so the
        # parent/teacher still gets a real-time alert.
        if doc["status"] != "sent" and telegram_chat_id:
            ok, tg_sid_or_err = tg.send_telegram(telegram_chat_id, message)
            if ok:
                doc["status"] = "sent"
                doc["provider"] = "telegram_fallback"
                doc["provider_sid"] = tg_sid_or_err
                doc["sent_at"] = utc_now()
                doc["delivery_note"] = "delivered_via_telegram_fallback"

    # SMS — Twilio (also tries Telegram fallback if recipient is linked)
    elif channel == "sms" and phone:
        ok = False
        client = _twilio()
        sender = os.environ.get("TWILIO_SMS_FROM", "").strip()
        if client and sender:
            try:
                msg = client.messages.create(from_=sender, body=message, to=phone if phone.startswith("+") else f"+{phone}")
                doc["status"] = "sent"
                doc["provider"] = "twilio_sms"
                doc["provider_sid"] = msg.sid
                doc["sent_at"] = utc_now()
                ok = True
            except Exception as e:
                doc["status"] = "failed"
                doc["delivery_error"] = str(e)
                doc["provider"] = "twilio_sms"
        else:
            doc["status"] = "queued"
            doc["delivery_note"] = "sms_not_configured"
        if not ok and telegram_chat_id:
            tok, tg_sid_or_err = tg.send_telegram(telegram_chat_id, message)
            if tok:
                doc["status"] = "sent"
                doc["provider"] = "telegram_fallback"
                doc["provider_sid"] = tg_sid_or_err
                doc["sent_at"] = utc_now()
                doc["delivery_note"] = "delivered_via_telegram_fallback"

    # Email — SMTP
    elif channel == "email" and email:
        sent, sid_or_err = send_email(email, subject or "Update from your school", message)
        if sent:
            doc["status"] = "sent"
            doc["provider"] = "smtp"
            doc["provider_sid"] = sid_or_err
            doc["sent_at"] = utc_now()
        elif sid_or_err is None:
            doc["status"] = "queued"
            doc["delivery_note"] = "smtp_not_configured"
        else:
            doc["status"] = "failed"
            doc["provider"] = "smtp"
            doc["delivery_error"] = sid_or_err

    # Telegram — bot sendMessage
    elif channel == "telegram" and telegram_chat_id:
        sent, sid_or_err = tg.send_telegram(telegram_chat_id, message)
        if sent:
            doc["status"] = "sent"
            doc["provider"] = "telegram"
            doc["provider_sid"] = sid_or_err
            doc["sent_at"] = utc_now()
        elif sid_or_err is None:
            doc["status"] = "queued"
            doc["delivery_note"] = "telegram_not_configured"
        else:
            doc["status"] = "failed"
            doc["provider"] = "telegram"
            doc["delivery_error"] = sid_or_err

    await db.notifications.insert_one(doc)
    return doc
