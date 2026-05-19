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

## Iteration — 2026-01 (current session, v41) — Locks, daily cap, Telegram-publish, ClassesPage parity
**Original ask:** (1) Publish saved batch timetable as PDF via Telegram to teachers + parents, (2) lock teacher per slot in the builder, (3) migrate ClassesPage suggest modal to /suggest-batch, (4) cap per-teacher periods/day.

**Backend**
- `SuggestTimetableRequest` extended with `locked_assignments[]` (`{day, period, teacher_id, subject_id?}`) and `max_periods_per_day_per_teacher` (int). Both also accepted on `BatchSectionRequest`.
- `_generate_section_schedule` now:
  - Excludes locked positions from greedy assignment.
  - Materialises locks with `is_locked=true` and warns if the locked teacher was already busy.
  - Enforces `max_periods_per_day_per_teacher` by tracking `(teacher_id, day) → count`; surfaces a “per-day cap” warning when the cap blocks an assignment.
  - Sorts final slots in canonical day/period order (locks were skipped during the greedy pass).
- `/suggest-batch` pre-seeds the global `busy` set with every section's locked teachers BEFORE per-section generation, so a lock in section A cannot be overridden by greedy in section B.
- **New endpoint `POST /api/timetable/publish`** — reads the saved timetable, generates per-teacher PDFs (their own weekly grid) and per-section PDFs (re-used for every child in that section), ships them via Telegram `sendDocument`. Returns a delivery report (`teachers_total/sent/failed`, `parents_total/sent/failed`, `failures[]` capped at 50 with `failures_truncated`).
- **New endpoint `GET /api/timetable/pdf/section`** — admin preview/download of a single section's PDF.
- **New helper `core/timetable_pdf.py`** — reportlab generators: `section_pdf`, `teacher_pdf`, `school_pdf` with landscape A4, colour-coded cells (blue = class teacher, purple = locked, yellow = break, red = unfilled).
- **`core/telegram_sender.py`** gained `send_telegram_document(chat_id, filename, bytes, caption, mime)`.
- `audit.log_action` is now imported at top of `routes/timetable.py`; publish actions are logged with delivery counts.

**Frontend**
- `TimetableBuilderPage.jsx`:
  - New global config field **“Max periods/day per teacher”** (blank = no cap).
  - Each section grid cell has an expandable **“Lock…”** sub-form: teacher dropdown + optional subject dropdown + clear-lock button. Locked cells render with a primary-tinted left border and a 🔒 icon.
  - New **“📤 Publish to Telegram”** button appears after the result panel; shows confirm dialog, posts to `/publish`, then renders a delivery-report panel (teachers sent/total, parents sent/total, first 20 failures with reasons).
- `ClassesPage.jsx` suggest modal: rewired from `/timetable/suggest` to `/timetable/suggest-batch` with a single-section payload; response is projected back into the legacy shape so the existing UI keeps working (no UI change for users).

**Tests**
- v41 testing subagent → **24/24 tests passed** (11 new + 13 v40 regression). Verified: `locked_assignments` single + cross-section busy priority + `is_locked` + teacher_view propagation; `max_periods_per_day_per_teacher` enforcement + warning; `/publish` shape + class_ids filter + 400 precondition; `/pdf/section` valid PDF binary + 404 path; `/suggest` back-compat; combined regression mixing locks + breaks + class-teacher pin + allowed-periods + heavy cap + day-cap in one call.
- Demo data: zero `telegram_chat_id`s configured, so the publish-delivery report intentionally shows every recipient as `telegram_not_linked` — exactly the right reporting behavior to verify.



## Iteration — 2026-01 (current session, v40) — Multi-section auto-scheduler
**Original ask:** Generate weekly timetables for multiple grades/sections in one go with these rules: subject frequency, balanced distribution, allowed periods (lab/sports/library), max consecutive heavy subjects, class-teacher period, fixed breaks, no cross-section teacher conflicts, conflict highlights, optimization suggestions. Outputs: per-section grid, teacher-wise grid, conflict summary, suggestions.

