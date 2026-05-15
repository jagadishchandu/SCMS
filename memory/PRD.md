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

## v1.3 — Per-school DB, Risk Flags, Activities, Mobile Attendance Cards (2026-01-15)
- **Per-school database provisioning**: Every school now also has a dedicated MongoDB database `scms_db_school_<code-slug>` with full schema/indexes (students/attendance/marks/exams/fees/activities/etc), seeded with a `meta._marker='school_db'` document. School documents now carry `db_name`. This is foundation infrastructure — operational reads/writes still go through the master DB with `school_id` filtering (verified by tests). Future migration to true per-tenant data isolation can route queries to `get_school_db(school)` without changing the API.
- **Predictive risk flag**: `GET /api/analytics/risk-students?limit=5` scores students using 30-day rolling windows (attendance drop + marks drop + absolute floor penalties). Top 5 displayed on the School Admin Dashboard as a "Students at risk" card with photo, reasons (badges), and a clickable link to the student analytics page. RBAC: school_admin & platform_admin only.
- **Monthly digest scheduler**: `core/scheduler.py` uses APScheduler in-process. Gated by env `ENABLE_DIGEST_SCHEDULER=true` (default false in the preview). When enabled, fires on the 1st of every month at 09:00 IST via cron trigger.
- **Teacher mobile attendance cards** at `/teacher/attendance-cards`: 3-phase flow (pick class/section/date → swipe-style card per student → review/submit). 3 large status buttons: **Present**, **Absent**, **Not in class**. Card flow uses progress bar, prev/skip/finish controls, mobile-first layout (constrained max-width). New attendance status `not_in_class` added to the model.
- **Extra-curricular activities** at `/school/activities`: CRUD activities (categories: sport / music / art / club / other), per-activity coach + schedule, multi-select enrollment from student list, donut chart for category mix, horizontal bar chart for top activities by enrollment, per-activity card showing student count + Enroll/Delete buttons. Backend: `/api/activities` CRUD + `/{id}/enroll` + `/{id}/roster` + `/stats/summary`. Seeded with 5 demo activities (Cricket, Football, Chess Club, Violin, Painting) and 23 enrollments across 8 students.

### Test status (cumulative)
- **78/78 pytest pass** (63 from iter1–3 regression + 15 new iter4 cases)
- Frontend smoke: dashboard risk widget, activities CRUD + modal flow, full teacher att-cards take→done→save flow with notification queueing toast — all green.

### Non-blocking testing-agent suggestions (deferred)
- Narrow `except Exception` in activity enrollment to `DuplicateKeyError`
- Aggregate-based replacement for N+1 counts in `/api/activities/stats/summary`
- Bucketed aggregation refactor for `/api/analytics/risk-students` before scaling beyond ~1000 students per school

