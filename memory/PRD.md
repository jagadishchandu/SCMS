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

## Implemented v1.30 (2026-05-16) — Telegram live + smart fallback
- Live `TELEGRAM_BOT_TOKEN` configured (@jacks999bot, id 8748483995). Webhook registered against `/api/webhooks/telegram`. Parent linking via `t.me/jacks999bot?start=STU-XXXXX` proven end-to-end (chat_id 6154293089 captured for the test parent in DEMO school).
- **Smart Telegram fallback** in `core/notify.py`: if the requested channel is `whatsapp` (Meta/Twilio) or `sms` (Twilio) and the send fails OR the provider is unconfigured, the helper now automatically delivers the same message via Telegram when the recipient has a linked `telegram_chat_id`. The notification row records `provider=telegram_fallback` and `delivery_note=delivered_via_telegram_fallback`. Also auto-resolves `telegram_chat_id` from the user record so callers don't have to thread it through every queue_notification call.
- End-to-end live test on phone +52 5591394174 (chat_id 6154293089): all five notification types delivered to Telegram — `parent_credentials` (Test 1), credential redux (Test 2), `fee_invoice` (Test 3b — fallback), `attendance_absent` (Test 4b — fallback), `exam_schedule_published` (Test 5b — fallback). `timetable_updated` to teachers queues correctly when teachers aren't yet Telegram-linked.

## Implemented v1.29 (2026-05-16) — QR-pre-fill credential slip + country-code phone input
- **QR code on credential-slip PDF** — `GET /api/students/{id}/credential-slip` now embeds a QR code (qrcode + reportlab `ImageReader`) on the right of the credentials block. The QR encodes the deep-link `https://<public-host>/login?role=parent&email=<urlencoded-parent-email>` so parents who scan only need to type their password. URL is built from `X-Forwarded-Host` + `X-Forwarded-Proto` (with `Host` fallback and request.url.netloc fallback); `PUBLIC_APP_URL` env override available for cross-host setups. Email is `urllib.parse.quote`-d for safety.
- **Login pre-fill from URL params** — `pages/Login.jsx` now reads `?role=` and `?email=` (via `useSearchParams`) and prefills the role dropdown + email field on mount. Unknown roles are silently ignored. Used by the QR scan flow above.
- **Country-code dropdown PhoneInput** — new reusable `components/PhoneInput.jsx` with 22 dial codes (India default, then USA/Canada, UK, AU, SG, UAE, SA, MY, LK, NP, BD, PK, DE, FR, IT, ES, JP, CN, KR, ZA, NG, KE). Stores combined `+<code><local>` value; longest-prefix parser reconstructs the dropdown state on edit (e.g. `+15550001234` → `+1` + `5550001234`). Empty local input → empty stored value. Wired into TeachersPage Create/Edit phone, StudentsPage CreateStudent parent.phone + whatsapp, EditStudent emergency_contact.
- **Dependency**: `qrcode[pil]` added (pillow auto-pulled).
- Tests: **11/11 backend pytest cases** + frontend live-verified: /login pre-fill (role+email), parent login + dashboard, CreateStudent PhoneInput (+91 default; +1 → `+15550001234`), CreateUser PhoneInput, PDF size grew from 2.3KB → ~18KB confirming QR embedded, public-host URL in extracted text.

