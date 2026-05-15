"""Notifications log."""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


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


@router.get("/stats")
async def notification_stats(user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    total = await db.notifications.count_documents(flt)
    queued = await db.notifications.count_documents({**flt, "status": "queued"})
    sent = await db.notifications.count_documents({**flt, "status": "sent"})
    failed = await db.notifications.count_documents({**flt, "status": "failed"})
    return {"total": total, "queued": queued, "sent": sent, "failed": failed}
