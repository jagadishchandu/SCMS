"""Excel bulk upload endpoints — supports students, attendance, marks, holidays."""
import io
import openpyxl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from core.auth import require_roles
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _read_excel(file_bytes: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for r in rows[1:]:
        if r is None or all(v is None for v in r):
            continue
        d = {h: v for h, v in zip(headers, r) if h}
        out.append(d)
    return out


def _write_excel(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- Templates ----------
@router.get("/template/{kind}")
async def template(kind: str, _: dict = Depends(require_roles("school_admin", "teacher", "accounts"))):
    templates = {
        "students": (
            ["name", "class_id", "section", "roll_number", "gender", "dob",
             "parent_name", "parent_phone", "parent_whatsapp", "parent_email"],
            [["Aarav Sharma", "CLASS_ID_HERE", "A", "1", "M", "2014-05-10",
              "Rakesh Sharma", "+911234567890", "+911234567890", "rakesh@example.com"]],
        ),
        "attendance": (
            ["student_uid", "date", "status", "remark"],
            [["STU-00001", "2025-01-15", "present", ""]],
        ),
        "marks": (
            ["student_uid", "exam_id", "subject_id", "marks_obtained", "max_marks", "remark"],
            [["STU-00001", "EXAM_ID", "SUBJECT_ID", 85, 100, "good"]],
        ),
        "holidays": (
            ["title", "date", "end_date", "type", "description"],
            [["Republic Day", "2025-01-26", "", "public", "National holiday"]],
        ),
    }
    if kind not in templates:
        raise HTTPException(status_code=404, detail="Unknown template")
    headers, rows = templates[kind]
    data = _write_excel(headers, rows)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={kind}_template.xlsx"},
    )


# ---------- Students ----------
@router.post("/students")
async def upload_students(file: UploadFile = File(...), user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    # If teacher, restrict to their assigned (class_id, section) pairs
    allowed_class_sections = None
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tdb = await tenant_db(user["school_id"])
        tflt = await _teacher_class_filter(tdb, user)
        if not tflt or tflt.get("_blocked_"):
            raise HTTPException(status_code=403, detail="You are not assigned to any class yet")
        allowed_class_sections = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
    else:
        tdb = await tenant_db(user["school_id"])
    rows = _read_excel(await file.read())
    inserted, errors = 0, []
    for idx, r in enumerate(rows, start=2):
        try:
            row_class = r.get("class_id")
            row_section = r.get("section") or "A"
            if allowed_class_sections is not None and (row_class, row_section) not in allowed_class_sections:
                errors.append({"row": idx, "error": "Class/section not in your assigned classes"})
                continue
            from core.auth import hash_password
            count = await tdb.students.count_documents({"school_id": user["school_id"]})
            uid = f"STU-{(count + 1):05d}"
            parent_email = (r.get("parent_email") or f"parent.{uid.lower()}@local").lower()
            existing_parent = await db.users.find_one({"email": parent_email})
            if existing_parent:
                parent_user_id = existing_parent["id"]
            else:
                parent_user_id = new_id()
                parent_doc = {
                    "id": parent_user_id,
                    "email": parent_email,
                    "password_hash": hash_password("Parent@123"),
                    "name": r.get("parent_name") or "Parent",
                    "role": "parent",
                    "school_id": user["school_id"],
                    "phone": str(r.get("parent_phone") or ""),
                    "is_active": True,
                    "created_at": utc_now(),
                }
                await db.users.insert_one(parent_doc)
                mirror = {k: v for k, v in parent_doc.items() if k != "_id"}
                await tdb.users.update_one({"email": parent_email}, {"$set": mirror}, upsert=True)
                await tdb.parents.update_one(
                    {"user_id": parent_user_id},
                    {"$set": {"user_id": parent_user_id, "email": parent_email,
                              "name": mirror["name"], "phone": mirror.get("phone"),
                              "created_at": mirror["created_at"]}},
                    upsert=True,
                )
            await tdb.students.insert_one({
                "id": new_id(),
                "school_id": user["school_id"],
                "student_uid": uid,
                "name": r.get("name"),
                "class_id": r.get("class_id"),
                "section": r.get("section") or "A",
                "roll_number": str(r.get("roll_number") or ""),
                "gender": r.get("gender"),
                "dob": str(r.get("dob") or "") or None,
                "parent": {
                    "name": r.get("parent_name") or "Parent",
                    "relationship": "guardian",
                    "phone": str(r.get("parent_phone") or ""),
                    "whatsapp": str(r.get("parent_whatsapp") or r.get("parent_phone") or ""),
                    "email": parent_email,
                },
                "parent_user_id": parent_user_id,
                "status": "active",
                "created_at": utc_now(),
            })
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})
    await tdb.bulk_uploads.insert_one({
        "id": new_id(), "school_id": user["school_id"], "kind": "students",
        "rows": len(rows), "inserted": inserted, "errors": errors,
        "by": user["id"], "created_at": utc_now(),
    })
    return {"rows": len(rows), "inserted": inserted, "errors": errors}


# ---------- Attendance ----------
@router.post("/attendance")
async def upload_attendance(
    file: UploadFile = File(...),
    class_id: str = Form(...),
    section: str = Form(...),
    user: dict = Depends(require_roles("school_admin", "teacher")),
):
    tdb = await tenant_db(user["school_id"])
    rows = _read_excel(await file.read())
    inserted, errors = 0, []
    for idx, r in enumerate(rows, start=2):
        try:
            student = await tdb.students.find_one({"school_id": user["school_id"], "student_uid": r["student_uid"]})
            if not student:
                errors.append({"row": idx, "error": f"Student {r['student_uid']} not found"})
                continue
            date_val = str(r["date"])
            if "T" in date_val:
                date_val = date_val.split("T")[0]
            await tdb.attendance.update_one(
                {"school_id": user["school_id"], "student_id": student["id"], "date": date_val},
                {"$set": {
                    "id": new_id(),
                    "school_id": user["school_id"],
                    "student_id": student["id"],
                    "class_id": class_id,
                    "section": section,
                    "date": date_val,
                    "status": (r.get("status") or "present"),
                    "remark": r.get("remark"),
                    "marked_by": user["id"],
                    "marked_at": utc_now(),
                }},
                upsert=True,
            )
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})
    return {"rows": len(rows), "inserted": inserted, "errors": errors}


# ---------- Holidays ----------
@router.post("/holidays")
async def upload_holidays(file: UploadFile = File(...), user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    rows = _read_excel(await file.read())
    inserted, errors = 0, []
    for idx, r in enumerate(rows, start=2):
        try:
            await tdb.holidays.insert_one({
                "id": new_id(),
                "school_id": user["school_id"],
                "title": r.get("title"),
                "date": str(r.get("date"))[:10],
                "end_date": str(r.get("end_date"))[:10] if r.get("end_date") else None,
                "type": r.get("type") or "school",
                "description": r.get("description"),
                "created_at": utc_now(),
            })
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})
    return {"rows": len(rows), "inserted": inserted, "errors": errors}


@router.get("/logs")
async def upload_logs(user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    db = get_db()
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    return await db.upload_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(100)
