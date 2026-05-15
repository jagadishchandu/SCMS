# SCMS — School Child Monitoring System (PRD)

## Original Problem Statement
Multi-school management platform with strict role-based visibility. Build:
- Platform Super Admin (creates schools & school admins)
- School Super Admin (highest role per school)
- Teacher (restricted to assigned classes; cannot view other staff)
- Class Teacher (assigned per student)
- Accounts (fees only)
- Parent (own child only)
Core modules: students/parents, attendance with auto WhatsApp alerts, marks/exams, syllabus, holidays, fees + receipts, teacher timetable, teacher performance scoring (40/30/15/15), student analytics dashboard with charts, Excel bulk import. Must run locally with Docker.

## Architecture
- Frontend: React 18 (CRA, JS), Tailwind, Recharts, Phosphor icons, react-router-dom, axios with `withCredentials`
- Backend: FastAPI, Motor (MongoDB), PyJWT, bcrypt, openpyxl. All routes under `/api`.
- Auth: JWT in httpOnly cookies (access + refresh). `require_roles(...)` dependency for RBAC.
- Tenant isolation: every collection includes `school_id`; queries scope by user's `school_id` except for `platform_admin`.
- Notifications: persisted to `notifications` collection as `queued` (mocked WhatsApp delivery, ready for Twilio plug-in).
- Containers: `docker compose up --build` (mongo + backend + frontend).

## Personas
- Platform Admin (SaaS operator)
- School Principal / Super Admin
- Teacher / Class Teacher
- Accounts staff
- Parent

## Implemented (v1.0 — 2026-01-15)
- Auth (login, me, logout) with httpOnly cookies + brute-force throttle
- Platform Admin: list/create schools, notification log
- School Admin Dashboard with 8 KPIs, upcoming exams, holidays, fee donut chart
- Students module: list, filter by class/section, search by name/UID, create with inline parent (auto-creates parent user)
- Teachers/Staff module: tabbed list (teachers/accounts/school admins), create staff
- Classes & Subjects setup; Class Teacher assignment
- Attendance: bulk entry by class+section+date with auto upsert, "mark all present", auto parent notifications for absent/sick
- Exams: list, create, publish (queues parent notifications), inline marks entry per subject
- Syllabus: publish per exam+class+subject with version, queues parent notifications
- Holidays: add (auto notify all parents) / delete
- Fees: structure setup, assign to class (creates fee records & invoices), record payments with auto receipt #, status auto-tracked (paid/partial/pending), payment notifications
- Timetable view (school) + My Timetable (teacher)
- Teacher Performance: 40% attendance + 30% marks + 15% compliance + 15% admin review with status badge (Excellent/Good/Needs Attention/Critical Review)
- Notifications log (filtered per role)
- Excel uploads: templates for students/attendance/holidays + upload endpoints + upload_logs
- Student Analytics Dashboard (search by UID): profile, donut attendance, line marks trend, bar subject-vs-class, monthly stacked bar, insights/alerts
- Parent Portal: per-child summary, charts, fee outstanding, insights
- Accounts Dashboard: billed/collected/outstanding, class-wise table, recent payments, unpaid students
- Strict RBAC (verified by tests): teacher can't list other teachers, can't access fees, parent only sees own child
- Demo data seeded: 1 school, 13 users, 2 classes, 5 subjects, 8 students, 20 days attendance, 2 exams + marks, fees, holidays, full timetable
- Earthy/organic design: sage green + terracotta + warm off-white, Outfit headings, Manrope body, Phosphor icons, Recharts charts, hero abstract image on login

## Test status
- Backend: 32/32 pytest cases (100%) — auth, RBAC, all CRUD, analytics, RBAC enforcement
- Frontend smoke: all 5 role logins + parent charts + student analytics deep link rendered

## Prioritized Backlog
### P1 (next)
- Email/PDF receipts and exportable reports
- Real WhatsApp delivery via Twilio Business API (queue worker)
- Student photo upload + parent portal profile picture
- Calendar view UI for holidays + exam dates (monthly grid)

### P2
- Recurring sick-leave tracker + medical certificate upload
- Audit log surface (UI page)
- Subscription/package management on Platform Admin

### P3
- Multilingual notification templates
- Mobile app shell (React Native) re-using API
- Public school directory page

## Key Risks / Notes
- WhatsApp delivery is MOCKED (entries persisted as `queued`). Toggle to real Twilio requires only swapping `core/notify.queue_notification` to call Twilio.
- For the preview environment cookies use samesite=lax (same-origin via ingress). For cross-origin production, switch `samesite="none", secure=True` in `set_auth_cookies`.

## Demo Credentials
See `/app/memory/test_credentials.md`.
