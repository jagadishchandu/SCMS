"""Attendance: bulk entry by class+section, list, alerts."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import AttendanceBulkCreate
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now, parse_date
from core.notify import queue_notification

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/bulk")
async def bulk_mark(payload: AttendanceBulkCreate, user: dict = Depends(require_roles("teacher", "school_admin"))):
    tdb = await tenant_db(user["school_id"])
    date = parse_date(payload.date).isoformat()
    school_id = user["school_id"]

    # validate students belong to that class/section in this school
    student_ids = [e.student_id for e in payload.entries]
    students = await tdb.students.find({"school_id": school_id, "id": {"$in": student_ids}}, {"_id": 0}).to_list(2000)
    student_map = {s["id"]: s for s in students}

    inserted = 0
    notifications_created = 0
    for entry in payload.entries:
        student = student_map.get(entry.student_id)
        if not student:
            continue
        rec = {
            "id": new_id(),
            "school_id": school_id,
            "student_id": entry.student_id,
            "class_id": payload.class_id,
            "section": payload.section,
            "date": date,
            "status": entry.status,
            "remark": entry.remark,
            "marked_by": user["id"],
            "marked_at": utc_now(),
        }
        await tdb.attendance.update_one(
            {"school_id": school_id, "student_id": entry.student_id, "date": date},
            {"$set": rec},
            upsert=True,
        )
        inserted += 1

        if entry.status in ("absent", "sick"):
            parent_phone = student.get("parent", {}).get("whatsapp") or student.get("parent", {}).get("phone")
            msg_template = "attendance_absent" if entry.status == "absent" else "attendance_sick"
            label = "absent" if entry.status == "absent" else "on sick leave"
            message = (
                f"Dear Parent, your child {student['name']} ({student['student_uid']}) "
                f"was marked {label} on {date}. Please contact the school if this is incorrect."
            )
            await queue_notification(
                school_id, "parent", student.get("parent_user_id"), parent_phone,
                "whatsapp", msg_template, message,
                context={"student_id": student["id"], "date": date, "status": entry.status},
            )
            notifications_created += 1

    return {"marked": inserted, "notifications": notifications_created}


@router.get("")
async def list_attendance(
    student_id: str | None = None,
    class_id: str | None = None,
    section: str | None = None,
    date: str | None = None,
    month: str | None = None,
    user: dict = Depends(get_current_user),
):
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            flt: dict = {}
            if student_id: flt["student_id"] = student_id
            if class_id: flt["class_id"] = class_id
            if section: flt["section"] = section
            if date: flt["date"] = date
            if month: flt["date"] = {"$regex": f"^{month}-"}
            out.extend(await tdb.attendance.find(flt, {"_id": 0}).sort("date", -1).to_list(2000))
        return out

    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if user["role"] == "parent":
        kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if student_id:
        flt["student_id"] = student_id
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section
    if date:
        flt["date"] = date
    if month:
        flt["date"] = {"$regex": f"^{month}-"}
    return await tdb.attendance.find(flt, {"_id": 0}).sort("date", -1).to_list(5000)


@router.get("/summary/{student_id}")
async def attendance_summary(student_id: str, user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    flt = {"student_id": student_id}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        s = await tdb.students.find_one({"id": student_id, "parent_user_id": user["id"]})
        if not s:
            raise HTTPException(status_code=403, detail="Forbidden")
    records = await tdb.attendance.find(flt, {"_id": 0}).to_list(5000)
    total = len(records)
    counts = {"present": 0, "absent": 0, "sick": 0, "late": 0, "half_day": 0, "excused": 0}
    monthly = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        m = r["date"][:7]
        monthly.setdefault(m, {"present": 0, "absent": 0, "sick": 0, "late": 0, "half_day": 0, "excused": 0})
        monthly[m][r["status"]] = monthly[m].get(r["status"], 0) + 1
    present_like = counts["present"] + counts["late"] + counts["half_day"]
    pct = (present_like / total * 100) if total else 0
    return {
        "total_days": total,
        "counts": counts,
        "attendance_percentage": round(pct, 1),
        "monthly": [{"month": m, **v} for m, v in sorted(monthly.items())],
    }
