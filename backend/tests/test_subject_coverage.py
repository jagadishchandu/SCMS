"""Backend tests for Subject⇄Teacher coverage + bulk-assign endpoints (iter14)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fee-template-clone.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("principal@sunrise.edu", "School@123")
TEACHER = ("priya@sunrise.edu", "Teacher@123")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def teacher():
    return _login(*TEACHER)


@pytest.fixture(scope="module")
def accounts():
    return _login(*ACCOUNTS)


# ---------- COVERAGE ----------
def test_coverage_admin_ok(admin):
    r = admin.get(f"{API}/academic/subjects/coverage")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "subjects" in d and isinstance(d["subjects"], list)
    assert "total_teachers" in d and isinstance(d["total_teachers"], int)
    assert "orphan_count" in d
    assert len(d["subjects"]) >= 1
    s0 = d["subjects"][0]
    for k in ("subject_id", "subject_name", "code", "teacher_count", "teachers"):
        assert k in s0
    assert isinstance(s0["teachers"], list)
    # orphan_count matches subjects with teacher_count==0
    real_orphan = sum(1 for s in d["subjects"] if s["teacher_count"] == 0)
    assert d["orphan_count"] == real_orphan


def test_coverage_forbidden_for_teacher(teacher):
    r = teacher.get(f"{API}/academic/subjects/coverage")
    assert r.status_code == 403, r.text


def test_coverage_forbidden_for_accounts(accounts):
    r = accounts.get(f"{API}/academic/subjects/coverage")
    assert r.status_code == 403, r.text


# ---------- BULK ASSIGN ----------
def _get_subjects_and_teachers(admin):
    cov = admin.get(f"{API}/academic/subjects/coverage").json()
    subjects = cov["subjects"]
    teachers = admin.get(f"{API}/users?role=teacher").json()
    # Ensure we have at least one of each
    assert subjects and teachers
    return subjects, teachers


def test_bulk_assign_idempotent_and_assigned_ids(admin):
    subjects, teachers = _get_subjects_and_teachers(admin)
    subj = subjects[0]
    tids = [t["id"] for t in teachers[:2]]
    # First call — may add 0..N depending on prior state
    r1 = admin.post(
        f"{API}/academic/subjects/{subj['subject_id']}/bulk-assign-teachers",
        json={"teacher_ids": tids},
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert set(d1["assigned_teacher_ids"]) == set(tids)
    assert d1["removed"] == 0  # default replace=False
    # Second call must be idempotent → added=0
    r2 = admin.post(
        f"{API}/academic/subjects/{subj['subject_id']}/bulk-assign-teachers",
        json={"teacher_ids": tids},
    )
    d2 = r2.json()
    assert r2.status_code == 200
    assert d2["added"] == 0
    assert d2["removed"] == 0
    # Verify persistence via coverage
    cov = admin.get(f"{API}/academic/subjects/coverage").json()
    row = next(s for s in cov["subjects"] if s["subject_id"] == subj["subject_id"])
    row_teacher_ids = {t["id"] for t in row["teachers"]}
    for tid in tids:
        assert tid in row_teacher_ids


def test_bulk_assign_invalid_teacher_id_400(admin):
    subjects, _ = _get_subjects_and_teachers(admin)
    subj = subjects[0]
    r = admin.post(
        f"{API}/academic/subjects/{subj['subject_id']}/bulk-assign-teachers",
        json={"teacher_ids": ["does-not-exist-xyz"]},
    )
    assert r.status_code == 400, r.text
    assert "teacher" in r.json().get("detail", "").lower() or "invalid" in r.json().get("detail", "").lower()


def test_bulk_assign_subject_not_found_404(admin):
    teachers = admin.get(f"{API}/users?role=teacher").json()
    tid = teachers[0]["id"]
    r = admin.post(
        f"{API}/academic/subjects/no-such-subject-id/bulk-assign-teachers",
        json={"teacher_ids": [tid]},
    )
    assert r.status_code == 404, r.text


def test_bulk_assign_replace_authoritative(admin):
    subjects, teachers = _get_subjects_and_teachers(admin)
    # use a subject we will toggle: pick last one to avoid clashing with prior test
    subj = subjects[-1]
    sid = subj["subject_id"]
    tids = [t["id"] for t in teachers]
    assert len(tids) >= 2
    # First: assign to ALL teachers (so we can shrink it later)
    admin.post(f"{API}/academic/subjects/{sid}/bulk-assign-teachers", json={"teacher_ids": tids})
    # Now assign only first teacher with replace=true → others should be pulled
    r = admin.post(
        f"{API}/academic/subjects/{sid}/bulk-assign-teachers",
        json={"teacher_ids": [tids[0]], "replace": True},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["removed"] >= 1
    # Verify via coverage
    cov = admin.get(f"{API}/academic/subjects/coverage").json()
    row = next(s for s in cov["subjects"] if s["subject_id"] == sid)
    assigned = {t["id"] for t in row["teachers"]}
    assert assigned == {tids[0]}


def test_bulk_assign_forbidden_for_teacher(teacher, admin):
    subjects, teachers_list = _get_subjects_and_teachers(admin)
    subj = subjects[0]
    tid = teachers_list[0]["id"]
    r = teacher.post(
        f"{API}/academic/subjects/{subj['subject_id']}/bulk-assign-teachers",
        json={"teacher_ids": [tid]},
    )
    assert r.status_code == 403


def test_bulk_assign_forbidden_for_accounts(accounts, admin):
    subjects, teachers_list = _get_subjects_and_teachers(admin)
    subj = subjects[0]
    tid = teachers_list[0]["id"]
    r = accounts.post(
        f"{API}/academic/subjects/{subj['subject_id']}/bulk-assign-teachers",
        json={"teacher_ids": [tid]},
    )
    assert r.status_code == 403


# ---------- UNASSIGN ----------
def test_unassign_teacher_removes_subject(admin):
    subjects, teachers = _get_subjects_and_teachers(admin)
    subj = subjects[0]
    sid = subj["subject_id"]
    tid = teachers[0]["id"]
    # Ensure assigned
    admin.post(f"{API}/academic/subjects/{sid}/bulk-assign-teachers", json={"teacher_ids": [tid]})
    # Unassign
    r = admin.post(f"{API}/academic/subjects/{sid}/unassign-teacher/{tid}")
    assert r.status_code == 200, r.text
    # Verify via coverage
    cov = admin.get(f"{API}/academic/subjects/coverage").json()
    row = next(s for s in cov["subjects"] if s["subject_id"] == sid)
    assert tid not in {t["id"] for t in row["teachers"]}
    # restore for downstream tests
    admin.post(f"{API}/academic/subjects/{sid}/bulk-assign-teachers", json={"teacher_ids": [tid]})


def test_unassign_teacher_not_in_school_404(admin):
    subjects, _ = _get_subjects_and_teachers(admin)
    sid = subjects[0]["subject_id"]
    r = admin.post(f"{API}/academic/subjects/{sid}/unassign-teacher/no-such-teacher")
    assert r.status_code == 404


def test_unassign_forbidden_for_teacher(teacher, admin):
    subjects, teachers_list = _get_subjects_and_teachers(admin)
    sid = subjects[0]["subject_id"]
    tid = teachers_list[0]["id"]
    r = teacher.post(f"{API}/academic/subjects/{sid}/unassign-teacher/{tid}")
    assert r.status_code == 403
