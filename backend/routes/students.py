"""Students + parent inline + attendance + marks views per student.

After v1.15: all student/parent operational data is stored in the per-school DB
(`scms_db_school_<code>`). The master `users` collection still authoritatively
holds login records (so email lookups at login work).
"""
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from core.models import StudentCreate, StudentUpdate
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/students", tags=["students"])


async def _gen_uid(tdb, school_id: str) -> str:
    count = await tdb.students.count_documents({"school_id": school_id})
    return f"STU-{(count + 1):05d}"


async def _teacher_class_filter(tdb, user: dict) -> dict | None:
    """Build a $or filter for the classes a teacher can see, based on the
    `class_teacher_map` + `timetable` rows in the school's tenant DB.
    """
    if user["role"] != "teacher":
        return None
    mappings = await tdb.class_teacher_map.find(
        {"school_id": user["school_id"], "teacher_id": user["id"]}, {"_id": 0},
    ).to_list(100)
    timetable = await tdb.timetable.find(
        {"school_id": user["school_id"], "teacher_id": user["id"]}, {"_id": 0},
    ).to_list(500)
    classes = {(m["class_id"], m["section"]) for m in mappings}
    classes.update({(t["class_id"], t["section"]) for t in timetable})
    if not classes:
        return {"_blocked_": True}
    return {"$or": [{"class_id": c, "section": s} for c, s in classes]}


@router.get("")
async def list_students(
    class_id: str | None = None,
    section: str | None = None,
    q: str | None = None,
    user: dict = Depends(get_current_user),
):
    if user["role"] == "platform_admin":
        # Aggregate across all schools by iterating.
        db = get_db()
        out = []
        async for school in db.schools.find({}, {"_id": 0, "id": 1, "db_name": 1, "code": 1, "name": 1}):
            tdb = await tenant_db(school["id"])
            flt: dict = {}
            if class_id: flt["class_id"] = class_id
            if section: flt["section"] = section
            if q:
                flt["$or"] = [
                    {"name": {"$regex": q, "$options": "i"}},
                    {"student_uid": {"$regex": q, "$options": "i"}},
                ]
            out.extend(await tdb.students.find(flt, {"_id": 0}).to_list(2000))
        return out

    if user["role"] not in ("school_admin", "teacher", "accounts", "parent"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tdb = await tenant_db(user["school_id"])
    if user["role"] == "parent":
        return await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0}).to_list(50)

    flt = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if tflt and tflt.get("_blocked_"):
            return []
        if tflt:
            flt.update(tflt)
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section
    if q:
        flt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"student_uid": {"$regex": q, "$options": "i"}},
        ]
    return await tdb.students.find(flt, {"_id": 0}).to_list(5000)


@router.post("")
async def create_student(payload: StudentCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()  # for users (master)
    tdb = await tenant_db(user["school_id"])

    # Teachers can only create students in classes/sections they teach
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="You are not assigned to any class yet")
        allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        if (payload.class_id, payload.section) not in allowed:
            raise HTTPException(status_code=403, detail="You can only add students to classes you teach")

    uid = payload.student_uid or await _gen_uid(tdb, user["school_id"])
    if await tdb.students.find_one({"school_id": user["school_id"], "student_uid": uid}):
        raise HTTPException(status_code=400, detail="Student UID already exists")

    parent_email = payload.parent.email or f"parent.{uid.lower()}@{user['school_id'][:6]}.school"
    parent_email = parent_email.lower()
    existing_parent = await db.users.find_one({"email": parent_email})
    DEFAULT_PARENT_PWD = "Parent@123"
    parent_is_new = False
    if existing_parent:
        parent_user_id = existing_parent["id"]
    else:
        from core.auth import hash_password
        parent_user_id = new_id()
        parent_is_new = True
        parent_doc = {
            "id": parent_user_id,
            "email": parent_email,
            "password_hash": hash_password(DEFAULT_PARENT_PWD),
            "name": payload.parent.name,
            "role": "parent",
            "school_id": user["school_id"],
            "phone": payload.parent.phone,
            "is_active": True,
            "created_at": utc_now(),
        }
        # Authoritative login row goes to master `users` (so login-by-email works).
        await db.users.insert_one(parent_doc)
        # Mirror into tenant DB.
        mirror = {k: v for k, v in parent_doc.items() if k != "_id"}
        await tdb.users.update_one({"email": parent_email}, {"$set": mirror}, upsert=True)
        await tdb.parents.update_one(
            {"user_id": parent_user_id},
            {"$set": {
                "user_id": parent_user_id, "email": parent_email, "name": payload.parent.name,
                "phone": payload.parent.phone, "created_at": parent_doc["created_at"],
            }},
            upsert=True,
        )

    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "student_uid": uid,
        "name": payload.name,
        "class_id": payload.class_id,
        "section": payload.section,
        "roll_number": payload.roll_number,
        "gender": payload.gender,
        "dob": payload.dob,
        "admission_date": payload.admission_date,
        "medical_notes": payload.medical_notes,
        "emergency_contact": payload.emergency_contact,
        "parent": payload.parent.model_dump(),
        "parent_user_id": parent_user_id,
        "status": "active",
        "photo": None,
        "created_at": utc_now(),
    }
    await tdb.students.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"], "create", "student", doc["id"], {"uid": uid})
    out = clean_doc(doc)
    # Attach parent-login hint so the UI can immediately surface credentials.
    out["parent_login"] = {
        "email": parent_email,
        "is_new_account": parent_is_new,
        "default_password": DEFAULT_PARENT_PWD if parent_is_new else None,
    }
    return out


