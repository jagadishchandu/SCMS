"""Educational trips management.

Admins create/manage trips. Teachers and parents view them (read-only).
Parents RSVP for their child(ren); school_admin / teacher see the RSVP roster.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.audit import log_action
from core.notify import queue_notification

router = APIRouter(prefix="/trips", tags=["trips"])


class TripCreate(BaseModel):
    title: str
    destination: str
    departure_date: str  # ISO date YYYY-MM-DD
    return_date: Optional[str] = None
    cost: float = 0
    transport_mode: Optional[str] = None  # bus / train / flight / etc
    itinerary: Optional[str] = None
    description: Optional[str] = None
    max_students: Optional[int] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    permission_slip_url: Optional[str] = None
    class_ids: List[str] = Field(default_factory=list)
    status: str = "open"  # open / closed / cancelled


class TripUpdate(BaseModel):
    title: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    cost: Optional[float] = None
    transport_mode: Optional[str] = None
    itinerary: Optional[str] = None
    description: Optional[str] = None
    max_students: Optional[int] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    permission_slip_url: Optional[str] = None
    class_ids: Optional[List[str]] = None
    status: Optional[str] = None


def _to_out(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("")
async def list_trips(user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "teacher", "parent", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            out.extend(await tdb.trips.find({}, {"_id": 0}).sort("departure_date", 1).to_list(500))
        return out
    tdb = await tenant_db(user["school_id"])
    return await tdb.trips.find(
        {"school_id": user["school_id"]}, {"_id": 0},
    ).sort("departure_date", 1).to_list(500)


@router.get("/{trip_id}")
async def get_trip(trip_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "teacher", "parent", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    doc = await tdb.trips.find_one({"id": trip_id, "school_id": user["school_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Trip not found")
    return doc


@router.post("")
async def create_trip(payload: TripCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **payload.model_dump(),
        "created_by": user["id"],
        "created_at": utc_now(),
    }
    await tdb.trips.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"], "create", "trip", doc["id"],
                     {"title": payload.title, "destination": payload.destination})

    # Notify parents & teachers
    cost_str = f"₹{int(payload.cost):,}" if payload.cost else "Free"
    date_str = payload.departure_date + (f" → {payload.return_date}" if payload.return_date else "")
    msg = (
        f"🚌 Educational trip: {payload.title}\n"
        f"📍 {payload.destination}\n"
        f"📅 {date_str}\n"
        f"💰 Cost: {cost_str}"
    )
    if payload.contact_person or payload.contact_phone:
        msg += f"\n☎️ {payload.contact_person or ''} {payload.contact_phone or ''}".strip()

    try:
        students = await tdb.students.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(5000)
        for s in students:
            if payload.class_ids and s.get("class_id") not in payload.class_ids:
                continue
            await queue_notification(
                user["school_id"], "parent", s.get("parent_user_id"),
                s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
                "whatsapp", "trip_announced",
                msg, context={"trip_id": doc["id"]},
            )
        rdb = get_db()
        teachers = await rdb.users.find(
            {"school_id": user["school_id"], "role": "teacher", "is_active": True},
            {"_id": 0, "id": 1, "phone": 1, "telegram_chat_id": 1},
        ).to_list(2000)
        for t in teachers:
            await queue_notification(
                user["school_id"], "teacher", t["id"], t.get("phone"),
                "telegram", "trip_announced", msg,
                context={"trip_id": doc["id"]}, telegram_chat_id=t.get("telegram_chat_id"),
            )
    except Exception as e:
        # Notifications are best-effort; don't fail trip creation.
        import logging
        logging.getLogger("scms.trips").warning("trip notify error: %s", e)

    return _to_out(doc)


@router.patch("/{trip_id}")
async def update_trip(trip_id: str, payload: TripUpdate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        return {"ok": True}
    update["updated_at"] = utc_now()
    res = await tdb.trips.update_one(
        {"id": trip_id, "school_id": user["school_id"]},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "trip", trip_id, update)
    doc = await tdb.trips.find_one({"id": trip_id, "school_id": user["school_id"]}, {"_id": 0})
    return doc


@router.delete("/{trip_id}")
async def delete_trip(trip_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    res = await tdb.trips.delete_one({"id": trip_id, "school_id": user["school_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    await log_action(user["id"], user["role"], user["school_id"], "delete", "trip", trip_id, {})
    return {"ok": True}



# --------- RSVP (parent confirms attendance for their child) ---------

class RSVPSubmit(BaseModel):
    student_id: str
    status: Literal["confirmed", "declined"]
    note: Optional[str] = None


async def _ensure_trip(tdb, school_id: str, trip_id: str) -> dict:
    trip = await tdb.trips.find_one({"id": trip_id, "school_id": school_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.post("/{trip_id}/rsvp")
async def submit_rsvp(trip_id: str, payload: RSVPSubmit, user: dict = Depends(require_roles("parent"))):
    """Parent confirms or declines attendance for one of their children."""
    tdb = await tenant_db(user["school_id"])
    trip = await _ensure_trip(tdb, user["school_id"], trip_id)
    if trip.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Trip is cancelled — RSVP not allowed.")

    student = await tdb.students.find_one(
        {"id": payload.student_id, "school_id": user["school_id"]}, {"_id": 0},
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your child")

    # If trip is restricted to specific classes, refuse if child isn't in scope.
    if trip.get("class_ids") and student.get("class_id") not in trip["class_ids"]:
        raise HTTPException(status_code=400, detail="This trip is not open to your child's class.")

    now = utc_now()
    existing = await tdb.trip_rsvps.find_one(
        {"trip_id": trip_id, "student_id": payload.student_id, "school_id": user["school_id"]},
        {"_id": 0},
    )
    if existing:
        await tdb.trip_rsvps.update_one(
            {"id": existing["id"]},
            {"$set": {"status": payload.status, "note": payload.note, "updated_at": now}},
        )
        doc = {**existing, "status": payload.status, "note": payload.note, "updated_at": now}
    else:
        doc = {
            "id": new_id(),
            "school_id": user["school_id"],
            "trip_id": trip_id,
            "student_id": payload.student_id,
            "student_name": student.get("name"),
            "student_uid": student.get("student_uid"),
            "class_id": student.get("class_id"),
            "section": student.get("section"),
            "parent_user_id": user["id"],
            "parent_name": user.get("name"),
            "status": payload.status,
            "note": payload.note,
            "created_at": now,
            "updated_at": now,
        }
        await tdb.trip_rsvps.insert_one(doc)

    await log_action(
        user["id"], user["role"], user["school_id"],
        "rsvp", "trip", trip_id,
        {"student_id": payload.student_id, "status": payload.status},
    )
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/{trip_id}/my-rsvps")
async def my_rsvps(trip_id: str, user: dict = Depends(require_roles("parent"))):
    """Parent: list the RSVP status for each of their children for this trip,
    plus the children that haven't responded yet."""
    tdb = await tenant_db(user["school_id"])
    trip = await _ensure_trip(tdb, user["school_id"], trip_id)
    children = await tdb.students.find(
        {"school_id": user["school_id"], "parent_user_id": user["id"]}, {"_id": 0},
    ).to_list(50)
    # Filter to children eligible for this trip (if it's class-scoped)
    if trip.get("class_ids"):
        children = [c for c in children if c.get("class_id") in trip["class_ids"]]
    rsvps = await tdb.trip_rsvps.find(
        {"trip_id": trip_id, "school_id": user["school_id"], "parent_user_id": user["id"]},
        {"_id": 0},
    ).to_list(100)
    by_student = {r["student_id"]: r for r in rsvps}
    out = []
    for c in children:
        r = by_student.get(c["id"])
        out.append({
            "student_id": c["id"],
            "student_name": c.get("name"),
            "student_uid": c.get("student_uid"),
            "class_id": c.get("class_id"),
            "section": c.get("section"),
            "status": (r or {}).get("status", "pending"),
            "note": (r or {}).get("note"),
            "updated_at": (r or {}).get("updated_at"),
        })
    return out


