# SCMS — Database Schema Reference

This document describes the SCMS multi-tenant MongoDB schema as of **v1.15**.
Every per-school operational collection lives in its own dedicated database; a
single master database holds cross-cutting tables. The schema is
auto-provisioned on backend startup — see *"Where the schema is created"* at
the bottom of this doc.

---

## 1. Two-tier database layout

```
┌────────────────────────────────────────────────────────────────────────┐
│                   MASTER DB   (DB_NAME, default `scms_db`)             │
│   Cross-cutting tables shared across all schools.                       │
│   See MASTER_ONLY_COLLECTIONS in core/db.py.                            │
└────────────────────────────────────────────────────────────────────────┘
                              │
              one row per school in `schools`
                              │
   ┌────────────┬─────────────┼─────────────┬────────────┐
   ▼            ▼             ▼             ▼            ▼
┌─────────────────────┐ ┌─────────────────────┐    …per-school DBs…
│  scms_db_school_demo│ │ scms_db_school_xyz  │
│  Operational data   │ │ Operational data    │
│  for SCHOOL "DEMO"  │ │ for SCHOOL "XYZ"    │
│  See TENANT_*       │ │ See TENANT_*        │
└─────────────────────┘ └─────────────────────┘
```

**DB name rule** — when a school is created, its dedicated DB is named:
```
{DB_NAME}_school_{slugify(school.code)}
```
Example: school with `code = "DEMO"` → `scms_db_school_demo`.

Resolution is done by `core.db.tenant_db(school_id_or_user)`. The mapping is
cached in-process so request-time lookup is free after the first hit.

---

## 2. MASTER DB collections

Each entry below shows the collection name, what it stores, and the indexes
provisioned by `core.db.ensure_indexes()` (called once on every startup).

### `users`
The single source of truth for authentication. Login is by email and must
work before we know which school the user belongs to — so this collection
must live in the master DB. Each row is **mirrored** into the per-school DB
when the user belongs to a school (see *Mirroring*).

| Field             | Type        | Notes                                                              |
|-------------------|-------------|--------------------------------------------------------------------|
| `id`              | `string`    | UUID-hex                                                           |
| `email`           | `string`    | Lowercased, unique                                                 |
| `password_hash`   | `string`    | bcrypt (`$2…`). Plaintext is **never** stored anywhere.            |
| `name`            | `string`    |                                                                    |
| `role`            | `enum`      | `platform_admin` / `school_admin` / `teacher` / `accounts` / `parent` / `student` |
| `school_id`       | `string?`   | Null for `platform_admin`                                          |
| `is_active`       | `bool`      |                                                                    |
| `phone`           | `string?`   |                                                                    |
| `subjects`        | `string[]?` | Teachers                                                           |
| `telegram_chat_id`| `int?`      | Set after the user runs `/start <STU-UID>` on the SCMS bot         |
| `language`        | `string?`   | `en` / `hi` / `te` / `ta` / `mr` / `bn` / `gu` / `kn` (i18n)       |
| `admin_review_score` | `int?`   | Manual teacher review (used by analytics)                          |
| `password_changed_at` | `datetime?` | Set on every password change                                    |
| `created_at`      | `datetime`  |                                                                    |

Indexes:
- `email` (unique)
- `(school_id, role)`
- `(role, is_active)`
- `telegram_chat_id`

### `schools`
| Field            | Type       | Notes                                                          |
|------------------|------------|----------------------------------------------------------------|
| `id`             | `string`   | UUID-hex                                                       |
| `code`           | `string`   | Unique business code (e.g. `DEMO`, `RST3BB8`)                  |
| `name`, `address`, `phone`, `email`, `academic_year` | `string` | |
| `db_name`        | `string`   | Computed `scms_db_school_<slug(code)>`                         |
| `status`         | `string`   | `active` / `inactive`                                          |
| `valid_until`    | `string?`  | YYYY-MM-DD — subscription expiry                                |
| `language`       | `string?`  | Default notification language                                  |
| `branding`       | `obj?`     | `{ logo, primary_color, tagline }`                             |
| `created_at`     | `datetime` |                                                                |

