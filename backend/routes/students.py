"""Students + parent inline + attendance + marks views per student.

After v1.15: all student/parent operational data is stored in the per-school DB
(`scms_db_school_<code>`). The master `users` collection still authoritatively
holds login records (so email lookups at login work).
"""
import base64
import io
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse
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


def _teacher_can_access_student(tflt: dict | None, student: dict, teacher_id: str) -> bool:
    """Return True if the teacher should be allowed to view/edit this student.
    Access path 1: student is in one of the teacher's assigned (class, section) pairs.
    Access path 2: teacher created the student themselves (created_by_id match).
    """
    if student.get("created_by_id") == teacher_id:
        return True
    if tflt and not tflt.get("_blocked_"):
        allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        if (student.get("class_id"), student.get("section")) in allowed:
            return True
    return False


async def _enforce_teacher_access(tdb, user: dict, student: dict) -> None:
    """Raise 403 if a teacher cannot access this student. No-op for other roles."""
    if user["role"] != "teacher":
        return
    tflt = await _teacher_class_filter(tdb, user)
    if not _teacher_can_access_student(tflt, student, user["id"]):
        raise HTTPException(status_code=403, detail="Not your class")


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
        # Build the visible set: either (class, section) is in an assigned pair,
        # OR the teacher created the student themselves. Without the second
        # clause, a teacher with no formal class assignment couldn't see any
        # students they had added.
        or_clauses: list[dict] = []
        if tflt and not tflt.get("_blocked_") and tflt.get("$or"):
            or_clauses.extend(tflt["$or"])
        or_clauses.append({"created_by_id": user["id"]})
        flt["$or"] = or_clauses
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section
    if q:
        q_or = [
            {"name": {"$regex": q, "$options": "i"}},
            {"student_uid": {"$regex": q, "$options": "i"}},
        ]
        # Preserve any existing $or (teacher visibility) by combining via $and.
        if "$or" in flt:
            flt["$and"] = [{"$or": flt.pop("$or")}, {"$or": q_or}]
        else:
            flt["$or"] = q_or
    students = await tdb.students.find(flt, {"_id": 0}).to_list(5000)

    # Enrich each row with parent_telegram_linked so admins can see who's
    # reachable via Telegram at-a-glance. One bulk-lookup against master users.
    parent_ids = [s.get("parent_user_id") for s in students if s.get("parent_user_id")]
    if parent_ids:
        db = get_db()
        linked = await db.users.find(
            {"id": {"$in": parent_ids}, "telegram_chat_id": {"$exists": True, "$ne": None}},
            {"_id": 0, "id": 1},
        ).to_list(len(parent_ids))
        linked_ids = {u["id"] for u in linked}
        for s in students:
            s["parent_telegram_linked"] = bool(s.get("parent_user_id") in linked_ids)

    # Enrich each row with the activities the student is enrolled in
    # (one $in lookup + one $in lookup on activities). Output is a list
    # of `{id, name, category}` so the Students list can render a small
    # "🏆 Painting · Football" strip under each name.
    student_ids = [s["id"] for s in students]
    if student_ids:
        enrolls = await tdb.activity_enrollments.find(
            {"school_id": user["school_id"], "student_id": {"$in": student_ids}},
            {"_id": 0, "student_id": 1, "activity_id": 1},
        ).to_list(20000)
        if enrolls:
            aids = list({e["activity_id"] for e in enrolls})
            acts = await tdb.activities.find(
                {"school_id": user["school_id"], "id": {"$in": aids}},
                {"_id": 0, "id": 1, "name": 1, "category": 1, "is_active": 1},
            ).to_list(len(aids))
            act_by_id = {a["id"]: a for a in acts if a.get("is_active", True)}
            by_student: dict[str, list[dict]] = {}
            for e in enrolls:
                a = act_by_id.get(e["activity_id"])
                if a:
                    by_student.setdefault(e["student_id"], []).append(
                        {"id": a["id"], "name": a["name"], "category": a.get("category", "other")}
                    )
            for s in students:
                s["activities"] = sorted(by_student.get(s["id"], []), key=lambda x: x["name"])
        else:
            for s in students:
                s["activities"] = []
    return students


