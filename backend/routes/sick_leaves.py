"""Sick leave tracker with optional medical certificate upload + multi-step approval.

Approval workflow (v1.20):
- If the leave duration (working days excluding Sundays) is <= 3, it is auto-approved
  regardless of who created it (parent, teacher, or admin).
- If the leave duration > 3 working days AND was created by a parent, it requires BOTH
  the class teacher AND the school admin to approve before becoming active.
- Attendance is only auto-marked 'sick' once status == 'approved'.
- Leaves recorded by teachers or admins themselves are always auto-approved (they are
  the approvers — no self-approval loop).
"""
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


class ApprovalDecision(BaseModel):
    note: str | None = None


class AppealRequest(BaseModel):
    appeal_note: str
    reason: str | None = None  # parent may update the reason on appeal
    diagnosis: str | None = None


def _working_days_excl_sunday(start_iso: str, end_iso: str) -> int:
    """Inclusive count of days between start and end, excluding Sundays."""
    start = datetime.fromisoformat(start_iso).date()
    end = datetime.fromisoformat(end_iso).date()
    if end < start:
        return 0
    count = 0
    d = start
    while d <= end:
        if d.weekday() != 6:  # not Sunday
            count += 1
        d += timedelta(days=1)
    return count


def _normalize_status(leave: dict) -> dict:
    """Backfill default status on docs created before the approval workflow existed."""
    if not leave.get("status"):
        leave["status"] = "approved"
    if "teacher_approval" not in leave:
        leave["teacher_approval"] = None
    if "admin_approval" not in leave:
        leave["admin_approval"] = None
    if "appeals" not in leave:
        leave["appeals"] = []
    return leave


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


async def _mark_attendance_for_leave(tdb, leave: dict, marked_by: str):
    """Mark attendance 'sick' for working days (Mon-Fri) within an approved leave span."""
    start = datetime.fromisoformat(leave["start_date"]).date()
    end = datetime.fromisoformat(leave["end_date"]).date()
    d = start
    while d <= end:
        if d.weekday() < 5:
            await tdb.attendance.update_one(
                {"school_id": leave["school_id"], "student_id": leave["student_id"], "date": d.isoformat()},
                {"$set": {
                    "id": new_id(),
                    "school_id": leave["school_id"],
                    "student_id": leave["student_id"],
                    "class_id": leave.get("class_id"),
                    "section": leave.get("section"),
                    "date": d.isoformat(),
                    "status": "sick",
                    "remark": (leave.get("reason") or "Sick leave")[:120],
                    "marked_by": marked_by,
                    "marked_at": utc_now(),
                }},
                upsert=True,
            )
        d += timedelta(days=1)


