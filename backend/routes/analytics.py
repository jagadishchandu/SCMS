"""Student analytics dashboard + school dashboard."""
from fastapi import APIRouter, Depends, HTTPException
from core.auth import get_current_user
from core.db import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/student/{student_uid}")
async def student_dashboard(student_uid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"student_uid": student_uid}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await db.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")

    # Attendance
    att = await db.attendance.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(5000)
    counts = {"present": 0, "absent": 0, "sick": 0, "late": 0, "half_day": 0, "excused": 0}
    monthly = {}
    for r in att:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        m = r["date"][:7]
        monthly.setdefault(m, {"present": 0, "absent": 0, "sick": 0, "late": 0, "half_day": 0, "excused": 0})
        monthly[m][r["status"]] += 1
    total = len(att)
    present_like = counts["present"] + counts["late"] + counts["half_day"]
    att_pct = round((present_like / total * 100) if total else 0, 1)

    # Marks
    marks = await db.marks.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(2000)
    subjects = await db.subjects.find({"school_id": s["school_id"]}, {"_id": 0}).to_list(500)
    subject_map = {sub["id"]: sub["name"] for sub in subjects}
    exams = await db.exams.find({"school_id": s["school_id"]}, {"_id": 0}).to_list(500)
    exam_map = {e["id"]: e["name"] for e in exams}

    # Subject-wise avg & exam trend
    by_subject = {}
    by_exam = {}
    for m in marks:
        sub_name = subject_map.get(m["subject_id"], m["subject_id"])
        by_subject.setdefault(sub_name, []).append(m["percentage"])
        ex_name = exam_map.get(m["exam_id"], m["exam_id"])
        by_exam.setdefault(ex_name, []).append(m["percentage"])

    subject_avg = [{"subject": k, "avg": round(sum(v) / len(v), 1)} for k, v in by_subject.items()]
    exam_trend = [{"exam": k, "avg": round(sum(v) / len(v), 1)} for k, v in by_exam.items()]
    overall_pct = round(sum(m["percentage"] for m in marks) / len(marks), 1) if marks else 0

    # Class average comparison (same class)
    class_marks = await db.marks.find({"school_id": s["school_id"]}, {"_id": 0}).to_list(20000)
    class_students = await db.students.find({"school_id": s["school_id"], "class_id": s["class_id"]}, {"_id": 0, "id": 1}).to_list(2000)
    class_ids = {c["id"] for c in class_students}
    class_marks = [m for m in class_marks if m["student_id"] in class_ids]
    class_by_subject = {}
    for m in class_marks:
        sub_name = subject_map.get(m["subject_id"], m["subject_id"])
        class_by_subject.setdefault(sub_name, []).append(m["percentage"])
    class_subject_avg = {k: round(sum(v) / len(v), 1) for k, v in class_by_subject.items()}

    # Strongest/weakest subject
    sorted_subjects = sorted(subject_avg, key=lambda x: x["avg"])
    weakest = sorted_subjects[0] if sorted_subjects else None
    strongest = sorted_subjects[-1] if sorted_subjects else None

    # Improvement trend (last 2 exams diff)
    sorted_exam = sorted(by_exam.items(), key=lambda x: x[0])
    improvement = None
    if len(sorted_exam) >= 2:
        last_avg = sum(sorted_exam[-1][1]) / len(sorted_exam[-1][1])
        prev_avg = sum(sorted_exam[-2][1]) / len(sorted_exam[-2][1])
        diff = round(last_avg - prev_avg, 1)
        improvement = {"diff": diff, "status": "improving" if diff > 1 else ("declining" if diff < -1 else "stable")}

    # Fees
    fees = await db.fees.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(100)
    fee_total = sum(f["total"] for f in fees)
    fee_paid = sum(f["paid"] for f in fees)
    fee_due = sum(f["due"] for f in fees)
    overdue = sum(f["due"] for f in fees if f.get("status") in ("pending", "partial"))

    # Insights
    insights = []
    if att_pct < 75 and total > 5:
        insights.append({"type": "warning", "text": f"Attendance below expected level ({att_pct}%)."})
    if weakest and weakest["avg"] < 50:
        insights.append({"type": "danger", "text": f"{weakest['subject']} needs attention ({weakest['avg']}%)."})
    if strongest and strongest["avg"] >= 80:
        insights.append({"type": "success", "text": f"Strongest subject: {strongest['subject']} ({strongest['avg']}%)."})
    if improvement and improvement["status"] == "improving":
        insights.append({"type": "success", "text": f"Improving trend (+{improvement['diff']}% vs last exam)."})
    if improvement and improvement["status"] == "declining":
        insights.append({"type": "warning", "text": f"Marks declining ({improvement['diff']}% vs last exam)."})
    if counts["sick"] >= 5:
        insights.append({"type": "warning", "text": f"High sick leave count ({counts['sick']})."})
    if fee_due > 0:
        insights.append({"type": "danger", "text": f"Fee outstanding: {fee_due}."})

    return {
        "student": s,
        "attendance": {
            "total_days": total,
            "counts": counts,
            "attendance_percentage": att_pct,
            "monthly": [{"month": m, **v} for m, v in sorted(monthly.items())],
        },
        "academics": {
            "subject_avg": subject_avg,
            "exam_trend": exam_trend,
            "overall_percentage": overall_pct,
            "strongest": strongest,
            "weakest": weakest,
            "improvement": improvement,
            "class_subject_avg": class_subject_avg,
        },
        "fees": {
            "total": fee_total, "paid": fee_paid, "due": fee_due, "overdue": overdue,
        },
        "insights": insights,
    }


