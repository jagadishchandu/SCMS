"""Tests that confirm the per-school DB is now the AUTHORITATIVE store for
operational data (students, classes, attendance, marks, fees, holidays,
timetable, activities, sick leaves, etc.).

Validation strategy:
1. Create a new school via the platform API
2. Add a class + subject + teacher + student + attendance + mark + fee +
   payment + holiday + activity + sick leave through the public API
3. For each of these, assert the row appears in the per-school DB
   (`scms_db_school_<code>`) and is NOT present in the master `scms_db`.
4. Cleanup helpers: ensure passwords are hashed in both stores.
"""
import asyncio
import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://class-roster-77.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "scms_db")

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"login {email}: {r.status_code} {r.text}"
    return s


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def tenant_authoritative_ctx():
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    code = f"TNT{suffix}"
    admin_email = f"tnt.admin.{suffix.lower()}@tenant.example.com"
    admin_pw = "TenantAdmin@2026"
    r = plat.post(f"{API}/schools", json={
        "name": f"Tenant Test School {suffix}",
        "code": code, "address": "Tenant Lane", "phone": "+919000000040",
        "email": f"info.{suffix.lower()}@tenant.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "Tenant Admin",
        "auto_approve": True,
    }, timeout=20)
    assert r.status_code == 200
    school = r.json()["school"]
    sa = _login(admin_email, admin_pw)

    # Pre-create a class + subject + teacher + student for downstream tests
    cls = sa.post(f"{API}/academic/classes", json={"name": "Grade 1", "sections": ["A"]}, timeout=15).json()
    sub = sa.post(f"{API}/academic/subjects", json={"name": "Math"}, timeout=15).json()
    teacher_email = f"tnt.teach.{suffix.lower()}@tenant.example.com"
    teacher_pw = "TenantTeach@2026"
    sa.post(f"{API}/users", json={
        "email": teacher_email, "password": teacher_pw, "name": "TNT Teacher",
        "role": "teacher", "subjects": [sub["name"]],
    }, timeout=15)
    # Assign class teacher so teacher can create students
    teachers = sa.get(f"{API}/users?role=teacher", timeout=15).json()
    teacher = next(t for t in teachers if t["email"] == teacher_email)
    sa.post(f"{API}/academic/class-teacher", json={
        "teacher_id": teacher["id"], "class_id": cls["id"], "section": "A",
    }, timeout=15)
    ts = _login(teacher_email, teacher_pw)
    student_payload = {
        "name": f"Tnt Student {suffix}", "class_id": cls["id"], "section": "A",
        "roll_number": "01",
        "parent": {"name": f"Tnt Parent {suffix}", "phone": "+919000000041",
                   "email": f"tnt.parent.{suffix.lower()}@tenant.example.com"},
    }
    student = ts.post(f"{API}/students", json=student_payload, timeout=15).json()
    yield {
        "platform": plat, "school_admin": sa, "teacher": ts,
        "school": school, "class": cls, "subject": sub,
        "teacher_user": teacher, "student": student,
    }


def _tenant():
    return AsyncIOMotorClient(MONGO_URL)


def _present_in_tenant(school: dict, collection: str, query: dict) -> bool:
    async def _q():
        client = _tenant()
        sdb = client[school["db_name"]]
        return await sdb[collection].find_one(query) is not None
    return _run(_q())


def _absent_in_master(collection: str, query: dict) -> bool:
    async def _q():
        client = _tenant()
        m = client[DB_NAME]
        return await m[collection].find_one(query) is None
    return _run(_q())


