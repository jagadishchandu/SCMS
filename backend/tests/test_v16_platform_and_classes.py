"""Tests for v1.16 changes:
- Platform admin /schools/with-stats endpoint enriches each school with live counts
- Platform admin /schools/{id}/people lists teachers + students for one school
- Teachers can ADD class/subject/section, only school admin can REMOVE
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://classroom-messenger-1.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"v16.admin.{suffix.lower()}@v16.example.com"
    admin_pw = "Admin@2026"
    payload = {
        "name": f"V16 School {suffix}", "code": f"V16{suffix}",
        "address": "x", "phone": "+910", "email": f"info.{suffix.lower()}@v16.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "V16 Admin",
        "auto_approve": True,
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200
    school = r.json()["school"]
    sa = _login(admin_email, admin_pw)

    # Pre-create a subject so we can pass it when creating a teacher (now required).
    sub = sa.post(f"{API}/academic/subjects", json={"name": f"Sub {suffix}"}, timeout=15).json()

    teacher_email = f"v16.t.{suffix.lower()}@v16.example.com"
    teacher_pw = "Teach@2026"
    sa.post(f"{API}/users", json={
        "email": teacher_email, "password": teacher_pw, "name": f"V16 T",
        "role": "teacher", "subjects": [sub["id"]],
    }, timeout=15)
    ts = _login(teacher_email, teacher_pw)
    yield {
        "platform": plat, "school_admin": sa, "teacher": ts,
        "school": school, "admin_email": admin_email, "teacher_email": teacher_email,
    }


class TestPlatformOverviewEndpoints:
    def test_with_stats_enriches_each_school(self, ctx):
        r = ctx["platform"].get(f"{API}/schools/with-stats", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ours = next(s for s in data if s["id"] == ctx["school"]["id"])
        assert "stats" in ours
        for k in ("students", "teachers", "parents", "school_admins", "classes", "sections", "fee_due", "fee_collected"):
            assert k in ours["stats"], f"missing {k}"
        # Sanity: our brand-new school has at least 1 admin + 1 teacher we created
        assert ours["stats"]["school_admins"] >= 1
        assert ours["stats"]["teachers"] >= 1

    def test_with_stats_requires_platform_admin(self, ctx):
        r = ctx["school_admin"].get(f"{API}/schools/with-stats", timeout=15)
        assert r.status_code == 403

    def test_people_endpoint_returns_teachers_and_students(self, ctx):
        r = ctx["platform"].get(f"{API}/schools/{ctx['school']['id']}/people", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["school"]["id"] == ctx["school"]["id"]
        emails = [t["email"] for t in body["teachers"]]
        assert ctx["teacher_email"] in emails
        # Teacher row must not leak password hash
        sample = body["teachers"][0]
        assert "password_hash" not in sample
        assert "counts" in body and "teachers" in body["counts"]

    def test_people_own_school_admin_allowed(self, ctx):
        r = ctx["school_admin"].get(f"{API}/schools/{ctx['school']['id']}/people", timeout=15)
        assert r.status_code == 200

    def test_people_other_school_admin_forbidden(self, ctx):
        # Create a second school and try cross-access
        plat = ctx["platform"]
        suffix = uuid.uuid4().hex[:5].upper()
        r = plat.post(f"{API}/schools", json={
            "name": f"V16 Other {suffix}", "code": f"OTH{suffix}",
            "address": "y", "phone": "+911", "email": f"o.{suffix.lower()}@v16.example.com",
            "academic_year": "2025-2026",
            "admin_email": f"v16.other.{suffix.lower()}@v16.example.com",
            "admin_password": "Other@2026", "admin_name": "Other",
            "auto_approve": True,
        }, timeout=15)
        other = r.json()["school"]
        r2 = ctx["school_admin"].get(f"{API}/schools/{other['id']}/people", timeout=15)
        assert r2.status_code == 403

    def test_people_teacher_forbidden(self, ctx):
        r = ctx["teacher"].get(f"{API}/schools/{ctx['school']['id']}/people", timeout=15)
        assert r.status_code == 403


class TestTeacherCanAddClassSubjectSection:
    def test_teacher_can_create_class(self, ctx):
        r = ctx["teacher"].post(f"{API}/academic/classes", json={
            "name": "T-Added Class", "sections": ["A", "B"],
        }, timeout=15)
        assert r.status_code == 200, r.text
        cls = r.json()
        # Save for later tests
        ctx["t_class"] = cls
        assert sorted(cls["sections"]) == ["A", "B"]

    def test_teacher_can_create_subject(self, ctx):
        r = ctx["teacher"].post(f"{API}/academic/subjects", json={
            "name": "Robotics", "code": "ROB",
        }, timeout=15)
        assert r.status_code == 200, r.text
        ctx["t_subject"] = r.json()

    def test_teacher_can_add_section(self, ctx):
        # Use a class created by school admin
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Grade 9", "sections": ["A"],
        }, timeout=15).json()
        r = ctx["teacher"].post(f"{API}/academic/classes/{cls['id']}/sections",
                                  json={"section": "B"}, timeout=15)
        assert r.status_code == 200
        assert "B" in r.json()["sections"]

    def test_add_section_rejects_duplicate(self, ctx):
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Grade 8", "sections": ["A"],
        }, timeout=15).json()
        r = ctx["teacher"].post(f"{API}/academic/classes/{cls['id']}/sections",
                                  json={"section": "A"}, timeout=15)
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"].lower()


class TestOnlyPrincipalCanRemove:
    def test_teacher_cannot_delete_class(self, ctx):
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Doomed Class", "sections": ["A"],
        }, timeout=15).json()
        r = ctx["teacher"].delete(f"{API}/academic/classes/{cls['id']}", timeout=15)
        assert r.status_code == 403

    def test_teacher_cannot_delete_subject(self, ctx):
        sub = ctx["school_admin"].post(f"{API}/academic/subjects", json={"name": "Doomed Sub"}, timeout=15).json()
        r = ctx["teacher"].delete(f"{API}/academic/subjects/{sub['id']}", timeout=15)
        assert r.status_code == 403

    def test_teacher_cannot_remove_section(self, ctx):
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Section Test", "sections": ["A", "B"],
        }, timeout=15).json()
        r = ctx["teacher"].delete(f"{API}/academic/classes/{cls['id']}/sections/B", timeout=15)
        assert r.status_code == 403

    def test_school_admin_can_remove_section(self, ctx):
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Admin Removal", "sections": ["A", "B"],
        }, timeout=15).json()
        r = ctx["school_admin"].delete(f"{API}/academic/classes/{cls['id']}/sections/B", timeout=15)
        assert r.status_code == 200
        assert "B" not in r.json()["sections"]
        assert "A" in r.json()["sections"]

    def test_school_admin_can_delete_class(self, ctx):
        cls = ctx["school_admin"].post(f"{API}/academic/classes", json={
            "name": "Doomed by Admin", "sections": ["A"],
        }, timeout=15).json()
        r = ctx["school_admin"].delete(f"{API}/academic/classes/{cls['id']}", timeout=15)
        assert r.status_code == 200
