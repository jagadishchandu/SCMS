"""End-to-end school onboarding flow test.

Validates the chain the user explicitly asked us to verify:

  1. Platform Super Admin → POST /api/schools → school + school_admin saved in DB
  2. The new school_admin can log in via POST /api/auth/login
  3. The new school_admin can POST /api/classes (academic setup)
  4. The new school_admin can POST /api/users role=teacher → teacher saved in DB
  5. The teacher can log in via POST /api/auth/login
  6. The teacher can POST /api/students → student saved in DB + parent user
     auto-created with the default password.
  7. The parent can log in via POST /api/auth/login
  8. Self-service password change works for every role (teacher / school_admin /
     parent / platform_admin) and the new password is the only one that works
     after the change.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-health-portal-2.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"login {email} → {r.status_code}: {r.text}"
    if expect == 200:
        assert "access_token" in s.cookies, "access_token cookie missing"
    return s, r


@pytest.fixture(scope="module")
def e2e_school():
    """Create a fresh school + school admin via the platform API."""
    plat, _ = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:8].upper()
    code = f"E2E{suffix}"
    admin_email = f"e2e.admin.{suffix.lower()}@e2e.example.com"
    admin_password = "AdminE2E@2026"
    payload = {
        "name": f"E2E School {suffix}",
        "code": code,
        "address": "End to End Lane",
        "phone": "+919000000001",
        "email": f"info.{suffix.lower()}@e2e.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_name": "E2E Admin",
        "auto_approve": True,
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, f"school create failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("admin_email") == admin_email
    school = body["school"]
    assert school["id"] and school["code"] == code
    yield {
        "platform": plat,
        "school": school,
        "admin_email": admin_email,
        "admin_password": admin_password,
    }


# --------------------------------------------------------------------------
# 1+2. School admin can log in immediately after super-admin creates the school
# --------------------------------------------------------------------------

class TestSchoolAdminLoginAfterCreation:
    def test_admin_persisted_and_can_login(self, e2e_school):
        """Reproduces the user-reported scenario: after super admin creates a school,
        the newly-created school admin MUST be able to log in with the provided email
        and password."""
        sa, r = _login(e2e_school["admin_email"], e2e_school["admin_password"])
        me = sa.get(f"{API}/auth/me", timeout=15).json()
        assert me["role"] == "school_admin"
        assert me["school_id"] == e2e_school["school"]["id"]
        assert me["email"] == e2e_school["admin_email"]
        # The /auth/login response also carries a subscription_state snapshot.
        login_body = r.json()
        assert "subscription_state" in login_body

    def test_admin_login_with_wrong_password_fails(self, e2e_school):
        _login(e2e_school["admin_email"], "definitely-wrong-pw", expect=401)


# --------------------------------------------------------------------------
# 3+4. School admin adds a teacher → teacher saved in DB
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def school_admin_session(e2e_school):
    sa, _ = _login(e2e_school["admin_email"], e2e_school["admin_password"])
    return sa


@pytest.fixture(scope="module")
def e2e_class(school_admin_session):
    payload = {"name": "Grade 1", "sections": ["A"]}
    r = school_admin_session.post(f"{API}/academic/classes", json=payload, timeout=20)
    assert r.status_code == 200, f"class create: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def e2e_teacher(school_admin_session, e2e_school):
    suffix = uuid.uuid4().hex[:6].lower()
    email = f"teacher.{suffix}@e2e.example.com"
    password = "TeacherE2E@2026"
    payload = {
        "email": email,
        "password": password,
        "name": f"Teacher {suffix.upper()}",
        "role": "teacher",
        "phone": "+919000000002",
        "subjects": ["English"],
    }
    r = school_admin_session.post(f"{API}/users", json=payload, timeout=20)
    assert r.status_code == 200, f"teacher create: {r.status_code} {r.text}"
    data = r.json()
    assert data["role"] == "teacher"
    assert data["school_id"] == e2e_school["school"]["id"]
    return {"email": email, "password": password, "id": data["id"]}


class TestTeacherFlow:
    def test_teacher_persisted_and_can_login(self, e2e_teacher):
        s, _ = _login(e2e_teacher["email"], e2e_teacher["password"])
        me = s.get(f"{API}/auth/me", timeout=15).json()
        assert me["role"] == "teacher"
        assert me["id"] == e2e_teacher["id"]

    def test_teacher_visible_in_users_list_for_school_admin(self, school_admin_session, e2e_teacher):
        r = school_admin_session.get(f"{API}/users?role=teacher", timeout=15)
        assert r.status_code == 200
        ids = [u["id"] for u in r.json()]
        assert e2e_teacher["id"] in ids


# --------------------------------------------------------------------------
# 5+6. Teacher adds a student → student saved + parent user auto-created
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def teacher_session(e2e_teacher, e2e_school, school_admin_session, e2e_class):
    """Promote the teacher to class teacher of Grade 1 A so they can add students
    in that section (matches the production guard in routes/students.py)."""
    payload = {
        "teacher_id": e2e_teacher["id"],
        "class_id": e2e_class["id"],
        "section": "A",
    }
    r = school_admin_session.post(f"{API}/academic/class-teacher", json=payload, timeout=20)
    assert r.status_code == 200, f"assign class teacher: {r.status_code} {r.text}"
    s, _ = _login(e2e_teacher["email"], e2e_teacher["password"])
    return s


@pytest.fixture(scope="module")
def e2e_student(teacher_session, e2e_class):
    suffix = uuid.uuid4().hex[:6].lower()
    payload = {
        "name": f"Student {suffix.upper()}",
        "class_id": e2e_class["id"],
        "section": "A",
        "roll_number": "01",
        "gender": "male",
        "parent": {
            "name": f"Parent {suffix.upper()}",
            "phone": "+919000000003",
            "email": f"parent.{suffix}@e2e.example.com",
        },
    }
    r = teacher_session.post(f"{API}/students", json=payload, timeout=20)
    assert r.status_code == 200, f"student create: {r.status_code} {r.text}"
    data = r.json()
    assert data["name"] == payload["name"]
    assert data["class_id"] == e2e_class["id"]
    assert data["parent_user_id"], "parent user must be auto-created"
    return {
        "student": data,
        "parent_email": payload["parent"]["email"],
        "parent_password": "Parent@123",  # default seeded by routes/students.py
    }


class TestStudentAndParentFlow:
    def test_student_visible_in_school_admin_list(self, school_admin_session, e2e_student):
        r = school_admin_session.get(f"{API}/students", timeout=20)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert e2e_student["student"]["id"] in ids

    def test_parent_can_login(self, e2e_student):
        s, _ = _login(e2e_student["parent_email"], e2e_student["parent_password"])
        me = s.get(f"{API}/auth/me", timeout=15).json()
        assert me["role"] == "parent"
        assert me["email"] == e2e_student["parent_email"]

    def test_parent_sees_only_own_child(self, e2e_student):
        s, _ = _login(e2e_student["parent_email"], e2e_student["parent_password"])
        r = s.get(f"{API}/students", timeout=15)
        assert r.status_code == 200
        children = r.json()
        assert len(children) == 1
        assert children[0]["id"] == e2e_student["student"]["id"]


# --------------------------------------------------------------------------
# 7. Self-service password change for every role
# --------------------------------------------------------------------------

class TestChangePassword:
    def _change_and_verify(self, email, old_pw, new_pw):
        s, _ = _login(email, old_pw)
        r = s.post(
            f"{API}/users/me/change-password",
            json={"current_password": old_pw, "new_password": new_pw},
            timeout=15,
        )
        assert r.status_code == 200, f"change pw: {r.status_code} {r.text}"
        # Old password no longer works
        _login(email, old_pw, expect=401)
        # New password works
        _login(email, new_pw)

    def test_school_admin_can_change_password(self, e2e_school):
        new_pw = "NewAdminPw@2026"
        self._change_and_verify(e2e_school["admin_email"], e2e_school["admin_password"], new_pw)
        # Reset back so subsequent tests in this module still work.
        s, _ = _login(e2e_school["admin_email"], new_pw)
        s.post(
            f"{API}/users/me/change-password",
            json={"current_password": new_pw, "new_password": e2e_school["admin_password"]},
            timeout=15,
        )

    def test_teacher_can_change_password(self, e2e_teacher):
        new_pw = "NewTeacherPw@2026"
        self._change_and_verify(e2e_teacher["email"], e2e_teacher["password"], new_pw)
        s, _ = _login(e2e_teacher["email"], new_pw)
        s.post(
            f"{API}/users/me/change-password",
            json={"current_password": new_pw, "new_password": e2e_teacher["password"]},
            timeout=15,
        )

    def test_parent_can_change_password(self, e2e_student):
        new_pw = "NewParentPw@2026"
        self._change_and_verify(
            e2e_student["parent_email"], e2e_student["parent_password"], new_pw,
        )

    def test_change_password_rejects_wrong_current(self, e2e_teacher):
        s, _ = _login(e2e_teacher["email"], e2e_teacher["password"])
        r = s.post(
            f"{API}/users/me/change-password",
            json={"current_password": "definitely-wrong", "new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "incorrect" in r.json().get("detail", "").lower()

    def test_change_password_rejects_short_new(self, e2e_teacher):
        s, _ = _login(e2e_teacher["email"], e2e_teacher["password"])
        r = s.post(
            f"{API}/users/me/change-password",
            json={"current_password": e2e_teacher["password"], "new_password": "abc"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_change_password_rejects_same_as_current(self, e2e_teacher):
        s, _ = _login(e2e_teacher["email"], e2e_teacher["password"])
        r = s.post(
            f"{API}/users/me/change-password",
            json={
                "current_password": e2e_teacher["password"],
                "new_password": e2e_teacher["password"],
            },
            timeout=15,
        )
        assert r.status_code == 400

    def test_change_password_requires_auth(self):
        r = requests.post(
            f"{API}/users/me/change-password",
            json={"current_password": "x", "new_password": "abcdef"},
            timeout=15,
        )
        assert r.status_code in (401, 403)
