"""Teacher timetable + calendar."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import TimetableBulk
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.post("/bulk")
async def set_timetable(payload: TimetableBulk, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    # remove existing slots for class+section
    await db.timetable.delete_many({"school_id": user["school_id"], "class_id": payload.class_id, "section": payload.section})
    docs = []
    for s in payload.slots:
        d = {
            "id": new_id(),
            "school_id": user["school_id"],
            "class_id": payload.class_id,
            "section": payload.section,
            "day": s.day,
            "period": s.period,
            "subject_id": s.subject_id,
            "teacher_id": s.teacher_id,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "created_at": utc_now(),
        }
        docs.append(d)
    if docs:
        await db.timetable.insert_many(docs)
    return {"inserted": len(docs)}


@router.get("")
async def list_timetable(class_id: str | None = None, section: str | None = None, teacher_id: str | None = None,
                          user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        # restrict to own
        flt["teacher_id"] = user["id"]
    elif teacher_id:
        flt["teacher_id"] = teacher_id
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section
    return await db.timetable.find(flt, {"_id": 0}).to_list(2000)
