"""Generate the SCMS one-page sales brochure (PDF).

Run:
    python3 /app/scripts/generate_one_pager.py
Output:
    /app/SCMS_OnePager.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = "/app/SCMS_OnePager.pdf"

# Brand palette
PRIMARY = HexColor("#4E5B3A")
SAND    = HexColor("#E6E1D6")
INK     = HexColor("#2F3E2E")
INK_SOFT = HexColor("#5C6656")
BG      = HexColor("#FAF8F2")
ACCENT  = HexColor("#C4553A")
SUCCESS = HexColor("#4F7A4F")
WARNING = HexColor("#C79A3A")

W, H = A4   # 210 x 297 mm
M = 12 * mm   # outer margin


def text(c, x, y, s, *, font="Helvetica", size=9, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, s)


def text_right(c, x, y, s, *, font="Helvetica", size=9, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawRightString(x, y, s)


def wrap(c, x, y, max_w, s, *, font="Helvetica", size=8, color=INK, leading=10):
    """Tiny manual word-wrap."""
    c.setFont(font, size)
    c.setFillColor(color)
    words = s.split()
    line = ""
    cur_y = y
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, font, size) <= max_w:
            line = test
        else:
            c.drawString(x, cur_y, line)
            cur_y -= leading
            line = w
    if line:
        c.drawString(x, cur_y, line)
        cur_y -= leading
    return cur_y  # next y to draw at


def rect(c, x, y, w, h, fill=None, stroke=None, stroke_w=0.4, radius=None):
    if fill is not None:
        c.setFillColor(fill)
    else:
        c.setFillAlpha(0)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_w)
    if radius:
        c.roundRect(x, y, w, h, radius, stroke=(1 if stroke else 0), fill=(1 if fill else 0))
    else:
        c.rect(x, y, w, h, stroke=(1 if stroke else 0), fill=(1 if fill else 0))
    c.setFillAlpha(1)


def build():
    c = canvas.Canvas(OUT, pagesize=A4)

    # ── Background cream ──
    rect(c, 0, 0, W, H, fill=BG)

    # ── Left accent band ──
    rect(c, 0, 0, 4 * mm, H, fill=ACCENT)

    # ────────────────────── HERO HEADER ──────────────────────
    hero_h = 42 * mm
    hero_y = H - hero_h
    rect(c, 0, hero_y, W, hero_h, fill=PRIMARY)
    # Left accent over hero
    rect(c, 0, hero_y, 4 * mm, hero_h, fill=ACCENT)

    # Logo block
    logo_size = 12 * mm
    logo_x = M + 2 * mm
    logo_y = hero_y + hero_h - logo_size - 8 * mm
    rect(c, logo_x, logo_y, logo_size, logo_size, fill=SAND, radius=2)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(PRIMARY)
    c.drawCentredString(logo_x + logo_size / 2, logo_y + logo_size / 2 - 4, "S")

    # Brand text
    text(c, logo_x + logo_size + 4 * mm, hero_y + hero_h - 12 * mm,
         "SCMS", font="Helvetica-Bold", size=18, color=white)
    text(c, logo_x + logo_size + 4 * mm, hero_y + hero_h - 17 * mm,
         "SCHOOL CHILD MONITORING SYSTEM", font="Helvetica-Bold", size=7, color=SAND)

    # Top right tag
    text_right(c, W - M, hero_y + hero_h - 10 * mm,
               "v1.18.1  ·  Feb 2026", font="Helvetica", size=8, color=SAND)

    # Hero headline
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(white)
    c.drawString(M + 2 * mm, hero_y + 17 * mm,
                 "Run a real school. Not a spreadsheet farm.")
    c.setFont("Helvetica", 10)
    c.setFillColor(SAND)
    c.drawString(M + 2 * mm, hero_y + 11 * mm,
                 "Multi-tenant SaaS for K-12 schools — attendance, marks, fees, HR & payroll, parent comms in 8 Indian languages.")
    c.drawString(M + 2 * mm, hero_y + 7 * mm,
                 "Strict role-based access. WhatsApp/Telegram-first alerts. Per-tenant database isolation. Docker one-liner deploy.")

    # ────────────────────── BENEFITS STRIP (just below hero) ──────────────────────
    strip_y = hero_y - 14 * mm
    strip_h = 12 * mm
    strip_x = M
    strip_w = W - 2 * M
    rect(c, strip_x, strip_y, strip_w, strip_h, fill=SAND, radius=2)

    kpis = [("283", "Backend tests"),
            ("31", "Tenant collections"),
            ("8", "Languages"),
            ("6", "Roles"),
            ("FREE", "WhatsApp + Telegram"),
            ("1-cmd", "Docker deploy")]
    cw = strip_w / len(kpis)
    for i, (big, label) in enumerate(kpis):
        cx = strip_x + i * cw
        text(c, cx + 4 * mm, strip_y + 7.5 * mm, big,
             font="Helvetica-Bold", size=14, color=PRIMARY)
        text(c, cx + 4 * mm, strip_y + 3 * mm, label,
             font="Helvetica", size=7.5, color=INK_SOFT)

    # ────────────────────── FEATURES GRID (3 cols × 3 rows) ──────────────────────
    grid_top = strip_y - 6 * mm
    grid_bottom = M + 55 * mm  # leave room for pricing + footer
    grid_h = grid_top - grid_bottom

    cols, rows = 3, 3
    pad = 3 * mm
    cell_w = (strip_w - (cols - 1) * pad) / cols
    cell_h = (grid_h - (rows - 1) * pad) / rows

    features = [
        ("Onboarding & RBAC",
         "Platform admin onboards schools. ONE Super Admin per school. 6 roles, every endpoint scoped. Wrong-role at login is blocked + cookie cleared.",
         PRIMARY),
        ("Subscription Approval & Lockdown",
         "New schools request approval with a child-count. Until approved, sidebar shows only Dashboard + Subscription (HTTP 423). Approval = full unlock.",
         ACCENT),
        ("Per-child Billing",
         "₹30/child/month or ₹300/child/year (~16% off). Live quote from active students. Auto-expiry guard + 7-day Telegram/WhatsApp renewal nudge.",
         WARNING),
        ("Attendance & Marks",
         "Mobile swipe-card attendance with auto WhatsApp alerts. Per-subject marks; publishing fires multilingual notifications to every parent.",
         ACCENT),
        ("HR & Finance",
         "Teachers + accounts + non-teaching staff (cleaners, drivers, security, coaches). Expenses + teacher reimbursement workflow. One-click Monthly Payroll PDF.",
         SUCCESS),
        ("Platform Compliance",
         "Read-only dashboard comparing each school's approved vs actual student count. Filter `over_capacity` for billing reconciliation & capacity planning.",
         PRIMARY),
        ("Multilingual Alerts",
         "Meta WhatsApp Cloud (FREE 1000/mo) → Twilio fallback → Telegram → Email. 8 Indian languages baked in. Parent override beats school default.",
         SUCCESS),
        ("Sick Leaves & Risk Flags",
         "Multi-day sick leaves with medical cert upload. Recurring-illness widget (≥3 in 90 days). Predictive risk scoring highlights at-risk students.",
         ACCENT),
        ("Audit, PDFs & Bulk Excel",
         "Audit log with filters + UTF-8 CSV export. ReportLab receipts + student academic report. Excel bulk-upload for students/attendance/holidays.",
         WARNING),
    ]

    for i, (title, body, color) in enumerate(features):
        col = i % cols; row = i // cols
        x = strip_x + col * (cell_w + pad)
        y = grid_top - (row + 1) * cell_h - row * pad
        # card
        rect(c, x, y, cell_w, cell_h, fill=white, stroke=SAND, radius=2)
        # accent bar
        rect(c, x + 3 * mm, y + cell_h - 4 * mm, 8 * mm, 1.2 * mm, fill=color)
        # title
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(INK)
        c.drawString(x + 3 * mm, y + cell_h - 9 * mm, title)
        # body
        wrap(c, x + 3 * mm, y + cell_h - 14 * mm, cell_w - 6 * mm, body,
             font="Helvetica", size=8, color=INK_SOFT, leading=10)

    # ────────────────────── PRICING + WHY-US STRIP ──────────────────────
    price_h = 30 * mm
    price_y = M + 22 * mm
    rect(c, M, price_y, W - 2 * M, price_h, fill=PRIMARY, radius=2)

    # Left half — pricing
    text(c, M + 6 * mm, price_y + price_h - 7 * mm,
         "PRICING", font="Helvetica-Bold", size=8, color=SAND)
    text(c, M + 6 * mm, price_y + price_h - 14 * mm,
         "₹30 / child / month",
         font="Helvetica-Bold", size=16, color=white)
    text(c, M + 6 * mm, price_y + price_h - 20 * mm,
         "₹300 / child / year  (≈ 16% saving)",
         font="Helvetica", size=10, color=SAND)
    text(c, M + 6 * mm, price_y + price_h - 25.5 * mm,
         "Live quote from your active student count. No setup fee. No lock-in.",
         font="Helvetica-Oblique", size=8, color=SAND)

    # Right half — why-us bullets
    rx = M + (W - 2 * M) / 2 + 4 * mm
    text(c, rx, price_y + price_h - 7 * mm,
         "WHY SCMS", font="Helvetica-Bold", size=8, color=SAND)
    reasons = [
        "FREE-first messaging (Meta WhatsApp Cloud, Telegram, SMTP)",
        "Strict per-tenant DB isolation — clean GDPR boundary",
        "Production hardened: 283 pytest cases, JWT brute-force throttle",
        "Idempotent seeds; 1-command Docker deploy with seeded demo",
    ]
    ry = price_y + price_h - 12 * mm
    for r in reasons:
        # bullet
        c.setFillColor(ACCENT)
        c.circle(rx + 1 * mm, ry + 1.5 * mm, 0.8 * mm, fill=1, stroke=0)
        text(c, rx + 4 * mm, ry, r, font="Helvetica", size=8.5, color=white)
        ry -= 4.5 * mm

    # ────────────────────── FOOTER / CTA ──────────────────────
    foot_y = M
    # Divider line
    c.setStrokeColor(SAND); c.setLineWidth(0.5)
    c.line(M, foot_y + 16 * mm, W - M, foot_y + 16 * mm)

    text(c, M, foot_y + 11 * mm,
         "Try it in 90 seconds",
         font="Helvetica-Bold", size=11, color=PRIMARY)
    text(c, M, foot_y + 7 * mm,
         "git clone <your-repo> scms  &&  cd scms  &&  docker compose up --build",
         font="Courier", size=8.5, color=INK)
    text(c, M, foot_y + 3 * mm,
         "Seeded with the DEMO school (Sunrise Public School, code DEMO) — 144 students, 3 teachers, 1 accounts, 8 parents, ready to click around.",
         font="Helvetica-Oblique", size=7.5, color=INK_SOFT)

    # Right-side contact
    text_right(c, W - M, foot_y + 11 * mm,
               "hello@yourdomain.com", font="Helvetica-Bold", size=10, color=ACCENT)
    text_right(c, W - M, foot_y + 7 * mm,
               "+91 90000 00000", font="Helvetica", size=9, color=INK)
    text_right(c, W - M, foot_y + 3 * mm,
               "github.com/your-org/scms", font="Helvetica-Oblique", size=8, color=INK_SOFT)

    c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
