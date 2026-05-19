"""Generate weekly timetable PDFs (school-wide, per-section, per-teacher)
using reportlab. Returns bytes for piping to Telegram sendDocument / S3 / etc.
"""
from io import BytesIO
from datetime import date as _date
from typing import Optional

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

DAYS_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat"]
DAY_LABEL = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday"}


def _styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title", parent=base["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#1f2937"),
    )
    subtitle = ParagraphStyle(
        "Subtitle", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#4b5563"),
    )
    body = ParagraphStyle("Body", parent=base["Normal"], fontSize=9, leading=12)
    return title, subtitle, body


def _grid_table(slots: list[dict], subject_map: dict, teacher_map: dict, periods_per_day: int) -> Table:
    """Render a (day x period) grid table for a single section."""
    periods = list(range(1, periods_per_day + 1))
    header = ["Day / Period"] + [f"P{p}" for p in periods]
    by = {}
    days_used = []
    for sl in slots:
        if sl["day"] not in by:
            by[sl["day"]] = {}
            days_used.append(sl["day"])
        by[sl["day"]][sl["period"]] = sl
    # Order Mon-Sat for consistent layout
    days_used = [d for d in DAYS_ORDER if d in by]
    rows = [header]
    cell_colors: list[tuple[int, int, str]] = []
    for r_idx, d in enumerate(days_used, start=1):
        row = [DAY_LABEL.get(d, d)]
        for c_idx, p in enumerate(periods, start=1):
            sl = by[d].get(p)
            if not sl:
                row.append("—")
                continue
            if sl.get("is_break"):
                row.append(f"<i>{sl.get('break_label') or 'Break'}</i>")
                cell_colors.append((c_idx, r_idx, "#fef3c7"))
                continue
            subj = subject_map.get(sl.get("subject_id")) or {}
            t = teacher_map.get(sl.get("teacher_id")) or {}
            sname = subj.get("name") or (sl.get("class_teacher_label") if sl.get("is_class_teacher_pin") else "—")
            tname = t.get("name") or ("Unfilled" if not sl.get("teacher_id") else "—")
            cell = f"<b>{sname}</b><br/><font size=7 color='#6b7280'>{tname}</font>"
            row.append(cell)
            if sl.get("is_class_teacher_pin"):
                cell_colors.append((c_idx, r_idx, "#dbeafe"))
            elif sl.get("is_locked"):
                cell_colors.append((c_idx, r_idx, "#ede9fe"))
            elif not sl.get("teacher_id"):
                cell_colors.append((c_idx, r_idx, "#fee2e2"))
        rows.append(row)
    # Render cells through Paragraph for HTML support
    _, _, body = _styles()
    body_para = ParagraphStyle("CellBody", parent=body, fontSize=8, leading=10, alignment=1)
    head_para = ParagraphStyle("CellHead", parent=body, fontSize=9, leading=11, alignment=1,
                                textColor=colors.white, fontName="Helvetica-Bold")
    rendered = []
    for r_i, row in enumerate(rows):
        rrow = []
        for c_i, val in enumerate(row):
            if r_i == 0 or c_i == 0:
                rrow.append(Paragraph(str(val), head_para if r_i == 0 else body))
            else:
                rrow.append(Paragraph(str(val), body_para))
        rendered.append(rrow)

    col_w = [28 * mm] + [(245 - 28) / max(1, periods_per_day) * mm] * periods_per_day
    tbl = Table(rendered, colWidths=col_w, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    for (c_i, r_i, hex_color) in cell_colors:
        style.add("BACKGROUND", (c_i, r_i), (c_i, r_i), colors.HexColor(hex_color))
    tbl.setStyle(style)
    return tbl


def section_pdf(
    *,
    school_name: str,
    class_name: str,
    section: str,
    slots: list[dict],
    subjects: list[dict],
    teachers: list[dict],
    periods_per_day: int,
    academic_year: Optional[str] = None,
) -> bytes:
    """One section's weekly timetable as a single-page A4 landscape PDF."""
    subject_map = {s["id"]: s for s in subjects}
    teacher_map = {t["id"]: t for t in teachers}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"{class_name} {section} weekly timetable",
    )
    title, subtitle, body = _styles()
    story = [
        Paragraph(f"{school_name}", title),
        Paragraph(
            f"Weekly timetable — <b>{class_name} · Section {section}</b>"
            + (f" · Academic year {academic_year}" if academic_year else "")
            + f" · Generated {_date.today().isoformat()}",
            subtitle,
        ),
        Spacer(1, 6 * mm),
        _grid_table(slots, subject_map, teacher_map, periods_per_day),
        Spacer(1, 4 * mm),
        Paragraph(
            "<font size=7 color='#6b7280'>Legend: <font backColor='#dbeafe'>&nbsp;blue&nbsp;</font> = class teacher · "
            "<font backColor='#ede9fe'>&nbsp;purple&nbsp;</font> = locked assignment · "
            "<font backColor='#fef3c7'>&nbsp;yellow&nbsp;</font> = break · "
            "<font backColor='#fee2e2'>&nbsp;red&nbsp;</font> = unfilled (find substitute).</font>",
            body,
        ),
    ]
    doc.build(story)
    return buf.getvalue()


