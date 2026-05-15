"""PDF receipts and exportable reports."""
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core.auth import get_current_user
from core.db import get_db, tenant_db

router = APIRouter(prefix="/receipts", tags=["receipts"])

PRIMARY = colors.HexColor("#4E5B3A")
SAND = colors.HexColor("#E6E1D6")
INK = colors.HexColor("#2F3E2E")
INK_SOFT = colors.HexColor("#5C6656")


def _pdf_response(buf: io.BytesIO, filename: str):
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/payment/{payment_id}.pdf")
async def payment_receipt(payment_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    # Search payment across tenant DBs (we don't know which school upfront).
    payment = None
    school = None
    if user.get("school_id"):
        tdb = await tenant_db(user["school_id"])
        payment = await tdb.fee_payments.find_one({"id": payment_id}, {"_id": 0})
        if payment:
            school = await db.schools.find_one({"id": payment["school_id"]}, {"_id": 0})
    if not payment:
        # Platform admin path: iterate all schools.
        async for s in db.schools.find({}, {"_id": 0}):
            stdb = await tenant_db(s["id"])
            p = await stdb.fee_payments.find_one({"id": payment_id}, {"_id": 0})
            if p:
                payment = p; school = s; break
    if not payment:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] not in ("platform_admin",) and user.get("school_id") != payment["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    tdb = await tenant_db(payment["school_id"])
    student = await tdb.students.find_one({"id": payment["student_id"]}, {"_id": 0})
    fee = await tdb.fees.find_one({"id": payment["fee_id"]}, {"_id": 0})

    if user["role"] == "parent" and student.get("parent_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold", textColor=PRIMARY, fontSize=22, leading=26, spaceAfter=4)
    label_style = ParagraphStyle("lbl", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=INK_SOFT, leading=12, spaceAfter=2)
    val_style = ParagraphStyle("val", parent=styles["Normal"], fontName="Helvetica", fontSize=11, textColor=INK, leading=14, spaceAfter=8)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=INK_SOFT)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    elements = []

    elements.append(Paragraph(school["name"] if school else "SCMS", title_style))
    elements.append(Paragraph(f'{(school.get("address") or "") if school else ""}', small))
    elements.append(Spacer(1, 8*mm))

    elements.append(Paragraph("PAYMENT RECEIPT", ParagraphStyle("rcpt", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=INK)))
    elements.append(Paragraph(f"Receipt No: <b>{payment['receipt_no']}</b>", small))
    elements.append(Paragraph(f"Date: {payment['created_at'].strftime('%d %b %Y, %I:%M %p') if hasattr(payment['created_at'], 'strftime') else str(payment['created_at'])}", small))
    elements.append(Spacer(1, 6*mm))

    # Student details
    elements.append(Paragraph("STUDENT", label_style))
    elements.append(Paragraph(f"{student['name']} ({student['student_uid']}) · Section {student.get('section','')}", val_style))
    if student.get("parent", {}).get("name"):
        elements.append(Paragraph("PARENT", label_style))
        elements.append(Paragraph(f"{student['parent']['name']} · {student['parent'].get('phone','')}", val_style))

    # Fee table
    table_data = [
        ["Description", "Amount (INR)"],
        [fee["name"] if fee else "Fee", f"{payment['amount']:,.2f}"],
    ]
    table_data.append(["Mode", payment["mode"].replace("_", " ").title()])
    table_data.append(["Receipt", payment["receipt_no"]])
    tbl = Table(table_data, colWidths=[110*mm, 50*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, SAND),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 8*mm))

    # Totals
    if fee:
        elements.append(Paragraph(f"Fee Total: <b>INR {fee['total']:,.2f}</b>", val_style))
        elements.append(Paragraph(f"Paid so far: INR {fee['paid']:,.2f}", small))
        elements.append(Paragraph(f"Outstanding: INR {fee['due']:,.2f}", small))

    elements.append(Spacer(1, 16*mm))
    elements.append(Paragraph("This is a system-generated receipt. Thank you for your payment.", small))

    doc.build(elements)
    return _pdf_response(buf, f"receipt_{payment['receipt_no']}.pdf")


