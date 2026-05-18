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
