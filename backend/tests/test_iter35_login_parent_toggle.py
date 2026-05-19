"""Iteration 35 — Case-insensitive login + simple (no-@) login ids + per-school
parent-login kill-switch + duplicate-id error messages + bus_driver/sports_coach
staff role regression.

Mirrors the review request from the main agent. Hits the real backend +
MongoDB at REACT_APP_BACKEND_URL. Created resources are tagged with a
TEST_ prefix and cleaned up at the end of the module where possible.
"""
import os
import time
import uuid
import requests
import pytest

def _load_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # fall back to /app/frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    assert url, "REACT_APP_BACKEND_URL not set"
    return url.rstrip("/")

BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

PLATFORM_ADMIN = {"email": "jagadishchandu789@gmail.com", "password": "Manasa@123"}
SCHOOL_ADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}
TEACHER = {"email": "priya@sunrise.edu", "password": "Teacher@123"}
PARENT = {"email": "parent.stu-00001@sunrise.edu", "password": "Parent@123"}
ACCOUNTS = {"email": "accounts@sunrise.edu", "password": "Accounts@123"}

# Unique suffix per pytest run so reruns don't collide.
RUN = uuid.uuid4().hex[:6]


def _login(creds, allow_fail=False):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    if not allow_fail:
        assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s, r


@pytest.fixture(scope="module")
def platform_session():
    s, _ = _login(PLATFORM_ADMIN)
    return s


@pytest.fixture(scope="module")
def school_admin_session():
    s, _ = _login(SCHOOL_ADMIN)
    return s


@pytest.fixture(scope="module")
def demo_school_id(platform_session):
    schools = platform_session.get(f"{API}/schools", timeout=20).json()
    demo = next((s for s in schools if s.get("code") == "DEMO" or "sunrise" in (s.get("name") or "").lower()), None)
    assert demo, f"DEMO school not found in {[s.get('code') for s in schools]}"
    return demo["id"]


# ---------- Case-insensitive + non-@ login ids ----------
class TestCaseInsensitiveLogin:
    def test_uppercase_email_logs_in(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "PRINCIPAL@SUNRISE.EDU", "password": "School@123"},
                          timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "school_admin"
        assert r.json()["email"] == "principal@sunrise.edu"  # normalised

    def test_mixed_case_teacher(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "Priya@Sunrise.Edu", "password": "Teacher@123"},
                          timeout=20)
        assert r.status_code == 200
        assert r.json()["role"] == "teacher"

    def test_wrong_password_still_401(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "PRINCIPAL@SUNRISE.EDU", "password": "wrongpw"},
                          timeout=20)
        assert r.status_code == 401

    def test_empty_email(self):
        r = requests.post(f"{API}/auth/login", json={"email": "", "password": "x"}, timeout=20)
        # Either 400 (our explicit guard) or 422 (pydantic) is acceptable.
        assert r.status_code in (400, 422)