**Backend (`routes/timetable.py`)**
- `SuggestTimetableRequest` extended with: `fixed_breaks[]`, `subject_categories{}`, `allowed_periods_per_subject{}`, `max_consecutive_heavy`, `class_teacher{teacher_id, period, subject_id?, label}`.
- Refactored greedy engine into `_generate_section_schedule(...)` which respects every constraint and **mutates a shared `busy` set + `rr_index`** so the same engine can be called in a loop for batch generation without cross-section conflicts.
- **New endpoint `POST /api/timetable/suggest-batch`** — takes `defaults` (constraints applied to every section) + `sections[]` (per-section overrides incl. `student_count`, per-section `class_teacher`). Returns:
  - `sections[]` — per-section grid (slots, warnings, subject_distribution, break_periods).
  - `teacher_view` — teacher-wise weekly grid grouped by day/period + min/max workload.
  - `conflict_summary` — cross-section `double_bookings`, `unfilled_slots` with class/section/day/period/subject/reason, plus collated warnings.
  - `optimization_suggestions[]` — actionable English hints (e.g. "Add 1 more teacher for 'Science' …").
- **New endpoint `POST /api/timetable/save-batch`** — persists every section atomically. Validates intra-payload + cross-class conflicts (HTTP 409 with the same detail shape as `/bulk`). Replaces each (class_id, section) in one shot, fires teacher Telegram notifications.
- Existing `/api/timetable/suggest` and `/api/timetable/bulk` continue to work (back-compat verified).

**Frontend (`pages/school/TimetableBuilderPage.jsx`)**
- New "Timetable Builder" admin page at `/school/timetable-builder` with sidebar nav.
- Global config panel: periods/day, start time, period length, lunch period, max-heavy-in-a-row, working-days toggles, **add-multiple-fixed-breaks** inline form.
- Subject constraints matrix table: per-subject **category dropdown** (heavy / light / lab / sports / library / regular), **periods/week** input, **allowed-periods** toggle grid, **avoid-last-period** checkbox.
- Sections panel: every class lists its sections as toggle chips; each selected section gets a row with `student_count` input + optional class-teacher teacher/period selectors.
- Result panel with 3 tabs: **Sections** (one weekly grid per section, unfilled slots flagged in red), **Teacher view** (per-teacher weekly grid with class·section badges), **Conflicts** (optimization suggestions, unfilled-slots table, warnings).
- "Save all sections" button posts to `/save-batch` and surfaces server-side 409 conflicts via the same `formatApiError`.

**Tests**
- v40 testing subagent → **13/13 backend tests passed**. Covered: `/suggest-batch` (4 sections), cross-section teacher uniqueness, fixed_breaks, allowed_periods_per_subject, max_consecutive_heavy, class_teacher pin propagation to teacher_view, subject_periods frequency, no_last_period_subjects, conflict_summary.unfilled_slots, optimization_suggestions, `/save-batch` persistence + atomic 409, `/bulk` & `/suggest` back-compat.
- Minor code-review item fixed: CT-subject frequency now correctly deducts `len(days)` when CT covers a subject, so `subject_periods` no longer overshoots.



## Iteration — 2026-01 (current session, v39) — Timetable conflict-free + Teacher leaves
**Original ask:** No collision of same teacher across grades/classes/sections when filling the timetable, even with multiple teachers per subject and 7+ classes. Time-table must also respect teacher leaves. Add a teacher-leave request page (teacher submits, school admin approves).

**Changes implemented**
- `POST /api/timetable/bulk` now strictly validates:
  - **Intra-payload conflicts** — same teacher in two slots at the same (day, period) in the submission.
  - **Cross-class collisions** — same teacher already booked at the same (day, period) in any OTHER class/section.
  - On any conflict the save is rejected with **HTTP 409** and a structured detail (`{error, message, intra_payload_conflicts, cross_class_conflicts}`) including human-friendly `teacher_name`, `class_name`, `subject_name`. The existing class/section's prior timetable is NOT touched until validation passes.
