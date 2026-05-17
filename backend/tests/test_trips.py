"""Trips feature: CRUD + role-based access tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for backend env
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
def parent():
    return _login("parent.stu-00001@sunrise.edu", "Parent@123")


@pytest.fixture(scope="module")
def created_trip(admin):
    payload = {
        "title": "TEST_ Zoo Visit",
        "destination": "Bannerghatta National Park",
        "departure_date": "2026-03-15",
        "return_date": "2026-03-15",
        "cost": 750,
        "transport_mode": "Bus",
        "itinerary": "8AM depart, 6PM return",
        "description": "Educational zoo trip",
        "max_students": 40,
        "contact_person": "Mr. Verma",
        "contact_phone": "+91-9999900003",
        "permission_slip_url": "https://example.com/slip.pdf",
        "status": "open",
    }
    r = admin.post(f"{BASE_URL}/api/trips", json=payload, timeout=20)
    assert r.status_code == 200, f"create trip failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["title"] == payload["title"]
    assert data["destination"] == payload["destination"]
    assert data["cost"] == 750
    assert data["max_students"] == 40
    assert "id" in data
    assert "_id" not in data  # mongo internal id excluded
    yield data
    # teardown
    try:
        admin.delete(f"{BASE_URL}/api/trips/{data['id']}", timeout=20)
    except Exception:
        pass


# --- Permissions ---
class TestTripPermissions:
    def test_teacher_cannot_create(self, teacher):
        r = teacher.post(f"{BASE_URL}/api/trips", json={
            "title": "TEST_x", "destination": "x", "departure_date": "2026-04-01",
        }, timeout=20)
        assert r.status_code == 403

    def test_parent_cannot_create(self, parent):
        r = parent.post(f"{BASE_URL}/api/trips", json={
            "title": "TEST_x", "destination": "x", "departure_date": "2026-04-01",
        }, timeout=20)
        assert r.status_code == 403

    def test_teacher_cannot_delete(self, teacher, created_trip):
        r = teacher.delete(f"{BASE_URL}/api/trips/{created_trip['id']}", timeout=20)
        assert r.status_code == 403

    def test_parent_cannot_delete(self, parent, created_trip):
        r = parent.delete(f"{BASE_URL}/api/trips/{created_trip['id']}", timeout=20)
        assert r.status_code == 403


# --- List / read ---
class TestTripList:
    def test_admin_list(self, admin, created_trip):
        r = admin.get(f"{BASE_URL}/api/trips", timeout=20)
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert created_trip["id"] in ids

    def test_teacher_list(self, teacher, created_trip):
        r = teacher.get(f"{BASE_URL}/api/trips", timeout=20)
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert created_trip["id"] in ids

    def test_parent_list(self, parent, created_trip):
        r = parent.get(f"{BASE_URL}/api/trips", timeout=20)
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert created_trip["id"] in ids

    def test_get_single(self, admin, created_trip):
        r = admin.get(f"{BASE_URL}/api/trips/{created_trip['id']}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == created_trip["title"]
        assert data["destination"] == created_trip["destination"]
        assert data["itinerary"] == "8AM depart, 6PM return"
        assert data["contact_phone"] == "+91-9999900003"
        assert "_id" not in data

    def test_get_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/trips/nonexistent-id-xxx", timeout=20)
        assert r.status_code == 404


# --- Update ---
class TestTripUpdate:
    def test_admin_update(self, admin, created_trip):
        r = admin.patch(f"{BASE_URL}/api/trips/{created_trip['id']}",
                        json={"cost": 999, "status": "closed"}, timeout=20)
        assert r.status_code == 200
        # GET to verify persistence
        r2 = admin.get(f"{BASE_URL}/api/trips/{created_trip['id']}", timeout=20)
        d = r2.json()
        assert d["cost"] == 999
        assert d["status"] == "closed"

    def test_teacher_cannot_update(self, teacher, created_trip):
        r = teacher.patch(f"{BASE_URL}/api/trips/{created_trip['id']}",
                          json={"cost": 1}, timeout=20)
        assert r.status_code == 403


# --- Delete + verify ---
class TestTripDelete:
    def test_admin_delete_and_verify(self, admin):
        # create new throwaway trip
        r = admin.post(f"{BASE_URL}/api/trips", json={
            "title": "TEST_DeleteMe", "destination": "Nowhere",
            "departure_date": "2026-05-01",
        }, timeout=20)
        assert r.status_code == 200
        tid = r.json()["id"]
        r = admin.delete(f"{BASE_URL}/api/trips/{tid}", timeout=20)
        assert r.status_code == 200
        r = admin.get(f"{BASE_URL}/api/trips/{tid}", timeout=20)
        assert r.status_code == 404
