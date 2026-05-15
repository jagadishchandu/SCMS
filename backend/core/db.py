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


async def init_school_db(school: dict):
    """Create initial schema/indexes for a school's dedicated database.
    Idempotent — safe to call repeatedly."""
    sdb = get_school_db(school)
    await sdb.students.create_index("student_uid", unique=True)
    await sdb.students.create_index([("class_id", 1), ("section", 1)])
    await sdb.attendance.create_index([("student_id", 1), ("date", 1)], unique=True)
    await sdb.attendance.create_index([("class_id", 1), ("section", 1), ("date", 1)])
    await sdb.marks.create_index([("student_id", 1), ("exam_id", 1), ("subject_id", 1)], unique=True)
    await sdb.classes.create_index("name")
    await sdb.subjects.create_index("name")
    await sdb.exams.create_index([("class_id", 1), ("start_date", 1)])
    await sdb.fees.create_index([("student_id", 1), ("structure_id", 1)])
    await sdb.fee_payments.create_index("fee_id")
    await sdb.holidays.create_index("date")
    await sdb.timetable.create_index([("teacher_id", 1), ("day", 1)])
    await sdb.notifications.create_index([("created_at", -1)])
    await sdb.activities.create_index("name")
    await sdb.activity_enrollments.create_index([("activity_id", 1), ("student_id", 1)], unique=True)
    await sdb.meta.update_one(
        {"_marker": "school_db"},
        {"$set": {
            "_marker": "school_db",
            "school_id": school["id"],
            "school_code": school.get("code"),
            "school_name": school.get("name"),
            "initialized_at_v": "1.3",
        }},
        upsert=True,
    )
    return school_db_name(school)


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
