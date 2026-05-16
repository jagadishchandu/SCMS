"""
iter23 — Backend RBAC + cascade tests for POST /api/schools/{id}/students/bulk-delete

Pattern (per agent_to_agent_context_note): create a THROWAWAY school
(code = QA<rand>), seed a class + students, then exercise the endpoint.
NEVER touches DEMO Sunrise data.
"""
import os
import secrets
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://admin-reset-tool-2.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def platform():
    return _login("jagadishchandu789@gmail.com", "Manasa@123")


@pytest.fixture(scope="session")
def school_admin():
    return _login("principal@sunrise.edu", "School@123")


@pytest.fixture(scope="session")
def teacher():
    return _login("priya@sunrise.edu", "Teacher@123")


@pytest.fixture(scope="session")
def throwaway_school(platform):
    """Create a fresh school + class + 3 students; return ids + cleanup later."""
    suffix = secrets.token_hex(3).upper()
    code = f"QA{suffix}"
    payload = {
        "name": f"QA School {suffix}",
        "code": code,
        "address": "QA Lane",
        "phone": "+910000000000",
        "email": f"qa{suffix.lower()}@qaschool.example.com",
        "academic_year": "2025-2026",
        "admin_email": f"admin.qa{suffix.lower()}@qaschool.example.com",
        "admin_password": "Admin@123",
        "admin_name": "QA Admin",
        "auto_approve": True,
        "initial_children_count": 50,
    }
    r = platform.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, f"create school failed: {r.status_code} {r.text}"
    school = r.json()["school"]
    school_id = school["id"]
    admin_email = payload["admin_email"]

    # Log in as the new school admin to create a class + students
    sa = _login(admin_email, payload["admin_password"])

    cr = sa.post(f"{API}/academic/classes", json={"name": "Grade 1", "sections": ["A"]}, timeout=20)
    assert cr.status_code == 200, f"create class failed: {cr.status_code} {cr.text}"
    class_id = cr.json()["id"]

    student_ids = []
    parent_user_ids = []
    for i in range(3):
        body = {
            "name": f"QA Student {i + 1}",
            "class_id": class_id,
            "section": "A",
            "roll_number": str(i + 1),
            "gender": "M",
            "parent": {
                "name": f"QA Parent {i + 1}",
                "phone": f"+9199999000{i:02d}",
                "email": f"parent.qa{suffix.lower()}.{i}@qaschool.example.com",
            },
        }
        sr = sa.post(f"{API}/students", json=body, timeout=20)
        assert sr.status_code == 200, f"create student failed: {sr.status_code} {sr.text}"
        sjson = sr.json()
        student_ids.append(sjson["id"])
        parent_user_ids.append(sjson.get("parent_user_id"))

    yield {
        "school_id": school_id,
        "code": code,
        "admin_email": admin_email,
        "admin_session": sa,
        "class_id": class_id,
        "student_ids": student_ids,
        "parent_user_ids": parent_user_ids,
    }
    # Best-effort cleanup: bulk-delete any remaining students
    try:
        remaining = sa.get(f"{API}/students").json()
        if isinstance(remaining, list) and remaining:
            ids = [s["id"] for s in remaining]
            platform.post(
                f"{API}/schools/{school_id}/students/bulk-delete",
                json={"student_ids": ids, "confirm_code": code},
                timeout=20,
            )
    except Exception:
        pass


# ---------- RBAC -------------------------------------------------------------