@router.get("/{trip_id}/rsvps")
async def trip_rsvps(trip_id: str, user: dict = Depends(get_current_user)):
    """School admin / teacher: full RSVP roster for a trip.

    Returns: { summary: {confirmed, declined, pending, total_eligible}, rows: [...] }
    Rows include students who haven't responded (status='pending').
    """
    if user["role"] not in ("school_admin", "teacher", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    trip = await _ensure_trip(tdb, user["school_id"], trip_id)

    # Eligible students = all students in school, or restricted to class_ids.
    student_q: dict = {"school_id": user["school_id"]}
    if trip.get("class_ids"):
        student_q["class_id"] = {"$in": trip["class_ids"]}
    students = await tdb.students.find(student_q, {"_id": 0}).to_list(5000)

    # Teachers see only students in their own classes
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter, _teacher_can_access_student
        tflt = await _teacher_class_filter(tdb, user)
        students = [s for s in students if _teacher_can_access_student(tflt, s, user["id"])]

    rsvps = await tdb.trip_rsvps.find(
        {"trip_id": trip_id, "school_id": user["school_id"]}, {"_id": 0},
    ).to_list(5000)
    by_student = {r["student_id"]: r for r in rsvps}

    rows = []
    counts = {"confirmed": 0, "declined": 0, "pending": 0}
    for s in students:
        r = by_student.get(s["id"])
        status = (r or {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
        rows.append({
            "student_id": s["id"],
            "student_name": s.get("name"),
            "student_uid": s.get("student_uid"),
            "class_id": s.get("class_id"),
            "section": s.get("section"),
            "parent_name": (r or {}).get("parent_name") or s.get("parent", {}).get("name"),
            "parent_phone": s.get("parent", {}).get("phone"),
            "status": status,
            "note": (r or {}).get("note"),
            "updated_at": (r or {}).get("updated_at"),
        })
    # Sort: confirmed first, then declined, then pending; then by name.
    order = {"confirmed": 0, "declined": 1, "pending": 2}
    rows.sort(key=lambda x: (order.get(x["status"], 3), x["student_name"] or ""))

    return {
        "trip_id": trip_id,
        "trip_title": trip.get("title"),
        "summary": {
            "confirmed": counts["confirmed"],
            "declined": counts["declined"],
            "pending": counts["pending"],
            "total_eligible": len(students),
        },
        "rows": rows,
    }