## v1.4 — Per-child Subscription & Single Super Admin (2026-05-15)
**Single Super Admin policy**
- Only ONE Platform Super Admin exists. Provisioned from `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars in `docker-compose.yml` (defaults: `jagadishchandu789@gmail.com` / `Manasa@123`).
- `seed_platform_admin()` auto-deactivates any other `platform_admin` rows on startup (single-admin policy enforcement).
- `POST /api/users` rejects role `school_admin` and `platform_admin` (defense-in-depth: schema + policy).
- Frontend `TeachersPage` no longer has a "School Admins" tab — each school keeps the single default school super admin created with the school.

**Per-child subscription billing**
- Pricing: ₹30 per active child per month, ₹300 per active child per year (≈ 16% discount).
- New endpoints in `routes/subscriptions.py`:
  - `GET /pricing` — current rates
  - `GET /my` — school admin: school + current subscription + live quote + pending payment
  - `GET /quote/{school_id}` — quote for any school (platform or own school)
  - `POST /payments` — school admin submits a payment (status=`pending_confirmation`); 2nd request blocked while one is pending
  - `GET /payments?status=…` — list (platform: all, school: own)
  - `POST /payments/{id}/confirm` — platform admin approves → school.subscription becomes active (extends from current `valid_until` if still active)
  - `POST /payments/{id}/reject` — platform admin rejects
- New frontend pages:
  - `/school/subscription` (`SchoolSubscription.jsx`) — quote KPIs + monthly/yearly plan cards + payment modal + history table
  - `/platform/subscriptions` (`SubscriptionsPage.jsx` rewritten) — pending/confirmed/rejected tabs with Confirm/Reject row actions
- Sidebar: added "Subscription" link for `school_admin`; "Branding" link `/school/settings` route now properly registered in App.js (was missing, causing the earlier Playwright timeout).

**Bug fixes**
- `routes/analytics.py` student dashboard: pre-seed attendance counters with `not_in_class` to avoid KeyError when the new attendance status appears in DB.

### Test status (cumulative)
- **Backend: 94/95 pytest pass** (iter5 added 20 new tests covering per-child pricing, payment workflow, single super admin policy — all green). The single iter4 regression (analytics KeyError on `not_in_class`) is fixed in this iteration.
- **Frontend smoke: 4/4** routes verified — `/school/subscription`, `/school/teachers` (no School Admins tab), `/school/settings`, `/platform/subscriptions`.

## Prioritized Backlog (refreshed)
### P1
- Audit log filters/search UI
- Recurring sick-leave tracker + medical certificate upload
- Email digest channel (in addition to WhatsApp)

### P2
- Stripe/Razorpay gateway for automated subscription payment (replace manual confirmation)
- Auto-disable school features when `subscription.valid_until` lapses
- S3 / GridFS for photo storage at scale
- Multilingual notification templates

### P3
- React Native mobile shell reusing the same API
- Public school directory + admissions inquiry page

## v1.5 — Bug fixes + P1 features + P2 expiry guard (2026-05-15)

**Bug fixes (from user report)**
- Teachers can now create students for classes/sections they teach (`POST /students` opened to `teacher` with `_teacher_class_filter` gating; wrong-section returns 403).
- Teachers can now Excel-bulk-upload students (`POST /uploads/students` opened to `teacher`; rows in classes they don't teach are reported in `errors[]` instead of blocking the request).
- Teacher sidebar now has **Bulk Uploads** + **Sick Leaves** links; `/teacher/uploads`, `/teacher/sick-leaves`, `/parent/sick-leaves`, `/school/sick-leaves` routes added.

**P1 — Audit log filters & search UI**
- `GET /api/audit` accepts `actor_role`, `action`, `resource`, `school_id`, `date_from`, `date_to`, `q`, `limit`.
- New `GET /api/audit/facets` returns distinct values for filter dropdowns.
- New audit page UI: 7 filter inputs (search, role, action, resource, from, to, limit) + apply/clear buttons, actor name + email column.

**P1 — Recurring sick-leave tracker with medical certificate upload**
- `POST /api/sick-leaves` — multi-day leave; auto-marks attendance `sick` for weekdays in the span (school admin / teacher (own class) / parent (own child)).
- `POST /api/sick-leaves/{id}/certificate` — base64 stored PDF/image up to 5 MB.
- `GET /api/sick-leaves/recurring?threshold=3&days=90` — aggregation of students with ≥3 leaves in the window, shown as a highlight card on the page.
- New unified `SickLeavesPage` for school admin / teacher / parent with KPIs (count, total days, with-certificate), recurring highlights, filter-by-UID, and inline cert upload.

**P2 — Subscription expiry guard (opt-in)**
- New middleware `core/subscription_guard.py` registered when `ENABLE_SUBSCRIPTION_GUARD=true`.
- Blocks write methods (`POST/PATCH/PUT/DELETE`) for schools whose `subscription.valid_until` has passed.
- Always-allowed prefixes: `/api/auth/`, `/api/subscriptions/` so users can log in and pay.
- Platform admin and schools without an `active` subscription (first-run) pass through unchanged.
- Response: `402 {"detail":"Subscription expired","code":"subscription_expired","valid_until":"...","renew_url":"/school/subscription"}`.

**Misc**
- Azure Blob env vars added as placeholders (`AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_CONTAINER`, `AZURE_STORAGE_ACCOUNT_URL`) — uploads will route to Azure once these are filled.
- Docker compose forwards all new env vars.
- README fully refreshed.

### Test status (cumulative)
- **Backend: 115/115 pytest pass** (iter6 added 22 new tests; iter5 analytics fix verified holding).
- Frontend smoke verified across teacher / school / parent / platform routes.

## Prioritized Backlog (refreshed)
### P1
- Stripe / Razorpay automated subscription payments (replace manual confirmation)
- Email digest channel (parallel to WhatsApp)
- Audit log CSV export from the filter UI

### P2
- Route uploads (photos, medical certs, PDF receipts) to Azure Blob once `AZURE_STORAGE_CONNECTION_STRING` is set
- Multilingual WhatsApp templates (English / Hindi / regional Indian languages)

### P3
- React Native shell reusing the API
- Public school directory + admissions inquiry