# ---------- Simple (no-@) login id flow ----------
class TestSimpleLoginId:
    teacher_id = None
    simple_email = f"test_teacher_{RUN}"

    def test_create_teacher_with_simple_id(self, school_admin_session):
        # Need a subject for teacher
        r = school_admin_session.post(f"{API}/users", json={
            "email": self.simple_email,  # NO @
            "password": "Teacher@123",
            "name": f"TEST Teacher {RUN}",
            "role": "teacher",
            "phone": "9999999999",
            "subjects": ["math"],
        }, timeout=20)
        assert r.status_code == 200, r.text
        TestSimpleLoginId.teacher_id = r.json()["id"]
        assert r.json()["email"] == self.simple_email.lower()

    def test_login_with_simple_id_uppercase(self):
        assert TestSimpleLoginId.teacher_id, "must create teacher first"
        r = requests.post(f"{API}/auth/login",
                          json={"email": self.simple_email.upper(), "password": "Teacher@123"},
                          timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "teacher"

    def test_duplicate_simple_id_case_insensitive(self, school_admin_session):
        # Same id, different case → must 400 with friendly message
        r = school_admin_session.post(f"{API}/users", json={
            "email": self.simple_email.upper(),
            "password": "Teacher@123",
            "name": "Dup",
            "role": "teacher",
            "subjects": ["math"],
        }, timeout=20)
        assert r.status_code == 400
        assert "already exists" in r.json().get("detail", "").lower()


# ---------- Parent-login kill switch ----------
class TestParentLoginToggle:
    def test_get_default_enabled(self, platform_session, demo_school_id):
        r = platform_session.get(f"{API}/schools/{demo_school_id}/parent-login", timeout=20)
        assert r.status_code == 200
        # Legacy schools may not have the flag — default True
        assert r.json()["enabled"] in (True,)

    def test_school_admin_can_read_flag(self, school_admin_session, demo_school_id):
        r = school_admin_session.get(f"{API}/schools/{demo_school_id}/parent-login", timeout=20)
        assert r.status_code == 200
        assert "enabled" in r.json()

    def test_school_admin_cannot_patch(self, school_admin_session, demo_school_id):
        r = school_admin_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                                       json={"enabled": False}, timeout=20)
        assert r.status_code == 403

    def test_disable_blocks_parent_allows_other_roles(self, platform_session, demo_school_id):
        # Disable
        r = platform_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                                   json={"enabled": False}, timeout=20)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        # Parent login denied
        rp = requests.post(f"{API}/auth/login", json=PARENT, timeout=20)
        assert rp.status_code == 403, rp.text
        assert "parent login is currently disabled" in rp.json().get("detail", "").lower()

        # Other roles still work
        for creds in (SCHOOL_ADMIN, TEACHER, ACCOUNTS):
            rok = requests.post(f"{API}/auth/login", json=creds, timeout=20)
            assert rok.status_code == 200, f"{creds['email']} got {rok.status_code}: {rok.text}"

    def test_reenable_restores_parent_login(self, platform_session, demo_school_id):
        r = platform_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                                   json={"enabled": True}, timeout=20)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

        rp = requests.post(f"{API}/auth/login", json=PARENT, timeout=20)
        assert rp.status_code == 200, rp.text
        assert rp.json()["role"] == "parent"

    def test_uppercase_parent_email_when_disabled(self, platform_session, demo_school_id):
        # Combine both features: even when login email arrives uppercase, the
        # kill switch must still take effect.
        platform_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                               json={"enabled": False}, timeout=20)
        try:
            rp = requests.post(f"{API}/auth/login",
                               json={"email": PARENT["email"].upper(), "password": PARENT["password"]},
                               timeout=20)
            assert rp.status_code == 403
        finally:
            platform_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                                   json={"enabled": True}, timeout=20)


