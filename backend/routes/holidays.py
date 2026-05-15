"""Holidays."""
from fastapi import APIRouter, Depends
from core.models import HolidayCreate
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("")
async def list_holidays(user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    return await db.holidays.find(flt, {"_id": 0}).sort("date", 1).to_list(500)


@router.post("")
async def create_holiday(payload: HolidayCreate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "title": payload.title,
        "date": payload.date,
        "end_date": payload.end_date,
        "type": payload.type,
        "description": payload.description,
        "created_at": utc_now(),
    }
    await db.holidays.insert_one(doc)
    doc.pop("_id", None)
    # notify all parents in school
    students = await db.students.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(5000)
    for s in students:
        await queue_notification(
            user["school_id"], "parent", s.get("parent_user_id"),
            s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
            "whatsapp", "holiday_announced",
            f"Holiday: {payload.title} on {payload.date}. " + (payload.description or ""),
            context={"holiday_id": doc["id"]},
        )
    return doc


@router.delete("/{holiday_id}")
async def delete_holiday(holiday_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    await db.holidays.delete_one({"id": holiday_id, "school_id": user["school_id"]})
    return {"ok": True}