@router.get("/student/{student_uid}/report.pdf")
async def student_report(student_uid: str, user: dict = Depends(get_current_user)):
    """Student summary report PDF (attendance + marks + fees overview)."""
    db = get_db()
    tdb = await tenant_db(user["school_id"])
    flt = {"student_uid": student_uid}
    if user["role"] != "platform_admin":
        flt["school_id"] = user["school_id"]
    if user["role"] == "parent":
        flt["parent_user_id"] = user["id"]
    s = await tdb.students.find_one(flt, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    school = await db.schools.find_one({"id": s["school_id"]}, {"_id": 0})

    att = await tdb.attendance.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(5000)
    counts = {"present": 0, "absent": 0, "sick": 0, "late": 0, "half_day": 0, "excused": 0}
    for r in att:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    total = len(att); present_like = counts["present"] + counts["late"] + counts["half_day"]
    pct = round(present_like / total * 100, 1) if total else 0

    marks = await tdb.marks.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(2000)
    subjects = await tdb.subjects.find({"school_id": s["school_id"]}, {"_id": 0}).to_list(500)
    sub_map = {x["id"]: x["name"] for x in subjects}
    by_subject = {}
    for m in marks:
        by_subject.setdefault(sub_map.get(m["subject_id"], m["subject_id"]), []).append(m["percentage"])
    subject_rows = [(k, f"{round(sum(v)/len(v),1)}%") for k, v in by_subject.items()]

    fees = await tdb.fees.find({"school_id": s["school_id"], "student_id": s["id"]}, {"_id": 0}).to_list(100)
    fee_total = sum(f["total"] for f in fees); fee_paid = sum(f["paid"] for f in fees); fee_due = sum(f["due"] for f in fees)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold", textColor=PRIMARY, fontSize=22, leading=26, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=INK, spaceBefore=10, spaceAfter=6)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=INK_SOFT)
    val = ParagraphStyle("v", parent=styles["Normal"], fontName="Helvetica", fontSize=11, textColor=INK, spaceAfter=4)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    e = []
    e.append(Paragraph(school["name"] if school else "SCMS", title_style))
    e.append(Paragraph("Student Performance Report", small))
    e.append(Spacer(1, 6*mm))

    e.append(Paragraph("STUDENT", h2))
    e.append(Paragraph(f"<b>{s['name']}</b> · {s['student_uid']} · Section {s.get('section','')}", val))
    if s.get("parent"):
        e.append(Paragraph(f"Parent: {s['parent'].get('name')} · {s['parent'].get('phone','')}", small))

    e.append(Paragraph("ATTENDANCE", h2))
    att_rows = [["Status", "Days"]] + [[k.title(), str(v)] for k, v in counts.items()] + [["Attendance %", f"{pct}%"]]
    t = Table(att_rows, colWidths=[80*mm, 30*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), SAND),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.4, SAND),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6),
    ])); e.append(t)

    if subject_rows:
        e.append(Paragraph("ACADEMICS", h2))
        ms_rows = [["Subject", "Average"]] + [list(r) for r in subject_rows]
        t = Table(ms_rows, colWidths=[80*mm, 30*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), SAND),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("GRID", (0,0), (-1,-1), 0.4, SAND),
            ("ALIGN", (1,0), (1,-1), "RIGHT"),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6),
        ])); e.append(t)

    e.append(Paragraph("FEES", h2))
    fee_rows = [["", "Amount (INR)"], ["Total billed", f"{fee_total:,.2f}"], ["Paid", f"{fee_paid:,.2f}"], ["Outstanding", f"{fee_due:,.2f}"]]
    t = Table(fee_rows, colWidths=[80*mm, 30*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), SAND),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.4, SAND),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6),
    ])); e.append(t)

    doc.build(e)
    return _pdf_response(buf, f"{s['student_uid']}_report.pdf")
