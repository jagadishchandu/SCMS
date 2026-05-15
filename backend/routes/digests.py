"""Monthly parent digest — composes attendance + marks + fees summary per child
and queues WhatsApp + Email messages via the notification pipeline.

Endpoints:
- POST /api/digests/run-monthly        → School Admin runs for own school (or any if platform_admin)
- GET  /api/digests/preview/{student_uid} → Returns the digest message body for a single student (debug)

The notification pipeline handles delivery gating: if Twilio (WhatsApp) or SMTP
(email) env vars are not set the message is persisted as `queued` and ready for
retry when configured.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import date, datetime, timedelta, timezone

from core.auth import get_current_user, require_roles
from core.db import get_db
from core.notify import queue_notification
from core.audit import log_action
from core.i18n import render

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


def _compose_message(school: dict, student: dict, label: str, d: dict, lang: str = "en") -> str:
    """Render the localized monthly digest message via i18n templates."""
    att_total = d["att_total"]
    if att_total:
        att_line = f"{d['att_pct']}% over {att_total} days (absent: {d['absent']}, sick: {d['sick']})"
    else:
        att_line = "no records"
    marks_line = f"{d['marks_pct']}%" if d["marks_pct"] is not None else "—"
    if d["fee_due"] > 0:
        fee_line = f"INR {d['fee_due']:,.0f} outstanding"
    else:
        fee_line = "all clear"
    return render(
        "monthly_digest", lang,
        school_name=school["name"],
        student_name=student["name"],
        student_uid=student["student_uid"],
        period=label,
        att_line=att_line,
        marks_line=marks_line,
        fee_line=fee_line,
    )


@router.get("/preview/{student_uid}")
async def preview(student_uid: str, lang: str | None = None, user: dict = Depends(get_current_user)):
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
    # Effective language: parent.language → school.language → 'en'
    parent = await db.users.find_one({"id": s.get("parent_user_id")}, {"_id": 0, "language": 1}) if s.get("parent_user_id") else None
    effective_lang = lang or (parent or {}).get("language") or school.get("language") or "en"
    return {
        "label": label, "start": start_iso, "end": end_iso,
        "language": effective_lang,
        "data": digest,
        "message": _compose_message(school, s, label, digest, effective_lang),
    }


@router.post("/run-monthly")
async def run_monthly(
    school_id: str | None = None,
    channels: str = "whatsapp,email",
    user: dict = Depends(require_roles("school_admin", "platform_admin")),
):
    """Generate and queue the previous-month digest for every active student.

    - school_admin: scoped to own school_id automatically
    - platform_admin: must pass school_id; if omitted, runs for all schools
    - channels: comma-separated list, from {whatsapp, email, telegram}
    """
    db = get_db()
    label, start_iso, end_iso = _previous_month_range()
    wanted_channels = [c.strip() for c in channels.split(",") if c.strip() in ("whatsapp", "email", "telegram")]
    if not wanted_channels:
        wanted_channels = ["whatsapp"]

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
        school_sent = 0
        school_queued = 0
        school_failed = 0
        for s in students:
            parent_user = await db.users.find_one({"id": s.get("parent_user_id")}, {"_id": 0}) if s.get("parent_user_id") else None
            lang = (parent_user or {}).get("language") or school.get("language") or "en"
            digest = await _compute_digest(db, school, s, start_iso, end_iso)
            msg = _compose_message(school, s, label, digest, lang)
            phone = (s.get("parent", {}) or {}).get("whatsapp") or (s.get("parent", {}) or {}).get("phone")
            email = (s.get("parent", {}) or {}).get("email") or (parent_user or {}).get("email")
            tg_chat_id = (parent_user or {}).get("telegram_chat_id")
            context = {"student_id": s["id"], "period": label, "language": lang,
                       "att_pct": digest["att_pct"], "marks_pct": digest["marks_pct"],
                       "fee_due": digest["fee_due"]}

            for ch in wanted_channels:
                if ch == "whatsapp" and not phone:
                    continue
                if ch == "email" and not email:
                    continue
                if ch == "telegram" and not tg_chat_id:
                    continue
                doc = await queue_notification(
                    sid, "parent", s.get("parent_user_id"),
                    phone if ch == "whatsapp" else None,
                    ch, "monthly_digest", msg,
                    context=context,
                    email=email if ch == "email" else None,
                    subject=f"Monthly update — {s['name']} ({label})",
                    telegram_chat_id=tg_chat_id if ch == "telegram" else None,
                )
                if doc["status"] == "sent":
                    sent += 1
                    school_sent += 1
                elif doc["status"] == "failed":
                    failed += 1
                    school_failed += 1
                else:
                    queued += 1
                    school_queued += 1
        by_school.append({"school_id": sid, "school_name": school["name"],
                          "students": len(students), "sent": school_sent,
                          "queued": school_queued, "failed": school_failed})
        await log_action(user["id"], user["role"], sid, "run_monthly_digest", "digest",
                         meta={"period": label, "students": len(students), "channels": wanted_channels})

    return {
        "period": label,
        "channels": wanted_channels,
        "totals": {"sent": sent, "queued": queued, "failed": failed},
        "by_school": by_school,
    }
