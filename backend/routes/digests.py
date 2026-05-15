"""Monthly parent digest — composes attendance + marks + fees summary per child
and queues WhatsApp messages via the notification pipeline.

Endpoints:
- POST /api/digests/run-monthly        → School Admin runs for own school (or any if platform_admin)
- GET  /api/digests/preview/{student_uid} → Returns the digest message body for a single student (debug)

The notification pipeline already handles the Twilio gating: if Twilio env vars
are not set the message is persisted as `queued` and ready for retry when
Twilio is configured.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import date, datetime, timedelta, timezone

from core.auth import get_current_user, require_roles
from core.db import get_db
from core.notify import queue_notification
from core.audit import log_action

router = APIRouter(prefix="/digests", tags=["digests"])


def _previous_month_range(today: date | None = None) -> tuple[str, str, str]:
    """Return (YYYY-MM, start_iso, end_iso) for the previous calendar month."""
    today = today or date.today()
    first_of_this = today.replace(day=1)
    last_of_prev = first_of_this - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    label = first_of_prev.strftime("%B %Y")  # e.g. "April 2026"
    return label, first_of_prev.isoformat(), last_of_prev.isoformat()


async def _compute_digest(db, school: dict, student: dict, start_iso: str, end_iso: str) -> dict:
    sid = school["id"]
    # Attendance for this month
    att = await db.attendance.find({
        "school_id": sid, "student_id": student["id"],
        "date": {"$gte": start_iso, "$lte": end_iso},
    }, {"_id": 0}).to_list(2000)
    total = len(att)
    present_like = sum(1 for a in att if a["status"] in ("present", "late", "half_day"))
    absent = sum(1 for a in att if a["status"] == "absent")
    sick = sum(1 for a in att if a["status"] == "sick")
    att_pct = round(present_like / total * 100, 1) if total else 0

    # Latest exam marks within range (anything entered in that window)
    marks = await db.marks.find({
        "school_id": sid, "student_id": student["id"],
        "entered_at": {"$gte": datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc),
                       "$lte": datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc) + timedelta(days=1)},
    }, {"_id": 0}).to_list(2000)
    overall_pct = round(sum(m["percentage"] for m in marks) / len(marks), 1) if marks else None

    # Fees
    fees = await db.fees.find({"school_id": sid, "student_id": student["id"]}, {"_id": 0}).to_list(50)
    due = sum(f["due"] for f in fees)

    return {"att_total": total, "att_pct": att_pct, "absent": absent, "sick": sick,
            "marks_pct": overall_pct, "fee_due": due}


def _compose_message(school: dict, student: dict, label: str, d: dict) -> str:
    parts = [f"📚 {school['name']} — Monthly update for {student['name']} ({student['student_uid']})"]
    parts.append(f"Period: {label}")
    if d["att_total"]:
        parts.append(f"Attendance: {d['att_pct']}% over {d['att_total']} days "
                     f"(absent: {d['absent']}, sick: {d['sick']})")
    else:
        parts.append("Attendance: no records this month")
    if d["marks_pct"] is not None:
        parts.append(f"Marks average: {d['marks_pct']}%")
    if d["fee_due"] > 0:
        parts.append(f"Fees outstanding: INR {d['fee_due']:,.0f}")
    else:
        parts.append("Fees: all clear ✅")
    parts.append("Reply STOP to opt out.")
    return "\n".join(parts)


@router.get("/preview/{student_uid}")
async def preview(student_uid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"student_uid": student_uid}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await db.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    school = await db.schools.find_one({"id": s["school_id"]}, {"_id": 0})
    label, start_iso, end_iso = _previous_month_range()
    digest = await _compute_digest(db, school, s, start_iso, end_iso)
    return {
        "label": label, "start": start_iso, "end": end_iso,
        "data": digest,
        "message": _compose_message(school, s, label, digest),
    }


@router.post("/run-monthly")
async def run_monthly(
    school_id: str | None = None,
    user: dict = Depends(require_roles("school_admin", "platform_admin")),
):
    """Generate and queue the previous-month digest for every active student.

    - school_admin: scoped to own school_id automatically
    - platform_admin: must pass school_id; if omitted, runs for all schools
    """
    db = get_db()
    label, start_iso, end_iso = _previous_month_range()

    targets = []
    if user["role"] == "school_admin":
        targets = [user["school_id"]]
    else:
        if school_id:
            targets = [school_id]
        else:
            schools = await db.schools.find({"is_active": True}, {"_id": 0, "id": 1}).to_list(500)
            targets = [s["id"] for s in schools]

    queued = 0
    sent = 0
    failed = 0
    by_school = []
    for sid in targets:
        school = await db.schools.find_one({"id": sid}, {"_id": 0})
        if not school:
            continue
        students = await db.students.find({"school_id": sid, "status": "active"}, {"_id": 0}).to_list(5000)
        school_sent = 0; school_queued = 0; school_failed = 0
        for s in students:
            digest = await _compute_digest(db, school, s, start_iso, end_iso)
            msg = _compose_message(school, s, label, digest)
            phone = (s.get("parent", {}) or {}).get("whatsapp") or (s.get("parent", {}) or {}).get("phone")
            doc = await queue_notification(
                sid, "parent", s.get("parent_user_id"), phone,
                "whatsapp", "monthly_digest", msg,
                context={"student_id": s["id"], "period": label,
                         "att_pct": digest["att_pct"], "marks_pct": digest["marks_pct"],
                         "fee_due": digest["fee_due"]},
            )
            if doc["status"] == "sent":
                sent += 1; school_sent += 1
            elif doc["status"] == "failed":
                failed += 1; school_failed += 1
            else:
                queued += 1; school_queued += 1
        by_school.append({"school_id": sid, "school_name": school["name"],
                          "students": len(students), "sent": school_sent,
                          "queued": school_queued, "failed": school_failed})
        await log_action(user["id"], user["role"], sid, "run_monthly_digest", "digest",
                         meta={"period": label, "students": len(students)})

    return {
        "period": label,
        "totals": {"sent": sent, "queued": queued, "failed": failed},
        "by_school": by_school,
    }
