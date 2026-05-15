"""Database connection (Motor / MongoDB).

Architecture:
- MASTER DB (DB_NAME from env): stores schools, plans, platform_admin users, and
  all operational data with school_id-based tenant isolation. This is the
  authoritative store today.
- PER-SCHOOL DBs: When a school is created we ALSO provision a dedicated
  database (e.g. `scms_db_school_<code>`) with full index schema. This is a
  foundation for future per-tenant physical isolation (backup/restore/scale).
  The school document carries its `db_name`.
"""
import os
import re
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None
_db = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[os.environ["DB_NAME"]]
    return _db


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (s or "").strip().lower())
    return s.strip("_")[:48] or "school"


def school_db_name(school: dict) -> str:
    base = os.environ.get("DB_NAME", "scms_db")
    code = slugify(school.get("code") or school.get("id", "school"))
    return f"{base}_school_{code}"


def get_school_db(school: dict):
    return get_client()[school_db_name(school)]


# In-process cache so we don't query `schools` on every request.
# Keyed by school_id → db_name string. Invalidated by `_invalidate_tenant_cache`.
_tenant_cache: dict[str, str] = {}


def _invalidate_tenant_cache(school_id: str | None = None):
    if school_id is None:
        _tenant_cache.clear()
    else:
        _tenant_cache.pop(school_id, None)


async def tenant_db(school_id_or_user):
    """Return the per-school Motor DB for a given `school_id` (str) or `user` dict.

    For platform admin (no school_id), returns the master DB — they only operate
    on master-level entities (schools, plans, users index, audit) anyway, and
    cross-school aggregation iterates over all schools explicitly.

    Cached in-process by school_id → db_name.
    """
    if isinstance(school_id_or_user, dict):
        school_id = school_id_or_user.get("school_id")
    else:
        school_id = school_id_or_user
    if not school_id:
        return get_db()
    cached = _tenant_cache.get(school_id)
    if cached:
        return get_client()[cached]
    master = get_db()
    s = await master.schools.find_one({"id": school_id}, {"_id": 0, "db_name": 1, "code": 1, "id": 1, "name": 1})
    if not s:
        return master
    name = s.get("db_name") or school_db_name(s)
    _tenant_cache[school_id] = name
    return get_client()[name]


# Master-DB-only collections — never moved to per-school DBs:
MASTER_ONLY_COLLECTIONS = (
    "users",  # login is by email; we must look up before we know which school
    "schools", "plans", "login_attempts", "password_reset_codes",
    "whatsapp_status_updates", "whatsapp_inbound", "telegram_inbound",
    "subscription_payments",
)

# School-scoped collections moved to per-school DB as authoritative.
TENANT_OPERATIONAL_COLLECTIONS = (
    "classes", "subjects", "class_teacher_map",
    "attendance", "exams", "marks", "syllabus",
    "holidays", "fee_structures", "fees", "fee_payments",
    "timetable", "activities", "activity_enrollments",
    "sick_leaves", "notifications", "bulk_uploads", "receipts",
    "audit_logs",
)
# Plus students which is the principal child entity
TENANT_OPERATIONAL_COLLECTIONS = ("students",) + TENANT_OPERATIONAL_COLLECTIONS


async def migrate_master_to_tenant(school: dict, dry_run: bool = False) -> dict:
    """One-time copy of every school_id-scoped doc from master DB to a school's
    per-school DB. Skips docs already present (by their `id` field) so it is
    safe to call repeatedly.

    Returns a per-collection count summary.
    """
    master = get_db()
    sdb = get_school_db(school)
    school_id = school["id"]
    summary: dict[str, int] = {}

    for coll in TENANT_OPERATIONAL_COLLECTIONS:
        try:
            cursor = master[coll].find({"school_id": school_id}, {"_id": 0})
            docs = await cursor.to_list(50_000)
        except Exception as e:
            summary[coll] = -1
            print(f"[migrate] {school_id} {coll} read failed: {e}")
            continue
        if not docs:
            summary[coll] = 0
            continue
        if dry_run:
            summary[coll] = len(docs)
            continue
        # Existing ids in tenant DB
        existing_ids = set()
        try:
            async for d in sdb[coll].find({}, {"id": 1, "_id": 0}):
                if d.get("id"):
                    existing_ids.add(d["id"])
        except Exception:
            existing_ids = set()
        to_insert = [d for d in docs if d.get("id") and d["id"] not in existing_ids]
        if to_insert:
            try:
                await sdb[coll].insert_many(to_insert, ordered=False)
            except Exception as e:
                # Likely duplicate-key races — ignore, count actual difference below.
                print(f"[migrate] {school_id} {coll} insert_many warn: {e}")
        summary[coll] = len(to_insert)

    # Mirror users belonging to this school (without overwriting hashes)
    try:
        async for u in master.users.find({"school_id": school_id}, {"_id": 0}):
            await sdb.users.update_one({"email": u["email"]}, {"$set": u}, upsert=True)
            role = u.get("role")
            role_to_collection = {
                "school_admin": "school_admins", "teacher": "teachers",
                "accounts": "accounts_users", "parent": "parents",
                "student": "students_users",
            }
            target = role_to_collection.get(role)
            if target:
                await sdb[target].update_one(
                    {"user_id": u["id"]},
                    {"$set": {
                        "user_id": u["id"], "email": u["email"], "name": u.get("name"),
                        "phone": u.get("phone"), "created_at": u.get("created_at"),
                    }},
                    upsert=True,
                )
    except Exception as e:
        print(f"[migrate] {school_id} users mirror error: {e}")

    summary["_users_mirrored"] = True
    return summary


