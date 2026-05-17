"""Tests for the new admin-driven password reset endpoint (iter21).

POST /api/users/{user_id}/reset-password
- school_admin can reset teacher/accounts in own school
- platform_admin can reset school_admin (any school)
- 403 for cross-school / wrong target role / wrong actor role
- 401 unauthenticated
- 400 for short password
- 404 for unknown user_id
- After reset, target can login with new password
- Audit log entry is created with action='reset_password' resource='user'
- GET /api/schools/{id}/people includes school_admins array + counts.school_admins

IMPORTANT: passwords for seeded demo accounts are restored at the end so
other regression suites stay green.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-admin-fix.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")
SCHOOL_ADMIN = ("principal@sunrise.edu", "School@123")
TEACHER_PRIYA = ("priya@sunrise.edu", "Teacher@123")
TEACHER_ROHIT = ("rohit@sunrise.edu", "Teacher@123")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123")
PARENT = ("parent.stu-00001@sunrise.edu", "Parent@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"login {email} → {r.status_code}: {r.text}"
    return s, r


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def platform_sess():
    s, _ = _login(*PLATFORM)
    return s


@pytest.fixture(scope="module")
def school_admin_sess():
    s, _ = _login(*SCHOOL_ADMIN)
    return s


@pytest.fixture(scope="module")
def teacher_sess():
    s, _ = _login(*TEACHER_PRIYA)
    return s


@pytest.fixture(scope="module")
def ids(platform_sess, school_admin_sess):
    """Resolve known user IDs for targets used in RBAC tests."""
    # Use school_admin /api/users to list users in school
    r = school_admin_sess.get(f"{API}/users", timeout=20)
    assert r.status_code == 200, r.text
    users = r.json()
    by_email = {u["email"].lower(): u for u in users}
    sunrise_school_id = by_email["priya@sunrise.edu"]["school_id"]

    # school_admin id — fetched via platform_admin (school_admin /api/users may not return self)
    r2 = platform_sess.get(f"{API}/schools/{sunrise_school_id}/people", timeout=20)
    assert r2.status_code == 200, r2.text
    people = r2.json()
    sch_admin_id = None
    for a in people.get("school_admins", []):
        if a.get("email", "").lower() == SCHOOL_ADMIN[0]:
            sch_admin_id = a["id"]
            break
    assert sch_admin_id, f"school_admin not found in people: {people}"

    return {
        "teacher_priya_id": by_email[TEACHER_PRIYA[0]]["id"],
        "teacher_rohit_id": by_email[TEACHER_ROHIT[0]]["id"],
        "accounts_id": by_email[ACCOUNTS[0]]["id"],
        "school_admin_id": sch_admin_id,
        "sunrise_school_id": sunrise_school_id,
        "people": people,
    }


@pytest.fixture(scope="module")
def other_school(platform_sess):
    """Create a second school with one teacher inside it to test cross-school 403."""
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"reset.otheradmin.{suffix.lower()}@reset.example.com"
    payload = {
        "name": f"Other School {suffix}",
        "code": f"OTH{suffix}",
        "address": "Lane",
        "phone": "+919000000099",
        "email": f"info.{suffix.lower()}@reset.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email,
        "admin_password": "OtherAdmin@123",
        "admin_name": "Other Admin",
        "auto_approve": True,
        "initial_children_count": 10,
    }
    r = platform_sess.post(f"{API}/schools", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    school = r.json()
    sid = (school.get("school") or {}).get("id") or school.get("id") or school.get("school_id")
    assert sid, f"could not resolve school id from response: {school}"
    # Login as that admin and create one teacher
    sa, _ = _login(admin_email, "OtherAdmin@123")
    t_payload = {
        "email": f"other.teacher.{suffix.lower()}@reset.example.com",
        "password": "OtherTeacher@123",
        "name": "Other Teacher",
        "role": "teacher",
        "subjects": ["Math"],
    }
    rt = sa.post(f"{API}/users", json=t_payload, timeout=20)
    assert rt.status_code == 200, rt.text
    teacher = rt.json()
    return {
        "school_id": sid,
        "admin_email": admin_email,
        "admin_password": "OtherAdmin@123",
        "teacher_id": teacher["id"],
        "teacher_email": t_payload["email"],
    }


# ---------------- 401 / 403 / 400 / 404 ----------------

class TestRBAC:
    def test_unauthenticated_returns_401(self, ids):
        r = requests.post(
            f"{API}/users/{ids['teacher_priya_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 401, r.text

    def test_teacher_actor_forbidden(self, teacher_sess, ids):
        r = teacher_sess.post(
            f"{API}/users/{ids['teacher_rohit_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_accounts_actor_forbidden(self, ids):
        s, _ = _login(*ACCOUNTS)
        r = s.post(
            f"{API}/users/{ids['teacher_priya_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_parent_actor_forbidden(self, ids):
        s, _ = _login(*PARENT)
        r = s.post(
            f"{API}/users/{ids['teacher_priya_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_school_admin_cannot_reset_school_admin(self, school_admin_sess, ids):
        r = school_admin_sess.post(
            f"{API}/users/{ids['school_admin_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text
        assert "school admin" in r.json().get("detail", "").lower() or \
               "teachers and accounts" in r.json().get("detail", "").lower()

    def test_school_admin_cross_school_forbidden(self, school_admin_sess, other_school):
        r = school_admin_sess.post(
            f"{API}/users/{other_school['teacher_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        # Cross-school check fires first (different school_id) so 403
        assert r.status_code == 403, r.text

    def test_platform_admin_cannot_reset_teacher(self, platform_sess, ids):
        r = platform_sess.post(
            f"{API}/users/{ids['teacher_priya_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text
        assert "school super admin" in r.json().get("detail", "").lower() or \
               "school_admin" in r.json().get("detail", "").lower()

    def test_platform_admin_cannot_reset_accounts(self, platform_sess, ids):
        r = platform_sess.post(
            f"{API}/users/{ids['accounts_id']}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_short_password_returns_400(self, school_admin_sess, ids):
        r = school_admin_sess.post(
            f"{API}/users/{ids['teacher_priya_id']}/reset-password",
            json={"new_password": "abc"},
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_unknown_user_returns_404(self, school_admin_sess):
        r = school_admin_sess.post(
            f"{API}/users/{uuid.uuid4().hex}/reset-password",
            json={"new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 404, r.text


# ---------------- Happy paths ----------------

class TestSchoolAdminResetTeacher:
    def test_school_admin_resets_teacher_and_teacher_logs_in(self, school_admin_sess, ids):
        new_pw = "TempReset@2026"
        try:
            r = school_admin_sess.post(
                f"{API}/users/{ids['teacher_rohit_id']}/reset-password",
                json={"new_password": new_pw},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("ok") is True
            assert body.get("email", "").lower() == TEACHER_ROHIT[0]
            assert body.get("new_password") == new_pw
            assert body.get("role") == "teacher"

            # Old password fails
            _login(TEACHER_ROHIT[0], TEACHER_ROHIT[1], expect=401)
            # New password works
            _login(TEACHER_ROHIT[0], new_pw)
        finally:
            # Always restore
            school_admin_sess.post(
                f"{API}/users/{ids['teacher_rohit_id']}/reset-password",
                json={"new_password": TEACHER_ROHIT[1]},
                timeout=15,
            )
            _login(*TEACHER_ROHIT)

    def test_school_admin_resets_accounts_and_logs_in(self, school_admin_sess, ids):
        new_pw = "TempReset@2026"
        try:
            r = school_admin_sess.post(
                f"{API}/users/{ids['accounts_id']}/reset-password",
                json={"new_password": new_pw},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            _login(ACCOUNTS[0], ACCOUNTS[1], expect=401)
            _login(ACCOUNTS[0], new_pw)
        finally:
            school_admin_sess.post(
                f"{API}/users/{ids['accounts_id']}/reset-password",
                json={"new_password": ACCOUNTS[1]},
                timeout=15,
            )
            _login(*ACCOUNTS)


class TestPlatformAdminResetSchoolAdmin:
    def test_platform_resets_school_admin_and_logs_in(self, platform_sess, other_school):
        new_pw = "TempPlatReset@2026"
        # find the other school's admin id
        r = platform_sess.get(f"{API}/schools/{other_school['school_id']}/people", timeout=20)
        assert r.status_code == 200, r.text
        people = r.json()
        admin_id = None
        for a in people.get("school_admins", []):
            if a.get("email", "").lower() == other_school["admin_email"].lower():
                admin_id = a["id"]
                break
        assert admin_id, f"admin not found in {people}"

        r2 = platform_sess.post(
            f"{API}/users/{admin_id}/reset-password",
            json={"new_password": new_pw},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("ok") is True
        assert body.get("role") == "school_admin"
        # Old fails, new succeeds
        _login(other_school["admin_email"], other_school["admin_password"], expect=401)
        _login(other_school["admin_email"], new_pw)


# ---------------- /schools/{id}/people enrichment ----------------

class TestSchoolPeopleSchoolAdmins:
    def test_people_includes_school_admins_array_and_count(self, platform_sess, ids):
        people = ids["people"]
        assert isinstance(people.get("school_admins"), list), "school_admins array missing"
        assert len(people["school_admins"]) >= 1
        counts = people.get("counts") or {}
        assert counts.get("school_admins") == len(people["school_admins"])
        # Validate shape: at least id, email
        sa = people["school_admins"][0]
        assert "id" in sa and "email" in sa


# ---------------- Audit log ----------------

class TestAuditLog:
    def test_audit_entry_created_after_reset(self, platform_sess, school_admin_sess, ids):
        new_pw = "AuditReset@2026"
        try:
            r = school_admin_sess.post(
                f"{API}/users/{ids['teacher_rohit_id']}/reset-password",
                json={"new_password": new_pw},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            # Now query audit as platform_admin
            ar = platform_sess.get(
                f"{API}/audit",
                params={"action": "reset_password", "resource": "user", "limit": 50},
                timeout=20,
            )
            assert ar.status_code == 200, ar.text
            entries = ar.json()
            # Find an entry referencing teacher rohit's id
            match = None
            for e in entries:
                if e.get("action") == "reset_password" and e.get("resource") == "user" \
                        and e.get("resource_id") == ids["teacher_rohit_id"]:
                    match = e
                    break
            assert match, f"No matching audit entry. Got: {entries[:3]}"
            assert match.get("actor_role") == "school_admin"
        finally:
            school_admin_sess.post(
                f"{API}/users/{ids['teacher_rohit_id']}/reset-password",
                json={"new_password": TEACHER_ROHIT[1]},
                timeout=15,
            )
            _login(*TEACHER_ROHIT)


# ---------------- Final teardown sanity ----------------

def test_zz_demo_credentials_intact():
    """Last test: ensure all seeded demo logins still work with their canonical
    passwords. If this fails, some previous test left a password mutated."""
    for email, pwd in [SCHOOL_ADMIN, TEACHER_PRIYA, TEACHER_ROHIT, ACCOUNTS, PARENT]:
        _login(email, pwd)
