# SCMS — School Child Monitoring System (PRD)

## Original Problem Statement
Multi-school management platform with strict role-based visibility (Platform Admin, School Admin, Teacher, Class Teacher, Accounts, Parent). Core modules: students/parents, attendance with auto WhatsApp alerts, marks/exams, syllabus, holidays, fees + receipts, teacher timetable, teacher performance (40/30/15/15), student analytics with charts, Excel imports, Docker-ready.

## Architecture
- Frontend: React 18 (CRA), Tailwind, Recharts, Phosphor icons, react-router-dom, axios (withCredentials)
- Backend: FastAPI, Motor (MongoDB), PyJWT, bcrypt, openpyxl, reportlab, twilio
- Auth: JWT in httpOnly cookies + bcrypt + brute-force throttle. require_roles(...) RBAC.
- Tenant isolation: school_id on every collection; non-platform roles strictly scoped to own school.
- Notifications: persisted to `notifications` collection. If Twilio env configured → real WhatsApp send; otherwise stays `queued` with delivery_note='twilio_not_configured'.
- Audit log: every important state change (student create/update/delete/photo) is recorded; visible only to School Admin and Platform Admin.
- Containers: `docker compose up --build` (mongo + backend + frontend).

## Personas
Platform Admin (SaaS operator), School Principal, Teacher / Class Teacher, Accounts staff, Parent.

## Implemented v1.1 (2026-01-15)
**v1.0** — Auth, all 6 roles, schools, students, teachers/staff, classes/subjects, class-teacher assignment, attendance (with auto parent alerts), exams + marks (publish notifies parents), syllabus, holidays, fees + payments with receipts, timetable + my-timetable, teacher performance scoring, notifications log, Excel templates/uploads, student analytics dashboard (donut/line/bar/stacked charts + insights), parent portal with charts, accounts dashboard. Strict RBAC verified.

**v1.1 — this iteration (2026-01-15)**:
- **Twilio WhatsApp integration** with env-var fallback (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM). Empty by default → notifications stay queued (mock log). Real delivery activates once tokens are added.
- **Monthly calendar grid UI** — `/school/calendar`, `/teacher/calendar`, `/parent/calendar` — color-coded holidays + exams, prev/next/today nav, upcoming-60-days list. New `/api/calendar/events` endpoint.
- **PDF receipts** — `/api/receipts/payment/{id}.pdf` and `/api/receipts/student/{uid}/report.pdf` rendered with reportlab. Download buttons added to Parent Portal (per payment), School Fees page, and Student Analytics.
- **Student photo upload** — `POST /api/students/{id}/photo` (base64 stored as data URL, max 2 MB, JPEG/PNG/WebP). Upload UI on Student Analytics dashboard + Parent Portal child card. Permissions: school_admin, teacher (own class), parent (own child).
- **Subscriptions / Plans** — Auto-seeded Starter (free), Growth (₹4,999/mo), Enterprise (₹14,999/mo). Platform Admin can assign plans to schools at `/platform/subscriptions`. Backend endpoints: GET /plans, POST /plans, POST /assign, GET /usage/{school_id}.
- **Audit log surface** — `/platform/audit` and `/school/audit` UI. Backend endpoint `/api/audit`. Student create/update/delete/photo events automatically logged.
- **Mobile-responsive UI** — sidebar collapses to a slide-in drawer on <1024px screens (hamburger toggle in top bar). All pages already use responsive grids (1/2/3/4 cols depending on screen). data-testids: mobile-menu-toggle, mobile-drawer, mobile-drawer-close.
- **Admin credentials updated** — Primary admin is now `jagadishchandu789@gmail.com` / `Manasa@123` (per user request). Legacy `platform@scms.com` / `Platform@123` is preserved for backward compatibility.
- **Demo backfill** — One-time backfill ensures DEMO school has matching `fee_payments` records so the parent's "Payment history" and receipt downloads are immediately usable.

## Test status
- Backend: **53/53 pytest cases** (iter1 32 + iter2 21) — auth, RBAC, CRUD, analytics, audit, subscriptions, Twilio scaffold, PDF receipts, photo upload.
- Frontend smoke: All role logins + new admin + subscriptions + audit + calendar + parent receipt download verified.
- Mobile: verified at 390x844 (mobile drawer opens/closes correctly).

## Prioritized Backlog
### P1
- Email digest (monthly attendance + marks summary auto-sent to parents)
- Real WhatsApp send: requires user to fill TWILIO_* env vars
- Recurring sick-leave tracker + medical certificate upload

### P2
- Subscription auto-billing (Stripe/Razorpay)
- Audit log filters/search UI (currently full table)
- S3 / GridFS for photo storage at scale
- Calendar event creation directly from the grid (click empty cell)

### P3
- Multilingual notification templates
- React Native mobile shell reusing the same API
- Public school directory + admissions inquiry page

## Demo Credentials
See `/app/memory/test_credentials.md`.

## v1.2 — Monthly Parent Digest (2026-01-15)
- **New backend endpoints**
  - `GET /api/digests/preview/{student_uid}` — composed digest preview for a single student (debug aid; parent-scoped automatically).
  - `POST /api/digests/run-monthly` — triggers the previous-calendar-month digest for every active student.
    - `school_admin` runs for their own school.
    - `platform_admin` can pass `?school_id=...` or omit it to run across all active schools.
- **Digest content**: school name, student name + UID, period (e.g. "April 2026"), attendance % + absent/sick counts, marks average for the month, fees outstanding, opt-out line. Composed once per student and queued via the existing `notifications` pipeline (so Twilio gating applies seamlessly).
- **Frontend**: "Send monthly digest" button on the School Admin Dashboard (`data-testid=send-monthly-digest-btn`), guarded by a confirm dialog, with toast summary of sent/queued/failed.
- **Audit**: every run logs an `action='run_monthly_digest'` entry per school with `meta.period` and `meta.students`.
- **Test status**: **63/63 pytest pass** (53 iter1+2 + 10 new TestDigests) + frontend smoke including KPI delta verification.

### Notes from testing agent (non-blocking)
- For schools with thousands of students, the per-student Mongo round-trips in the run-monthly loop can be optimised with an aggregation. Fine for current scale.
- Marks-window uses `entered_at` (not exam date). If teachers backfill marks late, those rows may be missed in the monthly digest. Document with the product owner.
