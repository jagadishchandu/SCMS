# SCMS Test Credentials

Login URL: <https://4d977b08-b8f9-4943-a6f8-176d61d36e7e.preview.emergentagent.com/login>

All accounts are seeded automatically on backend startup (idempotent).

| Role | Email | Password | Notes |
| --- | --- | --- | --- |
| Platform Super Admin (primary) | `jagadishchandu789@gmail.com` | `Manasa@123` | Default admin per user request |
| Platform Super Admin (legacy) | `platform@scms.com` | `Platform@123` | Kept for older bookmarks |
| School Super Admin | `principal@sunrise.edu` | `School@123` | Full access inside `Sunrise Public School` |
| Teacher (Class Teacher of Grade 5 A) | `priya@sunrise.edu` | `Teacher@123` | Restricted to own classes |
| Teacher | `rohit@sunrise.edu` | `Teacher@123` | Subject teacher |
| Teacher | `kavita@sunrise.edu` | `Teacher@123` | Subject teacher |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` | Fees only |
| Parent of STU-00001 (Aarav Sharma) | `parent.stu-00001@sunrise.edu` | `Parent@123` | Sees only own child |
| Parent of STU-00002 | `parent.stu-00002@sunrise.edu` | `Parent@123` | |

## Twilio WhatsApp (Optional)
To enable real WhatsApp delivery, set these in `/app/backend/.env`:
```
TWILIO_ACCOUNT_SID="ACxxxxxxxx..."
TWILIO_AUTH_TOKEN="..."
TWILIO_WHATSAPP_FROM="+14155238886"  # or your registered WA number
```
When unset, notifications stay `queued` in the DB (mock log).

## v1.3 endpoints (new in this iteration)
- `GET /api/analytics/risk-students?limit=5` — predictive risk top-K (school_admin / platform_admin)
- `GET /api/activities`, `POST`, `PATCH /{id}`, `DELETE /{id}` — activities CRUD
- `POST /api/activities/{id}/enroll` `{ student_ids: [...] }` — bulk enroll
- `DELETE /api/activities/{id}/enroll/{student_id}` — un-enroll
- `GET /api/activities/{id}/roster` — students enrolled
- `GET /api/activities/stats/summary` — KPI feed for the Activities page
- New attendance status: `not_in_class` (used by the teacher card flow)
- New scheduler env: `ENABLE_DIGEST_SCHEDULER=true` enables 1st-of-month 09:00 IST cron

## Per-school databases (new)
Each school has its own physical MongoDB database named `scms_db_school_<slug-of-code>` (auto-created on POST /api/schools). Operational reads/writes still flow through the master `scms_db` for simplicity and cross-school analytics, but every per-school DB carries identical indexes + a `meta` marker, ready for future routing to true per-tenant isolation.

## API endpoints (existing, summary)
- `GET /api/calendar/events` — holidays + exams events feed for monthly calendar
- `GET /api/audit` — audit log (school_admin: own school; platform_admin: all)
- `GET /api/subscriptions/plans` — list plans (auto-seeds 3 default plans on first call)
- `POST /api/subscriptions/plans` — create plan (platform_admin)
- `POST /api/subscriptions/assign` — assign plan to school
- `GET /api/subscriptions/usage/{school_id}` — usage stats
- `GET /api/receipts/payment/{payment_id}.pdf` — PDF receipt download
- `GET /api/receipts/student/{student_uid}/report.pdf` — student report PDF
- `POST /api/students/{student_id}/photo` — multipart photo upload (max 2 MB; JPEG/PNG/WebP)

## Seeded demo data (school: Sunrise Public School, code DEMO)
- 2 classes (Grade 5, Grade 6), 5 subjects, 3 teachers, 1 accounts, 1 school admin
- 8 students in Grade 5 Section A (STU-00001 to STU-00008)
- 20 days of attendance, 2 exams + marks, fees with mixed paid/partial/pending, 3 holidays, full timetable
- 3 subscription plans (Starter free, Growth ₹4999/mo, Enterprise ₹14999/mo) auto-seeded