@router.post("")
async def create_student(payload: StudentCreate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()  # for users (master)
    tdb = await tenant_db(user["school_id"])

    # Teachers can create students in classes/sections they teach. If a teacher
    # hasn't been formally assigned to any class/section yet (no class_teacher
    # mapping, no timetable slot), fall back to permissive school-wide add — many
    # subject teachers do data entry before being formally tied to a class.
    # Updates/moves/deletes remain tightly scoped via `_teacher_class_filter`.
    if user["role"] == "teacher":
        # Verify the target class+section actually exists in this school.
        cls = await tdb.classes.find_one({"id": payload.class_id, "school_id": user["school_id"]}, {"_id": 0, "sections": 1})
        if not cls:
            raise HTTPException(status_code=400, detail="Class not found in this school")
        valid_sections = [str(s).upper() for s in (cls.get("sections") or [])]
        if payload.section and payload.section.upper() not in valid_sections:
            raise HTTPException(status_code=400, detail=f"Section '{payload.section}' is not configured for this class. Available: {valid_sections}")

        tflt = await _teacher_class_filter(tdb, user)
        # If the teacher has explicit assignments, enforce them.
        if tflt and not tflt.get("_blocked_") and tflt.get("$or"):
            allowed = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
            if (payload.class_id, payload.section) not in allowed:
                raise HTTPException(status_code=403, detail="You can only add students to classes you teach")
        # else: teacher has no formal class assignment — permit school-wide add
        # (still tenant-scoped to their own school via tdb).

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
        "created_by_id": user["id"],
        "created_by_role": user["role"],
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
    await _enforce_teacher_access(tdb, user, s)
    db = get_db()
    parent = await db.users.find_one(
        {"id": s.get("parent_user_id")},
        {"_id": 0, "id": 1, "email": 1, "last_login_at": 1, "password_changed_at": 1, "password_reset_to_default_at": 1, "telegram_chat_id": 1, "telegram_linked_at": 1},
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
        "telegram_linked": bool(parent.get("telegram_chat_id")),
        "telegram_linked_at": parent.get("telegram_linked_at"),
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
    await _enforce_teacher_access(tdb, user, s)
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


@router.get("/{student_id}/credential-slip")
async def credential_slip_pdf(student_id: str, request: Request, user: dict = Depends(require_roles("school_admin", "teacher"))):
    """One-click PDF slip with student + parent login details for hand-off.

    Includes a QR code that deep-links to /login?role=parent&email=<parent_email>
    so parents only need to type their password.

    Note: we print the DEFAULT password (`Parent@123`) on the slip — this only
    matches the parent's real password if the parent hasn't changed it yet OR if
    the staff member just clicked "Reset to default". If the parent has changed
    their password since, the slip won't work — the staff member should reset
    first, then print.
    """
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    import qrcode
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    await _enforce_teacher_access(tdb, user, s)
    db = get_db()
    parent = await db.users.find_one({"id": s.get("parent_user_id")}, {"_id": 0, "email": 1}) or {}
    parent_email = parent.get("email") or (s.get("parent") or {}).get("email")
    cls = await tdb.classes.find_one({"id": s.get("class_id")}, {"_id": 0, "name": 1}) or {}
    school = await db.schools.find_one({"id": user["school_id"]}, {"_id": 0, "name": 1}) or {}

    # Build the deep-link URL using the public host the request arrived on.
    # When behind a reverse-proxy (Kubernetes ingress, Cloudflare etc), the
    # original Host is in X-Forwarded-Host. Allow env override via PUBLIC_APP_URL.
    public_url = os.environ.get("PUBLIC_APP_URL")
    if not public_url:
        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        fwd_proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        public_url = f"{fwd_proto}://{fwd_host}"
    login_url = f"{public_url.rstrip('/')}/login?role=parent"
    if parent_email:
        from urllib.parse import quote
        login_url += f"&email={quote(parent_email)}"
    qr_img = qrcode.make(login_url)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    w, h = A5
    y = h - 18 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, y, school.get("name") or "School")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(15 * mm, y, "Parent Portal — Login Credentials")
    y -= 10 * mm
    c.line(15 * mm, y, w - 15 * mm, y)
    y -= 8 * mm

    def line(label: str, value: str):
        nonlocal y
        c.setFont("Helvetica", 9)
        c.drawString(15 * mm, y, label)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50 * mm, y, str(value or "—"))
        y -= 7 * mm

    line("Student name", s.get("name"))
    line("Student UID", s.get("student_uid"))
    line("Class · Section", f"{cls.get('name') or s.get('class_id')} · {s.get('section')}")
    line("Parent / Guardian", (s.get("parent") or {}).get("name"))
    line("Parent phone", (s.get("parent") or {}).get("phone"))
    y -= 4 * mm

    # Credentials block (left) + QR code (right)
    block_top = y
    block_h = 38 * mm
    c.setFillColorRGB(0.96, 0.92, 0.78)
    c.rect(15 * mm, block_top - block_h, w - 30 * mm, block_h, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, block_top - 8 * mm, "How to log in")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, block_top - 16 * mm, f"Email: {parent_email or '—'}")
    c.drawString(20 * mm, block_top - 22 * mm, "Password: Parent@123")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(20 * mm, block_top - 28 * mm, "Scan the QR to open the login page →")
    c.drawString(20 * mm, block_top - 33 * mm, "Please change the password after first login.")
    # QR code aligned to the right side of the credentials block
    qr_size = 30 * mm
    qr_x = w - 15 * mm - qr_size - 2 * mm
    qr_y = block_top - block_h + (block_h - qr_size) / 2
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, qr_size, qr_size, mask='auto')
    y = block_top - block_h - 6 * mm

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(15 * mm, 12 * mm, f"Generated by school staff — keep this slip confidential. Login URL: {login_url}")
    c.showPage()
    c.save()
    buf.seek(0)
    fname = f"credentials-{s.get('student_uid') or 'student'}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{student_id}/send-credentials")
