"""Schools routes - platform admin only for create/list-all."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.models import SchoolCreate, SchoolUpdate, SchoolBranding
from core.auth import require_roles, hash_password, get_current_user
from core.db import get_db, init_school_db, school_db_name, get_school_db, school_db_status
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

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
    accounts = await db.users.find(
        {"school_id": school_id, "role": "accounts", "is_active": True},
        {"_id": 0, "password_hash": 0},
    ).sort("name", 1).to_list(500)
    school_admins = await db.users.find(
        {"school_id": school_id, "role": "school_admin"},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", 1).to_list(50)
    students = await tdb.students.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "student_uid": 1, "name": 1, "class_id": 1, "section": 1, "gender": 1, "parent": 1, "parent_user_id": 1},
    ).sort("student_uid", 1).to_list(5000)
    classes = await tdb.classes.find({}, {"_id": 0}).to_list(500)
    class_map = {c["id"]: c["name"] for c in classes}
    for s in students:
        s["class_name"] = class_map.get(s.get("class_id"))
    return {
        "school": school,
        "teachers": teachers,
        "accounts": accounts,
        "school_admins": school_admins,
        "students": students,
        "counts": {
            "teachers": len(teachers),
            "accounts": len(accounts),
            "school_admins": len(school_admins),
            "students": len(students),
            "classes": len(classes),
        },
    }


class BulkDeleteStudentsPayload(BaseModel):
    student_ids: list[str]
    confirm_code: str


@router.post("/{school_id}/students/bulk-delete")
async def bulk_delete_students(
    school_id: str,
    payload: BulkDeleteStudentsPayload,
    user: dict = Depends(require_roles("platform_admin")),
):
    """Platform Super Admin only — hard-delete the selected students from a school.

    Cascades into every per-tenant collection that references the student
    (`attendance`, `marks`, `fees`, `fee_payments`, `activity_enrollments`,
    `sick_leaves`) and deactivates parent users that have no remaining children
    in this school (so they cannot still log in to see an empty portal).

    The caller MUST send `confirm_code` matching the school's `code` exactly;
    this guards against fat-fingered drawer clicks.
    """
    from core.db import tenant_db
    db = get_db()
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    if (payload.confirm_code or "").strip() != school.get("code"):
        raise HTTPException(
            status_code=400,
            detail=f"confirm_code must match the school's code ('{school.get('code')}') to authorise deletion.",
        )
    if not payload.student_ids:
        raise HTTPException(status_code=400, detail="student_ids must contain at least one id")

    tdb = await tenant_db(school_id)
    # Resolve every selected student (validate they belong to this school)
    students = await tdb.students.find(
        {"id": {"$in": payload.student_ids}},
        {"_id": 0, "id": 1, "student_uid": 1, "name": 1, "parent_user_id": 1},
    ).to_list(10000)
    found_ids = [s["id"] for s in students]
    if not found_ids:
        raise HTTPException(status_code=404, detail="No matching students found in this school")

    # Cascade delete from every collection that references these students
    cascade_collections = (
        "attendance", "marks", "fees", "fee_payments",
        "activity_enrollments", "sick_leaves",
    )
    cascade_counts: dict[str, int] = {}
    for coll in cascade_collections:
        res = await tdb[coll].delete_many({"student_id": {"$in": found_ids}})
        cascade_counts[coll] = res.deleted_count
    students_res = await tdb.students.delete_many({"id": {"$in": found_ids}})
    # Also try to remove students from any timetable/attendance lookups in master (legacy)
    try:
        await db.students.delete_many({"id": {"$in": found_ids}, "school_id": school_id})
    except Exception:
        pass

    # Deactivate parent users that have no remaining active children in this school
    parent_ids = sorted({s.get("parent_user_id") for s in students if s.get("parent_user_id")})
    deactivated_parents = 0
    for pid in parent_ids:
        remaining = await tdb.students.count_documents({"parent_user_id": pid, "status": "active"})
        if remaining == 0:
            r = await db.users.update_one(
                {"id": pid, "role": "parent", "school_id": school_id},
                {"$set": {"is_active": False, "deactivated_at": utc_now(), "deactivated_reason": "all_children_deleted"}},
            )
            if r.modified_count:
                deactivated_parents += 1

    await log_action(
        user["id"], user["role"], school_id,
        "bulk_delete_students", "school", school_id,
        {
            "deleted_count": students_res.deleted_count,
            "requested_count": len(payload.student_ids),
            "cascade": cascade_counts,
            "deactivated_parents": deactivated_parents,
            "uids": [s.get("student_uid") for s in students][:50],
        },
    )

    return {
        "ok": True,
        "deleted_students": students_res.deleted_count,
        "requested": len(payload.student_ids),
        "cascade": cascade_counts,
        "deactivated_parents": deactivated_parents,
    }


@router.post("")
async def create_school(payload: SchoolCreate, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    # uniqueness
    if await db.schools.find_one({"code": payload.code}):
        raise HTTPException(status_code=400, detail="School code already exists")
    admin_login_id = (payload.admin_email or "").strip().lower()
    if not admin_login_id:
        raise HTTPException(status_code=400, detail="Admin login id is required")
    if await db.users.find_one({"email": admin_login_id}):
        raise HTTPException(status_code=400, detail=f"Login id '{admin_login_id}' already exists. Please choose a different one.")

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
        "email": admin_login_id,
        "password_hash": hash_password(payload.admin_password),
        "name": payload.admin_name,
        "phone": payload.admin_phone,
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


# ---------- Mandatory communication channels per school ----------
ALLOWED_CHANNELS = ("email", "whatsapp", "telegram")


class MandatoryChannelsPayload(_BaseModel):
    channels: list[str]


def _normalize_channels(value: list[str] | None) -> list[str]:
    """Return the school's mandatory_channels list with safe defaults.
    Default for legacy schools is ['telegram'] (back-compat with v1.30 banner)."""
    if not value:
        return ["telegram"]
    seen = []
    for c in value:
        if c in ALLOWED_CHANNELS and c not in seen:
            seen.append(c)
    return seen or ["telegram"]


@router.get("/{school_id}/mandatory-channels")
async def get_mandatory_channels(school_id: str, user: dict = Depends(get_current_user)):
    """Visible to platform admin and the school's own school admin."""
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0, "id": 1, "mandatory_channels": 1})
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "school_id": school_id,
        "channels": _normalize_channels(s.get("mandatory_channels")),
        "allowed": list(ALLOWED_CHANNELS),
    }


