"""v1.21 — Per-class fee structure templates: section + term + clone-to-sections.

Covers:
- POST /api/fees/structures with optional `section` + `term` (class-wide vs section-scoped).
- POST /api/fees/structures with invalid section -> 400.
- POST /api/fees/structures/{id}/clone-to-sections: clones to other sections, idempotent, class-wide -> message.
- POST /api/fees/structures/{id}/assign honors section filter.
- Accountant role can create + clone.
- GET /api/fees/structures returns section + term (works for legacy docs too).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}
ACCOUNTS = {"email": "accounts@sunrise.edu", "password": "Accounts@123"}


# ---------- helpers ----------

def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return login(ADMIN)


@pytest.fixture(scope="module")
def accounts_session():
    return login(ACCOUNTS)


@pytest.fixture(scope="module")
def grade5(admin_session):
    classes = admin_session.get(f"{API}/academic/classes").json()
    g5 = next((c for c in classes if c["name"] == "Grade 5"), None)
    assert g5, "Grade 5 not seeded"
    assert "A" in [s.upper() for s in (g5.get("sections") or [])]
    return g5


@pytest.fixture(scope="module")
def grade6(admin_session):
    classes = admin_session.get(f"{API}/academic/classes").json()
    g6 = next((c for c in classes if c["name"] == "Grade 6"), None)
    assert g6
    return g6


def _suffix():
    return str(int(time.time() * 1000))[-7:]


# ---------- 1) Create with section + term ----------

class TestCreateStructure:
    def test_create_classwide_no_section(self, admin_session, grade5):
        name = f"TEST_G5_ClassWide_{_suffix()}"
        r = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": name,
            "items": [{"type": "tuition", "amount": 1000}],
            "due_date": "2026-03-31",
            "term": "Term 1",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["section"] is None
        assert d["term"] == "Term 1"
        assert d["total"] == 1000
        assert d["class_id"] == grade5["id"]
        assert d["name"] == name
        # GET verifies persistence
        all_s = admin_session.get(f"{API}/fees/structures").json()
        assert any(x["id"] == d["id"] and x.get("section") is None for x in all_s)

    def test_create_section_scoped(self, admin_session, grade5):
        name = f"TEST_G5_A_{_suffix()}"
        r = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": name,
            "items": [{"type": "tuition", "amount": 1500}],
            "due_date": "2026-03-31",
            "section": "A",
            "term": "Term 1",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["section"] == "A"
        assert d["term"] == "Term 1"

    def test_create_lowercase_section_normalized_upper(self, admin_session, grade5):
        r = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": f"TEST_G5_lower_{_suffix()}",
            "items": [{"type": "tuition", "amount": 100}],
            "due_date": "2026-03-31",
            "section": "a",
        })
        assert r.status_code == 200
        assert r.json()["section"] == "A"

    def test_create_invalid_section_returns_400(self, admin_session, grade5):
        r = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": f"TEST_G5_BadSec_{_suffix()}",
            "items": [{"type": "tuition", "amount": 100}],
            "due_date": "2026-03-31",
            "section": "Z",
        })
        assert r.status_code == 400, r.text
        assert "Z" in r.text or "section" in r.text.lower()


# ---------- 2) Clone to sections ----------

class TestCloneToSections:
    def test_clone_section_scoped_to_other_sections(self, admin_session, grade5):
        name = f"TEST_CloneG5_{_suffix()}"
        src = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": name,
            "items": [{"type": "tuition", "amount": 2000}],
            "due_date": "2026-03-31",
            "section": "A",
            "term": "Term 1",
        }).json()
        r = admin_session.post(f"{API}/fees/structures/{src['id']}/clone-to-sections")
        assert r.status_code == 200, r.text
        d = r.json()
        # Grade 5 has A,B → only B should be cloned
        assert d["cloned"] == 1
        assert d["skipped"] == []
        assert d["target_sections"] == ["B"]
        assert len(d["created_ids"]) == 1

        # Verify cloned doc on GET
        listed = admin_session.get(f"{API}/fees/structures").json()
        cloned_doc = next((x for x in listed if x["id"] == d["created_ids"][0]), None)
        assert cloned_doc is not None
        assert cloned_doc["section"] == "B"
        assert cloned_doc["name"] == name
        assert cloned_doc["term"] == "Term 1"
        assert cloned_doc["total"] == 2000

        # Idempotency: second call clones 0 and skips B
        r2 = admin_session.post(f"{API}/fees/structures/{src['id']}/clone-to-sections")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["cloned"] == 0
        assert "B" in d2["skipped"]

    def test_clone_classwide_returns_message(self, admin_session, grade5):
        src = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": f"TEST_CloneClassWide_{_suffix()}",
            "items": [{"type": "tuition", "amount": 500}],
            "due_date": "2026-03-31",
            "term": "Term 2",
        }).json()
        r = admin_session.post(f"{API}/fees/structures/{src['id']}/clone-to-sections")
        assert r.status_code == 200
        d = r.json()
        assert d["cloned"] == 0
        assert d["skipped"] == []
        assert "message" in d
        assert "class-wide" in d["message"].lower() or "no specific section" in d["message"].lower()

    def test_clone_unknown_structure_404(self, admin_session):
        r = admin_session.post(f"{API}/fees/structures/nonexistent-id/clone-to-sections")
        assert r.status_code == 404


# ---------- 3) Assign filtered by section ----------

class TestAssignBySection:
    def test_assign_section_scoped_only_targets_that_section(self, admin_session, grade5):
        # Get students in Grade 5
        students = admin_session.get(f"{API}/students").json()
        g5_students = [s for s in students if s["class_id"] == grade5["id"]]
        section_a = [s for s in g5_students if (s.get("section") or "").upper() == "A"]
        assert len(section_a) > 0, "Need section A students seeded"

        src = admin_session.post(f"{API}/fees/structures", json={
            "class_id": grade5["id"],
            "name": f"TEST_AssignA_{_suffix()}",
            "items": [{"type": "tuition", "amount": 10}],
            "due_date": "2026-03-31",
            "section": "A",
            "term": "Term 1",
        }).json()
        r = admin_session.post(f"{API}/fees/structures/{src['id']}/assign")
        assert r.status_code == 200
        body = r.json()
        # Assigned count must equal number of section A students (or 0 if already assigned)
        assert body["assigned"] <= len(section_a)

        # Verify fees emitted carry section + term
        fees = admin_session.get(f"{API}/fees").json()
        struct_fees = [f for f in fees if f.get("structure_id") == src["id"]]
        assert len(struct_fees) == len(section_a)
        # all should be section A
        assert all((f.get("section") or "").upper() == "A" for f in struct_fees)
        assert all(f.get("term") == "Term 1" for f in struct_fees)
        # no Section B students received this
        section_a_ids = {s["id"] for s in section_a}
        assigned_ids = {f["student_id"] for f in struct_fees}
        assert assigned_ids.issubset(section_a_ids)


# ---------- 4) Accountant role ----------

class TestAccountantRole:
    def test_accountant_can_create_and_clone(self, accounts_session, grade6):
        name = f"TEST_Acc_G6A_{_suffix()}"
        r = accounts_session.post(f"{API}/fees/structures", json={
            "class_id": grade6["id"],
            "name": name,
            "items": [{"type": "tuition", "amount": 800}],
            "due_date": "2026-03-31",
            "section": "A",
            "term": "Term 1",
        })
        assert r.status_code == 200, r.text
        src = r.json()
        assert src["section"] == "A"

        cr = accounts_session.post(f"{API}/fees/structures/{src['id']}/clone-to-sections")
        assert cr.status_code == 200, cr.text
        d = cr.json()
        assert d["cloned"] >= 0
        assert "B" in d["target_sections"]


# ---------- 5) GET resilience for legacy docs ----------

class TestListResilience:
    def test_list_returns_section_and_term_fields(self, admin_session):
        r = admin_session.get(f"{API}/fees/structures")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # Each doc should be parseable and the API shouldn't break on legacy items
        for it in items:
            # section/term fields may be None or missing for legacy — should NOT 500
            assert "id" in it
            assert "class_id" in it
            assert "name" in it
            # If present, term must be string-like or None
            if "term" in it and it["term"] is not None:
                assert isinstance(it["term"], str)
            if "section" in it and it["section"] is not None:
                assert isinstance(it["section"], str)
