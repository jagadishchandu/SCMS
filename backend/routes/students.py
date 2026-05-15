"""Students + parent inline + attendance + marks views per student."""
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from core.models import StudentCreate, StudentUpdate
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/students", tags=["students"])


async def _gen_uid(db, school_id: str) -> str:
    count = await db.students.count_documents({"school_id": school_id})
    return f"STU-{(count + 1):05d}"


async def _teacher_class_filter(db, user: dict) -> dict | None:
    if user["role"] != "teacher":
        return None
    mappings = await db.class_teacher_map.find({"school_id": user["school_id"], "teacher_id": user["id"]}, {"_id": 0}).to_list(100)
    timetable = await db.timetable.find({"school_id": user["school_id"], "teacher_id": user["id"]}, {"_id": 0}).to_list(500)
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
    db = get_db()
    if user["role"] == "parent":
        return await db.students.find({"parent_user_id": user["id"]}, {"_id": 0}).to_list(50)
    if user["role"] not in ("platform_admin", "school_admin", "teacher", "accounts"):
        raise HTTPException(status_code=403, detail="Forbidden")
    flt = {"school_id": user["school_id"]} if user["role"] != "platform_admin" else {}
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(db, user)
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
    return await db.students.find(flt, {"_id": 0}).to_list(5000)


@router.post("")
async def create_student(payload: StudentCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    # Teachers can only create students in classes/sections they teach
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(db, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="You are not assigned to any class yet")
        allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        if (payload.class_id, payload.section) not in allowed:
            raise HTTPException(status_code=403, detail="You can only add students to classes you teach")
    uid = payload.student_uid or await _gen_uid(db, user["school_id"])
    if await db.students.find_one({"school_id": user["school_id"], "student_uid": uid}):
        raise HTTPException(status_code=400, detail="Student UID already exists")
    parent_email = payload.parent.email or f"parent.{uid.lower()}@{user['school_id'][:6]}.local"
    parent_email = parent_email.lower()
    existing_parent = await db.users.find_one({"email": parent_email})
    if existing_parent:
        parent_user_id = existing_parent["id"]
    else:
        from core.auth import hash_password
        parent_user_id = new_id()
        await db.users.insert_one({
            "id": parent_user_id,
            "email": parent_email,
            "password_hash": hash_password("Parent@123"),
            "name": payload.parent.name,
            "role": "parent",
            "school_id": user["school_id"],
            "phone": payload.parent.phone,
            "is_active": True,
            "created_at": utc_now(),
        })

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
    await db.students.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"], "create", "student", doc["id"], {"uid": uid})
    return clean_doc(doc)


@router.post("/{student_id}/photo")
async def upload_photo(student_id: str, file: UploadFile = File(...), user: dict = Depends(require_roles("school_admin", "teacher", "parent"))):
    """Upload a student photo. Stored as data URL in MongoDB (base64). Max ~2 MB.

    Access:
    - school_admin: any student in their school
    - teacher: students in their assigned class
    - parent: their own child
    """
    db = get_db()
    s = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] != "platform_admin" and s["school_id"] != user.get("school_id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "parent" and s.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(db, user)
        if tflt and tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Not your class")

    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 2 MB)")
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG or WebP allowed")
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:{file.content_type};base64,{b64}"
    await db.students.update_one({"id": student_id}, {"$set": {"photo": data_url}})
    await log_action(user["id"], user["role"], s["school_id"], "upload_photo", "student", student_id)
    return {"ok": True, "photo": data_url}


@router.get("/by-uid/{student_uid}")
async def get_student_by_uid(student_uid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"student_uid": student_uid}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await db.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "teacher":
        tflt = await _teacher_class_filter(db, user)
        if tflt and tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="Not your class")
        if tflt:
            ok = any((c.get("class_id") == s["class_id"] and c.get("section") == s["section"]) for c in tflt.get("$or", []))
            if not ok:
                raise HTTPException(status_code=403, detail="Not your class")
    return s


@router.get("/{student_id}")
async def get_student(student_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"id": student_id}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await db.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return s


@router.patch("/{student_id}")
async def update_student(student_id: str, payload: StudentUpdate, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    update = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await db.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "student", student_id, update)
    return {"ok": True}


@router.delete("/{student_id}")
async def delete_student(student_id: str, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    await db.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": {"status": "inactive"}})
    await log_action(user["id"], user["role"], user["school_id"], "deactivate", "student", student_id)
    return {"ok": True}