Indexes: `code` (unique), `status`, `db_name`.

### `plans`
Static pricing catalog (per-child monthly / yearly).
Index: `name`.

### `login_attempts`
Brute-force lock. Each failed login adds a row; auth code locks an identifier
after N failures in a window. Cleared on a successful password reset.

Indexes: `identifier`, `(identifier, created_at desc)`.

### `password_reset_codes`
6-digit OTPs sent to Telegram for the forgot-password flow. Codes are stored
as **bcrypt hashes** — never plaintext.

| Field              | Type        | Notes                                          |
|--------------------|-------------|------------------------------------------------|
| `id`               | `string`    |                                                |
| `email`            | `string`    | Lowercased                                     |
| `user_id`          | `string`    |                                                |
| `code_hash`        | `string`    | bcrypt of the 6-digit OTP                      |
| `channel`          | `string`    | `telegram`                                     |
| `telegram_chat_id` | `int`       |                                                |
| `created_at`       | `datetime`  |                                                |
| `expires_at`       | `datetime`  | 10 min after `created_at`                      |
| `attempts`         | `int`       | Wrong-code verify attempts; cap=5              |
| `consumed_at`      | `datetime?` | Null while active; set on use/expire/supersede |
| `consumed_reason`  | `string?`   | `used` / `expired` / `superseded` / `too_many_attempts` |

Indexes: `(email, created_at desc)`, `expires_at`.

### `whatsapp_inbound`, `whatsapp_status_updates`, `telegram_inbound`
Raw webhook events. We don't know the tenant before processing, so they land
in master and the handler routes to the right per-school DB if needed.

Indexes: `created_at desc` on all three.

### `audit_logs` (master)
Platform-wide audit feed. Every `log_action(...)` call also writes to the
per-school audit log (mirror) if `school_id` is provided.

Indexes: `created_at desc`, `action`, `school_id`, `actor_id`.

### `subscription_payments`
Cross-school payment ledger so Platform Admin can reconcile.

Indexes: `(school_id, created_at desc)`, `status`.

### `notifications`
Outbound message log (WhatsApp / Telegram / Email). Currently kept in master
for cross-school analytics; per-school dashboards filter by `school_id`.

Indexes: `(school_id, created_at desc)`, `status`, `channel`.

---

## 3. PER-SCHOOL DB collections

Each school's DB carries 29 collections. All operational reads/writes go
through `tenant_db(school_id)`. The schema is created by
`core.db.init_school_db(school)` and re-applied to every existing school on
every backend startup (so any schema change here lands on all schools without
a separate migration script).

### Identity mirror

| Collection         | Notes                                                                     |
|--------------------|---------------------------------------------------------------------------|
| `users`            | Mirror of master `users` rows for users belonging to this school. Same shape, same `password_hash`. Indexes: `email` (unique), `role`, `(role, is_active)`, `phone`, `telegram_chat_id`. |
| `school_admins`    | One row per school admin: `{ user_id, email, name, created_at }`          |
| `teachers`         | Same shape — for teachers                                                 |
| `parents`          | For parents (linked to `student_uid`)                                     |
| `accounts_users`   | For accounts role                                                         |
| `students_users`   | Reserved for future student login portal                                  |

Each role-marker collection has `user_id` and `email` unique sparse indexes.

### Academic structure

| Collection           | Key fields                                                                      | Indexes                                              |
|----------------------|---------------------------------------------------------------------------------|------------------------------------------------------|
| `classes`            | `id, school_id, name, sections[], created_at`                                   | `name`, `(name, sections)`                            |
| `subjects`           | `id, school_id, name, code?, created_at`                                        | `name`, `code` (sparse)                               |
| `class_teacher_map`  | `id, school_id, class_id, section, teacher_id, created_at`                      | `(class_id, section)` unique, `teacher_id`            |

### Students

