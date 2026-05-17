"""Excel bulk upload endpoints — supports students, attendance, marks, holidays."""
import csv
import io
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from core.auth import require_roles, get_current_user
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
        # Skip the hint/legend row (italic-grey) — it always starts with "e.g."
        first_val = r[0]
        if isinstance(first_val, str) and first_val.strip().lower().startswith("e.g."):
            continue
        d = {h: v for h, v in zip(headers, r) if h}
        out.append(d)
    return out


def _write_excel(
    headers: list[str],
    rows: list[list],
    hints: list[str] | None = None,
    references: dict[str, list[tuple[str, str]]] | None = None,
    column_validations: dict[str, str] | None = None,
) -> bytes:
    """Write an .xlsx with bolded headers, an optional italic-grey hint row, and
    cell comments on each header explaining the expected format.

    Args:
        references: optional {section_label: [(id, name), ...]} written to a
            hidden 'References' sheet so users can find the right ID. Also used
            as the source range for column_validations.
        column_validations: optional {column_header: reference_section_label}
            mapping that attaches a dropdown to that column populated with the
            IDs from the matching reference section.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Upload"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4E5B3A", end_color="4E5B3A", fill_type="solid")
    hint_font = Font(italic=True, color="9CA3AF")  # light grey
    centre = Alignment(horizontal="left", vertical="center")

    ws.append(headers)
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = centre
        ws.column_dimensions[c.column_letter].width = max(14, len(str(h)) + 4)

    if hints:
        ws.append(hints)
        for col_idx, hint in enumerate(hints, start=1):
            c = ws.cell(row=2, column=col_idx)
            c.font = hint_font
            c.alignment = centre
            header_cell = ws.cell(row=1, column=col_idx)
            if hint:
                header_cell.comment = Comment(hint, "SCMS")

    ws.freeze_panes = "A2"

    for r in rows:
        ws.append(r)

    # Reference sheet — visible so users can see name ↔ id mapping.
    ref_ranges: dict[str, str] = {}
    if references:
        rsheet = wb.create_sheet("References")
        rsheet.sheet_properties.tabColor = "B7A77A"
        row_cursor = 1
        title_font = Font(bold=True, color="4E5B3A", size=12)
        sub_header_font = Font(bold=True, color="FFFFFF")
        sub_header_fill = PatternFill(start_color="8F9C82", end_color="8F9C82", fill_type="solid")

        for section_label, items in references.items():
            tcell = rsheet.cell(row=row_cursor, column=1, value=section_label)
            tcell.font = title_font
            rsheet.merge_cells(
                start_row=row_cursor, start_column=1, end_row=row_cursor, end_column=2,
            )
            row_cursor += 1
            for ci, h in enumerate(["ID", "Name"], start=1):
                c = rsheet.cell(row=row_cursor, column=ci, value=h)
                c.font = sub_header_font
                c.fill = sub_header_fill
            row_cursor += 1
            start = row_cursor
            for (rid, rname) in items:
                rsheet.cell(row=row_cursor, column=1, value=rid)
                rsheet.cell(row=row_cursor, column=2, value=rname)
                row_cursor += 1
            end = row_cursor - 1
            if items:
                ref_ranges[section_label] = f"References!${get_column_letter(1)}${start}:${get_column_letter(1)}${end}"
            row_cursor += 1  # blank spacer

        rsheet.column_dimensions["A"].width = 30
        rsheet.column_dimensions["B"].width = 36

    if column_validations and ref_ranges:
        for col_header, ref_section in column_validations.items():
            ref_range = ref_ranges.get(ref_section)
            if not ref_range:
                continue
            try:
                col_idx = headers.index(col_header) + 1
            except ValueError:
                continue
            dv = DataValidation(type="list", formula1=f"={ref_range}", allow_blank=True)
            dv.error = f"Please pick a valid {col_header} from the dropdown."
            dv.errorTitle = "Invalid value"
            dv.prompt = f"Select a {col_header} from the References sheet."
            dv.promptTitle = col_header
            ws.add_data_validation(dv)
            # Apply to rows 3..1000 (skip header row + hint row)
            col_letter = get_column_letter(col_idx)
            dv.add(f"{col_letter}3:{col_letter}1000")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Column-format hints (kept short — shown as italic-grey legend row + header comment).
TEMPLATE_HINTS: dict[str, list[str]] = {
    "students": [
        "e.g. Aarav Sharma",
        "e.g. CLASS_ID (copy from Classes page)",
        "e.g. A",
        "e.g. 1",
        "M / F / Other",
        "e.g. 2014-05-10 (YYYY-MM-DD)",
        "e.g. Rakesh Sharma",
        "e.g. +911234567890 (with country code)",
        "e.g. +911234567890 (with country code)",
        "e.g. rakesh@example.com",
        "e.g. Parent@123 (min 6 chars)",
    ],
    "attendance": [
        "e.g. STU-00001 (student UID)",
        "e.g. 2025-01-15 (YYYY-MM-DD)",
        "present / absent / sick / late / half_day / excused",
        "e.g. fever (optional)",
    ],
    "marks": [
        "e.g. STU-00001 (student UID)",
        "e.g. EXAM_ID (from Exams page)",
        "e.g. SUBJECT_ID (from Subjects page)",
        "e.g. 85",
        "e.g. 100",
        "Optional comment",
    ],
    "holidays": [
        "e.g. Republic Day",
        "e.g. 2025-01-26 (YYYY-MM-DD)",
        "e.g. 2025-01-26 (optional, same as date for single-day)",
        "public / school / religious / festival",
        "Optional description",
    ],
}


TEMPLATE_SPECS: dict[str, dict] = {
    "students": {
        "headers": ["name", "class_id", "section", "roll_number", "gender", "dob",
                    "parent_name", "parent_phone", "parent_whatsapp", "parent_email", "parent_password"],
        "validations": {"class_id": "Classes (use the ID column)"},
        "ref_sections": ["classes"],
    },
    "attendance": {
        "headers": ["student_uid", "date", "status", "remark"],
        "validations": {"student_uid": "Students (use the ID column)", "status": "Attendance statuses"},
        "ref_sections": ["students", "attendance_statuses"],
    },
    "marks": {
        "headers": ["student_uid", "exam_id", "subject_id", "marks_obtained", "max_marks", "remark"],
        "validations": {
            "student_uid": "Students (use the ID column)",
            "exam_id": "Exams (use the ID column)",
            "subject_id": "Subjects (use the ID column)",
        },
        "ref_sections": ["students", "exams", "subjects"],
    },
    "holidays": {
        "headers": ["title", "date", "end_date", "type", "description"],
        "validations": {"type": "Holiday types"},
        "ref_sections": ["holiday_types"],
    },
}


async def _build_references(user: dict, sections: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Load reference lookups (id → label) for the school the user belongs to.
    Returns an ordered dict suitable for `_write_excel(references=...)`.
    """
    refs: dict[str, list[tuple[str, str]]] = {}
    if not user.get("school_id"):
        return refs
    tdb = await tenant_db(user["school_id"])

    if "classes" in sections:
        classes = await tdb.classes.find({}, {"_id": 0}).sort("name", 1).to_list(500)
        refs["Classes (use the ID column)"] = [
            (c["id"], f"{c.get('name')} (sections: {', '.join(c.get('sections') or [])})")
            for c in classes
        ]

    if "students" in sections:
        students = await tdb.students.find(
            {"status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "student_uid": 1, "name": 1, "section": 1},
        ).sort("student_uid", 1).to_list(2000)
        refs["Students (use the ID column)"] = [
            (s.get("student_uid"), f"{s.get('name')} · Sec {s.get('section')}") for s in students
        ]

    if "exams" in sections:
        exams = await tdb.exams.find({}, {"_id": 0}).sort("start_date", -1).to_list(500)
        refs["Exams (use the ID column)"] = [
            (e["id"], f"{e.get('name')} · {e.get('term') or ''}") for e in exams
        ]

    if "subjects" in sections:
        subjects = await tdb.subjects.find({}, {"_id": 0}).sort("name", 1).to_list(500)
        refs["Subjects (use the ID column)"] = [
            (s["id"], f"{s.get('name')} ({s.get('code') or ''})") for s in subjects
        ]

    if "attendance_statuses" in sections:
        refs["Attendance statuses"] = [
            ("present", "Present"), ("absent", "Absent"), ("sick", "Sick"),
            ("late", "Late"), ("half_day", "Half day"), ("excused", "Excused"),
        ]

    if "holiday_types" in sections:
        refs["Holiday types"] = [
            ("public", "Public holiday"), ("school", "School holiday"),
            ("religious", "Religious"), ("festival", "Festival"),
        ]

    return refs


# ---------- Templates ----------
@router.get("/template/{kind}")
async def template(kind: str, user: dict = Depends(require_roles("school_admin", "teacher", "accounts"))):
    spec = TEMPLATE_SPECS.get(kind)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown template")
    references = await _build_references(user, spec["ref_sections"])
    data = _write_excel(
        headers=spec["headers"],
        rows=[],
        hints=TEMPLATE_HINTS.get(kind),
        references=references,
        column_validations=spec["validations"],
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={kind}_template.xlsx"},
    )


@router.get("/template-csv/{kind}")
async def template_csv(kind: str, user: dict = Depends(require_roles("school_admin", "teacher", "accounts"))):
    """CSV variant of the template — same headers + hint row. Easy to import
    into Google Sheets via File → Import → Upload."""
    spec = TEMPLATE_SPECS.get(kind)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown template")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(spec["headers"])
    hints = TEMPLATE_HINTS.get(kind)
    if hints:
        w.writerow(hints)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={kind}_template.csv"},
    )


