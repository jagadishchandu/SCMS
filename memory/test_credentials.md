# SCMS Test Credentials

Login URL: <https://4d977b08-b8f9-4943-a6f8-176d61d36e7e.preview.emergentagent.com/login>

All non-admin accounts are seeded automatically on backend startup (idempotent).
The Platform Super Admin is provisioned from Docker env vars (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).

| Role | Email | Password | Notes |
| --- | --- | --- | --- |
| **Platform Super Admin** (the only one) | `jagadishchandu789@gmail.com` | `Manasa@123` | From `ADMIN_EMAIL` / `ADMIN_PASSWORD` env. Legacy `platform@scms.com` is auto-deactivated on startup. |
| School Super Admin (DEMO) | `principal@sunrise.edu` | `School@123` | 1 per school, created automatically when a school is added. |
| Teacher (Class Teacher of Grade 5 A) | `priya@sunrise.edu` | `Teacher@123` | Restricted to own classes |
| Teacher | `rohit@sunrise.edu` | `Teacher@123` | Subject teacher |
| Teacher | `kavita@sunrise.edu` | `Teacher@123` | Subject teacher |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` | Fees only |
| Parent of STU-00001 (Aarav Sharma) | `parent.stu-00001@sunrise.edu` | `Parent@123` | Sees only own child |
| Parent of STU-00002 | `parent.stu-00002@sunrise.edu` | `Parent@123` | |

## Single Super Admin policy
- Only one Platform Super Admin exists; it is provisioned from `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars in `docker-compose.yml`.
- The `POST /api/users` endpoint rejects role `school_admin` and `platform_admin` (both schema- and policy-blocked).
- Frontend `TeachersPage` no longer shows a "School Admins" tab.

## Per-child Subscription Pricing
- **Monthly**: ₹30 per active child per month
- **Yearly**:  ₹300 per active child per year (≈ 16% discount vs monthly)
- Endpoints:
  - `GET /api/subscriptions/pricing` — current rates
  - `GET /api/subscriptions/my` — school admin: school + quote + pending payment
  - `GET /api/subscriptions/quote/{school_id}` — quote for a school
  - `POST /api/subscriptions/payments` — school admin submits a payment (status = `pending_confirmation`)
  - `GET /api/subscriptions/payments?status=…` — list (platform: all, school: own)
  - `POST /api/subscriptions/payments/{id}/confirm` — platform admin approves → school.subscription becomes active
  - `POST /api/subscriptions/payments/{id}/reject` — platform admin rejects
- A school cannot submit a second payment while one is pending.
- Confirming extends the validity window from `valid_until` if currently active, otherwise from now (30 days monthly, 365 days yearly).

## Twilio WhatsApp (Optional)
To enable real WhatsApp delivery, set these in `/app/backend/.env`:
```
TWILIO_ACCOUNT_SID="ACxxxxxxxx..."
TWILIO_AUTH_TOKEN="..."
TWILIO_WHATSAPP_FROM="+14155238886"
```
When unset, notifications stay `queued` in the DB (mock log).

## Per-school databases
Each school has its own physical MongoDB database named `scms_db_school_<slug-of-code>` (auto-created on POST /api/schools). Operational reads/writes still flow through the master `scms_db` for simplicity; per-school DBs carry identical indexes + a `meta` marker for future routing.

## Seeded demo data (school: Sunrise Public School, code DEMO)
- 2 classes (Grade 5, Grade 6), 5 subjects, 3 teachers, 1 accounts, 1 school admin
- 8 students in Grade 5 Section A (STU-00001 to STU-00008)
- 20 days of attendance, 2 exams + marks, fees with mixed paid/partial/pending, 3 holidays, full timetable
- 5 extra-curricular activities + enrollments