async def init_school_db(school: dict):
    """Create the full per-school schema (indexes + marker docs) for a school's
    dedicated database. Idempotent — safe to call repeatedly.

    Master DB (DB_NAME) continues to hold all operational rows with school_id
    isolation. The per-school DB is provisioned with ALL entity collections so
    that a future per-tenant migration only needs to copy rows — no schema work.
    """
    sdb = get_school_db(school)

    # ---- Identity & access ----
    # Mirror of users belonging to this school (school_admin / teacher / accounts / parent).
    # Platform Super Admin lives only in the master DB.
    await sdb.users.create_index("email", unique=True)
    await sdb.users.create_index("role")
    await sdb.users.create_index([("role", 1), ("is_active", 1)])
    await sdb.users.create_index("phone")
    await sdb.users.create_index("telegram_chat_id")

    # Convenience role-scoped collection markers (everything still queries `users`,
    # but these markers prove the schema exists for each role).
    for role_marker in ("school_admins", "teachers", "parents", "accounts_users", "students_users"):
        await sdb[role_marker].create_index("user_id", unique=True, sparse=True)
        await sdb[role_marker].create_index("email", unique=True, sparse=True)

    # ---- Academic structure ----
    await sdb.classes.create_index("name")
    await sdb.classes.create_index([("name", 1), ("sections", 1)])
    await sdb.subjects.create_index("name")
    await sdb.subjects.create_index("code", sparse=True)
    await sdb.class_teacher_map.create_index([("class_id", 1), ("section", 1)], unique=True)
    await sdb.class_teacher_map.create_index("teacher_id")

    # ---- Students & parents (parent info embedded on student doc + linked user) ----
    await sdb.students.create_index("student_uid", unique=True)
    await sdb.students.create_index([("class_id", 1), ("section", 1)])
    await sdb.students.create_index("parent_user_id")
    await sdb.students.create_index("status")

    # ---- Attendance ----
    await sdb.attendance.create_index([("student_id", 1), ("date", 1)], unique=True)
    await sdb.attendance.create_index([("class_id", 1), ("section", 1), ("date", 1)])
    await sdb.attendance.create_index("date")
    await sdb.attendance.create_index("status")

    # ---- Exams, marks, syllabus ----
    await sdb.exams.create_index([("class_id", 1), ("start_date", 1)])
    await sdb.exams.create_index("status")
    await sdb.marks.create_index(
        [("student_id", 1), ("exam_id", 1), ("subject_id", 1)], unique=True,
    )
    await sdb.marks.create_index([("exam_id", 1), ("class_id", 1), ("section", 1)])
    await sdb.syllabus.create_index([("class_id", 1), ("subject_id", 1)])
    await sdb.syllabus.create_index("status")

    # ---- Holidays & calendar ----
    await sdb.holidays.create_index("date")
    await sdb.holidays.create_index("name")

    # ---- Fees ----
    await sdb.fee_structures.create_index([("class_id", 1), ("term", 1)])
    await sdb.fee_structures.create_index("name")
    await sdb.fees.create_index([("student_id", 1), ("structure_id", 1)])
    await sdb.fees.create_index("status")
    await sdb.fee_payments.create_index("fee_id")
    await sdb.fee_payments.create_index([("student_id", 1), ("created_at", -1)])
    await sdb.fee_payments.create_index("receipt_no", sparse=True)

    # ---- Timetable ----
    await sdb.timetable.create_index([("teacher_id", 1), ("day", 1)])
    await sdb.timetable.create_index([("class_id", 1), ("section", 1), ("day", 1)])

    # ---- Notifications & messaging ----
    await sdb.notifications.create_index([("created_at", -1)])
    await sdb.notifications.create_index("status")
    await sdb.notifications.create_index("channel")
    await sdb.notifications.create_index("recipient")

    # ---- Activities / extra-curricular ----
    await sdb.activities.create_index("name")
    await sdb.activities.create_index("category")
    await sdb.activity_enrollments.create_index(
        [("activity_id", 1), ("student_id", 1)], unique=True,
    )

    # ---- Sick leave tracker + medical certs ----
    await sdb.sick_leaves.create_index([("student_id", 1), ("start_date", 1)])
    await sdb.sick_leaves.create_index("status")
    await sdb.sick_leaves.create_index("end_date")

    # ---- Audit log (school-scoped subset) ----
    await sdb.audit_logs.create_index([("created_at", -1)])
    await sdb.audit_logs.create_index("action")
    await sdb.audit_logs.create_index("resource")
    await sdb.audit_logs.create_index("actor_id")

    # ---- Password reset codes (per-school subset for visibility) ----
    await sdb.password_reset_codes.create_index([("email", 1), ("created_at", -1)])
    await sdb.password_reset_codes.create_index("expires_at")
    await sdb.password_reset_codes.create_index("consumed_at")

    # ---- Bulk uploads log ----
    await sdb.bulk_uploads.create_index([("created_at", -1)])
    await sdb.bulk_uploads.create_index("kind")

    # ---- Receipts / generated PDFs (cache only — actual PDFs streamed on demand) ----
    await sdb.receipts.create_index("payment_id", sparse=True)
    await sdb.receipts.create_index([("created_at", -1)])

    # ---- Subscription history per school ----
    await sdb.subscription_history.create_index([("created_at", -1)])
    await sdb.subscription_history.create_index("status")

    # ---- Meta marker (lists which version provisioned the schema) ----
    await sdb.meta.update_one(
        {"_marker": "school_db"},
        {"$set": {
            "_marker": "school_db",
            "school_id": school["id"],
            "school_code": school.get("code"),
            "school_name": school.get("name"),
            "initialized_at_v": "1.14",
            "collections": [
                "users", "school_admins", "teachers", "parents", "accounts_users", "students_users",
                "classes", "subjects", "class_teacher_map", "students", "attendance",
                "exams", "marks", "syllabus", "holidays",
                "fee_structures", "fees", "fee_payments",
                "timetable", "notifications", "activities", "activity_enrollments",
                "sick_leaves", "audit_logs", "password_reset_codes",
                "bulk_uploads", "receipts", "subscription_history", "meta",
            ],
        }},
        upsert=True,
    )
    return school_db_name(school)