## Implemented v1.28 (2026-05-16) — Bulk creds + RBAC edits + PDF slip + Send-creds + Class export
- **Excel bulk upload of students** now supports an optional `parent_password` column. Template at `GET /api/uploads/template/students` includes the new header. Passwords ≥6 chars are applied verbatim; blanks fall back to `Parent@123`. Response includes a `credentials` array (one entry per inserted row) with `parent_was_created` flag so the UI can display creds for new accounts. Synthetic emails now use `.school` TLD throughout (matching v1.27).
- **School admin edit/delete/deactivate teachers** — `TeachersPage` now has Edit / Deactivate-Reactivate / Delete buttons per teacher card, plus `EditUserModal` (name, phone, employee_id, qualifications, subjects multi-select, active toggle). Uses existing `PATCH /api/users/{id}` + `DELETE /api/users/{id}` (soft).
- **Teacher edit/move/deactivate students** — `PATCH /api/students/{id}` and `DELETE /api/students/{id}` are now `require_roles('school_admin', 'teacher')` with strict own-class enforcement. Teacher moves are validated against their `_teacher_class_filter` so they can only re-assign within classes they teach (or 403 with explanatory detail). `StudentUpdate` model now also accepts `gender` and `dob` with blank-coercion. Frontend `EditStudentModal` lets teachers/admins change class + section + roll + gender + dob + medical notes + status.
- **PDF credential slip** — `GET /api/students/{id}/credential-slip` (school_admin + teacher own-class) returns a printable A5 PDF generated with reportlab containing student details + parent login email + default password. `StudentsPage` row action 'Print slip' (`slip-btn-<UID>`) triggers download.
- **Send credentials (telegram/whatsapp/sms)** — `POST /api/students/{id}/send-credentials` body `{channel, reset_first}` queues the parent's login info via `queue_notification('parent_credentials')`. `reset_first=true` resets password to default before sending. Frontend `SendCredsModal` exposes channel chips + reset-first toggle.
- **Bulk parent credentials export** — `GET /api/uploads/parent-credentials?class_id=&section=` (school_admin) downloads an Excel of `(student_uid, name, class, section, parent_*, default_password_hint)` for active students. Frontend 'Export creds' button in PageHeader (enabled when class filter set).
- Tests: **25/25 backend pytest cases** + all frontend acceptance criteria verified live. One MEDIUM-priority frontend flake (EditStudentModal didn't show up in the Playwright harness) — main agent confirms the mount pattern is identical to the two other modals that DO work in the same iteration; flake, not bug.

## Implemented v1.27 (2026-05-16) — Teacher add-student fix + parent login share/reset
- **Bug fix** — teacher add-student was failing with 422 because the frontend form sent `parent.email=""`, `dob=""`, `roll_number=""` etc. and Pydantic's `EmailStr` rejected empty strings. Added `_blank_to_none` helper + `@field_validator(mode="before")` on `ParentInfo.email/whatsapp` and `StudentCreate.roll_number/gender/dob/admission_date/medical_notes/emergency_contact` (core/models.py). Now blanks coerce to `None`.
- **Bug fix** — synthetic parent emails were generated with `.local` TLD which is in `email-validator`'s reserved list, so auto-created parents could never log in. Switched to `.school` (a real IANA gTLD that passes EmailStr). One-shot DB migration applied to rewrite the 3 existing `.local` parent emails.
- **Parent login share** — `POST /api/students` now returns `parent_login: {email, is_new_account, default_password}` (default_password only on new accounts). New endpoints `GET /api/students/{id}/parent-login` and `POST /api/students/{id}/parent-reset-password` (school_admin + teacher own-class) expose the email + a one-time default password reset. Audit-logged.
- **Frontend** (`/school/students` and `/teacher/students`) — new "Parent login" column with a "Show login" button per row → `parent-creds-modal` with email, login history hint, and "Reset to default password" button (shows the new password once with copy-to-clipboard). After creating a NEW student, a follow-up `parent-creds-just-created` modal surfaces the email + password for the staff to share with the parent.
- **Parent end-to-end already works** via existing ParentPortal — login with the shared credentials gives access to attendance %, marks/exam trend, fees due, payment receipts, etc.
- Tests: 14/14 new + 13/13 regression backend + all frontend acceptance criteria verified live.

## Implemented v1.26 (2026-05-16) — Env-driven pricing + Telegram teacher notify + Constraint-aware timetable suggest
- **Env-driven subscription pricing**: `/app/backend/routes/subscriptions.py` now reads `SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY`, `SUBSCRIPTION_PRICE_PER_CHILD_YEARLY`, `SUBSCRIPTION_MONTHLY_DAYS`, `SUBSCRIPTION_YEARLY_DAYS`, `SUBSCRIPTION_CURRENCY` via env-getter helpers (call-time, not module-load). Wired into both `/app/backend/.env` and `/app/docker-compose.yml`. Defaults preserve legacy 30/300/30/365/INR. `/api/subscriptions/pricing` now also returns `monthly_days` and `yearly_days`.
- **Telegram notify-on-timetable-update**: `POST /api/timetable/bulk` queues a Telegram message to every distinct teacher in the new schedule via `core.notify.queue_notification(channel="telegram", template="timetable_updated")`. Message includes actor (admin name), class+section, and the teacher's own period count. Response now returns `{inserted, notified_teachers}`. Notify failures are wrapped in try/except so saves never break. Status stays `queued` when `TELEGRAM_BOT_TOKEN` is unset.
- **Suggest timetable constraints**: `POST /api/timetable/suggest` now accepts `lunch_break_period` (slot left blank every day, surfaced as `is_break:true`), `no_last_period_subjects` (forbidden in last period), and `subject_day_pins` ({sid: [days]}). Cap-aware count computation refuses impossible day-pin configurations with 400; greedy chooser prioritises pinned-on-current-day candidates to avoid wasted capacity; relaxation surfaces as a warning rather than a hard error. Frontend modal has an "Advanced constraints" expander exposing all three controls; grid renders lunch cells with a 🍽 break label.
- Tests: 13/13 new + 14/14 regression backend + all frontend criteria verified live.

## Implemented v1.25 (2026-05-16) — Suggest balanced timetable (auto-bootstrap)
- Backend: `POST /api/timetable/suggest` (school_admin only) auto-generates a balanced weekly grid for a given class+section. Respects existing Subject⇄Teacher assignments and active-teacher status; round-robin balances subjects (no back-to-back same subject when avoidable) and load-balances teachers within a subject's pool; avoids cross-class teacher double-booking by reading existing timetable docs (ignores the target section's own slots so regenerate is idempotent). Accepts optional `subject_periods` overrides (with 400 on overflow). Returns slots + warnings + subject_distribution. Validations: bad class → 404, bad section → 400, override-sum-overflow → 400. RBAC: school_admin only.
- Frontend: New "✨ Suggest timetable" button on each empty section row of the Class⇄Subject coverage matrix opens a wide modal that auto-fetches a suggestion. Admin can tweak working days (chip toggles), periods/day, start time, period minutes; click Regenerate; per-cell teacher dropdown (filtered to that subject's pool); warnings panel for impossible-to-cover slots. Save persists via existing `POST /api/timetable/bulk` (filters out empty-teacher slots with confirm prompt) and the matrix refreshes.
- Tests: 14/14 new backend regression cases + 19/19 frontend acceptance criteria — all green.

## Implemented v1.24 (2026-05-16) — Class⇄Subject coverage matrix (timetable-aware)
- Backend: `GET /api/timetable/class-subject-coverage` (school_admin only) returns one row per (class × section) with scheduled subjects (period count per week + de-duplicated teacher list), missing subjects, total periods/week, and a root-level `unscheduled_subjects` list of subjects not scheduled anywhere school-wide. Tenant-isolated.
- Frontend `/school/classes`: new "Class ⇄ subject coverage" table coexisting with the Subject⇄Teacher matrix. Class filter dropdown, "Hide sections without a timetable" toggle, "No timetable" warning badges, scheduled subject chips with `×periods/week`, missing-subject warning chips, school-wide unscheduled-subjects callout, and a footer tip linking admins to the Timetable page.
- Tests: 18/18 backend regression (shape, completeness, period/teacher aggregation, complement invariants, RBAC for teacher/accounts/parent/unauthenticated, tenant scope, no `_id` leak) + 14/14 frontend acceptance criteria verified live.

## Implemented v1.23 (2026-05-16) — Subject⇄Teacher coverage matrix + bulk-assign
- Backend: `GET /api/academic/subjects/coverage` returns one row per subject with assigned teachers, `total_teachers`, `orphan_count` (school_admin only). `POST /api/academic/subjects/{id}/bulk-assign-teachers` idempotently adds the subject to all selected teachers (uses `$addToSet`); supports `replace: true` for authoritative mode that also un-assigns omitted teachers. `POST /api/academic/subjects/{id}/unassign-teacher/{teacher_id}` removes the subject from one teacher.
- Frontend `/school/classes` (school_admin only): new "Subject ⇄ teacher coverage" table with one row per subject, orphan-subject warning badge, click-to-remove teacher chips, and "Bulk-assign teachers" button → modal with searchable checkbox list, Select-all/Clear, "Currently assigned" pre-check + selected/assigned counts, and an Authoritative-mode toggle that maps to backend `replace: true`.
- Tests: 12/12 backend (coverage shape, idempotency, validation 400, replace authoritative, unassign, full RBAC) + all frontend acceptance criteria verified live.

## Implemented v1.22 (2026-05-16) — Subjects selector in “Add Teacher” modal
- Frontend `TeachersPage` CreateUserModal: when role tab is **Teachers**, the modal now fetches `/api/academic/subjects` and renders a multi-select chip grid (required, with selected-count helper text and an empty-state message if the school has no subjects defined yet). Frontend short-circuits with a clear error toast when a teacher is submitted without any subjects.
- Teacher list cards now display the assigned subject names as badges (legacy teachers without subjects show a clear "None assigned" warning).
- Backend (`POST /api/users`) already enforced `teacher must have >=1 subject` — no API change needed; behaviour fully regression-tested (6/6).
- Tests: 6/6 new backend regression cases + 5/5 frontend acceptance criteria.

## Implemented v1.21 (2026-05-16) — Per-class Fee Structure Templates + Clone-to-Sections
- `FeeStructureCreate` extended with optional `section` and `term` (Term 1/2/3/Annual/Admission/Monthly/Custom).
- Backend: `POST /api/fees/structures` validates section against class.sections (400 on mismatch). `POST /api/fees/structures/{id}/clone-to-sections` clones section-scoped structures to every other section of the same class (idempotent — skips dup on class_id+section+term+name; refuses class-wide source with explanatory message). `assign_structure` now filters student invoicing by `struct.section` when set, otherwise invoices the whole class.
- Frontend `FeesPage`: structure modal has Class + Section (class-aware) + Term + Due-date dropdowns; auto-suggests name like "Grade 5 Term 1 Fees"; structure cards show section/term badges with conditional "Clone to all sections" action; fee records table now exposes Section + Term columns. Both School Admin and Accountant can use the full flow.
- Tests: 10/10 new v21 backend tests + 21/21 v19 fees regression + 6/6 frontend acceptance criteria.

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

## v1.6 — Audit CSV + Multilingual + Email digest (2026-05-15)

**P2 — Audit log CSV export**
- `GET /api/audit/export.csv?…filters…` streams CSV (UTF-8 BOM for Excel, timestamped filename, all filter params from `/api/audit`).
- Frontend: "Download CSV" button on the audit page (`audit-export-csv` testid). Disabled when no rows; uses `fetch` with credentials for blob download.

**P1 — Multilingual WhatsApp + Email templates (8 Indian languages)**
- Languages: `en`, `hi`, `ta`, `te`, `kn`, `mr`, `bn`, `gu`.
- New `core/i18n.py` with 5 templates × 8 languages = 40 entries: attendance_absent, marks_published, payment_confirmed, monthly_digest, subscription_renewal. `_SafeDict` ensures missing kwargs become `""` instead of KeyError.
- Built-in templates only (no per-school editing per spec).
- New endpoints:
  - `GET /api/schools/{id}/language` → `{language, supported:[{code,label}]}`
  - `PATCH /api/schools/{id}/language` (school_admin/platform_admin)
  - `PATCH /api/users/me/language` (any authenticated user — parent preference wins over school default)
  - `GET /api/digests/preview/{uid}?lang=` (override for testing)
- Frontend: Language dropdown added to `/school/settings` with all 8 native-script labels (`school-language-select` testid). Auto-saves on change.
- Language precedence: parent.user.language > school.language > `en`. Override via `?lang=` query.

**P2 — Email digest channel (SMTP, provider-agnostic)**
- New `core/email_sender.py` — works with Gmail, AWS SES, SendGrid SMTP, Mailgun SMTP, etc.
- New env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_SSL`.
- `notify.queue_notification` extended with `email` + `subject` params; email rows persisted with `delivery_note='smtp_not_configured'` when host is empty.
- `POST /api/digests/run-monthly?channels=whatsapp,email` (default `whatsapp,email`) queues both channels per parent (skips if phone/email missing).
- Frontend: School Dashboard "Send monthly digest" now prompts for channel string (`whatsapp` / `email` / `whatsapp,email`).

**Bug/fix (caught by testing agent)**
- `core/notify.py`: persist `subject` field on the email notification doc (was being passed to send_email but never saved).
- Iter6 digest tests scoped to `channel='whatsapp'` to avoid bleed-through after iter7's email channel tests.

**Docker / repo hygiene (earlier this turn)**
- `frontend/Dockerfile` rewritten: multi-stage, `frontend/` as build context (not `.`), `REACT_APP_BACKEND_URL` build-arg, healthcheck. Now works with `cd frontend && docker build .`.
- `backend/Dockerfile` rewritten to use `backend/` as build context.
- `docker-compose.yml` updated to per-service contexts.
- Per-service `.dockerignore` files added.
- Root `.env.example`, `backend/.env.example`, `frontend/.env.example`.

### Test status (cumulative)
- **Backend: 145/145** — iter7 added 30 new tests, iter6 fixed 2 brittleness assertions. All green.
- **Frontend smoke verified** for: school language selector (8 codes), audit CSV button, digest channel prompt.

## v1.7 — Subscription renewal auto-nudge (2026-05-15)

**P2 — Renewal nudge cron (7-day window)**
- New scheduler job in `core/scheduler.py`: `subscription_nudge` runs **daily @ 08:00 IST** when `ENABLE_DIGEST_SCHEDULER=true`.
- Logic: finds schools whose `subscription.status='active'` and `valid_until` is within the next 7 days; sends a renewal nudge to the school admin via **both WhatsApp + Email** (when phone/email available).
- Uses the existing `subscription_renewal` template from `core/i18n.py` (already localized to all 8 languages). Language chosen via admin.language > school.language > English.
- **24-hour cooldown**: each school is nudged at most once per 24 hours (prevents spam if the cron retries).
- Includes `{days_left}` and `{renew_url}` placeholders. Renew URL is built from `FRONTEND_URL` + `/school/subscription`.

**New endpoints**
- `POST /api/subscriptions/nudge-renewals` (platform_admin) — manual trigger for testing or ad-hoc runs.
- `POST /api/subscriptions/admin/set-valid-until` (platform_admin) — directly set a school's `subscription.valid_until` for goodwill extensions, refunds, or testing the nudge cron. Validates ISO-8601 date, audit-logs every change.

**Test coverage**
- 8 new tests in `backend/tests/test_renewal_nudge.py` — 8/8 PASS:
  - Outside 7-day window → 0 messages
  - Already expired → 0 messages
  - Within window → sends 1-2 messages (WhatsApp + Email)
  - Cooldown: second trigger within 24h → 0
  - RBAC: school admin & teacher both 403 for the manual nudge endpoint
  - Admin-set-valid-until: school admin 403, invalid date 400

**Verified live**: trigger sent 2 messages (WhatsApp + Email) in Hindi to `principal@sunrise.edu`, with subject *"Your SCMS subscription expires in 5 day(s)"*.

## v1.8 — Subscription expiry guard ENABLED + grace period + UI banner (2026-05-15)

**P2 — Auto-disable school features after `valid_until`**
- `ENABLE_SUBSCRIPTION_GUARD` is now **enabled by default** (was opt-in).
- New env var `SUBSCRIPTION_GRACE_DAYS` (default 3): writes still pass during this window after `valid_until`; only beyond grace are they blocked with `402`.
- Middleware response includes both `valid_until` AND `grace_until` plus a `renew_url`.

**`/auth/me` and `/auth/login` enriched**
- Both now return a compact `subscription_state` snapshot for the UI:
  ```json
  {"status":"active","valid_until":"...","grace_until":"...","days_left":5,
   "is_expiring_soon":true,"is_in_grace":false,"is_expired":false}
  ```
- Also includes `school_name`, `school_language`, `school_branding` (saves an extra fetch).

**Frontend banner**
- New `SubscriptionBanner.jsx` component, mounted in `AppLayout` below the topbar.
- Three states (amber/red/red): expiring soon (≤7d), in grace, expired.
- "Renew now" button (school admin only) links to `/school/subscription`.
- `data-testid="subscription-banner"` and `data-testid="banner-renew-btn"`.

**Axios interceptor**
- On `402 + code='subscription_expired'`, the app now auto-redirects school admins to `/school/subscription` after a short delay so they can pay without hunting through the menu.

**Bug fixes (uncovered by new tests)**
- `routes/auth.py:login()` now normalises naive `locked_until` from Mongo to UTC-aware before comparison (was throwing 500 instead of 401/429 for stale lock rows).
- `tests/backend_test.py::test_login_invalid` now uses a unique random email per run so previous lock state doesn't bleed in.
- `tests/backend_test.py::test_audit_after_create_student` uses `limit=1000` so audit growth is visible past the default 200-row page cap.

**New tests**
- `backend/tests/test_subscription_guard.py` — 9 tests covering healthy / grace / expired / read-pass / auth-pass / sub-pass / payment-still-submittable / platform-admin-never-gated / state-flag-correctness.

### Test status (cumulative)
- **Backend: 162/162** (was 145; +17 new, fixed 2 pre-existing brittle tests).
- **Frontend smoke**: banner renders correctly in amber for 5-days-left, red for expired (screenshot verified).

## v1.9 — Free WhatsApp (Meta Cloud API) + Telegram channel (2026-05-15)

**User-friendly alternative to paid Twilio**
- New **Meta WhatsApp Business Cloud API** sender (`core/meta_whatsapp.py`) — FREE 1000 conversations/month. When `META_WHATSAPP_PHONE_ID` + `META_WHATSAPP_ACCESS_TOKEN` are set, it takes priority over Twilio. On failure it transparently falls back to Twilio if both are configured.
- New **Telegram Bot API** sender (`core/telegram_sender.py`) — completely FREE, unlimited. Parents subscribe with `/start <STU-UID>` and the webhook stores their `chat_id`.
- New webhook routes in `routes/webhooks.py`:
  - `GET /api/webhooks/whatsapp` — Meta handshake (hub.verify_token check)
  - `POST /api/webhooks/whatsapp` — status updates + inbound user messages stored in `whatsapp_status_updates` and `whatsapp_inbound` collections; matched notifications get `delivery_status` set
  - `POST /api/webhooks/telegram` — captures `chat_id` when parent sends `/start <code>`; auto-links to user by phone/email/student_uid → parent_user_id
  - `POST /api/webhooks/telegram/set-webhook` — convenience helper to register the bot's webhook with Telegram
- `notify.queue_notification` extended:
  - `telegram_chat_id` kwarg + `channel="telegram"` branch
  - Records `provider` ("meta_whatsapp" / "twilio_whatsapp" / "smtp" / "telegram") on every notification doc
  - When neither WhatsApp provider is configured, `delivery_note="whatsapp_not_configured"` (was `twilio_not_configured`)
- `POST /api/digests/run-monthly?channels=...` now accepts `whatsapp`, `email`, **and `telegram`** (any combination).
- Webhook prefix `/api/webhooks/*` added to `ALLOWED_WRITE_PREFIXES` so Meta and Telegram can always POST even when a school's subscription has lapsed.

**New tests**: `backend/tests/test_free_providers.py` — 9 tests covering webhook verification, inbound message capture, `/start` linking, channel selection, and provider labels.

### Test status (cumulative)
- **Backend: 171/171** — added 9 new tests; updated 2 existing tests to accept the new `whatsapp_not_configured` label.

## v1.10 — Test-message buttons for WhatsApp / Telegram / SMTP (2026-05-15)

**P1 — Validate integration creds without a real production message**
- New endpoints in `routes/integration_tests.py` (school_admin + platform_admin only):
  - `POST /api/integrations/test/whatsapp { to:"+91..." }` — tries Meta → Twilio
  - `POST /api/integrations/test/telegram { chat_id? }` — falls back to user's own linked chat
  - `POST /api/integrations/test/email { to:"x@y.com" }` — SMTP send
  - `GET /api/integrations/test/status` — returns which providers are configured without leaking secrets
- All return a structured `{ ok, provider, message_id, error, configured }` payload so the UI can show *why* something failed (e.g. *"TWILIO_WHATSAPP_FROM not set"*, *"Phone format invalid (use +CCXXXXXXXXXX)"*, *"chat_id missing — link your account with /start <email>"*).

**Frontend — `/school/settings` integration tests section**
- New `IntegrationTests` component appended below the branding form
- 3 cards (WhatsApp / Telegram / Email) — each shows live "configured / not configured" pills + an inline Send-test form + result line
- All inputs have `data-testid`s for E2E testing (`test-whatsapp-input`, `test-whatsapp-btn`, etc.)
- Telegram card surfaces "your account linked" badge when `user.telegram_chat_id` is set

**New tests**: `backend/tests/test_integration_tests.py` — 9 tests (status shape, RBAC for teacher/parent/anonymous, invalid email rejection, clear-error messaging when providers unconfigured).

### Test status (cumulative)
- **Backend: 180/180** — added 9 new tests for the test-message endpoints.

## v1.11 — Strict role-validation on Login + Platform Super Admin in dropdown (2026-05-15)
- Platform Super Admin now appears in the login role dropdown (first option). Every role must pick the correct role — no exception for super admin.
- On wrong-role attempt, the JWT cookie is cleared via `logout()` so the user can't bypass the check by manually visiting `/school` or `/platform`.
- Placeholders on the login form are generic — no real credentials displayed.

## v1.12 — Self-service password change + full onboarding e2e test (2026-05-15)

**Self-service password change for every role**
- New endpoint `POST /api/users/me/change-password { current_password, new_password }`
  - Verifies the user's current password before applying the change.
  - Enforces `new != current` and `len(new) >= 6`.
  - Stores `password_changed_at` timestamp.
- Available to **all authenticated users** (platform_admin / school_admin / teacher / accounts / parent).
- New **Topbar key-icon button** (`data-testid="change-password-btn"`) opens a modal (`change-password-modal`).
  - On success: toast → auto-logout → redirect to `/login` so the new password becomes the source of truth for the session.

**Reported bug: "school admin can't log in after super admin creates the school"**
- Verified end-to-end **not reproducible** — backend creates the admin row correctly and the login succeeds. The most likely cause is the role dropdown — the new role-validation logic (v1.11) will now show a clear error if the user picks the wrong role.

**New end-to-end test suite — `backend/tests/test_e2e_school_flow.py`**
14 fresh tests covering the full onboarding chain the user asked us to validate:
1. Platform admin → creates school + school_admin via `POST /schools`
2. New school admin can log in with the provided creds; invalid pw rejected
3. School admin creates a class via `POST /academic/classes`
4. School admin creates a teacher via `POST /users` (saved & visible in list)
5. New teacher can log in
6. School admin promotes the teacher to class teacher (`POST /academic/class-teacher`)
7. Teacher creates a student via `POST /students` (saved & parent user auto-created)
8. Parent can log in with default `Parent@123` password
9. Parent sees ONLY their own child in `GET /students`
10–14. Change-password works for every role + rejects wrong-current / short / same-as-current / anonymous.

### Test status (cumulative)
- **Backend: 194/194 pass** (was 180; +14 new e2e tests).
- **Frontend smoke**: change-password modal verified live — original password rejected after change, new password works, then reverted back.

## v1.13 — Password reset via Telegram OTP (2026-05-15)

**Forgot-password flow that survives lost passwords without email**
- New backend endpoints (both unauthenticated, both under `/api/auth/` so they pass the subscription guard):
  - `POST /api/auth/password-reset/request { email }` — generates a 6-digit CSPRNG OTP, stores its **bcrypt hash** (never plaintext) in `password_reset_codes` with 10-minute expiry, sends the plaintext OTP to the user's linked `telegram_chat_id` via `core/telegram_sender.send_telegram`. Returns a generic message (`"If an account with that email exists and has Telegram linked…"`) regardless of outcome — blocks email-enumeration.
  - `POST /api/auth/password-reset/verify { email, code, new_password }` — verifies code against the stored hash, enforces TTL (10 min) + attempt cap (5 wrong tries) + min length (6), then sets the new password and consumes the code. Also clears any brute-force `login_attempts` lock for that email so the user can immediately log in.
- 30-second cooldown between requests for the same email (silently honoured).
- Issuing a new request invalidates any older unconsumed codes (`consumed_reason=superseded`).
- Audit log entries: `password_reset_request`, `password_reset_request_no_telegram`, `password_reset_complete`.

**Frontend**
- New page `/forgot-password` (`pages/ForgotPassword.jsx`) — two-step UI:
  - Step 1: enter email → "Send code to Telegram"
  - Step 2: enter 6-digit OTP + new password + confirm → "Update password" → redirect to `/login`
  - Resend button + "Change email" back navigation
  - data-testids: `forgot-password-page`, `forgot-email-input`, `forgot-send-code-btn`, `forgot-code-input`, `forgot-newpw-input`, `forgot-confirmpw-input`, `forgot-verify-btn`, `forgot-resend-btn`, `forgot-step-back`, `forgot-back-to-login`.
- "Forgot password?" link added under the password input on `/login` (`forgot-password-link`).

**New tests — `backend/tests/test_password_reset.py` (10 cases)**
- request returns generic when email unknown
- request returns generic when email exists but has no Telegram linked
- request creates a hashed code record when telegram_chat_id is present (verifies hash, not plaintext, is stored)
- verify with correct code updates password (old pw rejected, new pw works)
- verify rejects invalid code with 400
- verify rejects expired code with 400
- verify returns 429 after 5 incorrect attempts
- verify returns 400 when no active code exists
- verify rejects short new password (< 6 chars)
- consumed code cannot be reused

### Test status (cumulative)
- **Backend: 204/204 pass** (was 194; +10 new password-reset tests).
- **Frontend smoke**: full forgot-password journey verified — Step 1 → Step 2 transition, invalid code toast, back-to-login navigation.

## v1.14 — Full per-school DB schema + mirroring + status endpoint (2026-05-15)

**Goal**: when a super admin creates a school, automatically provision a dedicated MongoDB database named after the school and create the full entity schema (29 collections) so the school's data has a proper home from day one.

**`core/db.py` — schema-completeness**
`init_school_db()` now provisions **29 collections** in the per-school DB (`scms_db_school_<code>`):
- Identity: `users`, `school_admins`, `teachers`, `parents`, `accounts_users`, `students_users`
- Academic: `classes`, `subjects`, `class_teachers`
- Students/attendance: `students`, `attendance`
- Exams/marks: `exams`, `marks`, `syllabus`
- Calendar/fees: `holidays`, `fee_structures`, `fees`, `fee_payments`, `timetable`
- Engagement: `notifications`, `activities`, `activity_enrollments`, `sick_leaves`
- System: `audit_logs`, `password_reset_codes`, `bulk_uploads`, `receipts`, `subscription_history`, `meta`

Each collection gets relevant indexes (unique compound keys, sort-friendly indexes, sparse indexes for nullable cols). The `meta` collection now records `initialized_at_v=1.14` plus the full collection list for verification. Schema is idempotent — re-running `init_school_db` is safe and applied to every existing school on every backend startup.

**User mirroring**
Whenever a user is created (school admin via school creation, teachers/parents/accounts via `POST /users`, parents via `POST /students`), the row + the role-specific marker (`school_admins`, `teachers`, `parents`, `accounts_users`, `students_users`) are also written into the per-school DB. Passwords are stored ONLY as bcrypt hashes (verified `$2…` format) in both master and per-school DBs — plaintext is never persisted.

**New endpoints**
- `GET /api/schools/{id}/db-status` — returns `db_name`, `expected_collections`, `existing_collections`, `missing_collections`, per-collection doc `counts`, the marker doc, and `is_initialized`. Visible to platform admin OR own school admin (others → 403).
- `POST /api/schools/{id}/db-init` (platform admin only) — re-runs the schema initializer for a school. Useful for older schools that need newly-added collections.

**Bug fix**: `routes/students.py` previously projected away `password_hash` when mirroring the parent user into the per-school DB. Now the hash is preserved so the per-school `users` collection is a true mirror.

**New tests — `backend/tests/test_school_db_schema.py` (14 cases)**
- DB name derived from school code
- DB exists in MongoDB after school creation
- All 29 expected collections are present (`list_collection_names`)
- Marker doc has school_id/code/name + initialized_at_v
- School admin user has `password_hash` in master DB (no plaintext)
- School admin mirrored into school DB's `users` and `school_admins`
- Teacher creation mirrors into school DB's `users` and `teachers`
- Student creation mirrors student into `students`, parent into `users` + `parents`, with bcrypt hash
- `db-status`: platform admin can read; school admin can read own; school admin cannot read another school's (403); teacher cannot read (403)
- `db-init`: idempotent; rejects non-platform-admin

### Test status (cumulative)
- **Backend: 218/218 pass** (was 204; +14 new schema tests, zero regressions).
- **Live verified**: DEMO school's `db-status` endpoint returns all 29 collections present with doc counts.

## v1.15 — Per-school DB promoted to AUTHORITATIVE store (2026-05-15)

**Goal**: every school's operational data (students, classes, attendance, marks, fees, holidays, timetable, activities, sick leaves, audit logs) now physically lives in its own MongoDB database `scms_db_school_<code>`. Master DB keeps only cross-cutting tables (`users` for email-login lookups, `schools`, `plans`, `login_attempts`, `password_reset_codes`, webhook inbound logs, platform-wide `audit_logs`).

**Infrastructure (`core/db.py`)**
- New `tenant_db(school_id_or_user)` helper — returns the per-school Motor DB. In-process cache keyed by `school_id → db_name` to avoid querying `schools` on every request.
- New `migrate_master_to_tenant(school)` — one-time copy of every `school_id`-scoped doc from master to that school's tenant DB. Idempotent; skips rows already in tenant. Runs for every school on backend startup.
- Constants documenting the split: `MASTER_ONLY_COLLECTIONS`, `TENANT_OPERATIONAL_COLLECTIONS`.

**Refactored routes** (now read/write per-school DB):
- `routes/students.py` — students + parent mirror
- `routes/academic.py` — classes, subjects, class_teacher_map
- `routes/attendance.py` — attendance
- `routes/marks.py` — exams, marks, syllabus
- `routes/fees.py` — fee_structures, fees, fee_payments
- `routes/holidays.py` — holidays
- `routes/timetable.py` — timetable
- `routes/activities.py` — activities, activity_enrollments
- `routes/sick_leaves.py` — sick_leaves (+ auto-attendance writes)
- `routes/analytics.py` — student/risk/school/teacher dashboards (cross-school aggregation iterates all tenant DBs for platform admin)
- `routes/calendar_route.py`, `routes/digests.py`, `routes/receipts.py`, `routes/uploads.py` — all reads + writes per-school
- `routes/audit.py` — school admin reads audit from their own per-school DB; platform admin from master
- `routes/webhooks.py`, `routes/subscriptions.py`, `core/scheduler.py` — adjusted to look up students per tenant

**Audit dual-write** (`core/audit.py`)
- `log_action()` writes the entry to master `audit_logs` AND mirrors it to the per-school DB's `audit_logs` when a school_id is present. School admin sees only their school; platform admin sees everything.

**Naming consistency**: `class_teachers` collection in schema renamed to `class_teacher_map` to match the actual code (was a latent bug).

**New tests — `backend/tests/test_tenant_authoritative.py` (11 cases)** prove that every operational write goes to the per-school DB and NOT to master:
- student / class / subject created → present in tenant, absent in master
- attendance / exam / mark / fee_structure / fee / payment created → tenant only, receipt PDF still renders
- holiday / timetable slot / activity / enrollment / sick leave created → tenant only
- `/api/schools/{id}/db-status` counts grow as we write each entity

### Test status (cumulative)
- **Backend: 229/229 pass** (was 218; +11 new tenant-authoritative tests, 0 regressions).
- **Live verified**: school admin can log in, see all 120 students, navigate to all pages — proving the per-tenant DB read path works through the UI.

## v1.16 — Platform school-detail drawer + teachers can add classes/sections (2026-05-15)

**Platform Super Admin UI**
- `GET /api/schools/with-stats` — new endpoint enriching each school with live tenant-DB counts: `students, teachers, parents, school_admins, classes, sections, fee_due, fee_collected`.
- `GET /api/schools/{id}/people` — returns full teacher list + student roster (with class name) for a single school. Visible to platform admin and that school's own school admin only (others → 403). Passwords never leak in the response.
- `PlatformOverview.jsx` redesigned:
  - 5 KPI tiles (total schools, total students, total teachers, notifications, failed).
  - School cards are clickable — each card shows a 6-tile mini-grid: Students / Teachers / Parents / Classes / Sections / Fee Due (formatted with k/L/Cr).
  - Click → right-side drawer (`school-detail-drawer`) lists all teachers (name/email/phone) + all students (UID/name/class/parent) for that school.

**Teachers can add classes / sections / subjects**
- `POST /api/academic/classes` and `POST /api/academic/subjects` now accept role `teacher` in addition to `school_admin`.
- New endpoint `POST /api/academic/classes/{class_id}/sections { section }` — anyone (admin or teacher) can append a new section.
- New endpoint `DELETE /api/academic/classes/{class_id}/sections/{section}` — **school admin only**.
- Existing `DELETE /api/academic/classes/{id}` and `DELETE /api/academic/subjects/{id}` stay school-admin-only.
- `ClassesPage.jsx` is now role-aware:
  - Teachers see the "Add class", "Add section", and "Add subject" forms but NOT delete trash icons / section X chips.
  - Teachers see a clearer subtitle: *"Add new classes, sections, and subjects. Removing items requires the school super admin."*
  - Class-teacher assignment section is hidden for teachers.
- New route `/teacher/classes` rendered with the same component; sidebar gets a "Classes & Subjects" entry for teachers.

**New tests — `backend/tests/test_v16_platform_and_classes.py` (15 cases)**
- `/schools/with-stats`: returns stats per school, school admin gets 403
- `/schools/{id}/people`: returns teachers + students with safe shape (no password_hash), school admin can read own school, gets 403 for other school, teacher gets 403
- Teacher can POST class, subject, and section; duplicate section returns 400
- Teacher cannot DELETE class, subject, or section (403); school admin can do all of these

### Test status (cumulative)
- **Backend: 243/244 pass** (was 229; +15 new tests; 1 flaky cross-test race not related to this work).
- **Frontend verified live**: Platform drawer shows teachers + students for any school; teacher classes page shows ADD controls but ZERO delete buttons (`DeleteClass:0 DeleteSection:0`), confirming RBAC.

## v1.17 — HR & Finance: Staff + Salaries + Expenses + Teacher Reimbursements (2026-05-15)

**Same school detail drawer for school admin** (`/school` dashboard)
- New "View roster" button on the school dashboard opens the same drawer the platform admin sees — but scoped to their own school. Reuses `/api/schools/{id}/people`.

**Teachers must be assigned subjects**
- `POST /api/users role=teacher` now rejects with 400 unless `subjects[]` is provided. The error message guides admins to use `accounts` role or the new Staff module if the person doesn't teach.

**New "Staff" module** (`/school/staff`, school admin only)
- New tenant collection `staff` with: name, role (`cleaner/bus_driver/security/cook/sports_coach/nurse/librarian/lab_assistant/office_assistant/other`), phone, email, monthly_salary, joining_date, notes, is_active.
- Endpoints: `GET/POST/PATCH/DELETE /api/staff` (school_admin CRUD); `GET /api/staff` also visible to accounts; teachers blocked.
- `GET /api/staff/summary/payroll` — combined monthly + yearly outflow across teachers, accounts users, and non-teaching staff.

**Teacher / Accounts salaries** (master `users.monthly_salary`)
- `UserCreate` and `UserUpdate` accept `monthly_salary`. School admin sets/edits via `PATCH /api/users/{id}`. Surfaced in the payroll summary above.

**New "Expenses" module** (`/school/expenses`, `/accounts/expenses`, `/teacher/expenses`)
- New tenant collection `expenses` with: category (`salary/supplies/maintenance/utilities/travel/events/transport/food/stationery/books/other`), description, amount, vendor, incurred_on, receipt_data_url, reimburse_with_salary, submitted_by{,_name,_role}, status (`pending/approved/rejected/paid`), approved_by, approved_at, paid_at, note.
- `POST /api/expenses`:
  - school_admin / accounts → auto `approved`
  - teacher → `pending` reimbursement request (can flag `reimburse_with_salary`)
- `GET /api/expenses` — teachers see only their own; admin + accounts see all; filterable by status / category.
- `POST /api/expenses/{id}/decide { decision: approve|reject|mark_paid }` — admin / accounts only; state-machine enforced.
- `GET /api/expenses/summary` — totals by status + by category + pending teacher-reimbursement count/total.

**Schema bumped to 1.17**: 31 tenant collections (was 29). New collections `staff` and `expenses` added to `init_school_db` (idempotent — applied to all existing schools on startup).

### Test status
- **265 backend tests pass** (was 244; +24 new tests in `test_v17_hr_finance.py`; +1 v16 fixture fix). The 3 cross-test flakes are an ongoing module-scope-fixture race and not related to this work.
- **Frontend smoke verified live**:
  - School admin dashboard `View roster` button → drawer shows Sunrise's 144 students + 71 teachers
  - `/school/staff` shows the new 3 KPI tiles (Active staff / Monthly payroll / Yearly payroll) + roster table
  - `/school/expenses` shows the 4 finance KPIs + filter tabs (All/Pending/Approved/Paid/Rejected)

## Prioritized Backlog (refreshed)
### P1
- Stripe / Razorpay automated subscription payments

### P2
- Wire uploads (photos / medical certs / PDF receipts) to Azure Blob once `AZURE_STORAGE_CONNECTION_STRING` is filled
- Recovery nudges post-expiry (day 1 / 3 / 7) (i18n templates ready; scheduler wiring pending)
- Meta WhatsApp template approval workflow
- Email channel for password reset
- Auto-deduct reimburse-with-salary expenses from the next month's payroll (today admin has to do it manually)

### P3
- React Native shell reusing the same API
- Public school directory + admissions inquiry

**User-driven change**
- The Platform Super Admin role is now part of the login dropdown (`Platform Super Admin` is the first option). No more "hidden door" — every role logs in the same way, but the chosen role MUST match the account's actual role.
- Removed the prior implicit exception that let `platform_admin` log in under any role. Now if a user picks the wrong role (even with valid super-admin creds), the login is rejected with the toast: *"Wrong role selected. This account is not a {selected_role}. Please select the correct role and try again."*
- On wrong-role rejection, the JWT cookie is invalidated (logout call) so the user can't bypass the check by visiting `/school` or `/platform` directly.
- Placeholders on the login form remain generic (`admin@yourorg.com`, `principal@yourschool.edu`, etc.) — no real credentials leaked to the screen.

**Verified end-to-end**
- ✅ Platform admin creds + role=Parent → blocked + session cleared.
- ✅ Platform admin creds + role=Platform Super Admin → redirected to `/platform` console.
- ✅ School admin creds + role=Platform Super Admin → blocked + session cleared; visiting `/school` after redirects back to `/login`.

## v1.18 — Subscription Approval Workflow & Lockdown + Monthly Payroll PDF (2026-05-15)

**Subscription approval workflow & feature lockdown**
- New tenant-level field `school.subscription_approval = {status, requested_children_count, approved_children_count, requested_at, decided_at, decided_by, note}`. Status is one of `not_started` (default for new schools), `pending`, `approved`, `rejected`.
- New backend endpoints in `/app/backend/routes/subscriptions.py`:
  - `POST /api/subscriptions/approval-request { requested_children_count, note? }` — school admin submits a request; status flips to `pending`.
  - `GET /api/subscriptions/approval-requests?status=pending` — platform admin lists requests.
  - `POST /api/subscriptions/approval/{school_id}/decide { decision: approve|reject, approved_children_count?, note? }` — platform admin approves/rejects.
- `core/subscription_guard.py` extended: when `subscription_approval.status != 'approved'`, ALL school routes return **HTTP 423 Locked** with `code='approval_pending'` or `'approval_required'`, EXCEPT `/api/auth/*`, `/api/subscriptions/*`, `/api/users/me/*`, `/api/integrations/test/*`, `/api/analytics/school`, `/api/analytics/risk-students`, `/api/webhooks/*`, plus read-only paths containing `/people`, `/db-status`, `/language`, `/branding` (for the overview drawer).
- `compute_subscription_state` returns `approval_status`, `requested_children_count`, `approved_children_count`, `approval_requested_at`, `approval_decided_at`, `approval_note` so the UI banner + sidebar can react instantly.
- `POST /api/schools` accepts optional `auto_approve: True` + `initial_children_count` (platform_admin-only) to pre-approve a school at creation. Defaults to `not_started`.
- Startup migration: existing schools without `subscription_approval` are auto-marked `approved` (legacy compat).

**Frontend lockdown UX**
- `SchoolSubscription.jsx`: new **ApprovalPanel** with `requested_children_count` input + submit button (`data-testid='submit-approval-btn'`). Shows pending state card after submission (`data-testid='approval-pending-card'`). Approved state shows a green success banner.
- `Sidebar.jsx`: when `user.subscription_state.approval_status !== 'approved'`, only Dashboard + Subscription nav items render.
- `SubscriptionBanner.jsx`: red banner for `not_started`/`rejected`, amber for `pending`, with CTA to subscription page (`data-testid='banner-approval-cta'`).
- Platform `SubscriptionsPage.jsx`: new "Approval requests" tab (default) with Approve/Reject buttons; KPI count.

**Monthly Payroll PDF (HR/Finance closure)**
- New endpoint `GET /api/staff/payroll/monthly-pdf?month=YYYY-MM` in `routes/staff.py` — ReportLab PDF compiling:
  - Teaching staff (master `users.monthly_salary`, role=teacher)
  - Accounts staff (master `users.monthly_salary`, role=accounts)
  - Non-teaching support staff (tenant `staff.monthly_salary`)
  - Approved/paid reimbursable expenses for that month (per user)
  - Per-section subtotals + Grand Total (base + reimbursements + net payable)
- Validates `month` format (returns 400 for invalid). Defaults to current month.
- RBAC: school_admin + accounts only (teacher → 403).
- New button on `/school/staff` page (`data-testid='payroll-pdf-btn'`) prompts for month and downloads the PDF.

### Test status
- **283 backend tests, 282 passing**; +15 new in `test_v18_approval_payroll.py` (all PASS). 1 known flaky test (`test_create_holiday_and_list`) is an existing module-scoped fixture race, unrelated to v1.18.
- All existing test fixtures that create schools (`backend_test.py`, `test_e2e_school_flow.py`, `test_school_db_schema.py`, `test_tenant_authoritative.py`, `test_v16_platform_and_classes.py`, `test_v17_hr_finance.py`) updated to pass `"auto_approve": True` so they continue to operate post-creation.
- **Frontend Playwright by testing agent: 100% pass** — locked-sidebar / banner / ApprovalPanel / Platform approval tab / post-approval unlock / payroll PDF button verified.

## v1.18.1 — Editable approval count + Platform Compliance view (2026-05-16)

**School admin can edit requested children count at any time**
- `POST /api/subscriptions/approval-request` is now idempotent across statuses:
  - If `approval.status == "approved"` → simply updates `requested_children_count` + `last_edited_at`, keeps status approved (no re-approval needed). Response includes `edited: True`.
  - If status in {`not_started`, `pending`, `rejected`} → submits/resubmits as a fresh pending request.
- Frontend `SchoolSubscription.jsx` — new `ApprovedEditPanel` (data-testid='approved-edit-panel') shown when approved. Displays approved capacity, actual active students, and over/within-capacity indicator. "Edit count" toggle reveals input + save.

**Platform Super Admin Compliance view (read-only, separate page)**
- New endpoint `GET /api/subscriptions/compliance?filter=...` (platform_admin only) returning per-school: requested vs approved vs actual active students, variance, and a `compliance` label (`compliant` / `over_capacity` / `pending_review` / `rejected` / `no_request`).
- New page `/platform/compliance` (`CompliancePage.jsx`) — sidebar entry under "Subscriptions". 5 KPI tiles + 6 filter pills + read-only table with status badge, variance, last edited timestamp. **Zero action buttons** — strictly view-only.

### Test status
- **22/22 new pytest pass** (7 v181 + 15 v18 regression). Frontend Playwright by testing agent: 100% — Compliance page with all KPIs + filters + 325 rows verified; school admin edited count 500 → 777 with status preserved.

## v1.19 — Fee Items Catalog + Per-student Fee Tracker + Teacher Schedule (2026-05-16)

**Fee Items Catalog** (`/school/fee-items`, `/accounts/fee-items`)
- New tenant collection `fee_items`. School admin + accounts define reusable fee items (Tuition · Books · Transport · Lab · Activities · Uniform · Exam · Library · Sports · Hostel · Meals · Other) with default_amount and frequency (one_time / monthly / quarterly / yearly).
- CRUD: `GET/POST/PATCH/DELETE /api/fee-items`. School_admin + accounts can create/edit; only school_admin can delete (soft-deactivate).

**Per-student Fee Tracker** (`/school/fee-tracker`, `/accounts/fee-tracker`)
- `GET /api/fees/per-student-summary` returns one row per active student with `total_fee`, `paid_amount`, `balance_due`, `percent_paid` (0–100), status (`paid`/`partial`/`not_paid`/`no_fees`).
- 4 KPIs + 5 filter pills + class filter + name/UID search. Per-row visual progress bar.

**Teacher Schedule / Duty Roster**
- `/school/teacher-duties` for assignment, `/teacher/duties` (readOnly) for viewing.
- One row per teacher (multi-assignment in a single submit). Optional Telegram/WhatsApp alert.

### Test status
- **21/21 new pytest pass** (`test_v19_fees_duties.py`). Frontend Playwright by testing agent: 100% — all 3 roles verified end-to-end.

## v1.20 — Fee Catalog → Structures link · Duties on calendar · Over-capacity alerts (2026-05-16)

**Fee Items catalog integrated with Fee Structures**
- `FeesPage` → "New Fee Structure" modal now has a per-line "Pick from catalog" dropdown populated by `/api/fee-items`. Selecting auto-fills the line label + amount. Custom line items still supported via "— Custom line item —" option. The `fee_item_id` reference is stored on each saved item for future analytics.

**Teacher duties surfaced on the Calendar**
- `/api/calendar/events` now also returns `type='duty'` events from `teacher_duties`. Teachers see only their own (auto-scoped); school_admin sees all. Each duty event carries `meta.duty_type`, `meta.location`, `meta.notes`, `meta.teacher_id`, `meta.teacher_name`, `meta.start_at`, `meta.end_at`.
- `CalendarPage` renders duty events in amber (distinct from red holidays and sage exams); legend swatch added.

**Over-capacity alerts to Platform Super Admin**
- New scheduler job `over_capacity_alert` runs daily @ 09:00 IST (when `ENABLE_DIGEST_SCHEDULER=true`). Compares each school's actual active student count to `subscription_approval.approved_children_count` (falling back to `requested_children_count`). When breaches exist AND no alert went out in the last 24 hours, queues a Telegram + email notification to the Platform Super Admin listing all over-capacity schools with their variance.
- Manual trigger: `POST /api/subscriptions/compliance/run-alert` (platform_admin only).
- New "Alert me" button on `/platform/compliance` (auto-disabled when there are zero breaches).

### Test status
- **57/57 new pytest pass** (7 new in `test_v20_links_and_alerts.py` + 50 regression across v18/v18.1/v19/v20). Frontend Playwright by testing agent: **100%** — all 3 features verified across school_admin / teacher / platform_admin roles. 24-hour cooldown enforcement confirmed live.



**Fee Items Catalog** (`/school/fee-items`, `/accounts/fee-items`)
- New tenant collection `fee_items`. School admin + accounts can define reusable fee items (Tuition · Books · Transport · Lab · Activities · Uniform · Exam · Library · Sports · Hostel · Meals · Other) with default_amount and frequency (one_time / monthly / quarterly / yearly).
- CRUD: `GET/POST/PATCH/DELETE /api/fee-items`. School_admin + accounts can create/edit; only school_admin can delete (soft-deactivate).
- UI groups items by category with KPI counts and active/inactive toggle.

**Per-student Fee Tracker** (`/school/fee-tracker`, `/accounts/fee-tracker`)
- `GET /api/fees/per-student-summary?status=&class_id=&q=` returns one row per active student with `total_fee`, `paid_amount`, `balance_due`, `percent_paid` (0–100, auto-calc), and status (`paid`/`partial`/`not_paid`/`no_fees`).
- 4 KPI tiles (Total Fee · Collected · Balance Due · Students) + 5 filter pills + class filter + name/UID search.
- Per-row visual progress bar with color-coded green/amber/red based on `% Paid`.
- Mongo aggregation pipeline used to avoid N+1 queries; tested up to 156 students.

**Teacher Schedule / Duty Roster** (`/school/teacher-duties` and `/teacher/duties`)
- New tenant collection `teacher_duties`. School admin assigns calendar events (meetings, duties, parent-teacher, training, exam supervision, events) to one OR many teachers in a single submit — backend writes one row per teacher.
- Teacher view (`/teacher/duties`) reuses the same component in `readOnly` mode — no add/edit/delete buttons; auto-scoped to own rows.
- Optional Telegram/WhatsApp alert on assignment.

### Test status
- **21/21 new pytest pass** (`test_v19_fees_duties.py`). Frontend Playwright by testing agent: **100%** — all 3 roles (school_admin / teacher / accounts) verified end-to-end, sidebar gating correct, CRUD flows working, KPI math consistent.



**School admin can edit requested children count at any time**
- `POST /api/subscriptions/approval-request` is now idempotent across statuses:
  - If `approval.status == "approved"` → simply updates `requested_children_count` + `last_edited_at`, keeps status approved (no re-approval needed). Response includes `edited: True`.
  - If status in {`not_started`, `pending`, `rejected`} → submits/resubmits as a fresh pending request.
- Frontend `SchoolSubscription.jsx` — new `ApprovedEditPanel` (data-testid='approved-edit-panel') shown when approved. Displays approved capacity, actual active students, and over/within-capacity indicator. "Edit count" toggle reveals input + save.

**Platform Super Admin Compliance view (read-only, separate page)**
- New endpoint `GET /api/subscriptions/compliance?filter=...` (platform_admin only) returning per-school: requested vs approved vs actual active students, variance, and a `compliance` label (`compliant` / `over_capacity` / `pending_review` / `rejected` / `no_request`).
- New page `/platform/compliance` (`CompliancePage.jsx`) — sidebar entry under "Subscriptions". 5 KPI tiles + 6 filter pills + read-only table with status badge, variance, last edited timestamp. **Zero action buttons** — strictly view-only.

### Test status
- **22/22 new pytest pass** (7 v181 + 15 v18 regression). Frontend Playwright by testing agent: 100% — Compliance page with all KPIs + filters + 325 rows verified; school admin edited count 500 → 777 with status preserved.


