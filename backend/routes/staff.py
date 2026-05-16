"""Non-teaching staff (cleaners, drivers, security, cook, sports coach, etc.).

Stored in the per-school DB collection `staff`. School admin manages CRUD;
Accounts can view (for payroll); teachers see no staff data.
"""
from typing import Literal, Optional
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core.auth import require_roles, get_current_user
from core.db import tenant_db, get_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/staff", tags=["staff"])

StaffRole = Literal[
    "cleaner", "bus_driver", "security", "cook", "sports_coach",
    "nurse", "librarian", "lab_assistant", "office_assistant", "other",
]


class StaffCreate(BaseModel):
    name: str
    role: StaffRole = "other"
    phone: Optional[str] = None
    email: Optional[str] = None
    monthly_salary: Optional[float] = None
    joining_date: Optional[str] = None
    notes: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[StaffRole] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    monthly_salary: Optional[float] = None
    joining_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_staff(user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    docs = await tdb.staff.find(
        {"school_id": user["school_id"]}, {"_id": 0},
    ).sort("name", 1).to_list(1000)
    return docs


@router.post("")
async def create_staff(payload: StaffCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **payload.model_dump(),
        "is_active": True,
        "created_at": utc_now(),
    }
    await tdb.staff.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"],
                      "create", "staff", doc["id"], {"name": payload.name, "role": payload.role})
    return clean_doc(doc)


