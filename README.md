# SCMS — School Child Monitoring System

A production-ready, multi-tenant SaaS for K–12 schools to run students, attendance, marks, fees, calendars, sick leaves and parent communications from one place. Built with **React + FastAPI + MongoDB**.

> One platform, many schools. One Super Admin per layer (Platform / School), strict role-based access, audit trail, per-child subscription billing, and WhatsApp-first parent alerts.

---

## Highlights

- **6 roles** — Platform Super Admin, School Super Admin, Teacher, Class Teacher, Accounts, Parent.
- **Single Super Admin policy** — exactly one Platform Super Admin (env-driven, set in Docker); exactly one School Super Admin per school (auto-created with the school). No UI to add more.
- **Per-tenant data isolation** — each school gets its own MongoDB database (`scms_db_school_<slug>`) for indexing & future routing; operational reads/writes use `school_id` filtering on the master DB.
- **Per-child subscription billing** — ₹30 per child / month or ₹300 per child / year. School Admin submits a payment; Platform Super Admin confirms it; subscription becomes active until `valid_until`.
- **Subscription expiry guard** (opt-in) — once `ENABLE_SUBSCRIPTION_GUARD=true`, write actions are blocked for schools whose subscription has lapsed. Read flows and the subscription/payments endpoints stay open so they can renew.
- **WhatsApp notifications via Twilio** — absence alerts, marks publish, monthly digest, payment confirmation. Notifications stay `queued` in DB if Twilio is not configured.
- **Monthly parent digest** — `POST /api/digests/run-monthly` or scheduled cron (`ENABLE_DIGEST_SCHEDULER=true`).
- **Sick-leave tracker** — multi-day leaves, optional medical certificate upload (image/PDF), auto-marks attendance as `sick`, and a "recurring sick leaves" widget for school admins.
- **Audit log with filters** — school admin & platform admin can filter by actor role, action, resource, date range and free text.
- **Extra-curricular activities** — CRUD, enrollment, donut & bar charts.
- **Bulk Excel uploads** — students, attendance, holidays. Teachers can also upload student & attendance Excels for **their** classes.
- **PDF receipts** — payment receipt + per-student report.
- **Predictive risk flags** — student-at-risk widget on the school dashboard.
- **Mobile-first** — Parent Portal bottom nav, teacher swipe-card attendance, responsive layout everywhere.
- **Dark mode** + per-school custom branding (logo, primary color, tagline).

---

## Quick start (Docker)

```bash
# 1. clone
git clone <your-repo> scms && cd scms

# 2. copy or create .env (optional — defaults below)
cat > .env <<'EOF'
ADMIN_EMAIL=jagadishchandu789@gmail.com
ADMIN_PASSWORD=Manasa@123
JWT_SECRET=change-me-in-production

# Optional integrations
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=

# Optional Azure Blob storage (for medical certs / photos / receipts)
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER=
AZURE_STORAGE_ACCOUNT_URL=

# Feature flags
ENABLE_DIGEST_SCHEDULER=false
ENABLE_SUBSCRIPTION_GUARD=false
EOF

# 3. up
docker compose up --build
```

- App: <http://localhost:3000>
- API: <http://localhost:8001/api>
- Mongo: `mongodb://localhost:27017`

The Platform Super Admin is **provisioned from `ADMIN_EMAIL` / `ADMIN_PASSWORD`**. Change these in `.env` (or `docker-compose.yml`) before going to prod. Legacy `platform@scms.com` is auto-deactivated on startup to enforce the single-super-admin policy.

---

