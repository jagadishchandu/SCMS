"""Backend tests for GET /api/timetable/class-subject-coverage (iter15)."""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://case-insensitive-id.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("principal@sunrise.edu", "School@123")
TEACHER = ("priya@sunrise.edu", "Teacher@123")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123")
PARENT = ("parent.stu-00001@sunrise.edu", "Parent@123")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
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


@pytest.fixture(scope="module")
def parent():
    return _login(*PARENT)


@pytest.fixture(scope="module")
def matrix(admin):
    r = admin.get(f"{API}/timetable/class-subject-coverage")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- SHAPE ----------
def test_response_top_level_shape(matrix):
    for key in (
        "matrix",
        "subjects_total",
        "classes_total",
        "sections_total",
        "sections_with_timetable",
        "unscheduled_subjects",
    ):
        assert key in matrix, f"missing key {key}"
    assert isinstance(matrix["matrix"], list)
    assert isinstance(matrix["unscheduled_subjects"], list)
    assert isinstance(matrix["subjects_total"], int)
    assert isinstance(matrix["classes_total"], int)


def test_each_row_has_required_fields(matrix):
    assert matrix["matrix"], "expected at least one (class,section) row"
    for r in matrix["matrix"]:
        for k in (
            "class_id",
            "class_name",
            "section",
            "subject_coverage",
            "missing_subjects",
            "total_periods",
            "has_timetable",
        ):
            assert k in r, f"row missing field {k}: {r}"
        assert isinstance(r["subject_coverage"], list)
        assert isinstance(r["missing_subjects"], list)
        assert isinstance(r["total_periods"], int)
        assert isinstance(r["has_timetable"], bool)
        # total_periods consistent with has_timetable
        assert (r["total_periods"] > 0) == r["has_timetable"]


# ---------- EVERY (class × section) ROW EXISTS ----------
def test_row_exists_for_every_class_section(admin, matrix):
    classes = admin.get(f"{API}/academic/classes").json()
    expected_pairs = set()
    for c in classes:
        for sec in (c.get("sections") or []):
            expected_pairs.add((c["id"], sec))
    got_pairs = {(r["class_id"], r["section"]) for r in matrix["matrix"]}
    assert expected_pairs == got_pairs, f"expected {expected_pairs} got {got_pairs}"
    assert matrix["sections_total"] == len(matrix["matrix"]) == len(expected_pairs)


# ---------- SUBJECT AGGREGATION ----------
def test_subject_coverage_period_count_matches_timetable(admin, matrix):
    """For at least one row that has_timetable, verify period_count == # slot docs for that class/section/subject."""
    populated = [r for r in matrix["matrix"] if r["has_timetable"]]
    assert populated, "no populated timetable rows in DEMO seed"
    r = populated[0]
    tt = admin.get(
        f"{API}/timetable",
        params={"class_id": r["class_id"], "section": r["section"]},
    ).json()
    # Build expected period count per subject from raw slots
    expected = {}
    teacher_per_sub = {}
    for sl in tt:
        expected[sl["subject_id"]] = expected.get(sl["subject_id"], 0) + 1
        if sl.get("teacher_id"):
            teacher_per_sub.setdefault(sl["subject_id"], set()).add(sl["teacher_id"])

    assert sum(expected.values()) == r["total_periods"]
    cov_by_sid = {sc["subject_id"]: sc for sc in r["subject_coverage"]}
    for sid, count in expected.items():
        assert sid in cov_by_sid, f"subject {sid} missing from coverage"
        assert cov_by_sid[sid]["period_count"] == count
        # teachers de-duplicated
        ret_ids = [t["id"] for t in cov_by_sid[sid]["teachers"]]
        assert len(ret_ids) == len(set(ret_ids)), "teachers list not de-duplicated"
        assert set(ret_ids) == teacher_per_sub.get(sid, set())