# ---------- Students ----------
@router.post("/students")
async def upload_students(file: UploadFile = File(...), user: dict = Depends(require_roles("school_admin", "teacher"))):
    db = get_db()
    # If teacher, restrict to their assigned (class_id, section) pairs. If a
    # teacher has NO formal assignment, fall back to permissive school-wide
    # add (matches POST /api/students behaviour after v1.32.2 bug fix).
    allowed_class_sections = None
    if user["role"] == "teacher":
        from routes.students import _teacher_class_filter
        tdb = await tenant_db(user["school_id"])
        tflt = await _teacher_class_filter(tdb, user)
        if tflt and not tflt.get("_blocked_") and tflt.get("$or"):
            allowed_class_sections = {(c["class_id"], c["section"]) for c in tflt.get("$or", [])}
        # else: no formal assignment — allow all rows through; class/section
        # validation still happens via the row's class_id/section being a real
        # row in the tenant DB at insert time.
    else:
        tdb = await tenant_db(user["school_id"])
    rows = _read_excel(await file.read())
    inserted, errors = 0, []
    credentials: list[dict] = []
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
            parent_email = (r.get("parent_email") or f"parent.{uid.lower()}@{user['school_id'][:6]}.school").lower()
            # Optional explicit password in Excel — falls back to school default.
            row_pwd = str(r.get("parent_password") or "").strip()
            parent_password = row_pwd if len(row_pwd) >= 6 else "Parent@123"
            existing_parent = await db.users.find_one({"email": parent_email})
            if existing_parent:
                parent_user_id = existing_parent["id"]
                # If a non-default password was provided for an existing parent, update it.
                if row_pwd and len(row_pwd) >= 6:
                    await db.users.update_one(
                        {"id": parent_user_id},
                        {"$set": {"password_hash": hash_password(row_pwd), "password_reset_to_default_at": utc_now()}},
                    )
                parent_was_created = False
            else:
                parent_user_id = new_id()
                parent_was_created = True
                parent_doc = {
                    "id": parent_user_id,
                    "email": parent_email,
                    "password_hash": hash_password(parent_password),
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
                "created_by_id": user["id"],
                "created_by_role": user["role"],
            })
            credentials.append({
                "row": idx,
                "student_uid": uid,
                "student_name": r.get("name"),
                "parent_email": parent_email,
                "parent_password": parent_password if parent_was_created else None,
                "parent_was_created": parent_was_created,
            })
            inserted += 1
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})
    await tdb.bulk_uploads.insert_one({
        "id": new_id(), "school_id": user["school_id"], "kind": "students",
        "rows": len(rows), "inserted": inserted, "errors": errors,
        "by": user["id"], "created_at": utc_now(),
    })
    return {"rows": len(rows), "inserted": inserted, "errors": errors, "credentials": credentials}


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
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        out = []
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            out.extend(await tdb.bulk_uploads.find({}, {"_id": 0}).sort("created_at", -1).to_list(50))
        return out
    tdb = await tenant_db(user["school_id"])
    return await tdb.bulk_uploads.find({"school_id": user["school_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


# ---------- Bulk export: parent credentials for a class ----------
@router.get("/parent-credentials")
async def export_parent_credentials(
    class_id: str | None = None,
    section: str | None = None,
    user: dict = Depends(require_roles("school_admin")),
):
    """Download an Excel sheet of (student_uid, name, class, section, parent_name,
    parent_phone, parent_email, default_password_hint) for every active student in
    the given class (or whole school if no class given).

    The 'default_password_hint' column is `Parent@123 (unless changed)` — we never
    persist plaintext passwords. To force-reset a parent back to the default, use
    POST /api/students/{id}/parent-reset-password.
    """
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"], "status": "active"}
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section.upper()
    students = await tdb.students.find(flt, {"_id": 0}).sort("student_uid", 1).to_list(5000)
    classes = await tdb.classes.find({"school_id": user["school_id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    cmap = {c["id"]: c["name"] for c in classes}
    headers = [
        "student_uid", "student_name", "class", "section",
        "parent_name", "parent_phone", "parent_whatsapp", "parent_email",
        "default_password_hint",
    ]
    body = []
    for s in students:
        p = s.get("parent") or {}
        body.append([
            s.get("student_uid"), s.get("name"),
            cmap.get(s.get("class_id"), s.get("class_id")), s.get("section"),
            p.get("name"), p.get("phone"), p.get("whatsapp"), p.get("email"),
            "Parent@123 (unless changed)",
        ])
    xlsx = _write_excel(headers, body)
    class_label = (cmap.get(class_id, class_id) if class_id else "all").replace(" ", "_")
    fname = f"parent-credentials-{class_label}{('-'+section) if section else ''}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