## Default demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Platform Super Admin | `jagadishchandu789@gmail.com` | `Manasa@123` |
| School Super Admin | `principal@sunrise.edu` | `School@123` |
| Class Teacher (Grade 5 A) | `priya@sunrise.edu` | `Teacher@123` |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` |
| Parent (STU-00001) | `parent.stu-00001@sunrise.edu` | `Parent@123` |

Full list: [`/app/memory/test_credentials.md`](memory/test_credentials.md).

---

## Architecture

```
/app
├── backend/
│   ├── core/                # auth, db (multi-tenant), audit, notify (Twilio), scheduler, subscription_guard
│   ├── routes/              # auth, schools, users, students, attendance, marks, exams, syllabus,
│   │                        # holidays, fees, timetable, notifications, analytics, audit, subscriptions,
│   │                        # receipts, calendar, digests, activities, sick_leaves, uploads
│   ├── tests/backend_test.py
│   └── server.py            # FastAPI app, lifespan seed, CORS, subscription middleware
├── frontend/
│   └── src/
│       ├── components/      # Sidebar, Topbar, Modal, Primitives, MobileBottomNav, ProtectedRoute
│       ├── contexts/        # AuthContext, ThemeContext (dark mode)
│       ├── layouts/         # AppLayout (sidebar + topbar + content)
│       ├── lib/             # api.js (axios with credentials), utils (currency, role labels, dates)
│       └── pages/           # role-scoped pages (platform/, school/, teacher/, accounts/, parent/, shared/)
├── docker-compose.yml
└── README.md
```

---

## Roles & access at a glance

| Capability | Platform | School Admin | Teacher | Accounts | Parent |
| --- | :-: | :-: | :-: | :-: | :-: |
| Create / delete schools | ✅ | — | — | — | — |
| Manage subscription plans / confirm payments | ✅ | — | — | — | — |
| Submit subscription payment | — | ✅ | — | — | — |
| Add students | — | ✅ | ✅ (own classes) | — | — |
| Add teachers / accounts staff | — | ✅ | — | — | — |
| Mark / view attendance | — | ✅ | ✅ (own) | — | own child |
| Enter / publish marks | — | ✅ | ✅ (own) | — | own child |
| Manage fees / payments | — | ✅ | — | ✅ | view |
| Record sick leaves | — | ✅ | ✅ (own) | — | own child |
| Excel bulk upload (students, attendance) | — | ✅ | ✅ (own classes) | — | — |
| Audit log | view (all schools) | view (own) | — | — | — |

---

## Key API endpoints

```http
# Auth
POST   /api/auth/login            # email + password → httpOnly JWT cookie
GET    /api/auth/me               # current user
POST   /api/auth/logout

# Subscriptions (per-child)
GET    /api/subscriptions/pricing             # → { per_child_monthly: 30, per_child_yearly: 300 }
GET    /api/subscriptions/my                  # school admin: school + quote + pending payment
GET    /api/subscriptions/quote/{school_id}   # quote for a school
POST   /api/subscriptions/payments            # school admin submits a payment
GET    /api/subscriptions/payments            # list (platform: all, school: own)
POST   /api/subscriptions/payments/{id}/confirm
POST   /api/subscriptions/payments/{id}/reject

# Students
GET    /api/students                          # role-scoped list
POST   /api/students                          # school admin OR teacher (own class)
POST   /api/students/{id}/photo               # multipart
PATCH  /api/students/{id}
DELETE /api/students/{id}                     # soft delete (status=inactive)

# Sick leaves
POST   /api/sick-leaves                       # school admin / teacher / parent
POST   /api/sick-leaves/{id}/certificate      # upload medical cert (PDF/image, ≤ 5 MB)
GET    /api/sick-leaves?student_uid=STU-…&days=90
GET    /api/sick-leaves/recurring?threshold=3&days=90
DELETE /api/sick-leaves/{id}

# Audit (filters)
GET    /api/audit?actor_role=&action=&resource=&date_from=&date_to=&q=&limit=200
GET    /api/audit/facets                      # distinct filter dropdown values

# Bulk uploads
GET    /api/uploads/template/{kind}           # download an .xlsx template
POST   /api/uploads/students                  # school admin OR teacher (rows validated against their classes)
POST   /api/uploads/attendance                # school admin or teacher
POST   /api/uploads/holidays                  # school admin

