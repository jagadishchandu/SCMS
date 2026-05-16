"""Extra-curricular activities (sports / music / arts / clubs) + enrollments."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional, List

from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
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
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            flt: dict = {}
            if category: flt["category"] = category
            out.extend(await tdb.activities.find(flt, {"_id": 0}).sort("name", 1).to_list(500))
        return out
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if category:
        flt["category"] = category
    return await tdb.activities.find(flt, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("")
async def create_activity(payload: ActivityCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **payload.model_dump(),
        "created_at": utc_now(),
    }
    await tdb.activities.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"], "create", "activity", doc["id"], {"name": payload.name})
    return {k: v for k, v in doc.items() if k != "_id"}


@router.patch("/{activity_id}")
async def update_activity(activity_id: str, payload: dict, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    allowed = {"name", "category", "description", "coach", "schedule", "is_active"}
    update = {k: v for k, v in payload.items() if k in allowed}
    if not update:
        return {"ok": True}
    res = await tdb.activities.update_one({"id": activity_id, "school_id": user["school_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.delete("/{activity_id}")
async def delete_activity(activity_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    await tdb.activities.delete_one({"id": activity_id, "school_id": user["school_id"]})
    await tdb.activity_enrollments.delete_many({"activity_id": activity_id})
    return {"ok": True}


@router.post("/{activity_id}/enroll")
async def enroll(activity_id: str, payload: EnrollRequest, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    act = await tdb.activities.find_one({"id": activity_id, "school_id": user["school_id"]})
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    # Teachers can only enroll students they have access to (their assigned
    # classes/sections OR students they created themselves).
    teacher_tflt = None
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter, _teacher_can_access_student
        teacher_tflt = await _teacher_class_filter(tdb, user)
    added = 0
    skipped = 0
    for sid in payload.student_ids:
        s = await tdb.students.find_one({"id": sid, "school_id": user["school_id"]})
        if not s:
            skipped += 1
            continue
        if user["role"] == "teacher":
            from routes.students import _teacher_can_access_student
            if not _teacher_can_access_student(teacher_tflt, s, user["id"]):
                skipped += 1
                continue
        try:
            await tdb.activity_enrollments.insert_one({
                "id": new_id(),
                "school_id": user["school_id"],
                "activity_id": activity_id,
                "student_id": sid,
                "created_at": utc_now(),
                "enrolled_by_id": user["id"],
                "enrolled_by_role": user["role"],
            })
            added += 1
        except Exception:
            skipped += 1
    return {"enrolled": added, "skipped": skipped}


@router.delete("/{activity_id}/enroll/{student_id}")
async def unenroll(activity_id: str, student_id: str, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    if user["role"] == "teacher":
        s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]})
        if not s:
            raise HTTPException(status_code=404, detail="Student not found")
        from routes.students import _teacher_class_filter, _teacher_can_access_student
        tflt = await _teacher_class_filter(tdb, user)
        if not _teacher_can_access_student(tflt, s, user["id"]):
            raise HTTPException(status_code=403, detail="Not your student")
    res = await tdb.activity_enrollments.delete_one({
        "school_id": user["school_id"], "activity_id": activity_id, "student_id": student_id,
    })
    return {"ok": True, "deleted": res.deleted_count}


@router.get("/{activity_id}/roster")
async def roster(activity_id: str, user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    rows = await tdb.activity_enrollments.find({"activity_id": activity_id, "school_id": user.get("school_id")}, {"_id": 0}).to_list(2000)
    if not rows:
        return []
    sids = [r["student_id"] for r in rows]
    students = await tdb.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(2000)
    return students


@router.get("/student/{student_id}")
async def list_student_activities(student_id: str, user: dict = Depends(get_current_user)):
    """List every activity a student is enrolled in. Visible to the student's
    parent, any school staff, and (via tenant scope) the platform admin."""
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user.get("school_id")}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "parent" and s.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter, _teacher_can_access_student
        tflt = await _teacher_class_filter(tdb, user)
        if not _teacher_can_access_student(tflt, s, user["id"]):
            raise HTTPException(status_code=403, detail="Not your class")
    rows = await tdb.activity_enrollments.find(
        {"school_id": user["school_id"], "student_id": student_id}, {"_id": 0},
    ).to_list(200)
    if not rows:
        return []
    aids = [r["activity_id"] for r in rows]
    acts = await tdb.activities.find(
        {"school_id": user["school_id"], "id": {"$in": aids}}, {"_id": 0},
    ).to_list(200)
    by_aid = {a["id"]: a for a in acts}
    out = []
    for r in rows:
        a = by_aid.get(r["activity_id"])
        if not a:
            continue
        out.append({
            "enrollment_id": r["id"],
            "activity_id": a["id"],
            "name": a.get("name"),
            "category": a.get("category", "other"),
            "coach": a.get("coach"),
            "schedule": a.get("schedule"),
            "is_active": a.get("is_active", True),
            "enrolled_at": r.get("created_at"),
        })
    out.sort(key=lambda x: x["name"] or "")
    return out


@router.get("/stats/summary")
async def stats(user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "platform_admin", "teacher", "accounts"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    activities = await tdb.activities.find(flt, {"_id": 0}).to_list(500)
    by_category = {}
    per_activity = []
    for a in activities:
        c = a.get("category", "other")
        by_category[c] = by_category.get(c, 0) + 1
        count = await tdb.activity_enrollments.count_documents({"activity_id": a["id"]})
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