- `POST /api/timetable/suggest` is now leave-aware:
  - New optional payload field `effective_week_start` (ISO Monday). When supplied, every teacher with an **approved** `teacher_leaves` row that covers a weekday inside that week is excluded for those days. The greedy assigner picks an alternate teacher of the same subject when available, else returns the slot with `teacher_id=""` and a warning so the admin can pencil-in a substitute.
- **New `routes/teacher_leaves.py`** (mounted on `/api/teacher-leaves`):
  - `POST /` — teacher creates leave (`leave_type`, `start_date`, `end_date`, `reason`).
  - `GET /` — list (teacher sees own; admin sees all in school) with `?status=` filter.
  - `GET /pending-count` — admin sidebar badge.
  - `GET /active?date=YYYY-MM-DD` — approved leaves covering the date (returns `teacher_ids` list for the timetable UI).
  - `POST /{id}/approve` — admin only. Sets status=`approved` AND auto-upserts `teacher_attendance` rows status=`leave` for each weekday (Mon-Sat) inside the range, stamped with `auto_from_leave_id`. Fires an in-app notification to the teacher.
  - `POST /{id}/reject` — admin only, with optional decision note.
  - `DELETE /{id}` — teacher cancels their own pending leave; admin can cancel any. Approved leave DELETE rolls back the auto-marked attendance rows.
- **Frontend**:
  - New `pages/shared/TeacherLeavesPage.jsx` (used by both teacher and admin routes).
    - Teacher: create form (leave type, dates with `DatePicker`, reason) + filterable history (pending/approved/rejected/cancelled).
    - Admin: pending queue first; one-click Approve / Reject; filterable history.
  - `TimetablePage.jsx`: queries `/api/teacher-leaves/active?date=…` and overlays an **"ON LEAVE — find substitute"** badge on every cell whose teacher is on approved leave for the picked date. Cell also tints warning (`status=leave`) for visibility.
  - `App.js`: new routes `/school/teacher-leaves` (admin) and `/teacher/teacher-leaves` (teacher).
  - `Sidebar.jsx`: nav items added for both roles; admin gets a live red pending-count badge fed by new `useTeacherLeavePending` hook (polls `/api/teacher-leaves/pending-count`).
  - `lib/api.js`: `formatApiError` now also unwraps `detail.message` so the 409 conflict message renders nicely in toasts.

**Tests**
- v39 testing subagent: **18/18 backend tests passed** (timetable conflict 409 paths, happy-path replace semantics, full teacher-leaves CRUD with auto attendance marking, decision idempotency, role guards, leave-aware suggest).
- Smoke-tested via curl: cross-class collision returns rich 409 detail; suggest with `effective_week_start=2026-06-01` correctly excludes Priya (approved leave Jun 1-3) from Mon/Tue/Wed assignments.

**Test credentials touched**
- No auth changes. Existing demo creds still valid (see `test_credentials.md`).



## Iteration — 2026-01 (current session, part 6) — DatePicker + Mongo aggregation
**Changes implemented**
- New `frontend/src/components/DatePicker.jsx` — popover calendar (day + month
  modes) using Tailwind + lucide icons (no extra deps; shadcn/radix not in
  this project). Trigger uses the existing `.input` class so it matches every
  other field.
- Replaced every browser-native `<input type="date">` on the attendance and
  timetable pages with `DatePicker`:
  - `AttendancePage`: Mark students (`att-date`), Absentees (`absentees-date`,
    flips to month mode when period=month), Teacher attendance (`teacher-att-date`).
  - `TimetablePage`: tint picker (`timetable-tint-date`).
