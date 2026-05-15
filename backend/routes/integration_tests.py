"""Test-message endpoints — let School Admins validate WhatsApp / Telegram / SMTP
credentials without sending a real production message.

All endpoints are restricted to school_admin + platform_admin.

Returns a structured result:
    {
      "ok": bool,
      "provider": "meta_whatsapp" | "twilio_whatsapp" | "telegram" | "smtp" | null,
      "message_id": "...",     # provider message ID when ok
      "error": "...",          # when not ok
      "configured": bool       # whether env vars look set
    }
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core.auth import require_roles
from core import meta_whatsapp as meta_wa
from core import telegram_sender as tg
from core.email_sender import send_email, _enabled as _smtp_enabled
from core.notify import _twilio, _format_whatsapp_number


router = APIRouter(prefix="/integrations/test", tags=["integration-tests"])


def _default_test_body() -> str:
    return ("✅ SCMS test message — your integration is configured correctly. "
            "You can ignore this message.")


class WhatsAppTest(BaseModel):
    to: str  # E.164 phone like +919999999999


class TelegramTest(BaseModel):
    chat_id: int | str | None = None  # If omitted, falls back to user.telegram_chat_id


class EmailTest(BaseModel):
    to: EmailStr


# ---------------- WhatsApp ----------------

@router.post("/whatsapp")
async def test_whatsapp(payload: WhatsAppTest, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    meta_on = meta_wa._enabled()
    twilio_on = _twilio() is not None
    if not meta_on and not twilio_on:
        return {
            "ok": False,
            "provider": None,
            "message_id": None,
            "error": "Neither META_WHATSAPP_* nor TWILIO_* env vars are set. Fill them and restart the backend.",
            "configured": False,
        }

    body = _default_test_body()
    # Prefer Meta
    if meta_on:
        sent, sid_or_err, _raw = meta_wa.send_whatsapp(payload.to, body)
        if sent:
            return {"ok": True, "provider": "meta_whatsapp", "message_id": sid_or_err, "error": None, "configured": True}
        # fall through to Twilio if it's also configured
        if not twilio_on:
            return {"ok": False, "provider": "meta_whatsapp", "message_id": None, "error": sid_or_err, "configured": True}

    # Twilio
    client = _twilio()
    if client is None:
        return {"ok": False, "provider": None, "message_id": None, "error": "Twilio not initialised", "configured": False}
    sender = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
    if not sender:
        return {"ok": False, "provider": "twilio_whatsapp", "message_id": None,
                "error": "TWILIO_WHATSAPP_FROM is not set.", "configured": False}
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    to = _format_whatsapp_number(payload.to)
    if not to:
        return {"ok": False, "provider": "twilio_whatsapp", "message_id": None,
                "error": "Invalid phone format. Use +CCXXXXXXXXXX (E.164).", "configured": True}
    try:
        msg = client.messages.create(from_=sender, body=body, to=to)
        return {"ok": True, "provider": "twilio_whatsapp", "message_id": msg.sid, "error": None, "configured": True}
    except Exception as e:
        return {"ok": False, "provider": "twilio_whatsapp", "message_id": None, "error": str(e), "configured": True}


# ---------------- Telegram ----------------

@router.post("/telegram")
async def test_telegram(payload: TelegramTest, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    if not tg._enabled():
        return {
            "ok": False, "provider": "telegram", "message_id": None,
            "error": "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather and restart the backend.",
            "configured": False,
        }
    chat_id = payload.chat_id or user.get("telegram_chat_id")
    if not chat_id:
        return {
            "ok": False, "provider": "telegram", "message_id": None,
            "error": ("No chat_id provided and you haven't linked Telegram to your own account yet. "
                      "Open the bot on Telegram and send /start <your-email> first, "
                      "or pass a chat_id explicitly."),
            "configured": True,
        }
    sent, sid_or_err = tg.send_telegram(chat_id, _default_test_body())
    if sent:
        return {"ok": True, "provider": "telegram", "message_id": sid_or_err, "error": None, "configured": True}
    return {"ok": False, "provider": "telegram", "message_id": None, "error": sid_or_err, "configured": True}


# ---------------- Email (SMTP) ----------------

@router.post("/email")
async def test_email(payload: EmailTest, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    if not _smtp_enabled():
        return {
            "ok": False, "provider": "smtp", "message_id": None,
            "error": "SMTP_HOST is not set. Configure SMTP_* env vars and restart the backend.",
            "configured": False,
        }
    sent, sid_or_err = send_email(
        str(payload.to),
        "SCMS — SMTP test message",
        _default_test_body(),
    )
    if sent:
        return {"ok": True, "provider": "smtp", "message_id": sid_or_err, "error": None, "configured": True}
    return {"ok": False, "provider": "smtp", "message_id": None, "error": sid_or_err or "unknown SMTP error", "configured": True}


# ---------------- Status snapshot ----------------

@router.get("/status")
async def status(user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    """Returns a snapshot of which integrations look configured (no secret values exposed)."""
    return {
        "meta_whatsapp": {
            "configured": meta_wa._enabled(),
            "api_version": os.environ.get("META_WHATSAPP_API_VERSION", "v21.0"),
        },
        "twilio_whatsapp": {
            "configured": _twilio() is not None and bool(os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()),
        },
        "telegram": {
            "configured": tg._enabled(),
            "linked_to_me": bool(user.get("telegram_chat_id")),
        },
        "smtp": {
            "configured": _smtp_enabled(),
            "from": os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", ""),
        },
    }