def test_missing_subjects_complement_covered(admin, matrix):
    subjects = admin.get(f"{API}/academic/subjects").json()
    all_sub_ids = {s["id"] for s in subjects}
    for r in matrix["matrix"]:
        covered = {sc["subject_id"] for sc in r["subject_coverage"]}
        missing = {m["subject_id"] for m in r["missing_subjects"]}
        # No overlap, union == all subjects
        assert not (covered & missing), f"overlap: {covered & missing}"
        assert (covered | missing) == all_sub_ids, f"row {r['class_id']}/{r['section']} mismatch"


# ---------- EMPTY (no timetable) ROWS ----------
def test_empty_section_has_all_subjects_missing(matrix):
    empties = [r for r in matrix["matrix"] if not r["has_timetable"]]
    if not empties:
        pytest.skip("DEMO seed has every section scheduled — empty-row case n/a")
    for r in empties:
        assert r["total_periods"] == 0
        assert r["subject_coverage"] == []
        # ALL subjects should be in missing_subjects for an empty section
        assert len(r["missing_subjects"]) == matrix["subjects_total"]


# ---------- UNSCHEDULED SUBJECTS ----------
def test_unscheduled_subjects_truly_unscheduled(admin, matrix):
    """Any subject in unscheduled_subjects must not appear in ANY row's subject_coverage."""
    scheduled_ids = set()
    for r in matrix["matrix"]:
        for sc in r["subject_coverage"]:
            scheduled_ids.add(sc["subject_id"])
    for u in matrix["unscheduled_subjects"]:
        assert u["subject_id"] not in scheduled_ids


def test_unscheduled_subjects_shape(matrix):
    for u in matrix["unscheduled_subjects"]:
        assert "subject_id" in u and "subject_name" in u and "code" in u


# ---------- COUNTS ----------
def test_sections_with_timetable_count(matrix):
    expected = sum(1 for r in matrix["matrix"] if r["has_timetable"])
    assert matrix["sections_with_timetable"] == expected


def test_subjects_total_matches_school(admin, matrix):
    subjects = admin.get(f"{API}/academic/subjects").json()
    assert matrix["subjects_total"] == len(subjects)


def test_classes_total_matches_school(admin, matrix):
    classes = admin.get(f"{API}/academic/classes").json()
    assert matrix["classes_total"] == len(classes)


# ---------- TEACHERS PRESENT ----------
def test_teachers_have_id_and_name(matrix):
    """De-duped teacher list with id+name (not just id)."""
    found_any = False
    for r in matrix["matrix"]:
        for sc in r["subject_coverage"]:
            for t in sc["teachers"]:
                assert "id" in t and "name" in t
                assert t["name"] and not t["name"].startswith("None")
                found_any = True
    assert found_any, "no teachers found in any subject coverage — unexpected for DEMO seed"


# ---------- RBAC ----------
def test_teacher_forbidden(teacher):
    r = teacher.get(f"{API}/timetable/class-subject-coverage")
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"


def test_accounts_forbidden(accounts):
    r = accounts.get(f"{API}/timetable/class-subject-coverage")
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"


def test_parent_forbidden(parent):
    r = parent.get(f"{API}/timetable/class-subject-coverage")
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"


def test_unauthenticated_rejected():
    r = requests.get(f"{API}/timetable/class-subject-coverage", timeout=10)
    assert r.status_code in (401, 403), r.status_code


# ---------- TENANT ISOLATION (no _id leak, no foreign teachers) ----------
def test_no_mongo_id_in_response(matrix):
    """Sanity: response must not contain `_id` from MongoDB."""
    import json
    blob = json.dumps(matrix)
    assert '"_id"' not in blob, "MongoDB _id leaked in response"


def test_teachers_are_school_scoped(admin, matrix):
    """Every teacher id surfaced in matrix must belong to the caller's school."""
    users = admin.get(f"{API}/users", params={"role": "teacher"}).json()
    school_teacher_ids = {u["id"] for u in users}
    for r in matrix["matrix"]:
        for sc in r["subject_coverage"]:
            for t in sc["teachers"]:
                assert t["id"] in school_teacher_ids, (
                    f"teacher {t['id']} in matrix not in school teachers"
                )
