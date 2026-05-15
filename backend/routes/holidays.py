"""Holidays."""
from fastapi import APIRouter, Depends
from core.models import HolidayCreate
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("")
async def list_holidays(user: dict = Depends(get_current_user)):
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            out.extend(await tdb.holidays.find({}, {"_id": 0}).sort("date", 1).to_list(200))
        return out
    tdb = await tenant_db(user["school_id"])
    return await tdb.holidays.find({"school_id": user["school_id"]}, {"_id": 0}).sort("date", 1).to_list(500)


@router.post("")
async def create_holiday(payload: HolidayCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
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
    await tdb.holidays.insert_one(doc)
    doc.pop("_id", None)
    students = await tdb.students.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(5000)
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
    tdb = await tenant_db(user["school_id"])
    await tdb.holidays.delete_one({"id": holiday_id, "school_id": user["school_id"]})
    return {"ok": True}