def test_rbac_anonymous_returns_401(throwaway_school):
    r = requests.post(
        f"{API}/schools/{throwaway_school['school_id']}/students/bulk-delete",
        json={"student_ids": throwaway_school["student_ids"][:1], "confirm_code": throwaway_school["code"]},
        timeout=20,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_rbac_school_admin_returns_403(throwaway_school):
    sa = throwaway_school["admin_session"]
    r = sa.post(
        f"{API}/schools/{throwaway_school['school_id']}/students/bulk-delete",
        json={"student_ids": throwaway_school["student_ids"][:1], "confirm_code": throwaway_school["code"]},
        timeout=20,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_rbac_teacher_returns_403(teacher, throwaway_school):
    r = teacher.post(
        f"{API}/schools/{throwaway_school['school_id']}/students/bulk-delete",
        json={"student_ids": throwaway_school["student_ids"][:1], "confirm_code": throwaway_school["code"]},
        timeout=20,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# ---------- Validation ------------------------------------------------------

def test_unknown_school_returns_404(platform, throwaway_school):
    r = platform.post(
        f"{API}/schools/does-not-exist-xyz/students/bulk-delete",
        json={"student_ids": throwaway_school["student_ids"][:1], "confirm_code": "ANY"},
        timeout=20,
    )
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"


def test_wrong_confirm_code_returns_400(platform, throwaway_school):
    r = platform.post(
        f"{API}/schools/{throwaway_school['school_id']}/students/bulk-delete",
        json={"student_ids": throwaway_school["student_ids"][:1], "confirm_code": "WRONG-CODE"},
        timeout=20,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    assert "confirm_code" in r.text.lower() or "code" in r.text.lower()


def test_empty_student_ids_returns_400(platform, throwaway_school):
    r = platform.post(
        f"{API}/schools/{throwaway_school['school_id']}/students/bulk-delete",
        json={"student_ids": [], "confirm_code": throwaway_school["code"]},
        timeout=20,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# ---------- Happy path + cascade -------------------------------------------

def test_bulk_delete_success_and_cascade(platform, throwaway_school):
    school_id = throwaway_school["school_id"]
    code = throwaway_school["code"]
    target_ids = list(throwaway_school["student_ids"])  # delete all 3
    parent_ids = list(throwaway_school["parent_user_ids"])

    # Sanity — students exist via /people
    pre = platform.get(f"{API}/schools/{school_id}/people").json()
    pre_ids = {s["id"] for s in pre.get("students", [])}
    assert set(target_ids).issubset(pre_ids), "seed students missing in /people before delete"

    # DELETE
    r = platform.post(
        f"{API}/schools/{school_id}/students/bulk-delete",
        json={"student_ids": target_ids, "confirm_code": code},
        timeout=30,
    )
    assert r.status_code == 200, f"bulk-delete failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("deleted_students") == len(target_ids), body
    assert body.get("requested") == len(target_ids)
    assert "cascade" in body and isinstance(body["cascade"], dict)
    # Every documented cascade collection is reported
    for coll in ("attendance", "marks", "fees", "fee_payments", "activity_enrollments", "sick_leaves"):
        assert coll in body["cascade"], f"cascade key missing: {coll}"

    # /people no longer lists those students
    post = platform.get(f"{API}/schools/{school_id}/people").json()
    post_ids = {s["id"] for s in post.get("students", [])}
    assert post_ids.isdisjoint(target_ids), f"students still listed after delete: {post_ids & set(target_ids)}"

    # Parent users had no other children -> should be deactivated.
    # We assert via the deactivated_parents count returned by the endpoint:
    # each of the 3 seed students has a unique parent and no other children,
    # so the count must equal the number of distinct parents that existed.
    distinct_parents = len([p for p in parent_ids if p])
    assert body.get("deactivated_parents") == distinct_parents, (
        f"deactivated_parents={body.get('deactivated_parents')} expected={distinct_parents}"
    )


def test_bulk_delete_audit_log(platform, throwaway_school):
    """Audit entries are created (run after happy-path test in the same session)."""
    school_id = throwaway_school["school_id"]
    # If the audit endpoint is restricted/absent, skip rather than fail the suite.
    r = platform.get(f"{API}/audit?school_id={school_id}&action=bulk_delete_students", timeout=20)
    if r.status_code == 404:
        pytest.skip("Audit endpoint not exposed under /audit")
    assert r.status_code == 200, f"audit GET failed: {r.status_code} {r.text}"
    entries = r.json()
    if isinstance(entries, dict) and "items" in entries:
        entries = entries["items"]
    matched = [
        e for e in entries
        if e.get("action") == "bulk_delete_students"
        and e.get("resource") == "school"
        and e.get("school_id") == school_id
    ]
    assert matched, f"no bulk_delete_students audit entry found for {school_id}"
    meta = matched[0].get("meta") or {}
    assert "deleted_count" in meta
    assert "cascade" in meta
    assert "deactivated_parents" in meta
    assert "uids" in meta