async def send_parent_credentials(
    student_id: str,
    payload: dict | None = None,
    user: dict = Depends(require_roles("school_admin", "teacher")),
):
    """Send the parent's login credentials directly to their phone via Telegram or WhatsApp/SMS.

    Body: {"channel": "telegram" | "whatsapp" | "sms", "reset_first": bool}
    - If reset_first=true, the parent's password is reset to the default `Parent@123`
      first, then the slip is sent.
    - Otherwise, the message tells the parent to use their existing password (or
      reset on their own from the login page).

    The actual delivery goes through the existing queue_notification path, so
    delivery success depends on whether Telegram/WhatsApp providers are configured.
    """
    body = payload or {}
    channel = (body.get("channel") or "telegram").lower()
    reset_first = bool(body.get("reset_first", False))
    if channel not in ("telegram", "whatsapp", "sms"):
        raise HTTPException(status_code=400, detail="channel must be one of: telegram, whatsapp, sms")

    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    await _enforce_teacher_access(tdb, user, s)
    if not s.get("parent_user_id"):
        raise HTTPException(status_code=400, detail="Student has no linked parent account")

    db = get_db()
    parent = await db.users.find_one({"id": s["parent_user_id"]}, {"_id": 0, "email": 1, "phone": 1, "telegram_chat_id": 1})
    if not parent:
        raise HTTPException(status_code=404, detail="Parent account not found")

    password_line: str
    if reset_first:
        from core.auth import hash_password
        await db.users.update_one(
            {"id": s["parent_user_id"]},
            {"$set": {"password_hash": hash_password("Parent@123"), "password_reset_to_default_at": utc_now()}},
        )
        password_line = "Password: Parent@123 (just reset — please change after login)"
    else:
        password_line = "Password: use your existing password, or tap 'Forgot password' on the login page"

    from core.notify import queue_notification
    parent_phone = (s.get("parent") or {}).get("phone") or parent.get("phone")
    parent_whatsapp = (s.get("parent") or {}).get("whatsapp") or parent_phone
    msg = (
        f"👋 Welcome to the school parent portal!\n"
        f"Student: {s.get('name')} ({s.get('student_uid')})\n\n"
        f"Login email: {parent.get('email')}\n"
        f"{password_line}\n\n"
        f"You can view attendance, marks and fees once you log in."
    )
    note = await queue_notification(
        school_id=user["school_id"],
        recipient_type="parent",
        recipient_id=s["parent_user_id"],
        phone=parent_whatsapp if channel == "whatsapp" else parent_phone,
        channel=channel,
        template="parent_credentials",
        message=msg,
        context={"student_id": student_id, "student_uid": s.get("student_uid"), "reset_first": reset_first},
        telegram_chat_id=parent.get("telegram_chat_id") if channel == "telegram" else None,
    )
    await log_action(user["id"], user["role"], user["school_id"], "send_parent_credentials", "user", s["parent_user_id"], {"channel": channel, "reset_first": reset_first})
    return {
        "ok": True,
        "channel": channel,
        "reset_first": reset_first,
        "delivery_status": note.get("status"),
        "delivery_note": note.get("delivery_note"),
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
    await _enforce_teacher_access(tdb, user, s)

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
        if not _teacher_can_access_student(tflt, s, user["id"]):
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
async def update_student(student_id: str, payload: StudentUpdate, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    # Teacher can only edit students in their assigned (class, section). They can
    # also MOVE a student to another (class, section) of theirs — but not into a
    # class they don't teach.
    await _enforce_teacher_access(tdb, user, s)
    update = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in payload.model_dump(exclude_unset=True).items()}
    # If a teacher tries to move the student to a class they don't teach, reject.
    # (Students they created themselves can also stay accessible after a move
    # because the move target still has to be one they teach.)
    if user["role"] == "teacher" and ("class_id" in update or "section" in update):
        tflt = await _teacher_class_filter(tdb, user)
        target = (update.get("class_id") or s["class_id"], update.get("section") or s["section"])
        allowed_move = set()
        if tflt and not tflt.get("_blocked_") and tflt.get("$or"):
            allowed_move = {(c["class_id"], c["section"]) for c in tflt["$or"]}
        if target not in allowed_move:
            raise HTTPException(status_code=403, detail="You can only move students to classes you teach")
    if not update:
        return {"ok": True}
    res = await tdb.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "student", student_id, update)
    return {"ok": True}


@router.delete("/{student_id}")
async def delete_student(student_id: str, user: dict = Depends(require_roles("school_admin", "teacher"))):
    tdb = await tenant_db(user["school_id"])
    s = await tdb.students.find_one({"id": student_id, "school_id": user["school_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    await _enforce_teacher_access(tdb, user, s)
    await tdb.students.update_one({"id": student_id, "school_id": user["school_id"]}, {"$set": {"status": "inactive"}})
    await log_action(user["id"], user["role"], user["school_id"], "deactivate", "student", student_id)
    return {"ok": True}