# Misc
GET    /api/analytics/risk-students?limit=5
GET    /api/calendar/events
POST   /api/digests/run-monthly
GET    /api/receipts/payment/{id}.pdf
```

---

## Environment variables

Set in `backend/.env` for local dev or in `docker-compose.yml` env block in Docker.

| Variable | Required | Default | Purpose |
| --- | :-: | --- | --- |
| `MONGO_URL` | ✓ | `mongodb://localhost:27017` | Master Mongo connection |
| `DB_NAME` | ✓ | `scms_db` | Master DB name (per-school DBs auto-created) |
| `JWT_SECRET` | ✓ | (insecure default — change!) | JWT signing key |
| `ADMIN_EMAIL` | ✓ | `jagadishchandu789@gmail.com` | The Platform Super Admin login |
| `ADMIN_PASSWORD` | ✓ | `Manasa@123` | Platform Super Admin password |
| `CORS_ORIGINS` | ✓ | `http://localhost:3000` | Comma-separated allowed origins |
| `FRONTEND_URL` | ✓ | `http://localhost:3000` | Used in some templates / emails |
| `TWILIO_ACCOUNT_SID` | ✗ | — | Enables real WhatsApp delivery |
| `TWILIO_AUTH_TOKEN` | ✗ | — | |
| `TWILIO_WHATSAPP_FROM` | ✗ | — | e.g. `whatsapp:+14155238886` |
| `ENABLE_DIGEST_SCHEDULER` | ✗ | `false` | 1st-of-month 09:00 IST cron for parent digests |
| `ENABLE_SUBSCRIPTION_GUARD` | ✗ | `false` | Block writes for schools whose subscription has lapsed |
| `AZURE_STORAGE_CONNECTION_STRING` | ✗ | — | If set, uploads route to Azure Blob (planned) |
| `AZURE_STORAGE_CONTAINER` | ✗ | — | Container name |
| `AZURE_STORAGE_ACCOUNT_URL` | ✗ | — | e.g. `https://<account>.blob.core.windows.net` |

> ⚠️ Never delete the protected variables (`MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL`). They are read directly by the app and supervisor.

---

## Subscription billing flow

```
                       School Admin                       Platform Super Admin
                       ────────────                       ─────────────────────
1. Open /school/subscription
2. See live quote (₹30 × N or ₹300 × N)
3. Click "Pay ₹540" / "Pay ₹5,400"
4. Submit mode + UTR  ──────────────►   /api/subscriptions/payments
                                        status = pending_confirmation

                                                          5. /platform/subscriptions
                                                             sees the pending row
                                                          6. Clicks Confirm
                                                             ─────────────►
                                                             /api/subscriptions/payments/{id}/confirm
                                                             school.subscription.status = active
                                                             valid_until = +30 / +365 days

7. School Admin sees "Active" KPI       ◄────  WhatsApp + UI notification (optional)
```

If `ENABLE_SUBSCRIPTION_GUARD=true` and `valid_until` is in the past, all write endpoints return:

```json
{ "detail": "Subscription expired", "code": "subscription_expired", "renew_url": "/school/subscription" }
```

Auth + subscription endpoints stay open so the school can still log in and renew.

---

## Development

```bash
# backend (hot reload via uvicorn + watchfiles)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# frontend
cd frontend && yarn install && yarn start  # opens http://localhost:3000

# tests
cd backend && pytest -v
```

Linting:

```bash
ruff check backend/
yarn --cwd frontend lint
```

---

## Roadmap

### P1
- Stripe / Razorpay automated subscription payments (replace manual confirmation)
- Email digest channel (in addition to WhatsApp)
- Audit log CSV export from the filter UI

### P2
- Migrate uploads (photos, medical certs, PDF receipts) to Azure Blob once `AZURE_STORAGE_CONNECTION_STRING` is filled
- Multilingual WhatsApp templates (English / Hindi / regional)
- S3 / GridFS storage option for self-hosted setups

### P3
- React Native shell reusing the same API
- Public school directory + admissions inquiry page
- Voice-to-text attendance for teachers

---

## License

Proprietary — © 2026 Emergent Labs. All rights reserved.
