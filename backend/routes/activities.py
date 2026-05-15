"""Extra-curricular activities (sports / music / arts / clubs) + enrollments."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional, List

from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.audit import log_action

router = APIRouter(prefix="/activities", tags=["activities"])


class ActivityCreate(BaseModel):
    name: str
    category: Literal["sport", "music", "art", "club", "other"] = "sport"
    description: Optional[str] = None
    coach: Optional[str] = None
    schedule: Optional[str] = None
    is_active: bool = True


class EnrollRequest(BaseModel):
    student_ids: List[str]


@router.get("")
async def list_activities(category: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if category:
        flt["category"] = category
    return await db.activities.find(flt, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("")
async def create_activity(payload: ActivityCreate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **payload.model_dump(),
        "created_at": utc_now(),
    }
    await db.activities.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"], "create", "activity", doc["id"], {"name": payload.name})
    return {k: v for k, v in doc.items() if k != "_id"}


@router.patch("/{activity_id}")
async def update_activity(activity_id: str, payload: dict, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    allowed = {"name", "category", "description", "coach", "schedule", "is_active"}
    update = {k: v for k, v in payload.items() if k in allowed}
    if not update:
        return {"ok": True}
    res = await db.activities.update_one({"id": activity_id, "school_id": user["school_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.delete("/{activity_id}")
async def delete_activity(activity_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    await db.activities.delete_one({"id": activity_id, "school_id": user["school_id"]})
    await db.activity_enrollments.delete_many({"activity_id": activity_id})
    return {"ok": True}


@router.post("/{activity_id}/enroll")
async def enroll(activity_id: str, payload: EnrollRequest, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    act = await db.activities.find_one({"id": activity_id, "school_id": user["school_id"]})
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    added = 0
    for sid in payload.student_ids:
        # validate student exists in this school
        s = await db.students.find_one({"id": sid, "school_id": user["school_id"]})
        if not s:
            continue
        try:
            await db.activity_enrollments.insert_one({
                "id": new_id(),
                "school_id": user["school_id"],
                "activity_id": activity_id,
                "student_id": sid,
                "created_at": utc_now(),
            })
            added += 1
        except Exception:
            pass  # duplicate enrollment ignored due to unique index
    return {"enrolled": added}


@router.delete("/{activity_id}/enroll/{student_id}")
async def unenroll(activity_id: str, student_id: str, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    res = await db.activity_enrollments.delete_one({
        "school_id": user["school_id"], "activity_id": activity_id, "student_id": student_id,
    })
    return {"ok": True, "deleted": res.deleted_count}


@router.get("/{activity_id}/roster")
async def roster(activity_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    rows = await db.activity_enrollments.find({"activity_id": activity_id, "school_id": user.get("school_id")}, {"_id": 0}).to_list(2000)
    if not rows:
        return []
    sids = [r["student_id"] for r in rows]
    students = await db.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(2000)
    return students


@router.get("/stats/summary")
async def stats(user: dict = Depends(get_current_user)):
    """Returns activity counts grouped by category + per-activity enrollment counts."""
    db = get_db()
    if user["role"] not in ("school_admin", "platform_admin", "teacher", "accounts"):
        raise HTTPException(status_code=403, detail="Forbidden")
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    activities = await db.activities.find(flt, {"_id": 0}).to_list(500)
    by_category = {}
    per_activity = []
    for a in activities:
        c = a.get("category", "other")
        by_category[c] = by_category.get(c, 0) + 1
        count = await db.activity_enrollments.count_documents({"activity_id": a["id"]})
        per_activity.append({
            "activity_id": a["id"],
            "name": a["name"],
            "category": c,
            "coach": a.get("coach"),
            "schedule": a.get("schedule"),
            "is_active": a.get("is_active", True),
            "enrolled": count,
        })
    per_activity.sort(key=lambda x: (-x["enrolled"], x["name"]))
    return {
        "total_activities": len(activities),
        "active_activities": sum(1 for a in activities if a.get("is_active", True)),
        "by_category": [{"category": k, "count": v} for k, v in sorted(by_category.items())],
        "per_activity": per_activity,
    }
