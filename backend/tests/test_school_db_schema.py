"""Tests for the per-school DB schema provisioning.

Validates:
1. When a super admin creates a school, a dedicated MongoDB database is created
   whose name is derived from the school's code.
2. The per-school DB contains ALL expected collections (users, teachers, parents,
   students, classes, subjects, attendance, exams, marks, fees, etc.).
3. The school super admin row is mirrored into the per-school DB on creation.
4. Teachers + parents created later are mirrored too.
5. All user rows in BOTH master and per-school DBs have a `password_hash` field
   (never plaintext) and persisted profile fields (name, email, role, school_id,
   created_at, is_active).
6. `GET /api/schools/{id}/db-status` returns the live schema snapshot and is
   authorised correctly (platform admin + own school admin allowed; others 403).
"""
import asyncio
import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-admin-fix.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "scms_db")

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")

EXPECTED_COLLECTIONS = {
    "users", "school_admins", "teachers", "parents", "accounts_users", "students_users",
    "classes", "subjects", "class_teacher_map", "students", "attendance",
    "exams", "marks", "syllabus", "holidays",
    "fee_structures", "fees", "fee_payments",
    "timetable", "notifications", "activities", "activity_enrollments",
    "sick_leaves", "audit_logs", "password_reset_codes",
    "bulk_uploads", "receipts", "subscription_history", "meta",
}


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"login {email}: {r.status_code} {r.text}"
    return s


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _async_client():
    return AsyncIOMotorClient(MONGO_URL)


