"""Schools routes - platform admin only for create/list-all."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import SchoolCreate, SchoolUpdate, SchoolBranding
from core.auth import require_roles, hash_password, get_current_user
from core.db import get_db, init_school_db, school_db_name, get_school_db, school_db_status
from core.utils import new_id, utc_now, clean_doc

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("")
async def list_schools(user: dict = Depends(get_current_user)):
    db = get_db()
    q = {}
    if user["role"] != "platform_admin":
        q["id"] = user.get("school_id")
    schools = await db.schools.find(q, {"_id": 0}).to_list(1000)
    return schools


@router.get("/with-stats")
async def list_schools_with_stats(user: dict = Depends(require_roles("platform_admin"))):
    """Returns every school enriched with live tenant-DB counts (students, teachers,
    parents, classes, attendance, fees outstanding) — used by the Platform Overview."""
    from core.db import tenant_db
    db = get_db()
    schools = await db.schools.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    enriched = []
    for s in schools:
        tdb = await tenant_db(s["id"])
        students = await tdb.students.count_documents({"status": "active"})
        teachers = await db.users.count_documents({"school_id": s["id"], "role": "teacher", "is_active": True})
        parents = await db.users.count_documents({"school_id": s["id"], "role": "parent", "is_active": True})
        admins = await db.users.count_documents({"school_id": s["id"], "role": "school_admin", "is_active": True})
        classes = await tdb.classes.count_documents({})
        sections_count = 0
        async for c in tdb.classes.find({}, {"sections": 1, "_id": 0}):
            sections_count += len(c.get("sections") or [])
        fees_due_agg = await tdb.fees.aggregate([
            {"$group": {"_id": None, "due": {"$sum": "$due"}, "paid": {"$sum": "$paid"}}}
        ]).to_list(1)
        fee_due = fees_due_agg[0]["due"] if fees_due_agg else 0
        fee_paid = fees_due_agg[0]["paid"] if fees_due_agg else 0
        enriched.append({
            **s,
            "stats": {
                "students": students, "teachers": teachers, "parents": parents,
                "school_admins": admins, "classes": classes, "sections": sections_count,
                "fee_due": fee_due, "fee_collected": fee_paid,
            },
        })
    return enriched


@router.get("/{school_id}/people")
async def school_people_overview(school_id: str, user: dict = Depends(get_current_user)):
    """Lists teachers + students for a single school (used by Platform admin school-detail drawer)."""
    if user["role"] not in ("platform_admin", "school_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    from core.db import tenant_db
    db = get_db()
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    tdb = await tenant_db(school_id)
    teachers = await db.users.find(
        {"school_id": school_id, "role": "teacher", "is_active": True},
        {"_id": 0, "password_hash": 0},
    ).sort("name", 1).to_list(500)
    students = await tdb.students.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "student_uid": 1, "name": 1, "class_id": 1, "section": 1, "gender": 1, "parent": 1},
    ).sort("student_uid", 1).to_list(5000)
    classes = await tdb.classes.find({}, {"_id": 0}).to_list(500)
    class_map = {c["id"]: c["name"] for c in classes}
    for s in students:
        s["class_name"] = class_map.get(s.get("class_id"))
    return {
        "school": school,
        "teachers": teachers,
        "students": students,
        "counts": {
            "teachers": len(teachers),
            "students": len(students),
            "classes": len(classes),
        },
    }


@router.post("")
async def create_school(payload: SchoolCreate, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    # uniqueness
    if await db.schools.find_one({"code": payload.code}):
        raise HTTPException(status_code=400, detail="School code already exists")
    if await db.users.find_one({"email": payload.admin_email.lower()}):
        raise HTTPException(status_code=400, detail="Admin email already exists")

    school_id = new_id()
    initial_approval = (
        {
            "status": "approved",
            "approved_children_count": payload.initial_children_count,
            "decided_at": utc_now(),
            "decided_by": user["id"],
            "note": "Auto-approved at creation by Platform Super Admin",
        }
        if payload.auto_approve else {"status": "not_started"}
    )
    school_doc = {
        "id": school_id,
        "name": payload.name,
        "code": payload.code,
        "address": payload.address,
        "phone": payload.phone,
        "email": payload.email,
        "academic_year": payload.academic_year or "2025-2026",
        "is_active": True,
        "subscription_approval": initial_approval,
        "created_at": utc_now(),
    }
    school_doc["db_name"] = school_db_name(school_doc)
    await db.schools.insert_one(school_doc)
    # Provision dedicated database with full index schema for this school
    try:
        await init_school_db(school_doc)
    except Exception as e:
        print(f"[schools] init_school_db failed for {school_id}: {e}")

    admin_doc = {
        "id": new_id(),
        "email": payload.admin_email.lower(),
        "password_hash": hash_password(payload.admin_password),
        "name": payload.admin_name,
        "role": "school_admin",
        "school_id": school_id,
        "is_active": True,
        "created_at": utc_now(),
    }
    await db.users.insert_one(admin_doc)

    # Mirror the school admin into the per-school DB so the schema isn't empty
    # and admins can verify their DB is wired correctly.
    try:
        sdb = get_school_db(school_doc)
        mirror = {k: v for k, v in admin_doc.items() if k != "_id"}
        await sdb.users.update_one({"email": mirror["email"]}, {"$set": mirror}, upsert=True)
        await sdb.school_admins.update_one(
            {"user_id": mirror["id"]},
            {"$set": {"user_id": mirror["id"], "email": mirror["email"], "name": mirror["name"], "created_at": mirror["created_at"]}},
            upsert=True,
        )
    except Exception as e:
        print(f"[schools] mirror admin to school db failed: {e}")

    return {"school": clean_doc(school_doc), "admin_email": admin_doc["email"]}


@router.get("/{school_id}/db-status")
async def get_school_db_status(school_id: str, user: dict = Depends(get_current_user)):
    """Return the per-school DB name, all collections, doc counts, missing collections,
    and marker. Visible to platform_admin and the school's own school_admin."""
    if user["role"] not in ("platform_admin", "school_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return await school_db_status(school)


@router.post("/{school_id}/db-init")
async def reinit_school_db(school_id: str, user: dict = Depends(require_roles("platform_admin"))):
    """Re-run the schema initializer for a school. Idempotent.
    Useful when new collections are added to SCHOOL_DB_COLLECTIONS and we want
    older schools to receive the new indexes."""
    db = get_db()
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    await init_school_db(school)
    return await school_db_status(school)


@router.patch("/{school_id}")
async def update_school(school_id: str, payload: SchoolUpdate, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await db.schools.update_one({"id": school_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="School not found")
    return {"ok": True}


@router.get("/{school_id}")
async def get_school(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    return s


@router.patch("/{school_id}/branding")
async def update_branding(school_id: str, payload: SchoolBranding, user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    branding = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # validate logo size if data URL
    if branding.get("logo", "").startswith("data:"):
        # rough size check ~ 1.4x bytes
        if len(branding["logo"]) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Logo too large (max ~1.4 MB)")
    res = await db.schools.update_one({"id": school_id}, {"$set": {"branding": branding}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "branding": branding}


from pydantic import BaseModel as _BaseModel
from core.i18n import SUPPORTED_LANGUAGES, supported_languages


class LanguagePayload(_BaseModel):
    language: str


@router.get("/{school_id}/language")
async def get_school_language(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ("platform_admin",) and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0, "language": 1})
    return {
        "language": (s or {}).get("language") or "en",
        "supported": supported_languages(),
    }


@router.patch("/{school_id}/language")
async def set_school_language(school_id: str, payload: LanguagePayload, user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {SUPPORTED_LANGUAGES}")
    db = get_db()
    res = await db.schools.update_one({"id": school_id}, {"$set": {"language": payload.language}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "language": payload.language}
