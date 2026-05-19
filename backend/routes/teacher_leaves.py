"""Teacher leave requests.

Teachers raise their own leave request; the school admin approves or rejects.
Once approved, the teacher's daily teacher_attendance is auto-marked `leave`
for every weekday (Mon-Sat) in the range. This naturally surfaces in the
timetable view (cells tint warning and show "ON LEAVE — find substitute").
"""
from datetime import date as date_cls, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.audit import log_action
from core.notify import queue_notification

router = APIRouter(prefix="/teacher-leaves", tags=["teacher-leaves"])

LeaveType = Literal["sick", "casual", "earned", "maternity", "other"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]


class TeacherLeaveCreate(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str
    leave_type: LeaveType = "casual"
    reason: Optional[str] = None


class TeacherLeaveDecision(BaseModel):
    note: Optional[str] = None


def _working_days(start_iso: str, end_iso: str) -> int:
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


async def _mark_attendance_for_leave(tdb, leave: dict):
    """Stamp teacher_attendance as 'leave' for every weekday (Mon-Sat) inside the range."""
    start = datetime.fromisoformat(leave["start_date"]).date()
    end = datetime.fromisoformat(leave["end_date"]).date()
    d = start
    while d <= end:
        if d.weekday() != 6:  # skip Sunday
            iso = d.isoformat()
            rec = {
                "id": new_id(),
                "school_id": leave["school_id"],
                "teacher_id": leave["teacher_id"],
                "date": iso,
                "status": "leave",
                "remark": (leave.get("reason") or f"{leave.get('leave_type','leave')} leave")[:120],
                "marked_by": leave.get("decided_by") or leave.get("teacher_id"),
                "marked_at": utc_now(),
                "auto_from_leave_id": leave["id"],
            }
            await tdb.teacher_attendance.update_one(
                {"school_id": leave["school_id"], "teacher_id": leave["teacher_id"], "date": iso},
                {"$set": rec},
                upsert=True,
            )
        d += timedelta(days=1)


async def _unmark_attendance_for_leave(tdb, leave: dict):
    """Remove the auto-marked leave attendance rows when a leave is cancelled
    or its approval is otherwise revoked. Only removes rows we stamped."""
    await tdb.teacher_attendance.delete_many(
        {
            "school_id": leave["school_id"],
            "teacher_id": leave["teacher_id"],
            "auto_from_leave_id": leave["id"],
        }
    )


@router.post("")
async def create_leave(
    payload: TeacherLeaveCreate,
    user: dict = Depends(require_roles("teacher")),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "teacher_id": user["id"],
        "teacher_name": user.get("name"),
        "leave_type": payload.leave_type,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "working_days": _working_days(payload.start_date, payload.end_date),
        "reason": (payload.reason or "").strip() or None,
        "status": "pending",
        "decided_by": None,
        "decided_by_name": None,
        "decided_at": None,
        "decision_note": None,
        "created_at": utc_now(),
    }
    await tdb.teacher_leaves.insert_one(doc)
    await log_action(
        user["id"], user["role"], user["school_id"],
        "request_teacher_leave", "teacher_leave", doc["id"],
        meta={"start": payload.start_date, "end": payload.end_date, "type": payload.leave_type},
    )
    # Notify school admin(s) in-app
    rdb = get_db()
    admins = await rdb.users.find(
        {"school_id": user["school_id"], "role": "school_admin", "is_active": True},
        {"_id": 0, "id": 1, "phone": 1},
    ).to_list(50)
    msg = (
        f"📝 Leave request from {user.get('name') or 'a teacher'}: "
        f"{payload.leave_type} · {payload.start_date} → {payload.end_date} "
        f"({doc['working_days']} day(s)). Open the app to review."
    )
    for a in admins:
        try:
            await queue_notification(
                school_id=user["school_id"],
                recipient_type="school_admin",
                recipient_id=a["id"],
                phone=a.get("phone"),
                channel="in_app",
                template="teacher_leave_requested",
                message=msg,
                context={"leave_id": doc["id"], "teacher_id": user["id"]},
            )
        except Exception:
            pass
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_leaves(
    status: Optional[LeaveStatus] = None,
    teacher_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("school_admin", "teacher"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    flt: dict = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        flt["teacher_id"] = user["id"]
    elif teacher_id:
        flt["teacher_id"] = teacher_id
    if status:
        flt["status"] = status
    return await tdb.teacher_leaves.find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.get("/pending-count")
async def pending_count(user: dict = Depends(get_current_user)):
    if user["role"] != "school_admin":
        return {"count": 0}
    tdb = await tenant_db(user["school_id"])
    n = await tdb.teacher_leaves.count_documents(
        {"school_id": user["school_id"], "status": "pending"}
    )
    return {"count": n}


@router.get("/active")
async def active_on_date(
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Approved leaves covering the given date (defaults to today).
    Returns teacher_id list — used by the Timetable view to show
    "ON LEAVE — find substitute" on the right cells.
    """
    if user["role"] not in ("school_admin", "teacher", "accounts"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    iso = date or date_cls.today().isoformat()
    rows = await tdb.teacher_leaves.find(
        {
            "school_id": user["school_id"],
            "status": "approved",
            "start_date": {"$lte": iso},
            "end_date": {"$gte": iso},
        },
        {"_id": 0},
    ).to_list(1000)
    return {"date": iso, "leaves": rows, "teacher_ids": sorted({r["teacher_id"] for r in rows})}


async def _decide(
    leave_id: str, user: dict, decision: Literal["approved", "rejected"], note: Optional[str],
):
    tdb = await tenant_db(user["school_id"])
    leave = await tdb.teacher_leaves.find_one({"id": leave_id, "school_id": user["school_id"]})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    if leave.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Leave already {leave.get('status')}")
    update = {
        "status": decision,
        "decided_by": user["id"],
        "decided_by_name": user.get("name"),
        "decided_at": utc_now(),
        "decision_note": (note or "").strip() or None,
    }
    await tdb.teacher_leaves.update_one({"id": leave_id}, {"$set": update})
    refreshed = await tdb.teacher_leaves.find_one({"id": leave_id}, {"_id": 0})
    if decision == "approved":
        await _mark_attendance_for_leave(tdb, refreshed)
    await log_action(
        user["id"], user["role"], user["school_id"],
        f"{decision}_teacher_leave", "teacher_leave", leave_id,
        meta={"note": note, "teacher_id": leave["teacher_id"]},
    )
    # In-app notify the teacher of the decision
    msg = (
        f"✅ Your leave ({refreshed['start_date']} → {refreshed['end_date']}) was approved."
        if decision == "approved"
        else f"❌ Your leave ({refreshed['start_date']} → {refreshed['end_date']}) was rejected."
    )
    if note:
        msg += f" Note: {note}"
    try:
        await queue_notification(
            school_id=user["school_id"],
            recipient_type="teacher",
            recipient_id=leave["teacher_id"],
            phone=None,
            channel="in_app",
            template=f"teacher_leave_{decision}",
            message=msg,
            context={"leave_id": leave_id, "decision": decision},
        )
    except Exception:
        pass
    return refreshed


@router.post("/{leave_id}/approve")
async def approve_leave(
    leave_id: str,
    payload: TeacherLeaveDecision | None = None,
    user: dict = Depends(require_roles("school_admin")),
):
    note = payload.note if payload else None
    return await _decide(leave_id, user, "approved", note)


@router.post("/{leave_id}/reject")
async def reject_leave(
    leave_id: str,
    payload: TeacherLeaveDecision | None = None,
    user: dict = Depends(require_roles("school_admin")),
):
    note = payload.note if payload else None
    return await _decide(leave_id, user, "rejected", note)


@router.delete("/{leave_id}")
async def cancel_leave(
    leave_id: str,
    user: dict = Depends(require_roles("teacher", "school_admin")),
):
    """Teacher cancels their own pending leave. School admin can cancel any
    pending leave (effectively a rejection without a note)."""
    tdb = await tenant_db(user["school_id"])
    leave = await tdb.teacher_leaves.find_one({"id": leave_id, "school_id": user["school_id"]})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    if user["role"] == "teacher" and leave["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your leave")
    if leave.get("status") == "approved":
        # Roll back the auto-marked attendance rows
        await _unmark_attendance_for_leave(tdb, leave)
    await tdb.teacher_leaves.update_one(
        {"id": leave_id},
        {"$set": {"status": "cancelled", "cancelled_at": utc_now(), "cancelled_by": user["id"]}},
    )
    await log_action(
        user["id"], user["role"], user["school_id"],
        "cancel_teacher_leave", "teacher_leave", leave_id,
    )
    return {"ok": True}
