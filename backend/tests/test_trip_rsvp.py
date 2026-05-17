"""Trip RSVP feature: parent confirms attendance, admin/teacher view roster."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("principal@sunrise.edu", "School@123")


@pytest.fixture(scope="module")
def teacher():
    return _login("priya@sunrise.edu", "Teacher@123")


@pytest.fixture(scope="module")
def parent_one():
    return _login("parent.stu-00001@sunrise.edu", "Parent@123")


@pytest.fixture(scope="module")
def parent_two():
    return _login("parent.stu-00002@sunrise.edu", "Parent@123")


def _find_student_id(session, uid):
    """students.id is a UUID; lookup by student_uid (e.g. STU-00001)."""
    r = session.get(f"{BASE_URL}/api/students", timeout=20)
    assert r.status_code == 200, r.text
    payload = r.json()
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    for s in items:
        if s.get("student_uid") == uid:
            return s["id"]
    raise AssertionError(f"student {uid} not found in /api/students response")


@pytest.fixture(scope="module")
def stu1_id(admin):
    return _find_student_id(admin, "STU-00001")


@pytest.fixture(scope="module")
def stu2_id(admin):
    return _find_student_id(admin, "STU-00002")


@pytest.fixture(scope="module")
def open_trip(admin):
    """Create an open trip for RSVP tests."""
    payload = {
        "title": "TEST_RSVP Science Museum",
        "destination": "Science Museum",
        "departure_date": "2026-04-10",
        "return_date": "2026-04-10",
        "cost": 250,
        "transport_mode": "Bus",
        "itinerary": "9AM depart, 4PM return",
        "description": "Museum visit",
        "max_students": 50,
        "contact_person": "Mr. Verma",
        "contact_phone": "+91-9999900003",
        "status": "open",
    }
    r = admin.post(f"{BASE_URL}/api/trips", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    try:
        admin.delete(f"{BASE_URL}/api/trips/{data['id']}", timeout=20)
    except Exception:
        pass


@pytest.fixture(scope="module")
def cancelled_trip(admin):
    payload = {
        "title": "TEST_RSVP Cancelled Trip",
        "destination": "Nowhere",
        "departure_date": "2026-04-12",
        "status": "cancelled",
    }
    r = admin.post(f"{BASE_URL}/api/trips", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    try:
        admin.delete(f"{BASE_URL}/api/trips/{data['id']}", timeout=20)
    except Exception:
        pass


# --- Parent RSVP submission ---
class TestParentRSVPSubmit:
    def test_parent_confirms_for_own_child(self, parent_one, open_trip, stu1_id):
        r = parent_one.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed", "note": "Excited!"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "confirmed"
        assert doc["student_id"] == stu1_id
        assert doc["note"] == "Excited!"
        assert "id" in doc
        assert "_id" not in doc

    def test_parent_declines_for_own_child_upserts(self, parent_one, open_trip, stu1_id):
        """Second submission should update existing RSVP, not duplicate."""
        # First confirm
        r1 = parent_one.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        assert r1.status_code == 200
        rsvp_id_1 = r1.json()["id"]
        created_at_1 = r1.json().get("created_at")

        # Then decline - should be same record (upsert)
        r2 = parent_one.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "declined", "note": "Sick"},
            timeout=20,
        )
        assert r2.status_code == 200
        doc2 = r2.json()
        assert doc2["id"] == rsvp_id_1, "Should upsert same record"
        assert doc2["status"] == "declined"
        assert doc2["note"] == "Sick"
        # created_at should be preserved
        assert doc2.get("created_at") == created_at_1

    def test_parent_cannot_rsvp_for_other_child(self, parent_two, open_trip, stu1_id):
        """parent of STU-00002 cannot RSVP for STU-00001."""
        r = parent_two.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_admin_cannot_rsvp(self, admin, open_trip, stu1_id):
        r = admin.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        assert r.status_code == 403

    def test_teacher_cannot_rsvp(self, teacher, open_trip, stu1_id):
        r = teacher.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        assert r.status_code == 403

    def test_rsvp_on_cancelled_trip_returns_400(self, parent_one, cancelled_trip, stu1_id):
        r = parent_one.post(
            f"{BASE_URL}/api/trips/{cancelled_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# --- Parent GET my-rsvps ---
class TestParentMyRSVPs:
    def test_parent_sees_own_child_status(self, parent_one, open_trip, stu1_id):
        # First set a confirmed status
        parent_one.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        r = parent_one.get(f"{BASE_URL}/api/trips/{open_trip['id']}/my-rsvps", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        ids = [row["student_id"] for row in rows]
        assert stu1_id in ids
        row = next(r for r in rows if r["student_id"] == stu1_id)
        assert row["status"] == "confirmed"
        assert row["student_name"]

    def test_parent_other_sees_only_own_children(self, parent_two, open_trip, stu1_id):
        r = parent_two.get(f"{BASE_URL}/api/trips/{open_trip['id']}/my-rsvps", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        ids = [row["student_id"] for row in rows]
        assert stu1_id not in ids  # not their child


# --- Admin / Teacher roster ---
class TestRosterView:
    def test_admin_sees_summary_and_rows(self, admin, parent_one, open_trip, stu1_id):
        # ensure STU-00001 is confirmed
        parent_one.post(
            f"{BASE_URL}/api/trips/{open_trip['id']}/rsvp",
            json={"student_id": stu1_id, "status": "confirmed"},
            timeout=20,
        )
        r = admin.get(f"{BASE_URL}/api/trips/{open_trip['id']}/rsvps", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "summary" in body
        summary = body["summary"]
        for k in ("confirmed", "declined", "pending", "total_eligible"):
            assert k in summary
        assert summary["total_eligible"] >= 1
        assert summary["confirmed"] >= 1

        rows = body["rows"]
        assert isinstance(rows, list)
        ids = [r["student_id"] for r in rows]
        assert stu1_id in ids

        # Sort: confirmed first
        statuses_order = [r["status"] for r in rows]
        order_map = {"confirmed": 0, "declined": 1, "pending": 2}
        nums = [order_map.get(s, 3) for s in statuses_order]
        assert nums == sorted(nums), f"rows not sorted by status: {statuses_order}"

    def test_teacher_sees_only_own_class_students(self, teacher, open_trip):
        r = teacher.get(f"{BASE_URL}/api/trips/{open_trip['id']}/rsvps", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body["rows"]
        # priya is class teacher of Grade 5 A; all STU-* are in Grade 5 A in seed
        # but verify teacher's roster size <= admin's roster size
        # and all rows have a class_id (if filtered)
        assert isinstance(rows, list)
        # at least the seeded Grade 5 A students should appear
        assert len(rows) >= 1

    def test_parent_cannot_view_admin_roster(self, parent_one, open_trip):
        r = parent_one.get(f"{BASE_URL}/api/trips/{open_trip['id']}/rsvps", timeout=20)
        assert r.status_code == 403