@router.post("")
async def create_leave(
    payload: SickLeaveCreate,
    user: dict = Depends(require_roles("school_admin", "teacher", "parent")),
):
    tdb = await tenant_db(user["school_id"])
    s = await _student_in_scope(tdb, user, payload.student_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    working_days = _working_days_excl_sunday(payload.start_date, payload.end_date)
    # Parents requesting > 3 working days need both teacher AND admin approval.
    needs_approval = user["role"] == "parent" and working_days > 3
    status = "pending" if needs_approval else "approved"

    doc = {
        "id": new_id(),
        "school_id": s["school_id"],
        "student_id": s["id"],
        "student_uid": s["student_uid"],
        "class_id": s.get("class_id"),
        "section": s.get("section"),
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "working_days": working_days,
        "reason": payload.reason,
        "diagnosis": payload.diagnosis,
        "medical_certificate": None,
        "status": status,
        "teacher_approval": {"status": "pending"} if needs_approval else None,
        "admin_approval": {"status": "pending"} if needs_approval else None,
        "recorded_by": user["id"],
        "recorded_by_role": user["role"],
        "recorded_by_name": user.get("name"),
        "created_at": utc_now(),
    }
    await tdb.sick_leaves.insert_one(doc)

    if status == "approved":
        await _mark_attendance_for_leave(tdb, doc, user["id"])

    await log_action(
        user["id"], user["role"], s["school_id"],
        "create_sick_leave" if status == "approved" else "request_sick_leave",
        "sick_leave", doc["id"],
        meta={"student_uid": s["student_uid"], "working_days": working_days, "status": status},
    )
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


async def _scope_filter_for_user(tdb, user: dict) -> dict | None:
    """Build a Mongo filter restricting sick_leaves to what `user` may see.
    Returns None if user has no access at all."""
    if user["role"] in ("school_admin", "accounts"):
        return {"school_id": user["school_id"]}
    if user["role"] == "parent":
        my_kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(10)
        return {"school_id": user["school_id"], "student_id": {"$in": [k["id"] for k in my_kids]}}
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            return None
        teacher_students = await tdb.students.find(
            {"school_id": user["school_id"], "$or": [{"class_id": c["class_id"], "section": c["section"]} for c in tflt["$or"]]},
            {"_id": 0, "id": 1},
        ).to_list(2000)
        return {"school_id": user["school_id"], "student_id": {"$in": [t["id"] for t in teacher_students]}}
    return None


@router.get("")
async def list_leaves(
    student_id: str | None = None,
    student_uid: str | None = None,
    days: int | None = None,
    status: str | None = None,
    user: dict = Depends(get_current_user),
):
    tdb = await tenant_db(user["school_id"])
    if user["role"] == "platform_admin":
        # Cross-school aggregation
        db = get_db()
        out = []
        async for school in db.schools.find({}, {"_id": 0, "id": 1}):
            stdb = await tenant_db(school["id"])
            out.extend(await stdb.sick_leaves.find({}, {"_id": 0}).sort("start_date", -1).to_list(500))
        return [_normalize_status(x) for x in out]

    flt = await _scope_filter_for_user(tdb, user)
    if flt is None:
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
    if status:
        flt["status"] = status
    docs = await tdb.sick_leaves.find(flt, {"_id": 0}).sort("start_date", -1).to_list(500)
    return [_normalize_status(d) for d in docs]


@router.get("/today")
async def todays_sick_list(user: dict = Depends(require_roles("school_admin", "teacher"))):
    """Approved sick leaves where today's date falls within [start, end]."""
    tdb = await tenant_db(user["school_id"])
    flt = await _scope_filter_for_user(tdb, user)
    if flt is None:
        return []
    today = date.today().isoformat()
    flt["status"] = "approved"
    flt["start_date"] = {"$lte": today}
    flt["end_date"] = {"$gte": today}
    docs = await tdb.sick_leaves.find(flt, {"_id": 0}).sort("start_date", -1).to_list(500)
    # Enrich with student names
    sids = list({d["student_id"] for d in docs})
    students = {s["id"]: s for s in await tdb.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(500)}
    out = []
    for d in docs:
        s = students.get(d["student_id"], {})
        out.append({
            **_normalize_status(d),
            "student_name": s.get("name"),
            "student_class": s.get("class_id"),
            "student_section": s.get("section"),
        })
    return out


@router.get("/pending-approvals")
async def pending_approvals(user: dict = Depends(require_roles("school_admin", "teacher"))):
    """Leaves awaiting THIS user's role-specific approval (teacher or school_admin).
    Returns a list with student info. Also includes a `count` summary via the list length."""
    tdb = await tenant_db(user["school_id"])
    flt = await _scope_filter_for_user(tdb, user)
    if flt is None:
        return []
    flt["status"] = "pending"
    role_key = "teacher_approval" if user["role"] == "teacher" else "admin_approval"
    flt[f"{role_key}.status"] = "pending"
    docs = await tdb.sick_leaves.find(flt, {"_id": 0}).sort("created_at", 1).to_list(500)
    sids = list({d["student_id"] for d in docs})
    students = {s["id"]: s for s in await tdb.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(500)}
    out = []
    for d in docs:
        s = students.get(d["student_id"], {})
        out.append({
            **_normalize_status(d),
            "student_name": s.get("name"),
            "student_class": s.get("class_id"),
            "student_section": s.get("section"),
            "parent_name": d.get("recorded_by_name"),
        })
    return out


@router.get("/pending-count")
async def pending_count(user: dict = Depends(get_current_user)):
    """Count of approval requests awaiting this user's action. 0 for non-approvers."""
    if user["role"] not in ("school_admin", "teacher"):
        return {"count": 0}
    tdb = await tenant_db(user["school_id"])
    flt = await _scope_filter_for_user(tdb, user)
    if flt is None:
        return {"count": 0}
    flt["status"] = "pending"
    role_key = "teacher_approval" if user["role"] == "teacher" else "admin_approval"
    flt[f"{role_key}.status"] = "pending"
    n = await tdb.sick_leaves.count_documents(flt)
    return {"count": n}


async def _record_decision(
    tdb, leave_id: str, user: dict, decision: str, note: str | None,
) -> dict:
    leave = await tdb.sick_leaves.find_one({"id": leave_id})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    await _student_in_scope(tdb, user, leave["student_id"])
    if leave.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Leave is already {leave.get('status', 'approved')}")

    role_key = "teacher_approval" if user["role"] == "teacher" else "admin_approval"
    existing = leave.get(role_key) or {}
    if existing.get("status") and existing.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"You have already {existing['status']} this request")

    stamp = {
        "status": decision,  # 'approved' or 'rejected'
        "by": user["id"],
        "by_name": user.get("name"),
        "by_role": user["role"],
        "note": note,
        "decided_at": utc_now(),
    }
    update = {f"{role_key}": stamp}

    if decision == "rejected":
        update["status"] = "rejected"
    else:
        # If the OTHER approver has also already approved, mark overall approved.
        other_key = "admin_approval" if role_key == "teacher_approval" else "teacher_approval"
        other = leave.get(other_key) or {}
        if other.get("status") == "approved":
            update["status"] = "approved"

    await tdb.sick_leaves.update_one({"id": leave_id}, {"$set": update})

    refreshed = await tdb.sick_leaves.find_one({"id": leave_id}, {"_id": 0})
    if refreshed and refreshed.get("status") == "approved":
        await _mark_attendance_for_leave(tdb, refreshed, user["id"])

    await log_action(
        user["id"], user["role"], leave["school_id"],
        f"{decision}_sick_leave", "sick_leave", leave_id,
        meta={"role_key": role_key, "note": note},
    )
    return _normalize_status(refreshed)