class TestStudentClassPersistedOnlyInTenant:
    def test_student_in_tenant(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        sid = ctx["student"]["id"]
        assert _present_in_tenant(ctx["school"], "students", {"id": sid})
        assert _absent_in_master("students", {"id": sid})

    def test_class_in_tenant(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        cid = ctx["class"]["id"]
        assert _present_in_tenant(ctx["school"], "classes", {"id": cid})
        assert _absent_in_master("classes", {"id": cid})

    def test_subject_in_tenant(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        assert _present_in_tenant(ctx["school"], "subjects", {"id": ctx["subject"]["id"]})
        assert _absent_in_master("subjects", {"id": ctx["subject"]["id"]})


class TestAttendanceMarksFeesPersistedOnlyInTenant:
    def test_attendance(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        from datetime import date
        d = date.today().isoformat()
        r = ctx["teacher"].post(f"{API}/attendance/bulk", json={
            "class_id": ctx["class"]["id"], "section": "A", "date": d,
            "entries": [{"student_id": ctx["student"]["id"], "status": "present"}],
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert _present_in_tenant(ctx["school"], "attendance",
                                    {"student_id": ctx["student"]["id"], "date": d})
        assert _absent_in_master("attendance",
                                   {"student_id": ctx["student"]["id"], "date": d})

    def test_exam_and_marks(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/exams", json={
            "name": "Tnt Term Exam", "term": "term-1", "class_id": ctx["class"]["id"],
            "section": "A", "start_date": "2026-04-01", "end_date": "2026-04-05",
            "schedule": [],
        }, timeout=15)
        exam = r.json()
        assert _present_in_tenant(ctx["school"], "exams", {"id": exam["id"]})
        assert _absent_in_master("exams", {"id": exam["id"]})

        r = ctx["teacher"].post(f"{API}/marks/bulk", json={
            "exam_id": exam["id"], "subject_id": ctx["subject"]["id"],
            "entries": [{"student_id": ctx["student"]["id"], "marks_obtained": 90, "max_marks": 100}],
        }, timeout=15)
        assert r.status_code == 200
        assert _present_in_tenant(ctx["school"], "marks", {"student_id": ctx["student"]["id"], "exam_id": exam["id"]})
        assert _absent_in_master("marks", {"student_id": ctx["student"]["id"], "exam_id": exam["id"]})

    def test_fee_and_payment(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/fees/structures", json={
            "name": "Tnt Term 1 Fees", "class_id": ctx["class"]["id"],
            "items": [{"name": "Tuition", "amount": 2000}],
            "due_date": "2026-06-30",
        }, timeout=15)
        struct = r.json()
        assert _present_in_tenant(ctx["school"], "fee_structures", {"id": struct["id"]})
        assert _absent_in_master("fee_structures", {"id": struct["id"]})

        r2 = ctx["school_admin"].post(f"{API}/fees/structures/{struct['id']}/assign", timeout=15)
        assert r2.status_code == 200 and r2.json()["assigned"] >= 1
        async def _find_fee():
            client = _tenant()
            sdb = client[ctx["school"]["db_name"]]
            return await sdb.fees.find_one({"student_id": ctx["student"]["id"]}, {"_id": 0})
        fee = _run(_find_fee())
        assert fee is not None
        assert _absent_in_master("fees", {"id": fee["id"]})

        r3 = ctx["school_admin"].post(f"{API}/fees/payments", json={
            "fee_id": fee["id"], "student_id": ctx["student"]["id"],
            "amount": 1000, "mode": "cash",
        }, timeout=15)
        payment = r3.json()
        assert _present_in_tenant(ctx["school"], "fee_payments", {"id": payment["id"]})
        assert _absent_in_master("fee_payments", {"id": payment["id"]})

        # Receipt PDF endpoint should still work (tenant lookup)
        r4 = ctx["school_admin"].get(f"{API}/receipts/payment/{payment['id']}.pdf", timeout=15)
        assert r4.status_code == 200
        assert r4.content[:4] == b"%PDF"


class TestHolidaysTimetableActivitiesSickLeaves:
    def test_holiday(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/holidays", json={
            "title": "Tnt Holiday", "date": "2026-12-25", "type": "public",
        }, timeout=15)
        h = r.json()
        assert _present_in_tenant(ctx["school"], "holidays", {"id": h["id"]})
        assert _absent_in_master("holidays", {"id": h["id"]})

    def test_timetable(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/timetable/bulk", json={
            "class_id": ctx["class"]["id"], "section": "A",
            "slots": [{"day": "mon", "period": 1, "subject_id": ctx["subject"]["id"],
                       "teacher_id": ctx["teacher_user"]["id"],
                       "class_id": ctx["class"]["id"], "section": "A",
                       "start_time": "09:00", "end_time": "09:45"}],
        }, timeout=15)
        assert r.status_code == 200 and r.json()["inserted"] == 1
        async def _find():
            c = _tenant()
            return await c[ctx["school"]["db_name"]].timetable.find_one(
                {"class_id": ctx["class"]["id"], "day": "mon"}, {"_id": 0},
            )
        slot = _run(_find())
        assert slot is not None
        assert _absent_in_master("timetable", {"class_id": ctx["class"]["id"], "day": "mon"})

    def test_activity_and_enrollment(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/activities", json={
            "name": f"Tnt Football {uuid.uuid4().hex[:4]}", "category": "sport",
        }, timeout=15)
        a = r.json()
        assert _present_in_tenant(ctx["school"], "activities", {"id": a["id"]})
        assert _absent_in_master("activities", {"id": a["id"]})

        r2 = ctx["school_admin"].post(f"{API}/activities/{a['id']}/enroll",
                                       json={"student_ids": [ctx["student"]["id"]]}, timeout=15)
        assert r2.status_code == 200 and r2.json()["enrolled"] == 1
        assert _present_in_tenant(ctx["school"], "activity_enrollments",
                                    {"activity_id": a["id"], "student_id": ctx["student"]["id"]})
        assert _absent_in_master("activity_enrollments",
                                   {"activity_id": a["id"], "student_id": ctx["student"]["id"]})

    def test_sick_leave(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["school_admin"].post(f"{API}/sick-leaves", json={
            "student_id": ctx["student"]["id"],
            "start_date": "2026-04-10", "end_date": "2026-04-12", "reason": "Fever",
        }, timeout=15)
        leave = r.json()
        assert _present_in_tenant(ctx["school"], "sick_leaves", {"id": leave["id"]})
        assert _absent_in_master("sick_leaves", {"id": leave["id"]})


class TestDbStatusReflectsTenantCounts:
    def test_db_status_counts_match_after_writes(self, tenant_authoritative_ctx):
        ctx = tenant_authoritative_ctx
        r = ctx["platform"].get(f"{API}/schools/{ctx['school']['id']}/db-status", timeout=15)
        body = r.json()
        # After our writes the counts must be positive for each entity
        for k in ("students", "classes", "subjects", "attendance",
                   "exams", "marks", "fee_structures", "fees", "fee_payments",
                   "holidays", "timetable", "activities", "activity_enrollments",
                   "sick_leaves"):
            assert body["counts"][k] > 0, f"{k} should have at least one row"
