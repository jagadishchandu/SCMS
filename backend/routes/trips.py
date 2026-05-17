"""Educational trips management.

Admins create/manage trips. Teachers and parents view them (read-only).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

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
