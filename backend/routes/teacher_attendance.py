"""Teacher attendance: school_admin / accounts mark teachers daily.

One row per (teacher_id, date) in the per-school `teacher_attendance` collection.
Statuses: present / absent / leave / half_day.
"""
from datetime import date as date_cls, timedelta
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now, parse_date
from core.audit import log_action

router = APIRouter(prefix="/teacher-attendance", tags=["teacher-attendance"])

TeacherAttStatus = Literal["present", "absent", "leave", "half_day"]


class TeacherAttEntry(BaseModel):
    teacher_id: str
    status: TeacherAttStatus
    remark: Optional[str] = None


class TeacherAttBulk(BaseModel):
    date: str  # YYYY-MM-DD
    entries: list[TeacherAttEntry]


@router.post("/bulk")
async def bulk_mark_teacher_attendance(
    payload: TeacherAttBulk,
    user: dict = Depends(require_roles("school_admin", "accounts")),
):
    """Upsert one row per (teacher_id, date). Idempotent."""
    db = get_db()
    tdb = await tenant_db(user["school_id"])
    iso_date = parse_date(payload.date).isoformat()
    teacher_ids = [e.teacher_id for e in payload.entries]
    # Validate all teacher_ids are real teachers in this school
    teachers = await db.users.find(
        {"id": {"$in": teacher_ids}, "school_id": user["school_id"], "role": "teacher"},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(2000)
    valid_ids = {t["id"] for t in teachers}
    marked = 0
    for entry in payload.entries:
        if entry.teacher_id not in valid_ids:
            continue
        rec = {
            "id": new_id(),
            "school_id": user["school_id"],
            "teacher_id": entry.teacher_id,
            "date": iso_date,
            "status": entry.status,
            "remark": entry.remark,
            "marked_by": user["id"],
            "marked_at": utc_now(),
        }
        await tdb.teacher_attendance.update_one(
            {"school_id": user["school_id"], "teacher_id": entry.teacher_id, "date": iso_date},
            {"$set": rec},
            upsert=True,
        )
        marked += 1
    await log_action(
        user["id"], user["role"], user["school_id"],
        "bulk_mark", "teacher_attendance", iso_date,
        {"marked": marked, "date": iso_date},
    )
    return {"marked": marked, "date": iso_date}


@router.get("")
async def list_teacher_attendance(
    date: Optional[str] = None,
    teacher_id: Optional[str] = None,
    month: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List teacher attendance rows. School admin / accounts / teachers (own only)."""
    if user["role"] not in ("school_admin", "accounts", "teacher", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    flt: dict = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        flt["teacher_id"] = user["id"]
    elif teacher_id:
        flt["teacher_id"] = teacher_id
    if date:
        flt["date"] = parse_date(date).isoformat()
    elif month:
        flt["date"] = {"$regex": f"^{month}-"}
    return await tdb.teacher_attendance.find(flt, {"_id": 0}).sort("date", -1).to_list(5000)


@router.get("/today")
async def teacher_attendance_today(user: dict = Depends(get_current_user)):
    """Today's roster: every teacher in the school + their marked status (or
    `unmarked`). Used by the Attendance > Teachers tab and timetable cell tints.
    """
    if user["role"] not in ("school_admin", "accounts", "teacher", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    tdb = await tenant_db(user["school_id"])
    today = date_cls.today().isoformat()
    teachers = await db.users.find(
        {"school_id": user["school_id"], "role": "teacher", "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1},
    ).sort("name", 1).to_list(2000)
    rows = await tdb.teacher_attendance.find(
        {"school_id": user["school_id"], "date": today}, {"_id": 0},
    ).to_list(2000)
    by_tid = {r["teacher_id"]: r for r in rows}
    out = []
    for t in teachers:
        rec = by_tid.get(t["id"])
        out.append({
            **t,
            "status": rec.get("status") if rec else "unmarked",
            "remark": rec.get("remark") if rec else None,
            "marked_by": rec.get("marked_by") if rec else None,
            "marked_at": rec.get("marked_at") if rec else None,
        })
    counts = {"present": 0, "absent": 0, "leave": 0, "half_day": 0, "unmarked": 0}
    for r in out:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"date": today, "teachers": out, "counts": counts}


# ---------- Student-absentee panel (day / week / month aggregation) ----------

absentee_router = APIRouter(prefix="/attendance", tags=["attendance"])


def _week_bounds(d: date_cls) -> tuple[date_cls, date_cls]:
    """Mon-Sun bounds for a given date (ISO week)."""
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


@absentee_router.get("/absentees")
async def list_absentees(
    period: Literal["day", "week", "month"] = "day",
    date: Optional[str] = None,
    class_id: Optional[str] = None,
    section: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """One-stop panel for the school admin: students absent in the picked
    period (day / week / month). Includes counts and attendance percentage.

    - day  -> simple list of absent students for the picked date
    - week -> students with any absence in the Mon-Sun week of the picked date
              (count of absent + sick days, and total days they had records)
    - month-> same as week but for the picked month + attendance percentage

    Implementation: Mongo aggregation pipeline ($group on student_id with
    conditional sums per status, then $match to keep only students with at
    least one absent/sick day). Scales to ~hundreds of thousands of rows
    without pulling them into Python.
    """
    if user["role"] not in ("school_admin", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    today = date_cls.today()
    base = parse_date(date) if date else today

    if period == "day":
        iso = base.isoformat()
        date_match: dict = {"date": iso}
    elif period == "week":
        start, end = _week_bounds(base)
        date_match = {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    else:  # month
        month_key = base.strftime("%Y-%m")
        date_match = {"date": {"$regex": f"^{month_key}-"}}

    match_stage: dict = {"school_id": user["school_id"], **date_match}
    if class_id:
        match_stage["class_id"] = class_id
    if section:
        match_stage["section"] = section

    # Build the $group expression: one counter per status using $sum + $cond.
    def _sum_when(status_val: str) -> dict:
        return {"$sum": {"$cond": [{"$eq": ["$status", status_val]}, 1, 0]}}

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": "$student_id",
            "absent_days": _sum_when("absent"),
            "sick_days": _sum_when("sick"),
            "present_days": _sum_when("present"),
            "late_days": _sum_when("late"),
            "half_day_days": _sum_when("half_day"),
            "excused_days": _sum_when("excused"),
            "total_days": {"$sum": 1},
            # Last absent/sick date — pick the max date when status is absent|sick.
            "last_absent_date": {"$max": {
                "$cond": [
                    {"$in": ["$status", ["absent", "sick"]]},
                    "$date",
                    None,
                ],
            }},
        }},
        # Keep only students with at least one absent/sick day.
        {"$match": {"$expr": {"$gt": [{"$add": ["$absent_days", "$sick_days"]}, 0]}}},
        # Order so the worst absentees are at the top (most absences first).
        {"$sort": {"absent_days": -1, "sick_days": -1}},
    ]

    rows = await tdb.attendance.aggregate(pipeline).to_list(20000)
    if not rows:
        return {
            "period": period,
            "date": base.isoformat(),
            "absentees": [],
            "summary": {"students": 0, "total_absent_days": 0, "total_sick_days": 0},
        }

    absentee_ids = [r["_id"] for r in rows]
    students = await tdb.students.find(
        {"school_id": user["school_id"], "id": {"$in": absentee_ids}}, {"_id": 0},
    ).to_list(20000)
    classes = await tdb.classes.find(
        {"school_id": user["school_id"]}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(500)
    class_map = {c["id"]: c["name"] for c in classes}
    s_map = {s["id"]: s for s in students}

    # Need the last-absent status (absent vs sick) — one extra targeted lookup
    # per matched student. Keeps the aggregation simple while preserving the row.
    absentees = []
    for r in rows:
        sid = r["_id"]
        stu = s_map.get(sid) or {}
        total = r.get("total_days", 0)
        present_like = r.get("present_days", 0) + r.get("late_days", 0) + r.get("half_day_days", 0)
        pct = round((present_like / total) * 100, 1) if total else 0.0
        last_status = None
        last_date = r.get("last_absent_date")
        if last_date:
            last_rec = await tdb.attendance.find_one(
                {"school_id": user["school_id"], "student_id": sid, "date": last_date,
                 "status": {"$in": ["absent", "sick"]}},
                {"_id": 0, "status": 1},
            )
            if last_rec:
                last_status = last_rec.get("status")
        absentees.append({
            "student_id": sid,
            "absent_days": r.get("absent_days", 0),
            "sick_days": r.get("sick_days", 0),
            "present_days": r.get("present_days", 0),
            "late_days": r.get("late_days", 0),
            "half_day_days": r.get("half_day_days", 0),
            "excused_days": r.get("excused_days", 0),
            "total_days": total,
            "last_absent_date": last_date,
            "last_absent_status": last_status,
            "name": stu.get("name"),
            "student_uid": stu.get("student_uid"),
            "class_id": stu.get("class_id"),
            "class_name": class_map.get(stu.get("class_id")),
            "section": stu.get("section"),
            "parent_phone": (stu.get("parent") or {}).get("phone"),
            "attendance_percentage": pct,
        })
    summary = {
        "students": len(absentees),
        "total_absent_days": sum(a["absent_days"] for a in absentees),
        "total_sick_days": sum(a["sick_days"] for a in absentees),
    }
    return {
        "period": period,
        "date": base.isoformat(),
        "absentees": absentees,
        "summary": summary,
    }