@router.patch("/{school_id}/mandatory-channels")
async def set_mandatory_channels(
    school_id: str,
    payload: MandatoryChannelsPayload,
    user: dict = Depends(require_roles("platform_admin")),
):
    """Platform Super Admin can set which communication channels each school
    must enforce for its users (any combination of email / whatsapp / telegram).
    At least one channel must be selected."""
    incoming = [c.lower().strip() for c in (payload.channels or [])]
    bad = [c for c in incoming if c not in ALLOWED_CHANNELS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported channels: {bad}. Allowed: {list(ALLOWED_CHANNELS)}")
    # De-dupe while preserving order
    cleaned: list[str] = []
    for c in incoming:
        if c not in cleaned:
            cleaned.append(c)
    if not cleaned:
        raise HTTPException(status_code=400, detail="At least one mandatory channel is required")
    db = get_db()
    res = await db.schools.update_one({"id": school_id}, {"$set": {"mandatory_channels": cleaned}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "school_id": school_id, "channels": cleaned}



# ---------- Parent-login per-school kill-switch (Platform Super Admin only) ----------

class ParentLoginPayload(_BaseModel):
    enabled: bool


@router.get("/{school_id}/parent-login")
async def get_parent_login_flag(school_id: str, user: dict = Depends(get_current_user)):
    """Returns whether parent login is enabled for this school.
    Default is True (enabled) for legacy schools without the flag.
    Visible to platform admin and the school's own school admin.
    """
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0, "parent_login_enabled": 1})
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "school_id": school_id,
        "enabled": s.get("parent_login_enabled", True),
    }


@router.patch("/{school_id}/parent-login")
async def set_parent_login_flag(
    school_id: str,
    payload: ParentLoginPayload,
    user: dict = Depends(require_roles("platform_admin")),
):
    """Platform Super Admin only — toggle parent login for an entire school.
    When `enabled=False`, every parent in this school is denied login (other
    roles continue to work). Used to quickly cut off parent access when a school
    is offboarded or under maintenance.
    """
    db = get_db()
    res = await db.schools.update_one(
        {"id": school_id},
        {"$set": {"parent_login_enabled": bool(payload.enabled)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(
        user["id"], user["role"], school_id,
        "set_parent_login_enabled", "school", school_id,
        {"enabled": bool(payload.enabled)},
    )
    return {"ok": True, "school_id": school_id, "enabled": bool(payload.enabled)}