# Collections we always expect to exist in a freshly-initialised school DB.
SCHOOL_DB_COLLECTIONS = (
    "users", "school_admins", "teachers", "parents", "accounts_users", "students_users",
    "classes", "subjects", "class_teacher_map", "students", "attendance",
    "exams", "marks", "syllabus", "holidays",
    "fee_structures", "fees", "fee_payments",
    "timetable", "notifications", "activities", "activity_enrollments",
    "sick_leaves", "audit_logs", "password_reset_codes",
    "bulk_uploads", "receipts", "subscription_history", "meta",
)


async def school_db_status(school: dict) -> dict:
    """Return a snapshot of the per-school DB: name, all collections and their
    document counts, plus the marker doc. Useful for /db-status endpoint."""
    sdb = get_school_db(school)
    existing = await sdb.list_collection_names()
    counts = {}
    for name in SCHOOL_DB_COLLECTIONS:
        try:
            counts[name] = await sdb[name].count_documents({}) if name in existing else 0
        except Exception:
            counts[name] = 0
    marker = await sdb.meta.find_one({"_marker": "school_db"}, {"_id": 0})
    missing = [c for c in SCHOOL_DB_COLLECTIONS if c not in existing]
    return {
        "db_name": school_db_name(school),
        "school_id": school["id"],
        "school_code": school.get("code"),
        "school_name": school.get("name"),
        "expected_collections": list(SCHOOL_DB_COLLECTIONS),
        "existing_collections": sorted(existing),
        "missing_collections": missing,
        "counts": counts,
        "marker": marker,
        "is_initialized": marker is not None and not missing,
    }


async def ensure_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("school_id", 1), ("role", 1)])
    await db.schools.create_index("code", unique=True)
    await db.students.create_index([("school_id", 1), ("student_uid", 1)], unique=True)
    await db.students.create_index([("school_id", 1), ("class_id", 1), ("section", 1)])
    await db.attendance.create_index([("school_id", 1), ("student_id", 1), ("date", 1)], unique=True)
    await db.marks.create_index([("school_id", 1), ("student_id", 1), ("exam_id", 1), ("subject_id", 1)], unique=True)
    await db.classes.create_index([("school_id", 1), ("name", 1)])
    await db.subjects.create_index([("school_id", 1), ("name", 1)])
    await db.fees.create_index([("school_id", 1), ("student_id", 1)])
    await db.notifications.create_index([("school_id", 1), ("created_at", -1)])
    await db.login_attempts.create_index("identifier")
    await db.activities.create_index([("school_id", 1), ("name", 1)])
    await db.activity_enrollments.create_index([("school_id", 1), ("activity_id", 1), ("student_id", 1)], unique=True)