def teacher_pdf(
    *,
    school_name: str,
    teacher_name: str,
    slots: list[dict],   # slots assigned to this teacher across all sections
    subjects: list[dict],
    classes: list[dict],
    periods_per_day: int,
    academic_year: Optional[str] = None,
) -> bytes:
    """A teacher's personal weekly timetable — landscape A4 with class·section in each cell."""
    subject_map = {s["id"]: s for s in subjects}
    class_map = {c["id"]: c for c in classes}
    # Render using a custom mini-grid that shows class·section instead of teacher name
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"{teacher_name} weekly timetable",
    )
    title, subtitle, body = _styles()
    periods = list(range(1, periods_per_day + 1))
    by = {}
    for sl in slots:
        by.setdefault(sl["day"], {})[sl["period"]] = sl
    days_used = [d for d in DAYS_ORDER if d in by]
    head_para = ParagraphStyle("H", parent=body, fontSize=9, leading=11, alignment=1, textColor=colors.white, fontName="Helvetica-Bold")
    cell_para = ParagraphStyle("C", parent=body, fontSize=8, leading=10, alignment=1)
    rows = [[Paragraph("Day / Period", head_para)] + [Paragraph(f"P{p}", head_para) for p in periods]]
    for d in days_used:
        row = [Paragraph(DAY_LABEL.get(d, d), body)]
        for p in periods:
            sl = by[d].get(p)
            if not sl:
                row.append(Paragraph("—", cell_para))
                continue
            subj = subject_map.get(sl.get("subject_id")) or {}
            cls = class_map.get(sl.get("class_id")) or {}
            sname = subj.get("name") or "—"
            row.append(Paragraph(
                f"<b>{sname}</b><br/><font size=7 color='#6b7280'>{cls.get('name','')} · {sl.get('section','')}</font>",
                cell_para,
            ))
        rows.append(row)
    col_w = [28 * mm] + [(245 - 28) / max(1, periods_per_day) * mm] * periods_per_day
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story = [
        Paragraph(f"{school_name}", title),
        Paragraph(
            f"Personal weekly timetable — <b>{teacher_name}</b>"
            + (f" · Academic year {academic_year}" if academic_year else "")
            + f" · Generated {_date.today().isoformat()}"
            + f" · {len(slots)} periods this week",
            subtitle,
        ),
        Spacer(1, 6 * mm),
        tbl,
    ]
    doc.build(story)
    return buf.getvalue()


def school_pdf(
    *,
    school_name: str,
    sections_by_class: list[dict],  # [{class_name, section, slots, periods_per_day}, ...]
    subjects: list[dict],
    teachers: list[dict],
    academic_year: Optional[str] = None,
) -> bytes:
    """Multi-section consolidated PDF (one page per section)."""
    subject_map = {s["id"]: s for s in subjects}
    teacher_map = {t["id"]: t for t in teachers}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"{school_name} — Master timetable",
    )
    title, subtitle, _ = _styles()
    story = [
        Paragraph(school_name, title),
        Paragraph(
            f"Master weekly timetable — {len(sections_by_class)} section(s)"
            + (f" · Academic year {academic_year}" if academic_year else "")
            + f" · Generated {_date.today().isoformat()}",
            subtitle,
        ),
        Spacer(1, 6 * mm),
    ]
    for i, sec in enumerate(sections_by_class):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(f"<b>{sec['class_name']} · Section {sec['section']}</b>", subtitle))
        story.append(Spacer(1, 3 * mm))
        story.append(_grid_table(sec["slots"], subject_map, teacher_map, sec.get("periods_per_day") or 6))
    doc.build(story)
    return buf.getvalue()