- `GET /api/attendance/absentees` rewrites the Python aggregation as a single
  Mongo pipeline: `$match -> $group` (conditional sums per status) `-> $match
  $expr -> $sort`. `last_absent_status` is then resolved with one `find_one`
  per matched absentee. Same JSON shape — drop-in replacement that scales past
  hundreds of thousands of attendance rows.
- Tests: `backend/tests/test_iter37_absentees_aggregation.py` (9/9) + iter36
  (14/14) + iter35 (25/25) = 48/48 pass. Frontend Playwright pass on all 4
  DatePicker instances.


## Iteration — 2026-01 (current session, part 5) — Absentees panel + Teacher attendance
**Changes implemented (backend + frontend)**
- New collection `teacher_attendance` in per-school DB (unique on
  `teacher_id+date`, statuses `present|absent|leave|half_day`).
- New API: `routes/teacher_attendance.py`
  - `POST /api/teacher-attendance/bulk` — school_admin + accounts; idempotent upsert.
  - `GET /api/teacher-attendance/today` — every active teacher + status (or
    `unmarked`) + aggregate counts. Used by the timetable to tint cells.
  - `GET /api/teacher-attendance?date=…|month=…` — role-scoped list (teachers
    see only their own rows).
  - `GET /api/attendance/absentees?period=day|week|month` — students absent
    in the picked period with counts, last-absent-date and (for month)
    attendance percentage. Optional `class_id` + `section` filter.
- `AttendancePage` rewritten with three tabs: **Mark students**, **Absentees**,
  **Teacher attendance**. Absentees tab has Day/Week/Month segmented control +
  KPI tiles. Teacher tab has a date picker, mark-all buttons, status pills, an
  Absent-today strip and a roster table.
- `TimetablePage` now has a "Color cells for" date picker. The matching weekday
  row is highlighted (`picked` ring) and each period cell is tinted green
  (present), red (absent), amber (leave), blue (half-day), or dashed (unmarked)
  based on the teacher's status for the picked date.
- Tests: `backend/tests/test_iter36_teacher_attendance.py` (14/14 pass) + iter35
  regression (25/25 pass).



## Iteration — 2026-01 (current session, part 4) — Login id rules + parent-login kill switch
**Changes implemented (backend + frontend)**
- Login ids are now case-insensitive and may be plain identifiers (no `@` required).
  Applies to platform_admin, school_admin, teacher, accounts, parent.
  - Backend: `LoginRequest.email`, `UserCreate.email`, `ParentInfo.email`,
    `SchoolCreate.admin_email` are now plain `str` (was `EmailStr`).
  - Backend: `auth.login` lowercases the incoming id before lookup; brute-force
    identifier is also lowercased so case-variants can't bypass the lockout.
  - Frontend `Login.jsx`: input type `email` → `text`, with helper copy.
- Per-school **Parent-login kill switch** controlled by the Platform Super Admin.
  - New endpoints: `GET /api/schools/{school_id}/parent-login`,
    `PATCH /api/schools/{school_id}/parent-login` (platform_admin only).
  - When `parent_login_enabled=False`, `auth.login` returns 403 to parents in
    that school; other roles unaffected.
  - Frontend: new `ParentLoginPanel` inside the Platform Overview school detail
    drawer with a green/red toggle.
- Duplicate-id guards (friendlier error messages):
  - `POST /api/users` 400: `"Login id '<id>' already exists (role: <role>). ..."`.
  - `POST /api/students` parent block: cannot reuse a non-parent (teacher/admin)
    login id; cannot reuse a parent id that belongs to another school.
  - `POST /api/schools` admin_email duplicate returns friendlier message.
- Other-staff add bug FIX:
  - Frontend `TeachersPage.jsx` CreateStaffModal sent `driver` / `coach` which
    aren't in backend `StaffRole` Literal (`bus_driver`, `sports_coach`, ...).
    Replaced `STAFF_ROLES` with `STAFF_ROLE_OPTIONS` listing the exact backend
    values + human labels. Fixes the 422 error school admins were seeing.
