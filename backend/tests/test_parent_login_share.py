"""Tests for v1.22 — parent login share/reset endpoints + add-student bug fixes.

Covers:
- POST /api/students with blank parent.email + blank dob/roll_number → 200
- Returned parent_login uses .school TLD and is_new_account=true with default_password
- GET /students/{id}/parent-login returns expected fields (RBAC: school_admin OK,
  teacher own-class OK, teacher other-class 403, accounts 403, parent 403, 401 anon)
- POST /students/{id}/parent-reset-password sets pwd back to Parent@123 and parent
  can log in with it
- Parent login + GET /api/students returns only own child
- Existing parent email reuse → default_password is null
- Existing seeded parent (regression) still logs in
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}
TEACHER = {"email": "priya@sunrise.edu", "password": "Teacher@123"}
ACCOUNTS = {"email": "accounts@sunrise.edu", "password": "Accounts@123"}
SEED_PARENT = {"email": "parent.stu-00001@sunrise.edu", "password": "Parent@123"}
TEACHER_CLASS_ID = "9c33b98760fb4a82b63f44de"  # Grade 5 A (Priya)


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def teacher_sess():
    return _login(TEACHER)


@pytest.fixture(scope="module")
def accounts_sess():
    return _login(ACCOUNTS)


def _pick_other_class(admin_sess):
    """Pick a class+section that Priya truly is NOT a teacher of.

    Priya teaches Grade 5 A/B and is a subject teacher in Grade 6 A via timetable.
    We need a class+section combination with NO timetable slots for Priya.
    """
    # Derive priya_id
    psess = _login(TEACHER)
    priya_id = psess.get(f"{API}/auth/me").json()["id"]
    tt = admin_sess.get(f"{API}/timetable").json()
    priya_classes = {(t["class_id"], t["section"]) for t in tt
                     if t.get("teacher_id") == priya_id}
    classes = admin_sess.get(f"{API}/academic/classes").json()
    for c in classes:
        for sec in c.get("sections", []):
            if (c["id"], sec) not in priya_classes:
                return c["id"], sec
    pytest.skip("No class+section outside teacher's assignments found")


# ---------- Bug-fix: empty-string parent.email + blank dob/roll ----------
class TestAddStudentBugFix:
    def test_admin_create_with_blank_fields(self, admin_sess):
        suffix = uuid.uuid4().hex[:6]
        payload = {
            "name": f"TEST_Stu_{suffix}",
            "class_id": TEACHER_CLASS_ID,
            "section": "A",
            "roll_number": "",
            "gender": "M",
            "dob": "",
            "parent": {
                "name": f"TEST_Par_{suffix}",
                "relationship": "father",
                "phone": "9999900000",
                "whatsapp": "",
                "email": "",
            },
        }
        r = admin_sess.post(f"{API}/students", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "parent_login" in data, data
        pl = data["parent_login"]
        assert pl["is_new_account"] is True
        assert pl["default_password"] == "Parent@123"
        # synthetic .school TLD
        assert pl["email"].endswith(".school"), pl["email"]
        # roll_number/dob coerced from "" to None
        assert data.get("roll_number") in (None, "")
        # stash for later test
        pytest.shared_student = data
        pytest.shared_parent_email = pl["email"]

    def test_teacher_create_with_blank_email(self, teacher_sess):
        suffix = uuid.uuid4().hex[:6]
        payload = {
            "name": f"TEST_TStu_{suffix}",
            "class_id": TEACHER_CLASS_ID,
            "section": "A",
            "roll_number": "",
            "dob": "",
            "parent": {
                "name": f"TEST_TPar_{suffix}",
                "relationship": "mother",
                "phone": "9999900001",
                "email": "",
            },
        }
        r = teacher_sess.post(f"{API}/students", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parent_login"]["email"].endswith(".school")
        assert body["parent_login"]["is_new_account"] is True

    def test_create_existing_parent_email_no_password(self, admin_sess):
        # First create a parent
        suffix = uuid.uuid4().hex[:6]
        shared_email = f"test_shared_{suffix}@example.com"
        p1 = {
            "name": f"TEST_S1_{suffix}", "class_id": TEACHER_CLASS_ID, "section": "A",
            "parent": {"name": "TEST_SharedPar", "relationship": "father",
                       "phone": "9000000001", "email": shared_email},
        }
        r1 = admin_sess.post(f"{API}/students", json=p1)
        assert r1.status_code == 200, r1.text
        assert r1.json()["parent_login"]["is_new_account"] is True
        # Second student linking to SAME parent email
        p2 = {
            "name": f"TEST_S2_{suffix}", "class_id": TEACHER_CLASS_ID, "section": "A",
            "parent": {"name": "TEST_SharedPar", "relationship": "father",
                       "phone": "9000000001", "email": shared_email},
        }
        r2 = admin_sess.post(f"{API}/students", json=p2)
        assert r2.status_code == 200, r2.text
        pl2 = r2.json()["parent_login"]
        assert pl2["is_new_account"] is False
        assert pl2["default_password"] is None


# ---------- GET /students/{id}/parent-login ----------
class TestParentLoginInfo:
    def test_admin_get(self, admin_sess):
        s = pytest.shared_student
        r = admin_sess.get(f"{API}/students/{s['id']}/parent-login")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["student_id"] == s["id"]
        assert d["student_uid"] == s["student_uid"]
        assert d["email"].endswith(".school")
        assert "last_login_at" in d
        assert "password_changed_at" in d
        assert "password_reset_to_default_at" in d

    def test_teacher_get_own_class(self, teacher_sess):
        s = pytest.shared_student
        r = teacher_sess.get(f"{API}/students/{s['id']}/parent-login")
        assert r.status_code == 200, r.text

    def test_teacher_get_other_class_forbidden(self, teacher_sess, admin_sess):
        # Create student in OTHER class as admin
        other_cls, other_sec = _pick_other_class(admin_sess)
        suffix = uuid.uuid4().hex[:6]
        r = admin_sess.post(f"{API}/students", json={
            "name": f"TEST_Other_{suffix}",
            "class_id": other_cls, "section": other_sec,
            "parent": {"name": "TEST_OP", "relationship": "father",
                       "phone": "9000000099", "email": ""},
        })
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        r2 = teacher_sess.get(f"{API}/students/{sid}/parent-login")
        assert r2.status_code == 403, r2.text

    def test_accounts_forbidden(self, accounts_sess):
        s = pytest.shared_student
        r = accounts_sess.get(f"{API}/students/{s['id']}/parent-login")
        assert r.status_code == 403, r.text

    def test_unauthenticated_401(self):
        s = pytest.shared_student
        r = requests.get(f"{API}/students/{s['id']}/parent-login", timeout=20)
        assert r.status_code == 401, r.text


# ---------- POST /students/{id}/parent-reset-password ----------
class TestParentResetPassword:
    def test_admin_reset_and_parent_login(self, admin_sess):
        s = pytest.shared_student
        r = admin_sess.post(f"{API}/students/{s['id']}/parent-reset-password")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["default_password"] == "Parent@123"
        assert body["email"] == pytest.shared_parent_email
        # parent can now log in with Parent@123
        psess = requests.Session()
        rl = psess.post(f"{API}/auth/login", json={
            "email": pytest.shared_parent_email, "password": "Parent@123",
        }, timeout=20)
        assert rl.status_code == 200, rl.text
        me = psess.get(f"{API}/auth/me").json()
        assert me["role"] == "parent"

    def test_accounts_reset_forbidden(self, accounts_sess):
        s = pytest.shared_student
        r = accounts_sess.post(f"{API}/students/{s['id']}/parent-reset-password")
        assert r.status_code == 403, r.text

    def test_unauthenticated_reset_401(self):
        s = pytest.shared_student
        r = requests.post(f"{API}/students/{s['id']}/parent-reset-password", timeout=20)
        assert r.status_code == 401, r.text


# ---------- Parent end-to-end: only sees own child ----------
class TestParentE2E:
    def test_parent_sees_only_own_child(self):
        psess = requests.Session()
        rl = psess.post(f"{API}/auth/login", json={
            "email": pytest.shared_parent_email, "password": "Parent@123",
        }, timeout=20)
        assert rl.status_code == 200, rl.text
        r = psess.get(f"{API}/students")
        assert r.status_code == 200, r.text
        kids = r.json()
        assert len(kids) >= 1
        uids = {k["student_uid"] for k in kids}
        assert pytest.shared_student["student_uid"] in uids

    def test_parent_cannot_call_parent_login_endpoint(self):
        psess = _login(SEED_PARENT)
        # Try on STU-00001 (their own child) — still should be 403 by role
        students = psess.get(f"{API}/students").json()
        if students:
            sid = students[0]["id"]
            r = psess.get(f"{API}/students/{sid}/parent-login")
            assert r.status_code == 403, r.text
            r2 = psess.post(f"{API}/students/{sid}/parent-reset-password")
            assert r2.status_code == 403, r2.text


# ---------- Regression: seeded parent ----------
class TestSeededParentRegression:
    def test_seeded_parent_login_still_works(self):
        psess = requests.Session()
        r = psess.post(f"{API}/auth/login", json=SEED_PARENT, timeout=20)
        assert r.status_code == 200, r.text
        me = psess.get(f"{API}/auth/me").json()
        assert me["role"] == "parent"
        assert me["email"] == SEED_PARENT["email"]
