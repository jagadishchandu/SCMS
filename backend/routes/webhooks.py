"""Public webhook endpoints for incoming messages from messaging providers.

- Meta WhatsApp:
    GET  /api/webhooks/whatsapp   handshake verification (hub.challenge)
    POST /api/webhooks/whatsapp   status updates + incoming user messages
- Telegram:
    POST /api/webhooks/telegram   bot updates (captures chat_id when parent /starts the bot)

None of these endpoints require authentication — Meta/Telegram identify themselves via
shared secrets (verify_token / X-Telegram-Bot-Api-Secret-Token) or signed payloads.
"""
import os
import logging
from fastapi import APIRouter, Request, Response, HTTPException, Header

from core.db import get_db
from core.utils import new_id, utc_now
from core import meta_whatsapp as meta_wa
from core import telegram_sender as tg

log = logging.getLogger("scms.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------- Meta WhatsApp ----------------

@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str | None = None,
    hub_verify_token: str | None = None,
    hub_challenge: str | None = None,
    request: Request = None,
):
    # FastAPI may not auto-map hyphenated query keys — read from request directly.
    qp = request.query_params if request else {}
    mode = qp.get("hub.mode", hub_mode or "")
    token = qp.get("hub.verify_token", hub_verify_token or "")
    challenge = qp.get("hub.challenge", hub_challenge or "")
    ok = meta_wa.verify_webhook(mode, token, challenge)
    if ok is None:
        raise HTTPException(status_code=403, detail="verification_failed")
    return Response(content=ok, media_type="text/plain")


@router.post("/whatsapp")
async def whatsapp_event(payload: dict):
    """Persist message status updates + inbound parent messages."""
    db = get_db()
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            # Statuses (sent/delivered/read/failed)
            for st in value.get("statuses", []) or []:
                await db.whatsapp_status_updates.insert_one({
                    "id": new_id(),
                    "message_id": st.get("id"),
                    "status": st.get("status"),
                    "recipient": st.get("recipient_id"),
                    "timestamp": st.get("timestamp"),
                    "raw": st,
                    "received_at": utc_now(),
                })
                # Try to update the corresponding notification row too
                if st.get("id") and st.get("status") in ("delivered", "read", "failed"):
                    await db.notifications.update_one(
                        {"provider_sid": st["id"]},
                        {"$set": {"delivery_status": st["status"], "delivery_updated_at": utc_now()}},
                    )
            # Inbound user messages
            for msg in value.get("messages", []) or []:
                await db.whatsapp_inbound.insert_one({
                    "id": new_id(),
                    "from": msg.get("from"),
                    "message_id": msg.get("id"),
                    "type": msg.get("type"),
                    "text": (msg.get("text") or {}).get("body"),
                    "raw": msg,
                    "received_at": utc_now(),
                })
    return {"ok": True}


# ---------------- Telegram ----------------

@router.post("/telegram")
async def telegram_event(
    payload: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Handle Telegram bot updates. The critical job is to capture chat_id when
    a parent sends /start so we can later send them messages.
    """
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=401, detail="bad_telegram_secret")

    msg = payload.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return {"ok": True}

    db = get_db()
    # Store every update for auditability
    await db.telegram_inbound.insert_one({
        "id": new_id(),
        "chat_id": chat_id,
        "username": chat.get("username"),
        "first_name": chat.get("first_name"),
        "text": text,
        "raw": payload,
        "received_at": utc_now(),
    })

    # /start <code>   → bind this chat_id to the user whose phone matches the code
    # /start          → ask them to send their phone number
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if code:
            # Code is the parent's phone or student_uid — try both
            user = await db.users.find_one({
                "$or": [
                    {"phone": code},
                    {"phone": "+" + code},
                    {"email": code.lower()},
                ],
            }) or None
            if not user:
                # try to find by student_uid → parent_user_id
                student = await db.students.find_one({"student_uid": code.upper()})
                if student and student.get("parent_user_id"):
                    user = await db.users.find_one({"id": student["parent_user_id"]})
            if user:
                await db.users.update_one(
                    {"id": user["id"]},
                    {"$set": {"telegram_chat_id": chat_id, "telegram_linked_at": utc_now()}},
                )
                tg.send_telegram(chat_id, "✅ You're linked. You'll receive school updates here.")
                return {"ok": True, "linked": True, "user_id": user["id"]}
        tg.send_telegram(
            chat_id,
            "Hi! To link your school account, send /start followed by your student UID "
            "(for example: /start STU-00001) or your registered email.",
        )

    return {"ok": True}


@router.post("/telegram/set-webhook")
async def telegram_set_webhook(public_url: str):
    """Convenience endpoint. POST with ?public_url=https://your-domain.com/api/webhooks/telegram"""
    ok, data = tg.set_webhook(public_url)
    return {"ok": ok, "telegram_response": data}
