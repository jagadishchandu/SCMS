"""Sick leave tracker with optional medical certificate upload."""
import base64
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.audit import log_action

router = APIRouter(prefix="/sick-leaves", tags=["sick-leaves"])


class SickLeaveCreate(BaseModel):
    student_id: str
    start_date: str
    end_date: str
    reason: str | None = None
    diagnosis: str | None = None


async def _student_in_scope(tdb, user: dict, student_id: str) -> dict:
    s = await tdb.students.find_one({"id": student_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "platform_admin":
        return s
    if user.get("school_id") != s["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "parent" and s.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Not your class")
        ok = any((c.get("class_id") == s["class_id"] and c.get("section") == s["section"]) for c in tflt.get("$or", []))
        if not ok:
            raise HTTPException(status_code=403, detail="Not your class")
    return s


@router.post("")
async def create_leave(
    payload: SickLeaveCreate,
    user: dict = Depends(require_roles("school_admin", "teacher", "parent")),
):
    tdb = await tenant_db(user["school_id"])
    s = await _student_in_scope(tdb, user, payload.student_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    doc = {
        "id": new_id(),
        "school_id": s["school_id"],
        "student_id": s["id"],
        "student_uid": s["student_uid"],
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "reason": payload.reason,
        "diagnosis": payload.diagnosis,
        "medical_certificate": None,
        "recorded_by": user["id"],
        "recorded_by_role": user["role"],
        "created_at": utc_now(),
    }
    await tdb.sick_leaves.insert_one(doc)
    start = datetime.fromisoformat(payload.start_date).date()
    end = datetime.fromisoformat(payload.end_date).date()
    d = start
    while d <= end:
        if d.weekday() < 5:
            await tdb.attendance.update_one(
                {"school_id": s["school_id"], "student_id": s["id"], "date": d.isoformat()},
                {"$set": {
                    "id": new_id(),
                    "school_id": s["school_id"],
                    "student_id": s["id"],
                    "class_id": s["class_id"],
                    "section": s["section"],
                    "date": d.isoformat(),
                    "status": "sick",
                    "remark": (payload.reason or "Sick leave")[:120],
                    "marked_by": user["id"],
                    "marked_at": utc_now(),
                }},
                upsert=True,
            )
        d += timedelta(days=1)
    await log_action(user["id"], user["role"], s["school_id"], "create_sick_leave", "sick_leave", doc["id"],
                     meta={"student_uid": s["student_uid"], "days": (end - start).days + 1})
    doc.pop("_id", None)
    return doc


@router.post("/{leave_id}/certificate")
async def upload_certificate(
    leave_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_roles("school_admin", "teacher", "parent")),
):
    tdb = await tenant_db(user["school_id"])
    leave = await tdb.sick_leaves.find_one({"id": leave_id})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    await _student_in_scope(tdb, user, leave["student_id"])
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    if file.content_type not in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP or PDF allowed")
    b64 = base64.b64encode(data).decode("ascii")
    cert = {
        "filename": file.filename,
        "content_type": file.content_type,
        "data_url": f"data:{file.content_type};base64,{b64}",
        "uploaded_by": user["id"],
        "uploaded_at": utc_now(),
    }
    await tdb.sick_leaves.update_one({"id": leave_id}, {"$set": {"medical_certificate": cert}})
    await log_action(user["id"], user["role"], leave["school_id"], "upload_medical_cert", "sick_leave", leave_id)
    return {"ok": True}


@router.get("")
async def list_leaves(
    student_id: str | None = None,
    student_uid: str | None = None,
    days: int | None = None,
    user: dict = Depends(get_current_user),
):
    tdb = await tenant_db(user["school_id"])
    flt: dict = {}
    if user["role"] == "platform_admin":
        # Cross-school aggregation
        db = get_db()
        out = []
        async for school in db.schools.find({}, {"_id": 0, "id": 1}):
            stdb = await tenant_db(school["id"])
            out.extend(await stdb.sick_leaves.find({}, {"_id": 0}).sort("start_date", -1).to_list(500))
        return out
    elif user["role"] in ("school_admin", "accounts"):
        flt["school_id"] = user["school_id"]
    elif user["role"] == "parent":
        flt["school_id"] = user["school_id"]
        my_kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(10)
        flt["student_id"] = {"$in": [k["id"] for k in my_kids]}
    elif user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            return []
        teacher_students = await tdb.students.find(
            {"school_id": user["school_id"], "$or": [{"class_id": c["class_id"], "section": c["section"]} for c in tflt["$or"]]},
            {"_id": 0, "id": 1},
        ).to_list(2000)
        flt["school_id"] = user["school_id"]
        flt["student_id"] = {"$in": [t["id"] for t in teacher_students]}
    else:
        return []
    if student_id:
        flt["student_id"] = student_id
    if student_uid:
        s = await tdb.students.find_one({"student_uid": student_uid}, {"_id": 0, "id": 1, "school_id": 1})
        if not s:
            return []
        flt["student_id"] = s["id"]
    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        flt["end_date"] = {"$gte": cutoff}
    docs = await tdb.sick_leaves.find(flt, {"_id": 0}).sort("start_date", -1).to_list(500)
    return docs


@router.get("/recurring")
async def recurring_summary(threshold: int = 3, days: int = 90, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    match: dict = {"school_id": user["school_id"], "end_date": {"$gte": cutoff}}
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            return []
        students = await tdb.students.find(
            {"school_id": user["school_id"], "$or": [{"class_id": c["class_id"], "section": c["section"]} for c in tflt["$or"]]},
            {"_id": 0, "id": 1},
        ).to_list(2000)
        match["student_id"] = {"$in": [s["id"] for s in students]}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$student_id", "count": {"$sum": 1},
                     "last_end": {"$max": "$end_date"},
                     "first_start": {"$min": "$start_date"}}},
        {"$match": {"count": {"$gte": threshold}}},
        {"$sort": {"count": -1, "last_end": -1}},
        {"$limit": 50},
    ]
    rows = await tdb.sick_leaves.aggregate(pipeline).to_list(50)
    if not rows:
        return []
    ids = [r["_id"] for r in rows]
    students = {s["id"]: s for s in await tdb.students.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)}
    out = []
    for r in rows:
        s = students.get(r["_id"], {})
        out.append({
            "student_id": r["_id"],
            "student_uid": s.get("student_uid"),
            "name": s.get("name"),
            "class_id": s.get("class_id"),
            "section": s.get("section"),
            "leaves_in_window": r["count"],
            "first_start": r["first_start"],
            "last_end": r["last_end"],
        })
    return out


@router.delete("/{leave_id}")
async def delete_leave(leave_id: str, user: dict = Depends(require_roles("school_admin", "teacher", "parent"))):
    tdb = await tenant_db(user["school_id"])
    leave = await tdb.sick_leaves.find_one({"id": leave_id})
    if not leave:
        raise HTTPException(status_code=404, detail="Not found")
    await _student_in_scope(tdb, user, leave["student_id"])
    if user["role"] == "parent" and leave.get("recorded_by") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the parent who recorded this leave can delete it")
    await tdb.sick_leaves.delete_one({"id": leave_id})
    await log_action(user["id"], user["role"], leave["school_id"], "delete_sick_leave", "sick_leave", leave_id)
    return {"ok": True}