@router.get("/school")
async def school_dashboard(user: dict = Depends(get_current_user)):
    if user["role"] not in ("platform_admin", "school_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    sid = user.get("school_id")
    flt = {"school_id": sid} if sid else {}

    total_students = await db.students.count_documents({**flt, "status": "active"})
    total_teachers = await db.users.count_documents({**flt, "role": "teacher", "is_active": True})
    total_users = await db.users.count_documents({**flt, "is_active": True})
    total_classes = await db.classes.count_documents(flt)

    # Today's attendance
    from datetime import date
    today = date.today().isoformat()
    today_att = await db.attendance.find({**flt, "date": today}, {"_id": 0}).to_list(5000)
    present_today = sum(1 for r in today_att if r["status"] in ("present", "late", "half_day"))
    att_pct_today = round(present_today / len(today_att) * 100, 1) if today_att else 0

    fees = await db.fees.find(flt, {"_id": 0}).to_list(10000)
    billed = sum(f["total"] for f in fees)
    collected = sum(f["paid"] for f in fees)
    outstanding = sum(f["due"] for f in fees)

    # Notifications
    notif_total = await db.notifications.count_documents(flt)

    # Upcoming exams
    upcoming = await db.exams.find({**flt, "start_date": {"$gte": today}}, {"_id": 0}).sort("start_date", 1).to_list(10)
    # Upcoming holidays
    upcoming_holidays = await db.holidays.find({**flt, "date": {"$gte": today}}, {"_id": 0}).sort("date", 1).to_list(10)

    return {
        "kpis": {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_users": total_users,
            "total_classes": total_classes,
            "attendance_today_pct": att_pct_today,
            "fees_billed": billed,
            "fees_collected": collected,
            "fees_outstanding": outstanding,
            "notifications_sent": notif_total,
        },
        "upcoming_exams": upcoming,
        "upcoming_holidays": upcoming_holidays,
    }


@router.get("/teacher-performance")
async def teacher_performance(teacher_id: str | None = None, user: dict = Depends(get_current_user)):
    """40% attendance trend, 30% marks trend, 15% timely submission, 15% admin review.
    Only school_admin/platform_admin can see all teachers. Teacher can see only own.
    """
    db = get_db()
    if user["role"] == "teacher":
        teacher_id = user["id"]
    elif user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    school_id = user.get("school_id")
    q = {"school_id": school_id, "role": "teacher"}
    if teacher_id:
        q["id"] = teacher_id
    teachers = await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(500)

    results = []
    for t in teachers:
        # find assigned classes (class teacher + timetable)
        mappings = await db.class_teacher_map.find({"school_id": school_id, "teacher_id": t["id"]}, {"_id": 0}).to_list(50)
        timetable = await db.timetable.find({"school_id": school_id, "teacher_id": t["id"]}, {"_id": 0}).to_list(500)
        class_keys = {(m["class_id"], m["section"]) for m in mappings} | {(tt["class_id"], tt["section"]) for tt in timetable}

        if not class_keys:
            results.append({"teacher": t, "score": 0, "status": "Needs Attention", "breakdown": {}, "assigned_classes": 0})
            continue

        # attendance pct in those classes
        students_in_classes = []
        for c, s in class_keys:
            ss = await db.students.find({"school_id": school_id, "class_id": c, "section": s}, {"_id": 0, "id": 1}).to_list(2000)
            students_in_classes.extend([x["id"] for x in ss])

        att_pct = 0
        if students_in_classes:
            att = await db.attendance.find({"school_id": school_id, "student_id": {"$in": students_in_classes}}, {"_id": 0}).to_list(20000)
            present_like = sum(1 for a in att if a["status"] in ("present", "late", "half_day"))
            att_pct = round((present_like / len(att) * 100) if att else 0, 1)

        # marks improvement: avg percentage
        marks_avg = 0
        if students_in_classes:
            marks = await db.marks.find({"school_id": school_id, "student_id": {"$in": students_in_classes}}, {"_id": 0}).to_list(20000)
            marks_avg = round(sum(m["percentage"] for m in marks) / len(marks), 1) if marks else 0

        # timely submission heuristic: any marks/attendance submitted at all
        att_submitted = await db.attendance.count_documents({"school_id": school_id, "marked_by": t["id"]})
        marks_submitted = await db.marks.count_documents({"school_id": school_id, "entered_by": t["id"]})
        compliance_pct = 100 if (att_submitted > 0 or marks_submitted > 0) else 40

        # admin review (placeholder)
        admin_review = t.get("admin_review_score", 75)

        score = round(att_pct * 0.40 + marks_avg * 0.30 + compliance_pct * 0.15 + admin_review * 0.15, 1)
        status = "Excellent" if score >= 85 else ("Good" if score >= 70 else ("Needs Attention" if score >= 50 else "Critical Review"))

        results.append({
            "teacher": t,
            "score": score,
            "status": status,
            "breakdown": {
                "attendance_pct": att_pct,
                "marks_avg": marks_avg,
                "compliance_pct": compliance_pct,
                "admin_review": admin_review,
            },
            "assigned_classes": len(class_keys),
        })

    return results
