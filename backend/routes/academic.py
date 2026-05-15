"""Classes, sections, subjects, class-teacher assignment.

After v1.15: persisted in per-school DB (`scms_db_school_<code>`).
"""
from fastapi import APIRouter, Depends, HTTPException
from core.models import ClassCreate, SubjectCreate, ClassTeacherAssign
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/academic", tags=["academic"])


# ---- Classes ----
@router.get("/classes")
async def list_classes(user: dict = Depends(get_current_user)):
    school_id = user.get("school_id")
    if user["role"] == "platform_admin" and not school_id:
        # Aggregate classes across all schools
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            out.extend(await tdb.classes.find({}, {"_id": 0}).to_list(500))
        return out
    tdb = await tenant_db(school_id)
    return await tdb.classes.find({"school_id": school_id}, {"_id": 0}).to_list(1000)


@router.post("/classes")
async def create_class(payload: ClassCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "name": payload.name,
        "sections": payload.sections or ["A"],
        "created_at": utc_now(),
    }
    await tdb.classes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/classes/{class_id}")
async def delete_class(class_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    await tdb.classes.delete_one({"id": class_id, "school_id": user["school_id"]})
    return {"ok": True}


# ---- Subjects ----
@router.get("/subjects")
async def list_subjects(user: dict = Depends(get_current_user)):
    school_id = user.get("school_id")
    if user["role"] == "platform_admin" and not school_id:
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            out.extend(await tdb.subjects.find({}, {"_id": 0}).to_list(500))
        return out
    tdb = await tenant_db(school_id)
    return await tdb.subjects.find({"school_id": school_id}, {"_id": 0}).to_list(1000)


@router.post("/subjects")
async def create_subject(payload: SubjectCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "name": payload.name,
        "code": payload.code,
        "created_at": utc_now(),
    }
    await tdb.subjects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/subjects/{subject_id}")
async def delete_subject(subject_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    await tdb.subjects.delete_one({"id": subject_id, "school_id": user["school_id"]})
    return {"ok": True}


# ---- Class teacher assignment ----
@router.post("/class-teacher")
async def assign_class_teacher(payload: ClassTeacherAssign, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    # remove existing class teacher for this class+section
    await tdb.class_teacher_map.delete_many({
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
    await tdb.class_teacher_map.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/class-teacher")
async def list_class_teachers(user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    return await tdb.class_teacher_map.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(1000)
