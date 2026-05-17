"""v1.32.2 — Teacher add-student RBAC fix.

Bug: a teacher created with subjects but no class_teacher_map / timetable row
got blocked with "You are not assigned to any class yet" (HTTP 403) when
trying to add a student. Subject teachers often handle data entry before
being formally tied to a class.

Fix (`routes/students.py` create_student): permit teachers with no formal
assignment to add students to any class in their school. Teachers WITH
formal assignment remain restricted to their classes.
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


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"v322.admin.{suffix.lower()}@v322.example.com"
    admin_pw = "Admin@2026"
    payload = {
        "name": f"V322 School {suffix}", "code": f"V322{suffix}",
        "address": "x", "phone": "+910", "email": f"i.{suffix.lower()}@v322.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "V322 Admin",
        "auto_approve": True,
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    sa = _login(admin_email, admin_pw)

    # Two classes with sections.
    cls_a = sa.post(f"{API}/academic/classes", json={"name": f"ClsA{suffix}", "sections": ["A", "B"]}, timeout=15).json()
    cls_b = sa.post(f"{API}/academic/classes", json={"name": f"ClsB{suffix}", "sections": ["A"]}, timeout=15).json()
    sub = sa.post(f"{API}/academic/subjects", json={"name": f"Sub{suffix}"}, timeout=15).json()

    # Teacher 1 — assigned as class teacher of ClsA / A
    t1_email = f"v322.t1.{suffix.lower()}@v322.example.com"
    t1_pw = "Teach@2026"
    sa.post(f"{API}/users", json={
        "email": t1_email, "password": t1_pw, "name": "T1",
        "role": "teacher", "subjects": [sub["id"]],
    }, timeout=15)
    t1_user = next(u for u in sa.get(f"{API}/users").json() if u["email"] == t1_email)
    sa.post(f"{API}/academic/class-teacher", json={
        "class_id": cls_a["id"], "section": "A", "teacher_id": t1_user["id"],
    }, timeout=15)
    t1 = _login(t1_email, t1_pw)

    # Teacher 2 — created with subjects but NO class assignment (the bug case)
    t2_email = f"v322.t2.{suffix.lower()}@v322.example.com"
    t2_pw = "Teach@2026"
    sa.post(f"{API}/users", json={
        "email": t2_email, "password": t2_pw, "name": "T2",
        "role": "teacher", "subjects": [sub["id"]],
    }, timeout=15)
    t2 = _login(t2_email, t2_pw)

    yield {
        "platform": plat, "school_admin": sa,
        "assigned_teacher": t1, "unassigned_teacher": t2,
        "class_a": cls_a, "class_b": cls_b,
    }


# ---------- The bug fix ----------

class TestUnassignedTeacherCanAdd:
    def test_unassigned_teacher_can_add_student_anywhere(self, ctx):
        """The exact bug repro: a teacher with subjects but no class assignment
        used to get 403 'You are not assigned to any class yet'. Now permitted."""
        r = ctx["unassigned_teacher"].post(f"{API}/students", json={
            "name": "Bug Repro Student", "class_id": ctx["class_a"]["id"], "section": "A",
            "parent": {"name": "P1", "phone": "+91100000001", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Bug Repro Student"
        assert body["class_id"] == ctx["class_a"]["id"]
        # Parent auto-created
        assert body["parent_login"]["is_new_account"] is True
        # Track for the visibility test below
        ctx["created_id"] = body["id"]
        ctx["created_uid"] = body["student_uid"]

    def test_created_student_appears_in_teachers_list(self, ctx):
        """v1.32.3 — a teacher must immediately see students they added, even
        without any class assignment. Tagged via `created_by_id` on the doc."""
        r = ctx["unassigned_teacher"].get(f"{API}/students", timeout=15)
        assert r.status_code == 200, r.text
        students = r.json()
        ids = [s["id"] for s in students]
        assert ctx.get("created_id") in ids, f"created student missing from teacher list: {ids}"
        own = next(s for s in students if s["id"] == ctx["created_id"])
        assert own.get("created_by_id"), "students must be tagged with created_by_id"
        assert own["created_by_role"] == "teacher"

    def test_created_student_accessible_via_get_by_uid(self, ctx):
        r = ctx["unassigned_teacher"].get(f"{API}/students/by-uid/{ctx['created_uid']}", timeout=15)
        assert r.status_code == 200, r.text

    def test_created_student_accessible_for_parent_login(self, ctx):
        r = ctx["unassigned_teacher"].get(f"{API}/students/{ctx['created_id']}/parent-login", timeout=15)
        assert r.status_code == 200, r.text

    def test_created_student_can_be_updated_by_creator(self, ctx):
        r = ctx["unassigned_teacher"].patch(
            f"{API}/students/{ctx['created_id']}",
            json={"medical_notes": "Allergies updated by teacher"},
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_unassigned_teacher_can_add_to_any_section(self, ctx):
        r = ctx["unassigned_teacher"].post(f"{API}/students", json={
            "name": "Bug Repro B", "class_id": ctx["class_a"]["id"], "section": "B",
            "parent": {"name": "P2", "phone": "+91100000002", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["section"] == "B"

    def test_unassigned_teacher_can_add_to_a_different_class(self, ctx):
        r = ctx["unassigned_teacher"].post(f"{API}/students", json={
            "name": "Bug Repro Cls2", "class_id": ctx["class_b"]["id"], "section": "A",
            "parent": {"name": "P3", "phone": "+91100000003", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["class_id"] == ctx["class_b"]["id"]


# ---------- Validation: unknown class / section still rejected ----------

class TestValidationStillEnforced:
    def test_unknown_class_id_returns_400(self, ctx):
        r = ctx["unassigned_teacher"].post(f"{API}/students", json={
            "name": "Bad Class", "class_id": "no-such-class-id-zzz", "section": "A",
            "parent": {"name": "P", "phone": "+91", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 400, r.text
        assert "Class not found" in r.json()["detail"]

    def test_invalid_section_returns_400_with_available_list(self, ctx):
        r = ctx["unassigned_teacher"].post(f"{API}/students", json={
            "name": "Bad Section", "class_id": ctx["class_a"]["id"], "section": "ZZ",
            "parent": {"name": "P", "phone": "+91", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert "ZZ" in detail
        # Surfaces available sections from the class config
        assert "['A', 'B']" in detail or "A" in detail


# ---------- Assigned teachers still tightly scoped ----------

class TestAssignedTeacherStillRestricted:
    def test_assigned_teacher_can_add_in_own_class(self, ctx):
        """Teacher T1 is class teacher of ClsA / A → can add there."""
        r = ctx["assigned_teacher"].post(f"{API}/students", json={
            "name": "Own Class Add", "class_id": ctx["class_a"]["id"], "section": "A",
            "parent": {"name": "POwn", "phone": "+91200000001", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 200, r.text

    def test_assigned_teacher_cannot_add_in_other_class(self, ctx):
        """T1 is NOT assigned to ClsB → still blocked with 403."""
        r = ctx["assigned_teacher"].post(f"{API}/students", json={
            "name": "Other Class Reject", "class_id": ctx["class_b"]["id"], "section": "A",
            "parent": {"name": "PRej", "phone": "+91200000002", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 403, r.text
        assert "only add students to classes you teach" in r.json()["detail"]

    def test_assigned_teacher_cannot_add_to_other_section_of_own_class(self, ctx):
        """T1 assigned to ClsA / A — section B in the same class is still off-limits."""
        r = ctx["assigned_teacher"].post(f"{API}/students", json={
            "name": "Other Section Reject", "class_id": ctx["class_a"]["id"], "section": "B",
            "parent": {"name": "PSec", "phone": "+91200000003", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 403, r.text


# ---------- School admin still works the same ----------

class TestSchoolAdminUnaffected:
    def test_school_admin_can_add_anywhere(self, ctx):
        r = ctx["school_admin"].post(f"{API}/students", json={
            "name": "Admin Add", "class_id": ctx["class_b"]["id"], "section": "A",
            "parent": {"name": "PAdm", "phone": "+91300000001", "relationship": "father"},
        }, timeout=15)
        assert r.status_code == 200, r.text