| Collection  | Key fields                                                                                                                                                          | Indexes                                                                          |
|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| `students`  | `id, school_id, student_uid (STU-00xxx), name, class_id, section, roll_number, gender, dob, admission_date, parent {name, phone, whatsapp, email, relationship}, parent_user_id, status, photo (data URL), medical_notes, emergency_contact, created_at` | `student_uid` unique, `(class_id, section)`, `parent_user_id`, `status` |

### Attendance

| Collection    | Key fields                                                                                              | Indexes                                                                |
|---------------|---------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| `attendance`  | `id, school_id, student_id, class_id, section, date (YYYY-MM-DD), status (present/absent/sick/late/half_day/excused), remark, marked_by, marked_at` | `(student_id, date)` unique, `(class_id, section, date)`, `date`, `status` |

### Exams, marks, syllabus

| Collection | Key fields                                                                                                                                          | Indexes                                                                |
|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| `exams`    | `id, school_id, name, term, class_id, section, start_date, end_date, schedule[], is_published, published_at, created_at`                            | `(class_id, start_date)`, `status` (legacy)                            |
| `marks`    | `id, school_id, exam_id, subject_id, student_id, marks_obtained, max_marks, percentage, remark, entered_by, entered_at`                             | `(student_id, exam_id, subject_id)` unique, `(exam_id, class_id, section)` |
| `syllabus` | `id, school_id, exam_id, class_id, subject_id, title, content (markdown), version, uploaded_by, created_at`                                         | `(class_id, subject_id)`, `status`                                     |

### Calendar / fees / timetable

| Collection         | Key fields                                                                                                                  | Indexes                                                  |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------|
| `holidays`         | `id, school_id, title, date, end_date?, type (public/school/exam), description, created_at`                                 | `date`, `name` (legacy)                                  |
| `fee_structures`   | `id, school_id, class_id, name, items[{name,amount}], total, due_date, created_at`                                          | `(class_id, term)`, `name`                               |
| `fees`             | `id, school_id, structure_id, student_id, class_id, name, total, paid, due, due_date, status (pending/partial/paid), created_at` | `(student_id, structure_id)`, `status`               |
| `fee_payments`     | `id, school_id, fee_id, student_id, amount, mode (cash/upi/bank/card), note, receipt_no, recorded_by, created_at`           | `fee_id`, `(student_id, created_at desc)`, `receipt_no` (sparse) |
| `timetable`        | `id, school_id, class_id, section, day (mon..sat), period, subject_id, teacher_id, start_time, end_time, created_at`        | `(teacher_id, day)`, `(class_id, section, day)`          |

### Engagement & welfare

| Collection             | Key fields                                                                                                                | Indexes                                                          |
|------------------------|---------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| `notifications`        | (currently mirrored from master — see above)                                                                              | `created_at desc`, `status`, `channel`, `recipient`              |
| `activities`           | `id, school_id, name, category (sport/music/art/club/other), description, coach, schedule, is_active, created_at`         | `name`, `category`                                               |
| `activity_enrollments` | `id, school_id, activity_id, student_id, created_at`                                                                      | `(activity_id, student_id)` unique                               |
| `sick_leaves`          | `id, school_id, student_id, student_uid, start_date, end_date, reason, diagnosis, medical_certificate {filename, content_type, data_url, uploaded_by, uploaded_at}, recorded_by, recorded_by_role, created_at` | `(student_id, start_date)`, `status`, `end_date` |

### System

| Collection              | Key fields                                                                                          | Indexes                                                                   |
|-------------------------|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| `audit_logs`            | Mirror of master audit entries scoped to this school. Same shape as master `audit_logs`.            | `created_at desc`, `action`, `resource`, `actor_id`                       |
| `password_reset_codes`  | Mirror of resets initiated for users in this school (informational/audit).                          | `(email, created_at desc)`, `expires_at`, `consumed_at`                   |
| `bulk_uploads`          | `id, school_id, kind (students/attendance/holidays), rows, inserted, errors[], by, created_at`      | `created_at desc`, `kind`                                                 |
| `receipts`              | Cache of generated PDF receipts (optional; receipts also stream-on-demand).                          | `payment_id` (sparse), `created_at desc`                                  |
| `subscription_history`  | Per-school history of plan changes / renewals.                                                      | `created_at desc`, `status`                                               |
| `meta`                  | Schema version marker (single doc `_marker: school_db`).                                            | n/a                                                                       |

