"""Regression tests for Teacher creation requiring subjects (v1.21+ UI exposes subjects multi-select).

Covered scenarios (per E1 review request):
- POST /api/users role=teacher with empty/missing subjects -> 400 with message about subjects.
- POST /api/users role=teacher with valid subjects -> 201/200 and stores subjects.
- GET /api/users?role=teacher returns subjects array on each teacher.
- (Sanity) GET /api/academic/subjects returns seeded subjects.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://classroom-messenger-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "principal@sunrise.edu"
ADMIN_PASSWORD = "School@123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    # Auth is cookie-based — session cookies will be reused for subsequent calls
    assert len(s.cookies) > 0, f"No auth cookies set after login: {dict(r.cookies)}"
    return s


# Backwards-compat alias for tests
@pytest.fixture(scope="module")
def auth_headers(admin_session):
    return admin_session


@pytest.fixture(scope="module")
def subjects(admin_session):
    r = admin_session.get(f"{API}/academic/subjects", timeout=20)
    assert r.status_code == 200, f"Subjects fetch failed: {r.status_code} {r.text}"
    data = r.json()
    assert isinstance(data, list) and len(data) > 0, "Expected seeded subjects in DEMO school"
    return data


# --- Tests --------------------------------------------------------------------

class TestTeacherSubjectValidation:
    def test_subjects_endpoint_returns_seeded(self, subjects):
        # Sanity: at least one subject must have id+name fields
        s = subjects[0]
        assert "id" in s and "name" in s

    def test_create_teacher_missing_subjects_returns_400(self, auth_headers):
        ts = int(time.time() * 1000)
        payload = {
            "email": f"TEST_no_subj_{ts}@sunrise.edu",
            "password": "Teacher@123",
            "name": "TEST No Subjects Teacher",
            "role": "teacher",
        }
        r = auth_headers.post(f"{API}/users", json=payload, timeout=20)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        body = r.json()
        detail = (body.get("detail") or body.get("message") or "").lower()
        assert "subject" in detail, f"Error message should mention 'subject': {detail}"

    def test_create_teacher_empty_subjects_returns_400(self, auth_headers):
        ts = int(time.time() * 1000)
        payload = {
            "email": f"TEST_empty_subj_{ts}@sunrise.edu",
            "password": "Teacher@123",
            "name": "TEST Empty Subjects Teacher",
            "role": "teacher",
            "subjects": [],
        }
        r = auth_headers.post(f"{API}/users", json=payload, timeout=20)
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert "subject" in detail

    def test_create_teacher_with_subjects_succeeds(self, auth_headers, subjects):
        ts = int(time.time() * 1000)
        sid = subjects[0]["id"]
        payload = {
            "email": f"TEST_ok_teacher_{ts}@sunrise.edu",
            "password": "Teacher@123",
            "name": "TEST OK Teacher",
            "role": "teacher",
            "subjects": [sid],
            "phone": "9999999999",
            "employee_id": f"EMP_TEST_{ts}",
            "qualifications": "B.Ed",
        }
        r = auth_headers.post(f"{API}/users", json=payload, timeout=20)
        assert r.status_code in (200, 201), f"Create teacher failed: {r.status_code} {r.text}"
        created = r.json()
        assert created.get("role") == "teacher"
        assert created.get("email") == payload["email"].lower()
        assert created.get("subjects") == [sid]
        assert "id" in created

        # GET list returns this teacher with subjects array
        r2 = auth_headers.get(f"{API}/users", params={"role": "teacher"}, timeout=20)
        assert r2.status_code == 200
        teachers = r2.json()
        found = [t for t in teachers if t.get("email") == payload["email"].lower()]
        assert found, "Newly created teacher not found in list"
        assert isinstance(found[0].get("subjects"), list)
        assert sid in found[0]["subjects"]

    def test_create_teacher_with_multiple_subjects(self, auth_headers, subjects):
        if len(subjects) < 2:
            pytest.skip("Need at least 2 seeded subjects for this test")
        ts = int(time.time() * 1000)
        sids = [subjects[0]["id"], subjects[1]["id"]]
        payload = {
            "email": f"TEST_multi_subj_{ts}@sunrise.edu",
            "password": "Teacher@123",
            "name": "TEST Multi Subjects Teacher",
            "role": "teacher",
            "subjects": sids,
        }
        r = auth_headers.post(f"{API}/users", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        assert set(r.json().get("subjects", [])) == set(sids)

    def test_create_accounts_without_subjects_succeeds(self, auth_headers):
        # Non-teacher roles should not require subjects (regression — UI hides the picker).
        ts = int(time.time() * 1000)
        payload = {
            "email": f"TEST_acc_{ts}@sunrise.edu",
            "password": "Accounts@123",
            "name": "TEST Accounts User",
            "role": "accounts",
        }
        r = auth_headers.post(f"{API}/users", json=payload, timeout=20)
        assert r.status_code in (200, 201), f"Create accounts failed: {r.status_code} {r.text}"
        assert r.json().get("role") == "accounts"