- Tests: `backend/tests/test_iter35_login_parent_toggle.py` — 25/25 pass.


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

## Iteration — 2026-01 (current session, part 4)
**In-app chat (WebSocket-based real-time messaging)**

### Backend (`/app/backend/routes/messaging.py`)
- `WS /api/messaging/ws` — JWT auth via `access_token` cookie or `?token=` query.
  Fans out `message` / `typing` / `read` events; in-process `ConnectionManager`
  keyed by user_id supports multiple devices per user.
- `GET /api/messaging/contacts` — role-gated peer list:
  - school_admin → all teachers in the same school
  - teacher → school_admins + parents of students in the teacher's (class, section) mappings
  - parent → class teacher(s) of their own children only
- `GET /api/messaging/conversations` — threads with last_message + unread count, sorted desc.
- `GET /api/messaging/conversations/{peer_id}/messages` — chronological history, `?before=` pagination.
- `POST /api/messaging/conversations/{peer_id}/messages` — persist + WS fan-out.
- `POST /api/messaging/conversations/{peer_id}/read` — marks recipient's unread to 0 and flips read_at.
- `POST /api/messaging/conversations/{peer_id}/typing` — REST fallback for typing events.
- `GET /api/messaging/unread-count` — total unread for sidebar/bottom-nav badge.
- Storage in per-school tenant DB: `messages` + `conversations` collections.
  Conversation key = sorted `[participants[a], participants[b]]`.
- Indexes added to `init_school_db` in `core/db.py`.

### Frontend
- `pages/shared/ChatPage.jsx` — two-pane layout (contacts + window), mobile
  drill-in pattern with back button, search, animated bubbles, read receipts
  (single ✓ sent / filled ✓ read), live typing dots, "Live" WS status pill.
- `hooks/useMessagingSocket.js` — auto-reconnecting WebSocket client with
  exponential backoff.
- `hooks/useUnreadChat.js` — polls /unread-count every 25s + on focus +
  on `scms:chat:refresh-unread` custom event.
- `components/Sidebar.jsx` — new Chat entry for school_admin / teacher / parent
  with unread badge.
- `components/MobileBottomNav.jsx` — bottom nav now available for teacher and
  school_admin (previously parent-only), each with a Chat tab + badge.
- `App.js` — `/chat` route for the three eligible roles.
- `index.css` — chat layout, message bubble enter animation, typing-dot
  blink, contact-row hover, online pulse, mobile responsive grid that
  swaps list/window via `.is-shown`.

### Backend tests (12/12 pass)
`tests/test_messaging.py` — contacts RBAC, send/receive auth, conversation
ordering, read receipts/unread-count, typing auth, full WS round-trip.

## Backlog / Next
- P2: file/image attachments in chat
- P2: push notifications when a chat message arrives while offline
- P2: archive / delete conversation

## Iteration — 2026-01 (current session, part 5)
**Chat polish: mute, @mentions, attachments, web push, history cap**

### Backend (`/app/backend/routes/messaging.py`)
- `POST /messaging/conversations/{peer_id}/mute` + `GET /…/settings` — per-user
  mute flag stored in `conv_settings` (tenant DB). Muted threads stop bumping
  the user's unread badge (mentions still break through).
