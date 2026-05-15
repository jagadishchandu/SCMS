"""Classes, sections, subjects, class-teacher assignment."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import ClassCreate, SubjectCreate, ClassTeacherAssign
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/academic", tags=["academic"])


# ---- Classes ----
@router.get("/classes")
async def list_classes(user: dict = Depends(get_current_user)):
    db = get_db()
    school_id = user.get("school_id")
    if user["role"] == "platform_admin" and not school_id:
        return await db.classes.find({}, {"_id": 0}).to_list(1000)
    return await db.classes.find({"school_id": school_id}, {"_id": 0}).to_list(1000)


@router.post("/classes")
async def create_class(payload: ClassCreate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "name": payload.name,
        "sections": payload.sections or ["A"],
        "created_at": utc_now(),
    }
    await db.classes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/classes/{class_id}")
async def delete_class(class_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    await db.classes.delete_one({"id": class_id, "school_id": user["school_id"]})
    return {"ok": True}


# ---- Subjects ----
@router.get("/subjects")
async def list_subjects(user: dict = Depends(get_current_user)):
    db = get_db()
    school_id = user.get("school_id")
    return await db.subjects.find({"school_id": school_id}, {"_id": 0}).to_list(1000)


@router.post("/subjects")
async def create_subject(payload: SubjectCreate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "name": payload.name,
        "code": payload.code,
        "created_at": utc_now(),
    }
    await db.subjects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/subjects/{subject_id}")
async def delete_subject(subject_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    await db.subjects.delete_one({"id": subject_id, "school_id": user["school_id"]})
    return {"ok": True}


# ---- Class teacher assignment ----
@router.post("/class-teacher")
async def assign_class_teacher(payload: ClassTeacherAssign, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    # remove existing class teacher for this class+section
    await db.class_teacher_map.delete_many({
        "school_id": user["school_id"], "class_id": payload.class_id, "section": payload.section
    })
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "class_id": payload.class_id,
        "section": payload.section,
        "teacher_id": payload.teacher_id,
        "created_at": utc_now(),
    }
    await db.class_teacher_map.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/class-teacher")
async def list_class_teachers(user: dict = Depends(get_current_user)):
    db = get_db()
    return await db.class_teacher_map.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(1000)
