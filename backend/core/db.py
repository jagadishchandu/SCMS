"""Database connection (Motor / MongoDB)."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None
_db = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        mongo_url = os.environ["MONGO_URL"]
        _client = AsyncIOMotorClient(mongo_url)
    return _client


def get_db():
    global _db
    if _db is None:
        db_name = os.environ["DB_NAME"]
        _db = get_client()[db_name]
    return _db


async def ensure_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("school_id", 1), ("role", 1)])
    await db.schools.create_index("code", unique=True)
    await db.students.create_index([("school_id", 1), ("student_uid", 1)], unique=True)
    await db.students.create_index([("school_id", 1), ("class_id", 1), ("section_id", 1)])
    await db.attendance.create_index([("school_id", 1), ("student_id", 1), ("date", 1)], unique=True)
    await db.marks.create_index([("school_id", 1), ("student_id", 1), ("exam_id", 1), ("subject_id", 1)], unique=True)
    await db.classes.create_index([("school_id", 1), ("name", 1)])
    await db.subjects.create_index([("school_id", 1), ("name", 1)])
    await db.fees.create_index([("school_id", 1), ("student_id", 1)])
    await db.notifications.create_index([("school_id", 1), ("created_at", -1)])
    await db.login_attempts.create_index("identifier")
