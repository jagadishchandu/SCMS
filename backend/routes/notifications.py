"""Notifications log."""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db
from core.utils import utc_now

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _unread_filter(user: dict) -> dict:
    """Notifications addressed *to this user* that haven't been read yet.
    Only in-app channel rows count for the unread badge — other channels
    (whatsapp/email/telegram) deliver out-of-band."""
    flt = {
        "channel": "in_app",
        "recipient_id": user["id"],
        "read_at": {"$exists": False},
    }
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    return flt


@router.get("")
async def list_notifications(limit: int = 100, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["recipient_id"] = user["id"]
    if user["role"] == "teacher":
        flt["$or"] = [{"recipient_id": user["id"]}, {"recipient_type": "teacher"}]
    return await db.notifications.find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    """Count of unread in-app notifications addressed to the current user.
    Powers the sidebar badge."""
    db = get_db()
    count = await db.notifications.count_documents(_unread_filter(user))
    return {"count": count}


@router.post("/mark-all-read")
async def mark_all_read(user: dict = Depends(get_current_user)):
    """Mark every in-app notification addressed to the current user as read.
    Called by the NotificationsLog page on mount so the badge clears automatically."""
    db = get_db()
    res = await db.notifications.update_many(
        _unread_filter(user),
        {"$set": {"read_at": utc_now(), "read_by": user["id"]}},
    )
    return {"ok": True, "marked": res.modified_count}


@router.get("/stats")
async def notification_stats(user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    total = await db.notifications.count_documents(flt)
    queued = await db.notifications.count_documents({**flt, "status": "queued"})
    sent = await db.notifications.count_documents({**flt, "status": "sent"})
    failed = await db.notifications.count_documents({**flt, "status": "failed"})
    return {"total": total, "queued": queued, "sent": sent, "failed": failed}
