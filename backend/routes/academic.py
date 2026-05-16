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
async def create_class(payload: ClassCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
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


@router.post("/classes/{class_id}/sections")
async def add_section(class_id: str, payload: dict, user: dict = Depends(require_roles("school_admin", "teacher"))):
    """Add a new section to an existing class. Available to school_admin and teacher."""
    section = (payload.get("section") or "").strip().upper()
    if not section:
        raise HTTPException(status_code=400, detail="Section name is required")
    tdb = await tenant_db(user["school_id"])
    cls = await tdb.classes.find_one({"id": class_id, "school_id": user["school_id"]})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    existing = [s.upper() for s in (cls.get("sections") or [])]
    if section in existing:
        raise HTTPException(status_code=400, detail=f"Section '{section}' already exists in this class")
    new_sections = sorted(existing + [section])
    await tdb.classes.update_one({"id": class_id}, {"$set": {"sections": new_sections}})
    return {"ok": True, "sections": new_sections}


@router.delete("/classes/{class_id}/sections/{section}")
async def remove_section(class_id: str, section: str, user: dict = Depends(require_roles("school_admin"))):
    """Remove a section from a class. School_admin only."""
    section = section.strip().upper()
    tdb = await tenant_db(user["school_id"])
    cls = await tdb.classes.find_one({"id": class_id, "school_id": user["school_id"]})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    sections = [s for s in (cls.get("sections") or []) if s.upper() != section]
    await tdb.classes.update_one({"id": class_id}, {"$set": {"sections": sections}})
    return {"ok": True, "sections": sections}


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
async def create_subject(payload: SubjectCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
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


# ---- Subject ⇄ teacher coverage & bulk-assignment ----
@router.get("/subjects/coverage")
async def subject_teacher_coverage(user: dict = Depends(require_roles("school_admin"))):
    """One row per subject with the list of teachers who teach it.

    Includes subjects with zero teachers (orphan subjects) so admins can spot them.
    Used by the Academic → Subjects page to show the coverage matrix.
    """
    from core.db import get_db as _root_db
    tdb = await tenant_db(user["school_id"])
    rdb = _root_db()
    subjects = await tdb.subjects.find({"school_id": user["school_id"]}, {"_id": 0}).sort("name", 1).to_list(1000)
    teachers = await rdb.users.find(
        {"school_id": user["school_id"], "role": "teacher", "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "subjects": 1},
    ).to_list(2000)
    rows = []
    for s in subjects:
        assigned = [
            {"id": t["id"], "name": t["name"], "email": t.get("email")}
            for t in teachers if s["id"] in (t.get("subjects") or [])
        ]
        rows.append({
            "subject_id": s["id"],
            "subject_name": s["name"],
            "code": s.get("code"),
            "teacher_count": len(assigned),
            "teachers": assigned,
        })
    return {
        "subjects": rows,
        "total_teachers": len(teachers),
        "orphan_count": sum(1 for r in rows if r["teacher_count"] == 0),
    }


@router.post("/subjects/{subject_id}/bulk-assign-teachers")
async def bulk_assign_subject_to_teachers(
    subject_id: str,
    payload: dict,
    user: dict = Depends(require_roles("school_admin")),
):
    """Idempotently add this subject to each teacher's `subjects` array.

    Body: {"teacher_ids": ["...", "..."], "replace": false}
    - When replace=False (default): adds the subject id to each teacher (uses $addToSet — safe for re-runs).
    - When replace=True: the provided teacher list becomes the AUTHORITATIVE list of teachers for this subject — i.e. it is removed from all other teachers in the school.
    """
    from core.db import get_db as _root_db
    teacher_ids = list(dict.fromkeys(payload.get("teacher_ids") or []))  # de-dup, keep order
    replace = bool(payload.get("replace", False))
    tdb = await tenant_db(user["school_id"])
    rdb = _root_db()
    subj = await tdb.subjects.find_one({"id": subject_id, "school_id": user["school_id"]})
    if not subj:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Validate that all teacher_ids actually belong to this school & role
    if teacher_ids:
        valid = await rdb.users.find(
            {"school_id": user["school_id"], "role": "teacher", "id": {"$in": teacher_ids}},
            {"_id": 0, "id": 1},
        ).to_list(2000)
        valid_ids = {t["id"] for t in valid}
        invalid = [tid for tid in teacher_ids if tid not in valid_ids]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid teacher_ids: {invalid}")

    added = 0
    if teacher_ids:
        res = await rdb.users.update_many(
            {"school_id": user["school_id"], "role": "teacher", "id": {"$in": teacher_ids}},
            {"$addToSet": {"subjects": subject_id}},
        )
        added = res.modified_count

    removed = 0
    if replace:
        res = await rdb.users.update_many(
            {
                "school_id": user["school_id"],
                "role": "teacher",
                "id": {"$nin": teacher_ids},
                "subjects": subject_id,
            },
            {"$pull": {"subjects": subject_id}},
        )
        removed = res.modified_count

    return {"added": added, "removed": removed, "assigned_teacher_ids": teacher_ids}


@router.post("/subjects/{subject_id}/unassign-teacher/{teacher_id}")
async def unassign_subject_from_teacher(
    subject_id: str,
    teacher_id: str,
    user: dict = Depends(require_roles("school_admin")),
):
    """Remove this subject from a single teacher's `subjects` array.

    Note: this does NOT auto-block the teacher's submit guard (a teacher with
    zero subjects is technically inconsistent with the create-time rule). The
    UI should warn admins before stripping the last subject from a teacher.
    """
    from core.db import get_db as _root_db
    rdb = _root_db()
    res = await rdb.users.update_one(
        {"school_id": user["school_id"], "role": "teacher", "id": teacher_id},
        {"$pull": {"subjects": subject_id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Teacher not found in this school")
    return {"ok": True, "removed": res.modified_count}


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
