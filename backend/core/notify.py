"""Notification helper: stores WhatsApp-style notifications in DB.
In production this would call Twilio/WhatsApp Business API; for now it persists
a record marked as 'queued' which can be processed by a worker."""
from .db import get_db
from .utils import new_id, utc_now


async def queue_notification(
    school_id: str,
    recipient_type: str,  # parent | teacher | student | admin
    recipient_id: str | None,
    phone: str | None,
    channel: str,  # whatsapp | sms | email | in_app
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
    await db.notifications.insert_one(doc)
    return doc
