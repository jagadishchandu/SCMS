"""Marks + Exams + Syllabus."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import ExamCreate, SyllabusCreate, MarksBulkCreate
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(tags=["academic-ops"])


# ---------- Exams ----------
@router.get("/exams")
async def list_exams(class_id: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if class_id:
        flt["class_id"] = class_id
    if user["role"] == "parent":
        kids = await db.students.find({"parent_user_id": user["id"]}, {"_id": 0, "class_id": 1}).to_list(50)
        flt["class_id"] = {"$in": [k["class_id"] for k in kids]}
    return await db.exams.find(flt, {"_id": 0}).to_list(500)


@router.post("/exams")
async def create_exam(payload: ExamCreate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "name": payload.name,
        "term": payload.term,
        "class_id": payload.class_id,
        "section": payload.section,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "schedule": payload.schedule,
        "is_published": False,
        "created_at": utc_now(),
    }
    await db.exams.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/exams/{exam_id}/publish")
async def publish_exam(exam_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    exam = await db.exams.find_one({"id": exam_id, "school_id": user["school_id"]})
    if not exam:
        raise HTTPException(status_code=404, detail="Not found")
    await db.exams.update_one({"id": exam_id}, {"$set": {"is_published": True, "published_at": utc_now()}})
    # notify parents in that class
    students = await db.students.find({"school_id": user["school_id"], "class_id": exam["class_id"]}, {"_id": 0}).to_list(2000)
    for s in students:
        await queue_notification(
            user["school_id"], "parent", s.get("parent_user_id"),
            s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
            "whatsapp", "exam_schedule_published",
            f"Exam schedule for {exam['name']} ({exam['term']}) is now published. Starting {exam['start_date']}.",
            context={"exam_id": exam["id"], "student_id": s["id"]},
        )
    return {"ok": True, "notified_students": len(students)}


# ---------- Syllabus ----------
@router.get("/syllabus")
async def list_syllabus(exam_id: str | None = None, class_id: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if exam_id:
        flt["exam_id"] = exam_id
    if class_id:
        flt["class_id"] = class_id
    return await db.syllabus.find(flt, {"_id": 0}).to_list(500)


@router.post("/syllabus")
async def create_syllabus(payload: SyllabusCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "exam_id": payload.exam_id,
        "class_id": payload.class_id,
        "subject_id": payload.subject_id,
        "title": payload.title,
        "content": payload.content,
        "version": payload.version,
        "uploaded_by": user["id"],
        "created_at": utc_now(),
    }
    await db.syllabus.insert_one(doc)
    doc.pop("_id", None)
    # notify parents in class
    students = await db.students.find({"school_id": user["school_id"], "class_id": payload.class_id}, {"_id": 0}).to_list(2000)
    for s in students:
        await queue_notification(
            user["school_id"], "parent", s.get("parent_user_id"),
            s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
            "whatsapp", "syllabus_published",
            f"Syllabus '{payload.title}' has been published for {s['name']}'s class.",
            context={"syllabus_id": doc["id"], "student_id": s["id"]},
        )
    return doc


# ---------- Marks ----------
@router.post("/marks/bulk")
async def bulk_marks(payload: MarksBulkCreate, user: dict = Depends(require_roles("teacher", "school_admin"))):
    db = get_db()
    school_id = user["school_id"]
    saved = 0
    for e in payload.entries:
        rec = {
            "id": new_id(),
            "school_id": school_id,
            "exam_id": payload.exam_id,
            "subject_id": payload.subject_id,
            "student_id": e.student_id,
            "marks_obtained": e.marks_obtained,
            "max_marks": e.max_marks,
            "percentage": round((e.marks_obtained / e.max_marks * 100) if e.max_marks else 0, 2),
            "remark": e.remark,
            "entered_by": user["id"],
            "entered_at": utc_now(),
        }
        await db.marks.update_one(
            {"school_id": school_id, "student_id": e.student_id, "exam_id": payload.exam_id, "subject_id": payload.subject_id},
            {"$set": rec}, upsert=True,
        )
        saved += 1
    return {"saved": saved}


@router.get("/marks")
async def list_marks(student_id: str | None = None, exam_id: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        kids = await db.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if student_id:
        flt["student_id"] = student_id
    if exam_id:
        flt["exam_id"] = exam_id
    return await db.marks.find(flt, {"_id": 0}).to_list(5000)