@router.get("/{student_id}/parent-login")
async def get_parent_login(student_id: str, user: dict = Depends(require_roles("school_admin", "teacher"))):
    """Return the parent's login email for this student (+ whether the default
    password was reset since creation). Never returns plaintext password except
    immediately after a reset.
    """
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    # Teacher visibility constraint
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Forbidden")
        allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        if (s["class_id"], s["section"]) not in allowed:
            raise HTTPException(status_code=403, detail="Not your class")
    db = get_db()
    parent = await db.users.find_one(
        {"id": s.get("parent_user_id")},
        {"_id": 0, "id": 1, "email": 1, "last_login_at": 1, "password_changed_at": 1, "password_reset_to_default_at": 1},
    ) or {}
    return {
        "student_id": student_id,
        "student_name": s["name"],
        "student_uid": s.get("student_uid"),
        "parent_user_id": s.get("parent_user_id"),
        "email": parent.get("email") or (s.get("parent") or {}).get("email"),
        "phone": (s.get("parent") or {}).get("phone"),
        "last_login_at": parent.get("last_login_at"),
        "password_changed_at": parent.get("password_changed_at"),
        "password_reset_to_default_at": parent.get("password_reset_to_default_at"),
    }


@router.post("/{student_id}/parent-reset-password")
async def reset_parent_password(student_id: str, user: dict = Depends(require_roles("school_admin", "teacher"))):
    """Reset the parent's password to the default (`Parent@123`) and return it
    once so the staff member can hand it to the parent.
    """
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Forbidden")
        allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        if (s["class_id"], s["section"]) not in allowed:
            raise HTTPException(status_code=403, detail="Not your class")
    if not s.get("parent_user_id"):
        raise HTTPException(status_code=400, detail="Student has no linked parent account")
    from core.auth import hash_password
    DEFAULT_PARENT_PWD = "Parent@123"
    db = get_db()
    res = await db.users.update_one(
        {"id": s["parent_user_id"]},
        {"$set": {
            "password_hash": hash_password(DEFAULT_PARENT_PWD),
            "password_reset_to_default_at": utc_now(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Parent account not found")
    await log_action(user["id"], user["role"], user["school_id"], "reset_parent_password", "user", s["parent_user_id"], {"student_uid": s.get("student_uid")})
    parent = await db.users.find_one({"id": s["parent_user_id"]}, {"_id": 0, "email": 1})
    return {
        "ok": True,
        "email": (parent or {}).get("email"),
        "default_password": DEFAULT_PARENT_PWD,
    }


@router.post("/{student_id}/photo")
async def upload_photo(student_id: str, file: UploadFile = File(...), user: dict = Depends(require_roles("school_admin", "teacher", "parent"))):
    """Upload a student photo. Stored as data URL in MongoDB (base64). Max ~2 MB."""
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] != "platform_admin" and s["school_id"] != user.get("school_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "parent" and s.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if tflt and tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Not your class")

    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 2 MB)")
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG or WebP allowed")
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:{file.content_type};base64,{b64}"
    await tdb.students.update_one({"id": student_id}, {"$set": {"photo": data_url}})
    await log_action(user["id"], user["role"], s["school_id"], "upload_photo", "student", student_id)
    return {"ok": True, "photo": data_url}


@router.get("/by-uid/{student_uid}")
async def get_student_by_uid(student_uid: str, user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    flt = {"student_uid": student_uid}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await tdb.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(tdb, user)
        if tflt and tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Not your class")
        if tflt:
            ok = any((c.get("class_id") == s["class_id"] and c.get("section") == s["section"]) for c in tflt.get("$or", []))
            if not ok:
                raise HTTPException(status_code=403, detail="Not your class")
    return s


@router.get("/{student_id}")
async def get_student(student_id: str, user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    flt = {"id": student_id}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await tdb.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return s


@router.patch("/{student_id}")
async def update_student(student_id: str, payload: StudentUpdate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    update = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await tdb.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "student", student_id, update)
    return {"ok": True}


@router.delete("/{student_id}")
async def delete_student(student_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    await tdb.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": {"status": "inactive"}})
    await log_action(user["id"], user["role"], user["school_id"], "deactivate", "student", student_id)
    return {"ok": True}