- @mentions detected via `_detect_mentions` (regex against peer's name).
  Conversation `mention_for.{user}` counter incremented + WS event carries
  `message.mentions = [user_id]` to highlight on the recipient.
- Attachments: optional `attachment={name,type,size,data_url}` on send. Allowed
  MIME types: jpg/png/webp/gif/pdf, ≤ ~1.8 MB raw. Stored base64 in MongoDB.
- History cap: `_trim_conversation_history` after every send keeps only the
  latest `CHAT_HISTORY_MAX=10` rows per conversation (env-tunable). Older
  messages are auto-deleted.
- Web Push (VAPID) — `GET /messaging/push/config`, `POST /push/subscribe`,
  `POST /push/unsubscribe`. Send-message triggers a push to the peer iff the
  peer is offline (no WS) AND the thread is not muted (mentions bypass mute).
- Master DB collection `push_subscriptions` (unique by endpoint).
- New `pywebpush` + `py-vapid` Python deps; VAPID keys in `backend/.env`.

### Frontend
- `pages/shared/ChatPage.jsx` — chat header now has push-enable (bell) + mute
  (bell-slash) toggle. Composer has a paperclip for attachments (image
  preview / file chip), an @-mention auto-complete menu, and inline rendering
  of mentions with a flash highlight on the recipient side. Contact rows
  show an `@` badge for unread mentions and a bell-slash icon for muted convs.
- `hooks/useWebPush.js` — registers `/sw.js`, calls `/push/config` for the
  VAPID public key, then subscribes via `pushManager.subscribe`.
- `hooks/useUnreadChat.js` — now exposes `{count, mentions}`.
- `public/sw.js` — service worker handling `push` + `notificationclick` (focus
  existing tab or open `/chat`).

### Tests
- `tests/test_iter30_messaging_v2.py` (10 new) — history cap, mute, mentions,
  attachments (allowed + rejected MIME), push subscribe/unsubscribe,
  unread-count vs mute interaction.
- Combined with iter29: **22/22 pass**.

## Iteration — 2026-01 (current session, part 6)
**Chat: Group broadcasts, channel-update mirror, hardened trim**

### Backend
- **Group chat** (`groups`, `group_messages` collections in tenant DB):
  - Auto-provisioned via `_ensure_admin_to_teachers_group` (per admin) and
    `_ensure_teacher_to_class_parents_groups` (one per teacher × class-section).
  - Members are read-only; only the owner can POST.
  - Endpoints: `GET /messaging/groups`, `GET /…/{id}/messages`,
    `POST /…/{id}/messages`, `POST /…/{id}/read`.
  - History capped at `CHAT_HISTORY_MAX` (10) using keep-set delete.
  - WS event `group_message` fanned out to every member.
- **Channel-update mirror**: `core/notify.py:queue_notification` now also
  writes to per-school `chat_updates` for whatsapp/sms/telegram/email
  channels (regardless of provider delivery status). Trimmed to the latest
  7 per `(recipient_id, related_student_id)` on every insert.
- **Endpoints**: `GET /messaging/updates`, `…/unread-count`, `…/mark-all-read`.
- **Hardened 1-1 history trim**: switched from `$lte cutoff` to id-based
  keep-set (`delete WHERE id NOT IN <latest_10_ids>`) — eliminates the edge
  case where identical `created_at` could evict a kept row.
- **Confirmed**: student photo upload still stores base64 in MongoDB
  (`students.photo` data URL); no Azure dependency.

### Frontend
- `pages/shared/ChatPage.jsx`:
  - Top tab switcher `[Chats | Updates]` inside the contact panel.
  - `GroupRow` with megaphone for owners + scope badge ("Teacher → Parents"
    or "Admin → Teachers"); "Broadcast Groups" section above "Direct"
    contacts.
  - `UpdateCard` with channel-coloured left border (WhatsApp green,
    Telegram blue, SMS amber, Email blue) and student-name header for
    parents.
  - Group chat thread: locked composer for members ("Read-only — only the
    school admin / your class teacher can post"); owner sees a regular
    composer with "Broadcast to N members" placeholder.
  - WS `group_message` event handler updates open thread + group list.
  - `index.css` — `.chat-tabs`, `.chat-update-card`, `.chat-group-avatar`,
    `.chat-composer-locked` styles + entrance animations.

### Tests
- `tests/test_iter31_groups_updates.py` (14 new). Combined with iter29 +
  iter30: **36/36 pass**.

### Verified end-to-end
- Admin → all teachers broadcast received over WebSocket
- Teacher → class parents broadcast received and visible in parent's UI
- Parent's Updates tab shows latest 7 Telegram-channel mirrors
- 1-1 chat trim retains exactly the newest 10 by send order
- Cross-class teacher cannot post to / read another teacher's group (403)

## Iteration — 2026-01 (current session, part 7)
**Chat: System "School Notifications" peer + Group mute + Pin broadcast**

### Backend (`/app/backend/routes/messaging.py`)
- **System virtual peer** `SYSTEM_PEER_ID = "system::school-notifications"` —
  no DB row. Surfaced as a contact at the top of every user's list.
  - `list_messages` synthesises message-shaped dicts from `chat_updates`
    rows when peer_id == SYSTEM_PEER_ID (carries channel/student_name).
  - `mark_read` flips read_at on chat_updates.
  - `get_conv_settings` returns `muted: false` (no per-user mute on the
    system feed; users should always see school alerts).
- **Per-group mute**: reuses `conv_settings` collection with
  `conv_id = "group:{group_id}"`. Endpoints `POST /groups/{id}/mute` and
  `GET /groups/{id}/settings`. Group sends now web-push every non-muted,
  offline member.
- **Pin broadcast**: owner-only `POST /groups/{id}/pin {message_id, hours?}`
  (default 24h, max 168h) and `DELETE /groups/{id}/pin`. WS event
  `type='group_pin'` fanned to all members. `list_groups` auto-expires the
  pin when `pinned_until < now`.
- **`core/notify.py`** mirror also dispatches a `type='message'` WS event
  so the parent's open Chat page slides the new "School Notifications"
  message in real-time without a refresh.

### Frontend (`pages/shared/ChatPage.jsx`)
- **Updates tab removed** — single chat list view.
- `Avatar` gains `isSystem` branch (Buildings icon).
- `MessageBubble` renders a channel header (TELEGRAM / WHATSAPP / SMS /
  EMAIL with brand colours) inside system bubbles + dashed-bottom separator.
- Group header: mute toggle, owner-only unpin button; group banner
  (`chat-pin-banner`) above thread when a pin exists.
- Group message bubble: hover-reveal pin button (owner only).
- System chat: locked composer with "read-only feed" copy.

### Tests
- `tests/test_iter32_system_peer_pin_mute.py` (16 new) + 
  `tests/test_iter32_app_regression.py` (15 broad-app regression).
- Combined with iter29 + iter30 + iter31: **67/67 pass**.

## Iteration — 2026-01 (current session, part 8)
**Chat: Semantic system bubbles + Parent quick-reply round-trip**

### Backend (`/app/backend/routes/messaging.py`)
- **Removed channel labels** (TELEGRAM/WHATSAPP/SMS/EMAIL) from system
  bubbles. Updates are now classified by **kind**:
  `attendance | fee | exam | sick | holiday | trip | general`.
- `_KIND_BY_TEMPLATE` maps 13 known templates + best-effort partial-match
  fallback. `_classify_update()` returns `{kind, label, color, quick_replies}`.
- `_chat_update_to_message` emits `kind, kind_label, kind_color, subject,
  quick_replies, replied_at, reply_text, student_name, student_uid` instead
  of the old `channel` field.
- **POST `/messaging/system/reply` {update_id, text}** — parent (or any
  user) sends a quick-reply that:
  1. Is routed via `_resolve_reply_recipient`:
     - attendance / sick / exam (with related_student_id) → child's
       class teacher (via `class_teacher_map`).
     - fee or unknown → first `school_admin` of the school.
  2. Persists as a regular 1-1 chat message prefixed with
     `↩︎ Re: <subject> · <student name> (<UID>)` for traceability.
  3. Reuses `_upsert_conversation` + `_trim_conversation_history` so all
     existing plumbing (WS / push / unread / 10-msg cap) fires.
  4. Stamps `chat_updates.replied_at` + `reply_text` + `reply_recipient_id`
     so the UI hides quick-reply chips on subsequent loads.
  5. WS-fans to both sender and recipient, web-pushes if recipient offline.
- 409 on second reply, 404 when caller doesn't own the update.

### Frontend (`pages/shared/ChatPage.jsx`)
- `KIND_META` palette with kind-icon (ClipboardText, Receipt, GraduationCap,
  Heartbeat, CalendarBlank, AirplaneTilt, Buildings).
- `MessageBubble` renders a dedicated `.chat-system-card` for system msgs:
  coloured 4 px left border, icon tile, semantic title, optional
  "For <student> · <UID>" subtitle, body.
- `.chat-quick-replies` row of pill buttons; tap → `sendQuickReply`
  optimistically marks replied, POSTs `/system/reply`, toast
  "Sent to <staff name>". Replied state shows
  "✓ You replied: '…'" pill.
- All chip / done states carry data-testid for testability.

### Tests
- `tests/test_iter33_system_replies.py` (14 new). Combined with all prior
  suites: **66/66** when each is run as a separate pytest process
  (motor's first-touched event-loop binding prevents bundling — already
  the documented regression mode).

## Iteration — 2026-01 (current session, part 9)
**Chat: expanded contact matrix + smart-action follow-through**

### Backend (`/app/backend/routes/messaging.py`)
- **Expanded `_is_allowed_peer` matrix** — symmetric OPEN_PAIRS:
  `school_admin↔teacher`, `school_admin↔parent`, `school_admin↔accounts`,
  `accounts↔parent`. `teacher↔parent` still gated by `class_teacher_map`.
- **`list_contacts` per role**:
  - `school_admin` → teachers + accounts + parents
  - `teacher` → school_admins + parents-of-own-class (existing)
  - `parent` → principal(s) + class teacher(s) + accounts (with `context`
    labels for triage)
  - `accounts` → school_admins + ALL parents (enriched with child-name
    context "Parent of <Name> (<UID>), <Name> (<UID>) +N more")
- **Accounts role enabled** for chat throughout (was previously excluded).
- **Smart actions embedded on `/system/reply`** — the 1-1 message persisted
  to the recipient carries `smart_actions: [...]` derived from the source
  update's kind + the parent's chosen reply phrase:
  - attendance/sick + "unwell" → mark_absent_today, approve_sick_leave (3d),
    send_wellness_check
  - attendance/sick + "tomorrow/be there" → mark_absent_today
  - fee + "pay today" → send_payment_link, acknowledge_reply
  - fee + "extension" → grant_fee_extension (7d), acknowledge_reply
- **`POST /messaging/messages/{id}/smart-action`** — recipient executes one
  of the suggestions. Role-gated via `_SMART_ACTION_ROLES`. Idempotent via
  `smart_action_done` stamp (409 on dup). Outcomes:
  - `mark_absent_today` → upsert `attendance` row for today, status=absent
  - `approve_sick_leave` → insert approved `sick_leaves` row from today
    spanning N days
  - `send_wellness_check` → enqueue in `wellness_checks` collection
  - `send_payment_link` → sends a follow-up 1-1 message to parent with the
    `/parent/fees` URL (env-based base)
  - `grant_fee_extension` → 1-1 follow-up granting N-day extension
  - `acknowledge_reply` → simple "Got it, thanks" follow-up
- **WS event `type='smart_action_done'`** fanned to every conv participant
  so the parent sees the outcome live without refresh.

### Frontend (`pages/shared/ChatPage.jsx`)
- `MessageBubble` now renders an orange dashed "⚡ Suggested actions" row
  under any quick-reply bubble received by staff. Tap → toast w/ outcome,
  bubble collapses to a green `chat-smart-action-done` outcome line.
- WS listener for `smart_action_done` keeps remote tabs in sync.
- Updated CSS (`.chat-smart-actions`, `.chat-smart-action`, …).

### Tests (`tests/test_iter34_contacts_smart_actions.py`, 15 new)
- Combined across 6 chat suites: **81/81 pass** (each run as separate
  pytest invocation per motor-loop binding).