@router.post("/{leave_id}/approve")
async def approve_leave(
    leave_id: str,
    payload: ApprovalDecision | None = None,
    user: dict = Depends(require_roles("school_admin", "teacher")),
):
    tdb = await tenant_db(user["school_id"])
    note = payload.note if payload else None
    return await _record_decision(tdb, leave_id, user, "approved", note)


@router.post("/{leave_id}/reject")
async def reject_leave(
    leave_id: str,
    payload: ApprovalDecision | None = None,
    user: dict = Depends(require_roles("school_admin", "teacher")),
):
    tdb = await tenant_db(user["school_id"])
    note = payload.note if payload else None
    return await _record_decision(tdb, leave_id, user, "rejected", note)


@router.post("/{leave_id}/appeal")
async def appeal_leave(
    leave_id: str,
    payload: AppealRequest,
    user: dict = Depends(require_roles("parent")),
):
    """Parent appeals a rejected sick leave. Resets it back to pending so both
    approvers review again, with the prior rejection captured in `appeals` history."""
    tdb = await tenant_db(user["school_id"])
    leave = await tdb.sick_leaves.find_one({"id": leave_id})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    await _student_in_scope(tdb, user, leave["student_id"])
    if leave.get("recorded_by") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the parent who recorded this leave can appeal it")
    if leave.get("status") != "rejected":
        raise HTTPException(status_code=400, detail=f"Only rejected leaves can be appealed (current: {leave.get('status', 'approved')})")
    if not payload.appeal_note or not payload.appeal_note.strip():
        raise HTTPException(status_code=400, detail="Appeal note is required")

    appeals = leave.get("appeals") or []
    appeals.append({
        "appealed_at": utc_now(),
        "appeal_note": payload.appeal_note.strip(),
        "previous_reason": leave.get("reason"),
        "previous_teacher_approval": leave.get("teacher_approval"),
        "previous_admin_approval": leave.get("admin_approval"),
    })

    update = {
        "status": "pending",
        "teacher_approval": {"status": "pending"},
        "admin_approval": {"status": "pending"},
        "appeals": appeals,
        "last_appeal_at": utc_now(),
        "last_appeal_note": payload.appeal_note.strip(),
    }
    if payload.reason is not None and payload.reason.strip():
        update["reason"] = payload.reason.strip()
    if payload.diagnosis is not None:
        update["diagnosis"] = payload.diagnosis.strip() or None

    await tdb.sick_leaves.update_one({"id": leave_id}, {"$set": update})
    await log_action(
        user["id"], user["role"], leave["school_id"],
        "appeal_sick_leave", "sick_leave", leave_id,
        meta={"appeal_count": len(appeals), "appeal_note": payload.appeal_note[:200]},
    )
    refreshed = await tdb.sick_leaves.find_one({"id": leave_id}, {"_id": 0})
    return _normalize_status(refreshed)


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
