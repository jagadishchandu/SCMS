# SCMS — Product Requirements (running log)

## Original problem statement (2026-01)
> Build a mobile app: read my repo understand my code.
> In my code there is a bug where in school admin subscription when he added number of children he is not able to see the updates values charge — fix it.
> Also I want to run frontend and backend in separate containers (not as a compose file). I should be able to give the frontend my backend URL as a variable, and the backend my frontend URL as a variable, so they can communicate. Also increase timeout value for calls.

## Architecture
- **Frontend**: React 19 (CRA), served by nginx (or `yarn start` in dev). Talks to backend through `REACT_APP_BACKEND_URL` (build-time arg).
- **Backend**: FastAPI + Motor (MongoDB). Multi-tenant per-school DBs. Runs on `:8001`.
- **DB**: MongoDB (local for dev, Cosmos-for-Mongo on prod).
- **Auth**: JWT in cookie + header. Roles: platform_admin / school_admin / accounts / teacher / parent.

## Personas
- Platform Super Admin (single seed account)
- School Super Admin (per school)
- Accounts / Teacher / Parent

## Iteration — 2026-01 (current session, part 3)
**Unread-count badge on sidebar Notifications link**
- New endpoints `GET /api/notifications/unread-count` and
  `POST /api/notifications/mark-all-read` (in-app channel, recipient_id-scoped).
- New hook `frontend/src/hooks/useUnreadNotifications.js` polls every 30s,
  on window focus, and on a `scms:notifications:refresh-unread` custom event
  so any caller (e.g. NotificationsLog page) can clear the badge instantly.
- `Sidebar.jsx` wires the count into the existing `badges` map for
  `/school/notifications` and `/platform/notifications`.
- `NotificationsLog.jsx` calls mark-all-read on mount and broadcasts the
  refresh event — badge clears the moment the page renders.

## Iteration — 2026-01 (current session, part 2)
**Yearly upgrade nudge** (env-tunable threshold, default 50 children)
- `GET /api/subscriptions/pricing` now returns `yearly_nudge_threshold` from
  `SUBSCRIPTION_YEARLY_NUDGE_THRESHOLD` (default 50).
- `SchoolSubscription.jsx` shows a one-click upgrade banner whenever the
  school is approved, has no pending payment, billed_children ≥ threshold,
  and is currently on monthly / not subscribed. Banner CTA opens the existing
  PayModal pre-set to yearly.

**Next-bill widget on school dashboard**
- `SchoolDashboard.jsx` now fetches `/api/subscriptions/my` and renders a
  prominent "Next bill estimate" card showing the live amount (monthly or
  yearly based on current cycle), child count, and renewal date.

**Platform admin — Active Subscriptions tab + in-app reminders**
- New backend endpoint `GET /api/subscriptions/active` — every school's
  cycle, amount, last renewed, valid_until, days_left, last_nudge timestamp.
- New backend endpoint `POST /api/subscriptions/notify/{school_id}` — sends
  an in-app reminder (auto-generated body based on days_left, or custom).
  Adds a row in `db.notifications` with `channel="in_app"` so the school
  admin sees it on their notifications page.
- `core/notify.py`: added explicit `in_app` channel branch (logs row as `sent`).
- `core/scheduler.py`: daily 08:00 IST job now fires at **T-7** and **T-1**
  with per-checkpoint cooldown (24h) and always queues an `in_app`
  notification in addition to any configured WhatsApp/Email channels.
- `SubscriptionsPage.jsx` (platform admin) gains an "Active subscriptions"
  tab with a "Notify school" button per row.

## Iteration — 2026-01 (current session, part 1)
**Bug fix — subscription charge stuck at ₹0**
- `_quote_for_school` (backend/routes/subscriptions.py) now bills the *greater of*
  `approved_children_count`, `requested_children_count` and live `students_active`.
  Returns the new `billed_children` field.
- `SchoolSubscription.jsx` form now shows live monthly + yearly cost preview as
  the admin types. PlanCard caption reworded to reflect "billed children" basis.

**Separate-container support**
- `backend/server.py`: CORS now automatically appends `FRONTEND_URL` env var to
  the allowlist so the operator only needs to set one env var.
- `frontend/nginx.conf`: backend upstream is now `${BACKEND_UPSTREAM}` (default
  `backend:8001`), rendered via nginx envsubst templating at container start.
- `frontend/Dockerfile`: copies nginx conf to `/etc/nginx/templates/*.template`
  and sets `BACKEND_UPSTREAM` env var.
- `backend/Dockerfile`: uvicorn now runs with `--timeout-keep-alive 400`.
- New `STANDALONE.md` documents the two-container deployment, including which
  env vars + build-args to use.

**Timeouts bumped to 400s**
- `frontend/src/lib/api.js` axios timeout: 30s → 400s.
- `frontend/nginx.conf` `proxy_read_timeout` / `proxy_send_timeout`: 120s → 400s.
- backend uvicorn `--timeout-keep-alive`: default → 400s.

**Local-dev Mongo fix (incidental)**
- `core/db.py` no longer forces TLS for plain `mongodb://` URLs — only enables
  TLS for `mongodb+srv://` or when the URL explicitly opts in. Prod (Cosmos)
  still uses TLS via the `tls=true` query param.

## Backlog / Next
- P1: surface a "your next bill" widget on the school dashboard.
- P1: a "lock count to actual onboarded students" toggle so price stops growing
  past planned capacity.
- P2: auto-renew + auto-charge via Razorpay/Stripe.