# ---------- Staff role regression (bus_driver / sports_coach) ----------
class TestStaffRoles:
    created_ids = []

    def test_create_bus_driver(self, school_admin_session):
        r = school_admin_session.post(f"{API}/staff", json={
            "name": f"TEST Driver {RUN}", "role": "bus_driver", "phone": "1111111111",
        }, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "bus_driver"
        TestStaffRoles.created_ids.append(r.json()["id"])

    def test_create_sports_coach(self, school_admin_session):
        r = school_admin_session.post(f"{API}/staff", json={
            "name": f"TEST Coach {RUN}", "role": "sports_coach",
        }, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "sports_coach"
        TestStaffRoles.created_ids.append(r.json()["id"])

    def test_legacy_driver_role_rejected(self, school_admin_session):
        # Backend literal does NOT include 'driver' — must 422.
        r = school_admin_session.post(f"{API}/staff", json={
            "name": "TEST bad", "role": "driver",
        }, timeout=20)
        assert r.status_code == 422

    def test_invalid_role_rejected(self, school_admin_session):
        r = school_admin_session.post(f"{API}/staff", json={
            "name": "TEST bad2", "role": "wizard",
        }, timeout=20)
        assert r.status_code == 422


# ---------- Student create: parent reuse + non-parent collision ----------
class TestStudentParentLink:
    teacher_login = f"test_teach_collide_{RUN}"
    created_parent_email = f"test_parent_{RUN}@sunrise.edu"
    student_ids = []

    def test_create_teacher_for_collision(self, school_admin_session):
        r = school_admin_session.post(f"{API}/users", json={
            "email": self.teacher_login,
            "password": "Teacher@123",
            "name": "TEST teacher collide",
            "role": "teacher",
            "subjects": ["math"],
        }, timeout=20)
        assert r.status_code == 200, r.text

    def _pick_class(self, school_admin_session):
        r = school_admin_session.get(f"{API}/academic/classes", timeout=20)
        assert r.status_code == 200, r.text
        cs = r.json()
        assert cs, "Demo school must have at least one class"
        cls = cs[0]
        sec = (cls.get("sections") or ["A"])[0]
        return cls["id"], sec

    def test_create_student_with_new_parent(self, school_admin_session):
        cid, sec = self._pick_class(school_admin_session)
        r = school_admin_session.post(f"{API}/students", json={
            "name": f"TEST Stu1 {RUN}",
            "class_id": cid,
            "section": sec,
            "gender": "male",
            "parent": {"name": "TEST Parent A", "phone": "2222222222", "email": self.created_parent_email},
        }, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("parent_login", {}).get("is_new_account") is True
        TestStudentParentLink.student_ids.append(body["id"])

    def test_reuse_parent_links_existing(self, school_admin_session):
        cid, sec = self._pick_class(school_admin_session)
        r = school_admin_session.post(f"{API}/students", json={
            "name": f"TEST Stu2 {RUN}",
            "class_id": cid,
            "section": sec,
            "gender": "female",
            "parent": {"name": "TEST Parent A", "phone": "2222222222", "email": self.created_parent_email.upper()},
        }, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("parent_login", {}).get("is_new_account") is False
        TestStudentParentLink.student_ids.append(body["id"])

    def test_parent_email_collision_with_teacher_blocked(self, school_admin_session):
        cid, sec = self._pick_class(school_admin_session)
        r = school_admin_session.post(f"{API}/students", json={
            "name": f"TEST StuBad {RUN}",
            "class_id": cid,
            "section": sec,
            "gender": "male",
            "parent": {"name": "TEST Parent X", "phone": "3333333333", "email": self.teacher_login.upper()},
        }, timeout=20)
        assert r.status_code == 400, r.text
        assert "teacher" in r.json().get("detail", "").lower()


# ---------- POST /api/schools admin_email rules ----------
class TestSchoolCreate:
    new_school_id = None
    simple_admin = f"test_admin_{RUN}"
    code = f"TST{RUN.upper()}"

    def test_create_school_with_simple_admin_id(self, platform_session):
        r = platform_session.post(f"{API}/schools", json={
            "name": f"TEST School {RUN}",
            "code": self.code,
            "admin_email": self.simple_admin,  # no @
            "admin_password": "School@123",
            "admin_name": "TEST Admin",
            "auto_approve": True,
            "initial_children_count": 50,
        }, timeout=30)
        assert r.status_code == 200, r.text
        TestSchoolCreate.new_school_id = r.json()["school"]["id"]
        assert r.json()["admin_email"] == self.simple_admin.lower()

    def test_login_new_admin_uppercase(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": self.simple_admin.upper(), "password": "School@123"},
                          timeout=20)
        assert r.status_code == 200
        assert r.json()["role"] == "school_admin"

    def test_duplicate_admin_id_blocked(self, platform_session):
        r = platform_session.post(f"{API}/schools", json={
            "name": f"TEST School Dup {RUN}",
            "code": self.code + "X",
            "admin_email": self.simple_admin.upper(),
            "admin_password": "School@123",
            "admin_name": "Dup",
        }, timeout=20)
        assert r.status_code == 400
        assert "already exists" in r.json().get("detail", "").lower()


# ---------- Cleanup ----------
def test_zz_cleanup(school_admin_session, platform_session, demo_school_id):
    """Best-effort cleanup. Failures here are non-fatal — we only soft-delete."""
    # Deactivate created users by id where we know them
    try:
        users = school_admin_session.get(f"{API}/users", timeout=20).json()
        for u in users:
            if (u.get("name") or "").startswith("TEST "):
                school_admin_session.delete(f"{API}/users/{u['id']}", timeout=20)
    except Exception:
        pass
    # Deactivate staff
    try:
        staff = school_admin_session.get(f"{API}/staff", timeout=20).json()
        for s in staff:
            if (s.get("name") or "").startswith("TEST "):
                school_admin_session.delete(f"{API}/staff/{s['id']}", timeout=20)
    except Exception:
        pass
    # Re-enable parent login just in case a test failed mid-flight
    try:
        platform_session.patch(f"{API}/schools/{demo_school_id}/parent-login",
                               json={"enabled": True}, timeout=10)
    except Exception:
        pass
