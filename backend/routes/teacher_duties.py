"""Teacher Schedule / Duty Roster.

School admin assigns calendar events (meetings, duties, parent-teacher
conferences, training, exam supervision, etc.) to specific teachers.
Teachers see only their own events on /teacher/calendar.

Distinct from `timetable` (period × day grid) — this is for ad-hoc events.
"""
from datetime import datetime
from typing import Literal, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import require_roles, get_current_user
from core.db import tenant_db, get_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action
from core.notify import queue_notification

router = APIRouter(prefix="/teacher-duties", tags=["teacher-duties"])

DUTY_TYPES = Literal[
    "meeting", "duty", "parent_teacher", "training", "exam_supervision",
    "event", "other",
]


class TeacherDutyCreate(BaseModel):
    teacher_ids: List[str] = Field(..., min_length=1)
    title: str
    type: DUTY_TYPES = "duty"
    start_at: datetime  # iso datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    notify: bool = True  # send WhatsApp/Telegram alert


class TeacherDutyUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[DUTY_TYPES] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None


def _serialize(d: dict) -> dict:
    out = dict(d)
    for k in ("start_at", "end_at", "created_at", "updated_at"):
        if hasattr(out.get(k), "isoformat"):
            out[k] = out[k].isoformat()
    out.pop("_id", None)
    return out


@router.get("")
async def list_duties(
    teacher_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    tdb = await tenant_db(user["school_id"])
    flt: dict = {"school_id": user["school_id"]}
    # Teachers can only see their own duties.
    if user["role"] == "teacher":
        flt["teacher_id"] = user["id"]
    elif user["role"] in ("school_admin", "accounts", "platform_admin"):
        if teacher_id:
            flt["teacher_id"] = teacher_id
    else:
        raise HTTPException(status_code=403, detail="Not authorised")
    # Date range filter
    if from_date or to_date:
        rng = {}
        if from_date:
            try: rng["$gte"] = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            except ValueError: pass
        if to_date:
            try: rng["$lte"] = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            except ValueError: pass
        if rng:
            flt["start_at"] = rng
    rows = await tdb.teacher_duties.find(flt).sort("start_at", 1).to_list(2000)
    return [_serialize(r) for r in rows]


@router.post("")
async def create_duty(payload: TeacherDutyCreate,
                       user: dict = Depends(require_roles("school_admin"))):
    """Assign a duty to one or more teachers. Creates one row per teacher
    so each teacher's calendar query stays simple.
    """
    db = get_db()
    tdb = await tenant_db(user["school_id"])
    # Validate teacher_ids
    teachers = await db.users.find(
        {"id": {"$in": payload.teacher_ids}, "school_id": user["school_id"], "role": "teacher"},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "telegram_chat_id": 1},
    ).to_list(200)
    if len(teachers) != len(payload.teacher_ids):
        found = {t["id"] for t in teachers}
        missing = [t for t in payload.teacher_ids if t not in found]
        raise HTTPException(status_code=400, detail=f"Unknown teacher_id(s): {missing}")

    now = utc_now()
    created = []
    for t in teachers:
        doc = {
            "id": new_id(),
            "school_id": user["school_id"],
            "teacher_id": t["id"],
            "teacher_name": t.get("name"),
            "title": payload.title,
            "type": payload.type,
            "start_at": payload.start_at,
            "end_at": payload.end_at,
            "location": payload.location,
            "notes": payload.notes,
            "created_at": now,
            "created_by": user["id"],
            "status": "scheduled",
        }
        await tdb.teacher_duties.insert_one(doc)
        created.append(_serialize(doc))
        if payload.notify:
            when = payload.start_at.strftime("%d %b %Y · %I:%M %p") if hasattr(payload.start_at, "strftime") else str(payload.start_at)
            await queue_notification(
                user["school_id"], "teacher", t["id"],
                t.get("telegram_chat_id") or t.get("phone"),
                "telegram", "teacher_duty",
                f"New duty assigned: {payload.title} on {when}" + (f" at {payload.location}" if payload.location else ""),
                context={"duty_type": payload.type},
            )
    await log_action(
        user["id"], user["role"], user["school_id"], "create_teacher_duty",
        "teacher_duty", created[0]["id"] if created else None,
        {"title": payload.title, "type": payload.type, "teacher_count": len(created)},
    )
    return created


@router.patch("/{duty_id}")
async def update_duty(duty_id: str, payload: TeacherDutyUpdate,
                       user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    existing = await tdb.teacher_duties.find_one({"id": duty_id, "school_id": user["school_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Duty not found")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        return _serialize(existing)
    update["updated_at"] = utc_now()
    await tdb.teacher_duties.update_one({"id": duty_id}, {"$set": update})
    await log_action(user["id"], user["role"], user["school_id"],
                      "update_teacher_duty", "teacher_duty", duty_id, update)
    refreshed = await tdb.teacher_duties.find_one({"id": duty_id})
    return _serialize(refreshed)


@router.delete("/{duty_id}")
async def delete_duty(duty_id: str,
                       user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    res = await tdb.teacher_duties.delete_one({"id": duty_id, "school_id": user["school_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Duty not found")
    await log_action(user["id"], user["role"], user["school_id"],
                      "delete_teacher_duty", "teacher_duty", duty_id)
    return {"ok": True}