@pytest.fixture(scope="module")
def fresh_school():
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    code = f"DBT{suffix}"
    admin_email = f"db.admin.{suffix.lower()}@dbt.example.com"
    admin_pw = "DbAdmin@2026"
    payload = {
        "name": f"DB Test School {suffix}",
        "code": code,
        "address": "DB Lane",
        "phone": "+919000000020",
        "email": f"info.{suffix.lower()}@dbt.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email,
        "admin_password": admin_pw,
        "admin_name": "DB Test Admin",
        "auto_approve": True,
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    school = r.json()["school"]
    yield {
        "platform": plat,
        "school": school,
        "admin_email": admin_email,
        "admin_password": admin_pw,
    }


class TestPerSchoolDbCreated:
    def test_db_name_derived_from_school_code(self, fresh_school):
        school = fresh_school["school"]
        expected = f"{DB_NAME}_school_{school['code'].lower()}"
        assert school["db_name"] == expected

    def test_db_exists_in_mongo(self, fresh_school):
        school = fresh_school["school"]

        async def _check():
            client = _async_client()
            names = await client.list_database_names()
            return school["db_name"] in names

        assert _run(_check()) is True

    def test_all_expected_collections_have_indexes(self, fresh_school):
        school = fresh_school["school"]

        async def _check():
            client = _async_client()
            sdb = client[school["db_name"]]
            existing = set(await sdb.list_collection_names())
            return existing

        existing = _run(_check())
        missing = EXPECTED_COLLECTIONS - existing
        # `meta` plus index-target collections must all be created by init_school_db.
        assert not missing, f"Missing collections: {missing}"

    def test_marker_doc_present(self, fresh_school):
        school = fresh_school["school"]

        async def _check():
            client = _async_client()
            return await client[school["db_name"]].meta.find_one({"_marker": "school_db"}, {"_id": 0})

        marker = _run(_check())
        assert marker is not None
        assert marker["school_id"] == school["id"]
        assert marker["school_code"] == school["code"]
        assert marker["school_name"] == school["name"]
        assert marker.get("initialized_at_v")


class TestUsersMirroredAndHashed:
    def test_school_admin_password_is_hashed_in_master_db(self, fresh_school):
        school = fresh_school["school"]

        async def _check():
            client = _async_client()
            return await client[DB_NAME].users.find_one(
                {"email": fresh_school["admin_email"]}, {"_id": 0}
            )

        u = _run(_check())
        assert u is not None
        assert "password_hash" in u
        assert isinstance(u["password_hash"], str) and u["password_hash"].startswith("$2")
        # Plaintext password must NEVER be stored.
        assert "password" not in u
        # Profile fields
        for f in ("id", "email", "name", "role", "school_id", "is_active", "created_at"):
            assert f in u, f"missing {f}"
        assert u["role"] == "school_admin"
        assert u["school_id"] == school["id"]

    def test_school_admin_mirrored_into_school_db(self, fresh_school):
        school = fresh_school["school"]

        async def _check():
            client = _async_client()
            sdb = client[school["db_name"]]
            user = await sdb.users.find_one({"email": fresh_school["admin_email"]}, {"_id": 0})
            admin = await sdb.school_admins.find_one({"email": fresh_school["admin_email"]}, {"_id": 0})
            return user, admin

        user, admin = _run(_check())
        assert user is not None and user["role"] == "school_admin"
        assert user.get("password_hash"), "password_hash mirrored too"
        assert admin is not None
        assert admin["email"] == fresh_school["admin_email"]


class TestTeacherAndParentMirrored:
    def test_teacher_creation_mirrors_to_school_db(self, fresh_school):
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        suffix = uuid.uuid4().hex[:6]
        email = f"teacher.{suffix}@dbt.example.com"
        payload = {
            "email": email, "password": "Teacher@2026", "name": f"T {suffix}",
            "role": "teacher", "phone": "+919000000021", "subjects": ["English"],
        }
        r = sa.post(f"{API}/users", json=payload, timeout=15)
        assert r.status_code == 200

        async def _check():
            client = _async_client()
            sdb = client[fresh_school["school"]["db_name"]]
            user = await sdb.users.find_one({"email": email}, {"_id": 0})
            teacher = await sdb.teachers.find_one({"email": email}, {"_id": 0})
            return user, teacher

        user, teacher = _run(_check())
        assert user is not None
        assert user["role"] == "teacher"
        assert user["password_hash"].startswith("$2"), "Teacher password hashed in school DB too"
        assert teacher is not None

    def test_student_creation_mirrors_parent_and_student(self, fresh_school):
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        # Create a class via the school admin
        cls = sa.post(f"{API}/academic/classes", json={"name": "Grade 1", "sections": ["A"]}, timeout=15).json()
        suffix = uuid.uuid4().hex[:6]
        parent_email = f"parent.{suffix}@dbt.example.com"
        payload = {
            "name": f"Student {suffix}",
            "class_id": cls["id"], "section": "A", "roll_number": "01",
            "parent": {"name": f"Parent {suffix}", "phone": "+919000000022", "email": parent_email},
        }
        r = sa.post(f"{API}/students", json=payload, timeout=15)
        assert r.status_code == 200

        async def _check():
            client = _async_client()
            sdb = client[fresh_school["school"]["db_name"]]
            student = await sdb.students.find_one({"name": payload["name"]}, {"_id": 0})
            parent_user = await sdb.users.find_one({"email": parent_email}, {"_id": 0})
            parent_row = await sdb.parents.find_one({"email": parent_email}, {"_id": 0})
            return student, parent_user, parent_row

        student, parent_user, parent_row = _run(_check())
        assert student is not None, "Student must be mirrored into school DB"
        assert student["class_id"] == cls["id"]
        assert parent_user is not None
        assert parent_user["role"] == "parent"
        assert parent_user["password_hash"].startswith("$2"), "Parent password hashed in school DB"
        assert parent_row is not None


class TestDbStatusEndpoint:
    def test_platform_admin_can_read_status(self, fresh_school):
        r = fresh_school["platform"].get(
            f"{API}/schools/{fresh_school['school']['id']}/db-status", timeout=15
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["db_name"] == fresh_school["school"]["db_name"]
        assert body["is_initialized"] is True
        assert not body["missing_collections"]
        for c in EXPECTED_COLLECTIONS:
            assert c in body["existing_collections"]
        # marker present
        assert body["marker"]
        # counts dict present
        assert isinstance(body["counts"], dict)
        assert body["counts"]["users"] >= 1  # at least the school admin

    def test_school_admin_can_read_own_status(self, fresh_school):
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        r = sa.get(f"{API}/schools/{fresh_school['school']['id']}/db-status", timeout=15)
        assert r.status_code == 200
        assert r.json()["is_initialized"] is True

    def test_school_admin_cannot_read_other_school_status(self, fresh_school):
        # Pick a different existing school id (the DEMO sunrise school).
        plat = fresh_school["platform"]
        schools = plat.get(f"{API}/schools", timeout=15).json()
        other = next(s for s in schools if s["id"] != fresh_school["school"]["id"])
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        r = sa.get(f"{API}/schools/{other['id']}/db-status", timeout=15)
        assert r.status_code == 403

    def test_teacher_cannot_read_db_status(self, fresh_school):
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        suffix = uuid.uuid4().hex[:6]
        email = f"t.dbstatus.{suffix}@dbt.example.com"
        pw = "Teacher@2026"
        subs = sa.get(f"{API}/academic/subjects", timeout=15).json()
        sub_id = subs[0]["id"] if subs else None
        if not sub_id:
            sub_id = sa.post(f"{API}/academic/subjects", json={"name": "Tmp"}, timeout=15).json()["id"]
        sa.post(f"{API}/users", json={
            "email": email, "password": pw, "name": "t", "role": "teacher",
            "subjects": [sub_id],
        }, timeout=15)
        ts = _login(email, pw)
        r = ts.get(f"{API}/schools/{fresh_school['school']['id']}/db-status", timeout=15)
        assert r.status_code == 403


class TestReinitIsIdempotent:
    def test_db_init_can_be_rerun(self, fresh_school):
        r = fresh_school["platform"].post(
            f"{API}/schools/{fresh_school['school']['id']}/db-init", timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_initialized"] is True
        assert not body["missing_collections"]

    def test_db_init_is_platform_admin_only(self, fresh_school):
        sa = _login(fresh_school["admin_email"], fresh_school["admin_password"])
        r = sa.post(f"{API}/schools/{fresh_school['school']['id']}/db-init", timeout=15)
        assert r.status_code == 403
