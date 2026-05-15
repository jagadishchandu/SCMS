# SCMS — School Child Monitoring System

A production-ready, multi-tenant SaaS for K-12 schools to run **students, attendance, marks, fees, calendars, sick leaves, and parent communications** from one place. Built with **React + FastAPI + MongoDB**, packaged as **Docker** for one-command deployment.

> One platform, many schools. Strict role-based access. WhatsApp-first parent alerts in **8 Indian languages**. Per-child subscription billing with auto-expiry guard and 7-day renewal nudge.

---

## Table of Contents
1. [Headline Features](#headline-features)
2. [Quick Start (Docker)](#quick-start-docker)
3. [Default Demo Accounts](#default-demo-accounts)
4. [Architecture](#architecture)
5. [Roles & Access Matrix](#roles--access-matrix)
6. [Key API Endpoints](#key-api-endpoints)
7. [Environment Variables — Full Reference](#environment-variables--full-reference)
8. [Subscription Billing Flow](#subscription-billing-flow)
9. [Subscription Expiry Guard](#subscription-expiry-guard)
10. [Multilingual Notifications](#multilingual-notifications)
11. [Scheduled Cron Jobs](#scheduled-cron-jobs)
12. [Development (without Docker)](#development-without-docker)
13. [Testing](#testing)
14. [Roadmap](#roadmap)

---

## Headline Features

| Category | What's there | Where to look |
| --- | --- | --- |
| 🔐 **6 roles** | Platform Super Admin, School Super Admin, Teacher, Class Teacher, Accounts, Parent | `backend/core/auth.py` |
| 🏫 **Multi-tenant** | Each school gets its own MongoDB DB; data isolated at the API layer too | `backend/core/db.py` |
| 👑 **Single Super Admin** | Exactly ONE Platform Super Admin (env-driven via Docker); ONE School Super Admin per school (auto-created with the school) | `backend/server.py:seed_platform_admin` |
| 💰 **Per-child subscription** | **₹30/child/month** or **₹300/child/year** (~16% off). School Admin submits payment → Platform Admin confirms | `routes/subscriptions.py` |
| 🚧 **Subscription expiry guard** | Writes auto-block when `valid_until + grace_period` passes; reads, auth, and `/subscriptions/*` stay open | `core/subscription_guard.py` |
| 🌐 **8 Indian languages** | English, हिन्दी, தமிழ், తెలుగు, ಕನ್ನಡ, मराठी, বাংলা, ગુજરાતી. School default + per-parent override | `core/i18n.py` |
| 📲 **WhatsApp (FREE preferred)** | **Meta Cloud API** (FREE 1000/mo) → Twilio fallback → `queued` mock. Absence alerts, marks publish, monthly digest, payment confirm | `core/notify.py`, `core/meta_whatsapp.py` |
| 📨 **Telegram bot (FREE)** | Free + unlimited. Parents subscribe via `/start <STU-UID>` | `core/telegram_sender.py`, `routes/webhooks.py` |
| 📧 **Email digests via SMTP** | Provider-agnostic (Gmail / SES / SendGrid / Mailgun). Falls back to `queued` if SMTP unset | `core/email_sender.py` |
| 🗓️ **Auto-cron jobs** | Monthly parent digest (1st @ 09:00 IST), Subscription renewal nudge (daily @ 08:00 IST) | `core/scheduler.py` |
| 🏥 **Sick-leave tracker** | Multi-day spans, optional medical certificate (PDF/image), auto-marks attendance `sick`, recurring widget (≥3 in 90 days) | `routes/sick_leaves.py` |
| 📑 **Audit log + filters + CSV** | Filter by role/action/resource/date/free-text; download as Excel-safe UTF-8 CSV with BOM | `routes/audit.py` |
| 📤 **Bulk Excel uploads** | Students, attendance, holidays. Teachers can upload for their classes only | `routes/uploads.py` |
| 🧾 **PDF receipts** | Fee payment + per-student academic report | `routes/receipts.py` |
| 📊 **Predictive risk flags** | Highlight students with low attendance, missed fees, or falling marks | `routes/analytics.py` |
| 📱 **Mobile-first** | Parent Portal bottom nav, teacher swipe-card attendance, fully responsive | `components/MobileBottomNav.jsx` |
| 🎨 **Branding & dark mode** | Per-school logo, primary color, tagline. Dark mode toggle persisted in localStorage | `pages/school/SchoolSettings.jsx` |
| 🚦 **Subscription banner** | Site-wide banner: amber when ≤7 days left, red in grace, red+blocked when fully expired | `components/SubscriptionBanner.jsx` |

---

## Quick Start (Docker)

```bash
# 1. clone
git clone <your-repo> scms && cd scms

# 2. copy and edit env
cp .env.example .env
$EDITOR .env       # change ADMIN_PASSWORD and JWT_SECRET at minimum

# 3. start everything
docker compose up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| Frontend | <http://localhost:3000> | nginx serving the React build + reverse-proxying `/api/*` to the backend |
| Backend API | <http://localhost:8001/api> | Direct access (optional — frontend already proxies it) |
| MongoDB | `mongo:27017` (internal only) | Uncomment the `ports:` block in `docker-compose.yml` to expose to host |

The Platform Super Admin is **provisioned from `ADMIN_EMAIL` / `ADMIN_PASSWORD`** on first startup. Legacy `platform@scms.com` is auto-deactivated to enforce the single-super-admin policy.

---

## Default Demo Accounts

| Role | Email | Password |
| --- | --- | --- |
| Platform Super Admin | `jagadishchandu789@gmail.com` | `Manasa@123` |
| School Super Admin | `principal@sunrise.edu` | `School@123` |
| Class Teacher (Grade 5 A) | `priya@sunrise.edu` | `Teacher@123` |
| Subject Teachers | `rohit@sunrise.edu`, `kavita@sunrise.edu` | `Teacher@123` |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` |
| Parent (STU-00001) | `parent.stu-00001@sunrise.edu` | `Parent@123` |

Full list at [`/app/memory/test_credentials.md`](memory/test_credentials.md).

---

## Architecture

```
/app
├── backend/
│   ├── core/
│   │   ├── auth.py                  # JWT auth, bcrypt, brute-force lockout
│   │   ├── db.py                    # Motor (async Mongo), multi-tenant helpers
│   │   ├── audit.py                 # Audit log writer
│   │   ├── notify.py                # WhatsApp + Email dispatcher
│   │   ├── email_sender.py          # SMTP sender (provider-agnostic)
│   │   ├── i18n.py                  # 5 templates × 8 languages
│   │   ├── scheduler.py             # APScheduler cron jobs
│   │   ├── subscription_guard.py    # Expiry middleware + state computation
│   │   └── models.py                # Pydantic schemas
│   ├── routes/
│   │   ├── auth.py    schools.py  users.py     students.py
│   │   ├── attendance.py  marks.py  exams.py    syllabus.py
│   │   ├── holidays.py    fees.py   timetable.py
│   │   ├── notifications.py  analytics.py  audit.py
│   │   ├── subscriptions.py  receipts.py    calendar.py
│   │   ├── digests.py     activities.py     sick_leaves.py
│   │   └── uploads.py
│   ├── tests/                       # 162 pytest cases
│   ├── server.py                    # FastAPI app, CORS, middleware, seeding
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/   # Sidebar, Topbar, Modal, Primitives,
│   │   │                 # MobileBottomNav, SubscriptionBanner, ProtectedRoute
│   │   ├── contexts/     # AuthContext, ThemeContext (dark mode)
│   │   ├── layouts/      # AppLayout
│   │   ├── lib/          # api.js (axios + 402 interceptor), utils
│   │   └── pages/        # role-scoped (platform/, school/, teacher/,
│   │                     # accounts/, parent/, shared/)
│   ├── nginx.conf        # production proxy (proxy_pass /api → backend:8001)
│   ├── Dockerfile        # multi-stage build (node → nginx)
│   └── package.json
├── docker-compose.yml
├── .env.example
└── README.md (you are here)
```

---

## Roles & Access Matrix

| Capability | Platform | School Admin | Teacher | Accounts | Parent |
| --- | :-: | :-: | :-: | :-: | :-: |
| Create / delete schools | ✅ | — | — | — | — |
| Confirm subscription payments | ✅ | — | — | — | — |
| Set school's `valid_until` (goodwill) | ✅ | — | — | — | — |
| Trigger renewal nudge manually | ✅ | — | — | — | — |
| Submit subscription payment | — | ✅ | — | — | — |
| Add / edit students | — | ✅ | ✅ (own class) | — | — |
| Excel bulk upload (students, attendance) | — | ✅ | ✅ (own class) | — | — |
| Add teachers / accounts staff | — | ✅ | — | — | — |
| Mark / view attendance | — | ✅ | ✅ (own class) | — | own child |
| Enter / publish marks | — | ✅ | ✅ (own class) | — | own child |
| Manage fees / payments | — | ✅ | — | ✅ | view only |
| Record sick leaves | — | ✅ | ✅ (own class) | — | own child |
| Upload medical certificates | — | ✅ | ✅ (own class) | — | ✅ |
| Audit log + CSV export | all schools | own school | — | — | — |
| Set school's notification language | — | ✅ | — | — | — |
| Set personal notification language | ✅ | ✅ | ✅ | ✅ | ✅ |
| Custom branding (logo / color / tagline) | — | ✅ | — | — | — |

Super-admin creation is **blocked** at the API level: `POST /api/users` rejects `role=school_admin` or `role=platform_admin`. There is exactly one Platform Super Admin (env-provisioned) and one School Super Admin per school (auto-created when the school is created).

---

## Key API Endpoints

### Auth
```http
POST   /api/auth/login              # email + password → httpOnly JWT cookie
GET    /api/auth/me                 # current user + subscription_state + school metadata
POST   /api/auth/logout
```

### Subscriptions (per-child billing)
```http
GET    /api/subscriptions/pricing                 # → { per_child_monthly:30, per_child_yearly:300 }
GET    /api/subscriptions/my                      # school admin: quote + current state + pending
GET    /api/subscriptions/quote/{school_id}
POST   /api/subscriptions/payments                # school admin submits payment
GET    /api/subscriptions/payments?status=...     # platform: all, school: own
POST   /api/subscriptions/payments/{id}/confirm   # platform admin only
POST   /api/subscriptions/payments/{id}/reject    # platform admin only
POST   /api/subscriptions/nudge-renewals          # platform admin — manual 7-day nudge
POST   /api/subscriptions/admin/set-valid-until   # platform admin — set school's expiry directly
```

### Students
```http
GET    /api/students                              # role-scoped
POST   /api/students                              # school admin OR teacher (own class)
POST   /api/students/{id}/photo                   # multipart
PATCH  /api/students/{id}
DELETE /api/students/{id}                         # soft delete
```

### Sick Leaves
```http
POST   /api/sick-leaves                           # school admin / teacher (own) / parent (own child)
POST   /api/sick-leaves/{id}/certificate          # upload medical cert (PDF/image, ≤ 5 MB)
GET    /api/sick-leaves?student_uid=STU-...&days=90
GET    /api/sick-leaves/recurring?threshold=3&days=90
DELETE /api/sick-leaves/{id}
```

### Audit
```http
GET    /api/audit?actor_role=&action=&resource=&date_from=&date_to=&q=&limit=200
GET    /api/audit/facets                          # distinct values for filter dropdowns
GET    /api/audit/export.csv?...                  # same filters → CSV download (UTF-8 BOM)
```

### Languages
```http
GET    /api/schools/{id}/language                 # → { language, supported:[{code,label}] }
PATCH  /api/schools/{id}/language                 # school_admin / platform_admin
PATCH  /api/users/me/language                     # any authenticated user
```

### Notifications & Digests
```http
POST   /api/digests/run-monthly?channels=whatsapp,email
GET    /api/digests/preview/{uid}?lang=en
GET    /api/notifications
```

### Bulk Uploads
```http
GET    /api/uploads/template/{kind}               # students / attendance / holidays template
POST   /api/uploads/students                      # admin OR teacher (rows validated against their classes)
POST   /api/uploads/attendance
POST   /api/uploads/holidays                      # admin only
```

### Misc
```http
GET    /api/analytics/risk-students?limit=5
GET    /api/calendar/events
GET    /api/receipts/payment/{id}.pdf
GET    /api/health                                # liveness probe (used by docker healthcheck)
```

---

## Environment Variables — Full Reference

All variables live in either `backend/.env` (local dev) or `docker-compose.yml`'s env block (Docker). The root `.env` file is consumed by `docker compose up` and overrides the defaults.

### 🔴 Required for any deployment

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONGO_URL` | `mongodb://mongo:27017` (Docker) / `mongodb://localhost:27017` (dev) | Connection string for the master MongoDB. |
| `DB_NAME` | `scms_db` | Master database name. Per-school databases (`scms_db_school_<slug>`) are created automatically when a school is added. |
| `JWT_SECRET` | *insecure dev default* | **CHANGE IN PRODUCTION.** Secret used to sign access + refresh JWTs. Use a 64+ char random string. |
| `ADMIN_EMAIL` | `jagadishchandu789@gmail.com` | Email of the **single** Platform Super Admin. Created/upserted at startup. Any other `platform_admin` rows are auto-deactivated. |
| `ADMIN_PASSWORD` | `Manasa@123` | Password for the Platform Super Admin. **Change to something strong before going live.** |

### 🟢 CORS / Networking

| Variable | Default | Purpose |
| --- | --- | --- |
| `FRONTEND_URL` | `http://localhost:3000` | Used in renewal-nudge links and email bodies. Set to your public frontend URL in production. |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://frontend:3000` | Comma-separated list of allowed origins for CORS. When the frontend is served behind nginx on the same origin, CORS isn't strictly necessary — but `localhost:3000` is kept so `yarn start` works against the dockerized backend. |
| `REACT_APP_BACKEND_URL` (frontend build-time) | empty | **For Docker: leave blank.** The React build then uses relative `/api` paths and nginx proxies them. **Only set this** when the frontend is served from a different origin than the backend (e.g. CDN + separate API), in which case use the full HTTPS URL (no trailing `/`). |

### 🟡 Feature Flags

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENABLE_DIGEST_SCHEDULER` | `false` | When `true`, starts the in-process APScheduler with two cron jobs (monthly digest @ 1st 09:00 IST + renewal nudge @ daily 08:00 IST). |
| `ENABLE_SUBSCRIPTION_GUARD` | `true` | When `true`, the middleware blocks write requests (POST/PATCH/PUT/DELETE) for schools whose `valid_until + grace_period` has passed. Reads + auth + `/subscriptions/*` always pass. Set to `false` for a soft-launch where you don't yet want to enforce billing. |
| `SUBSCRIPTION_GRACE_DAYS` | `3` | Days of grace after `valid_until` before writes are blocked. Banner shows red "in grace period" during this window. |

### 🟦 WhatsApp Provider (Optional — Meta is FREE, Twilio is fallback)

WhatsApp delivery tries providers in this order: **Meta Cloud API → Twilio → queued (mock log)**.
Leaving both blank keeps notifications in `queued` status so you can develop without sending real messages.

#### Option 1 — Meta WhatsApp Business Cloud API (recommended, FREE 1000 conversations/month)

Get keys from <https://developers.facebook.com/> → your app → WhatsApp → API Setup.

| Variable | Example | Purpose |
| --- | --- | --- |
| `META_WHATSAPP_PHONE_ID` | `123456789012345` | Numeric phone-number ID from Meta dashboard. |
| `META_WHATSAPP_ACCESS_TOKEN` | `EAAxxxxxxxx...` | Long-lived system-user access token. |
| `META_WHATSAPP_VERIFY_TOKEN` | `your-secret-string` | Arbitrary secret you make up; Meta uses it to verify the webhook at `/api/webhooks/whatsapp`. |
| `META_WHATSAPP_API_VERSION` | `v21.0` | API version path (default `v21.0`). |

Webhook endpoint (configure in Meta dashboard → WhatsApp → Configuration):
```
GET / POST  https://your-domain.com/api/webhooks/whatsapp
```

#### Option 2 — Twilio (paid backup)

Leave Meta blank if you only want Twilio.

| Variable | Example | Purpose |
| --- | --- | --- |
| `TWILIO_ACCOUNT_SID` | `ACxxxxxxxx...` | <https://console.twilio.com/> |
| `TWILIO_AUTH_TOKEN` | `xxxxxxxx...` | Twilio console |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` | Approved sender (sandbox or production) |

### 📨 Telegram Bot (Optional — FREE, unlimited)

Telegram bot is a **separate channel** (parents who prefer Telegram over WhatsApp). Parents subscribe by opening the bot and sending `/start <STU-UID-or-email>` once — the webhook stores their `chat_id` on their user record, and you can then push messages to them through the `telegram` channel.

| Variable | Example | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | `5123456789:AAHxxxxxxxxxxxxxxxx` | Get from [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_WEBHOOK_SECRET` | `your-secret-string` | Optional shared secret; recommended in production |

One-time setup (after `TELEGRAM_BOT_TOKEN` is filled):
```bash
# Tell Telegram where to send updates (run once after deploy)
curl -X POST "https://your-domain.com/api/webhooks/telegram/set-webhook?public_url=https://your-domain.com/api/webhooks/telegram"
```

Then ask parents to open `https://t.me/<your_bot_username>` and send `/start STU-00001`.

To send through Telegram in code: `POST /api/digests/run-monthly?channels=telegram` (or include `telegram` in the comma-separated list).

### 📧 SMTP Email (Optional)

Universal — works with Gmail, AWS SES, SendGrid SMTP, Mailgun SMTP, Postmark, etc.

| Variable | Example | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `email-smtp.us-east-1.amazonaws.com` | SMTP server. Leave blank to disable email delivery (rows stay `queued`). |
| `SMTP_PORT` | `587` (STARTTLS) or `465` (SSL) | Default `587`. |
| `SMTP_USER` | username / API key | Login username. For SendGrid SMTP use `apikey`. |
| `SMTP_PASSWORD` | password / API key value | Login password (use Gmail App Password if you use Gmail; never the raw account password). |
| `SMTP_FROM` | `"Sunrise School <noreply@school.com>"` | The `From:` shown to recipients. Falls back to `SMTP_USER` if not set. |
| `SMTP_USE_SSL` | `false` | Set to `true` only if you're using port 465 SSL-on-connect. STARTTLS on 587 works without this. |

### 💾 Azure Blob Storage (Optional, future use)

Currently student photos, medical certificates, and PDF receipts are stored as base64 in MongoDB. Filling these env vars sets up the future migration target (planned in v1.9).

| Variable | Where to get it | Purpose |
| --- | --- | --- |
| `AZURE_STORAGE_CONNECTION_STRING` | Azure Portal → Storage Account → Access keys | Full connection string (`DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...`). |
| `AZURE_STORAGE_CONTAINER` | container you create in the account | Container name (e.g. `scms-uploads`). |
| `AZURE_STORAGE_ACCOUNT_URL` | `https://<account>.blob.core.windows.net` | Used to build public URLs for served files. |

### 🛡️ Protected Variables (DO NOT REMOVE)

These are baked into the Emergent platform; never delete them from `.env`:
- `backend/.env`: `MONGO_URL`, `DB_NAME`
- `frontend/.env`: `REACT_APP_BACKEND_URL` (key must exist; can be empty for Docker)

---

## Subscription Billing Flow

```
                       School Admin                       Platform Super Admin
                       ────────────                       ─────────────────────
1. Open /school/subscription
2. See live quote (₹30 × N or ₹300 × N students)
3. Click "Pay ₹540" or "Pay ₹5,400"
4. Pick mode (UPI/Bank/Card) + paste UTR
   ───────────────────────────────────►  POST /api/subscriptions/payments
                                         status = "pending_confirmation"

                                                          5. /platform/subscriptions
                                                             sees the pending row
                                                          6. Verifies payment in their bank
                                                             ────────────────────────►
                                                             POST /payments/{id}/confirm
                                                             school.subscription.status = "active"
                                                             valid_until = now + 30/365 days

7. School Admin sees "Active" KPI       ◄────  WhatsApp + Email confirmation queued
```

**Renewal** stacks: confirming a new payment while the school is still active **extends** `valid_until` from the existing date, not from "now". This rewards early renewers.

---

## Subscription Expiry Guard

When `ENABLE_SUBSCRIPTION_GUARD=true` (default):

1. **Healthy** (`now < valid_until`): all writes pass.
2. **Expiring soon** (`days_left ≤ 7`): writes still pass. Amber banner appears: *"Subscription expires in N days. Renew to keep all features active."*
3. **In grace period** (`valid_until < now ≤ valid_until + SUBSCRIPTION_GRACE_DAYS`): writes still pass. Red banner: *"Subscription expired N days ago — grace period."*
4. **Beyond grace** (`now > valid_until + SUBSCRIPTION_GRACE_DAYS`): writes return **HTTP 402** with:
   ```json
   {
     "detail": "Subscription expired. Please renew to continue making changes.",
     "code": "subscription_expired",
     "valid_until": "2026-04-15T...",
     "grace_until": "2026-04-18T...",
     "renew_url": "/school/subscription"
   }
   ```

**Always-allowed paths** (even when expired): `/api/auth/*`, `/api/subscriptions/*`, all GET/HEAD/OPTIONS. So schools can still log in and pay.

**Platform Super Admin** is never gated.

The `/auth/me` and `/auth/login` responses include a `subscription_state` object so the UI banner renders immediately:
```json
{
  "status": "active",
  "valid_until": "2026-05-20T19:05:21+00:00",
  "grace_until": "2026-05-23T19:05:21+00:00",
  "days_left": 5,
  "is_expiring_soon": true,
  "is_in_grace": false,
  "is_expired": false
}
```

A global axios interceptor on the frontend auto-redirects to `/school/subscription` whenever it sees a `402 subscription_expired`.

---

## Multilingual Notifications

8 languages × 5 message templates = 40 entries baked into `core/i18n.py`.

| Code | Label |
| --- | --- |
| `en` | English |
| `hi` | हिन्दी (Hindi) |
| `ta` | தமிழ் (Tamil) |
| `te` | తెలుగు (Telugu) |
| `kn` | ಕನ್ನಡ (Kannada) |
| `mr` | मराठी (Marathi) |
| `bn` | বাংলা (Bengali) |
| `gu` | ગુજરાતી (Gujarati) |

**Templates**: `attendance_absent`, `marks_published`, `payment_confirmed`, `monthly_digest`, `subscription_renewal`.

**Language precedence** when sending a message:
1. The recipient's `user.language` (if set via `PATCH /users/me/language`)
2. The school's `school.language` (set via `/school/settings` → Notification language dropdown)
3. `en` (English fallback)

Templates use `_SafeDict` formatting — a missing kwarg becomes `""` rather than throwing `KeyError`, so additions of new placeholders never break older callers.

---

## Scheduled Cron Jobs

When `ENABLE_DIGEST_SCHEDULER=true`, `core/scheduler.py` starts an in-process APScheduler (IST timezone) with two jobs:

### 1. `monthly_digest` — **1st of each month @ 09:00 IST**
Sends a per-student attendance + marks + fees summary to every active student's parent, via both WhatsApp + Email (whichever channels have a contact). Uses the localized template for each parent's language.

Manual trigger: `POST /api/digests/run-monthly?channels=whatsapp,email` (school admin or platform admin).

### 2. `subscription_nudge` — **daily @ 08:00 IST**
Finds schools whose `subscription.valid_until` is within the next 7 days and sends a renewal nudge to the school admin via WhatsApp + Email. **24-hour cooldown** per school prevents spam.

Manual trigger: `POST /api/subscriptions/nudge-renewals` (platform admin only).

---

## Development (without Docker)

```bash
# --- Backend ---
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edit MONGO_URL if not on localhost
uvicorn server:app --reload --port 8001
# → API at http://localhost:8001/api

# --- Frontend ---
cd ../frontend
yarn install
cp .env.example .env
yarn start                 # opens http://localhost:3000
# (REACT_APP_BACKEND_URL points to http://localhost:8001)

# --- MongoDB ---
# Run any local mongo: docker run -p 27017:27017 mongo:7
```

---

## Testing

```bash
cd /app && python -m pytest backend/tests/ -v
```

Current state: **162/162 backend tests pass** covering:
- Auth (login, role-based access, brute-force lock, password reset)
- Single Super Admin policy enforcement
- Students, attendance, marks, fees, exams CRUD + RBAC
- Per-child subscription pricing + payment lifecycle
- Audit log filters, facets, CSV export
- Sick leaves + medical certificates + recurring aggregation
- Multilingual templates (8 languages × 5 templates)
- Email digest channel via SMTP (mocked)
- Subscription expiry guard (healthy / grace / blocked / state flags)
- Subscription renewal nudge (window edges, cooldown, RBAC)
- Notifications, calendar, holidays, timetable

Linting:
```bash
ruff check backend/
yarn --cwd frontend lint
```

---

## Roadmap

### P1 (next up)
- Stripe / Razorpay automated subscription payments (skip the manual confirm step)
- "Send test email" button on `/school/settings` to validate SMTP before relying on it

### P2
- Wire uploads (photos, medical certs, PDF receipts) to Azure Blob once the `AZURE_STORAGE_*` env vars are set
- Recovery nudges after expiry (day 1 / 3 / 7) before full lockout
- Per-school WhatsApp template editing UI (if customisation is requested)
- `make` Makefile wrapper for common dev ops

### P3
- React Native mobile shell reusing the same API
- Public school directory + admissions inquiry page
- Voice-to-text attendance for teachers

---

## License

Proprietary — © 2026 Emergent Labs. All rights reserved.