---

## 4. Mirroring

When a school is **first created** (or after a user is added later), the
following identity rows are also written into the per-school DB so the
school-side schema is fully populated:

| Trigger                                  | Master write                                  | Tenant mirror                                                                                                |
|------------------------------------------|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| `POST /api/schools` (creates school admin) | `users` (`role=school_admin`)                | `users`, `school_admins`                                                                                     |
| `POST /api/users` (teacher/accounts/parent) | `users`                                     | `users` + role-specific marker (`teachers` / `accounts_users` / `parents`)                                    |
| `POST /api/students` (creates parent user) | `users` (`role=parent`)                     | `users`, `parents`, and the student itself in `students`                                                     |
| `POST /api/uploads/students` (bulk Excel)  | `users` (parents)                           | `users`, `parents`, `students`, `bulk_uploads`                                                               |
| `log_action(...)`                          | `audit_logs`                                | `audit_logs` (per school)                                                                                    |

The `users` mirror keeps `password_hash` intact so per-school admins can audit
that passwords are properly hashed without ever touching master.

---

## 5. Where the schema is created

| File                                          | Role                                                                                                  |
|-----------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `backend/core/db.py :: ensure_indexes()`      | Runs once at startup; creates **master DB** indexes.                                                  |
| `backend/core/db.py :: init_school_db(school)`| Idempotent. Provisions ALL 29 collections + indexes in a school's tenant DB. Records `meta._marker`.  |
| `backend/server.py :: lifespan`               | On every startup, calls `ensure_indexes()`, seeds the platform admin + demo data, then loops over every school and calls `init_school_db()` + `migrate_master_to_tenant()`. So schema additions in `init_school_db` propagate automatically to all schools — no separate migration. |
| `backend/core/db.py :: migrate_master_to_tenant(school)` | One-time copy of `school_id`-scoped rows from master to tenant; idempotent (skips rows already in tenant by `id`).                                                                                                       |

To re-run the schema manually (e.g. after editing `init_school_db`):
```bash
# As platform admin:
curl -X POST $REACT_APP_BACKEND_URL/api/schools/<school_id>/db-init \
     -b <auth-cookie-jar>
```

To inspect the live schema state of a school:
```bash
# Platform admin OR that school's own school admin:
curl $REACT_APP_BACKEND_URL/api/schools/<school_id>/db-status \
     -b <auth-cookie-jar>
```
Response includes `expected_collections`, `existing_collections`,
`missing_collections`, per-collection `counts`, and the `meta` marker.

---

## 6. Schema versioning

`init_school_db()` stores `initialized_at_v` in the per-school `meta`
collection. When this version is bumped, future schema migrations can compare
against it to decide what to backfill. Today the version is `1.14` (the
collection-name fix for `class_teacher_map` shipped in v1.15 without bumping
the marker since the fix is index-only and `init_school_db` is idempotent).

---

## 7. Tests

End-to-end coverage:

| File                                                | What it proves                                                                                       |
|-----------------------------------------------------|------------------------------------------------------------------------------------------------------|
| `backend/tests/test_school_db_schema.py`            | DB created on school creation, 29 collections present, marker doc correct, users mirrored & hashed, `db-status` RBAC. |
| `backend/tests/test_tenant_authoritative.py`        | Every operational write (student/class/attendance/exam/mark/fee/payment/holiday/timetable/activity/sick leave) lands in tenant DB **only** (absent in master). |
| `backend/tests/test_e2e_school_flow.py`             | Super admin creates school → admin logs in → admin creates teacher → teacher creates student → parent logs in (with default password) → password change flow for every role. |
| `backend/tests/test_password_reset.py`              | Telegram-OTP password reset (codes stored hashed, TTL, attempt cap, replay protection).              |

Run the full backend test suite:
```bash
cd /app/backend && python -m pytest tests/ -q
```
Today: **229 passed** in ~90s.