@router.patch("/{staff_id}")
async def update_staff(staff_id: str, payload: StaffUpdate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await tdb.staff.update_one(
        {"id": staff_id, "school_id": user["school_id"]}, {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "staff", staff_id, update)
    return {"ok": True}


@router.delete("/{staff_id}")
async def delete_staff(staff_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    res = await tdb.staff.update_one(
        {"id": staff_id, "school_id": user["school_id"]},
        {"$set": {"is_active": False}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "deactivate", "staff", staff_id)
    return {"ok": True}


@router.get("/summary/payroll")
async def payroll_summary(user: dict = Depends(require_roles("school_admin", "accounts"))):
    """Returns total monthly outflow combining teacher + staff salaries."""
    from core.db import get_db
    db = get_db()
    tdb = await tenant_db(user["school_id"])

    # Teachers + accounts (master users)
    pipe_users = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}, "role": {"$in": ["teacher", "accounts"]}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    users_rows = await db.users.aggregate(pipe_users).to_list(20)
    by_role = {r["_id"]: {"count": r["count"], "monthly_total": r["total"]} for r in users_rows}

    # Non-teaching staff (tenant)
    pipe_staff = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    staff_rows = await tdb.staff.aggregate(pipe_staff).to_list(20)
    by_role.update({r["_id"]: {"count": r["count"], "monthly_total": r["total"]} for r in staff_rows})

    monthly_total = sum(v["monthly_total"] for v in by_role.values())
    return {
        "by_role": by_role,
        "monthly_total": monthly_total,
        "yearly_total": monthly_total * 12,
    }



# ----------------- Monthly Payroll PDF -----------------

PRIMARY = colors.HexColor("#4E5B3A")
SAND = colors.HexColor("#E6E1D6")
INK = colors.HexColor("#2F3E2E")
INK_SOFT = colors.HexColor("#5C6656")
ALT_ROW = colors.HexColor("#FAF8F2")


def _fmt_inr(v) -> str:
    try:
        return f"INR {float(v):,.2f}"
    except Exception:
        return "INR 0.00"


def _parse_month(month: Optional[str]) -> tuple[str, str]:
    """Return ('YYYY-MM', 'Month YYYY'). Defaults to current UTC month."""
    if month:
        try:
            dt = datetime.strptime(month, "%Y-%m")
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM (e.g. 2026-02)")
    else:
        now = utc_now()
        dt = datetime(now.year, now.month, 1)
    return dt.strftime("%Y-%m"), dt.strftime("%B %Y")


@router.get("/payroll/monthly-pdf")
async def monthly_payroll_pdf(month: Optional[str] = None,
                               user: dict = Depends(require_roles("school_admin", "accounts"))):
    """Generate a consolidated monthly payroll PDF combining:
    - Teachers + accounts (master users.monthly_salary)
    - Non-teaching staff (tenant staff.monthly_salary)
    - Approved reimbursable expenses for the given month
    Net payable per person and grand totals included.
    """
    month_key, month_label = _parse_month(month)
    db = get_db()
    tdb = await tenant_db(user["school_id"])
    school = await db.schools.find_one({"id": user["school_id"]}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    # ----- Teaching + accounts staff -----
    teaching = await db.users.find(
        {"school_id": user["school_id"], "is_active": True,
         "role": {"$in": ["teacher", "accounts"]}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "monthly_salary": 1},
    ).sort("role", 1).to_list(2000)

    # ----- Non-teaching staff -----
    support = await tdb.staff.find(
        {"school_id": user["school_id"], "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "phone": 1, "monthly_salary": 1},
    ).sort("name", 1).to_list(2000)

    # ----- Approved + paid reimbursable expenses in the given month -----
    expenses = await tdb.expenses.find(
        {"school_id": user["school_id"],
         "status": {"$in": ["approved", "paid"]},
         "reimburse_with_salary": True},
        {"_id": 0},
    ).to_list(5000)

    def _expense_month_key(e):
        v = e.get("incurred_on") or e.get("created_at")
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m")
        if isinstance(v, str) and len(v) >= 7:
            return v[:7]
        return None

    month_expenses = [e for e in expenses if _expense_month_key(e) == month_key]
    reimb_by_user: dict[str, float] = {}
    for e in month_expenses:
        uid = e.get("submitted_by")
        if uid:
            reimb_by_user[uid] = reimb_by_user.get(uid, 0.0) + float(e.get("amount") or 0)

    # ----- Build PDF -----
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold",
                                  textColor=PRIMARY, fontSize=20, leading=24, spaceAfter=2)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                                fontSize=10, textColor=INK_SOFT, spaceAfter=4)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                               fontSize=12, textColor=INK, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=INK_SOFT)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                             topMargin=15*mm, bottomMargin=15*mm)
    elements = []
    elements.append(Paragraph(school["name"], title_style))
    elements.append(Paragraph(f"Monthly Payroll — {month_label}", sub_style))
    elements.append(Paragraph(
        f"Generated on {utc_now().strftime('%d %b %Y, %I:%M %p UTC')} by {user.get('name') or user.get('email')}",
        small,
    ))
    elements.append(Spacer(1, 6*mm))

    grand_base = 0.0
    grand_reimb = 0.0
    grand_net = 0.0

    def _section(title: str, rows: list[dict], salary_key: str = "monthly_salary",
                  show_role: bool = True, role_labels: Optional[dict] = None,
                  user_id_key: str = "id"):
        nonlocal grand_base, grand_reimb, grand_net
        elements.append(Paragraph(title, h2_style))
        if not rows:
            elements.append(Paragraph("No records.", small))
            return
        header = ["#", "Name", "Role" if show_role else "Contact", "Base Salary", "Reimb.", "Net Payable"]
        data = [header]
        sub_base = sub_reimb = sub_net = 0.0
        for i, r in enumerate(rows, 1):
            base = float(r.get(salary_key) or 0)
            reimb = float(reimb_by_user.get(r.get(user_id_key), 0.0))
            net = base + reimb
            sub_base += base; sub_reimb += reimb; sub_net += net
            role_label = (role_labels.get(r.get("role"), r.get("role", "")).title()
                          if role_labels else (r.get("role", "") or "").replace("_", " ").title())
            third_col = role_label if show_role else (r.get("phone") or r.get("email") or "—")
            data.append([str(i), r.get("name") or "—", third_col,
                          _fmt_inr(base), _fmt_inr(reimb), _fmt_inr(net)])
        data.append(["", "", "Subtotal", _fmt_inr(sub_base), _fmt_inr(sub_reimb), _fmt_inr(sub_net)])
        grand_base += sub_base; grand_reimb += sub_reimb; grand_net += sub_net
        tbl = Table(data, colWidths=[10*mm, 50*mm, 40*mm, 28*mm, 22*mm, 30*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.25, INK_SOFT),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, ALT_ROW]),
            ("BACKGROUND", (0, -1), (-1, -1), SAND),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        elements.append(tbl)
        elements.append(Spacer(1, 4*mm))

    teacher_rows = [u for u in teaching if u.get("role") == "teacher"]
    accounts_rows = [u for u in teaching if u.get("role") == "accounts"]
    _section("Teaching staff", teacher_rows)
    _section("Accounts staff", accounts_rows)
    _section("Non-teaching support staff", support, show_role=True)

    # Grand total
    grand_data = [
        ["GRAND TOTAL", _fmt_inr(grand_base), _fmt_inr(grand_reimb), _fmt_inr(grand_net)],
    ]
    grand_tbl = Table(grand_data, colWidths=[100*mm, 28*mm, 22*mm, 30*mm])
    grand_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(Spacer(1, 4*mm))
    elements.append(grand_tbl)
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        f"Note: Reimbursable expenses included only when status is Approved/Paid and "
        f"flagged as 'reimburse with salary' (incurred during {month_label}).",
        small,
    ))

    doc.build(elements)
    buf.seek(0)

    await log_action(
        user["id"], user["role"], user["school_id"], "generate_payroll_pdf",
        "payroll", month_key, {"month": month_key},
    )
    filename = f"payroll_{school.get('code', 'school')}_{month_key}.pdf"
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
