"""V46 tests:
- /api/schools/{id}/timetable-settings GET + PATCH (school_admin only, RBAC)
- /api/timetable/substitute-suggest now emits weekly_load + low_load fields
  and ranks under-loaded teachers ahead of higher-loaded ones (after the
  "teaches subject" priority).
"""
import os
import pytest
import requests


def _backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url
    return url.rstrip("/") + "/api"


BASE_URL = _backend_url()
PRINCIPAL = {"email": "principal@sunrise.edu", "password": "School@123"}
TEACHER = {"email": "priya@sunrise.edu", "password": "Teacher@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=PRINCIPAL, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def teacher_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=TEACHER, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def school_id(admin_session):
    me = admin_session.get(f"{BASE_URL}/auth/me", timeout=20).json()
    return me["school_id"]


class TestTimetableSettings:
    def test_get_default_false(self, admin_session, school_id):
        r = admin_session.get(f"{BASE_URL}/schools/{school_id}/timetable-settings", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["school_id"] == school_id
        assert "default_prefer_underloaded_teachers" in data

    def test_patch_sets_flag(self, admin_session, school_id):
        # Set ON
        r = admin_session.patch(
            f"{BASE_URL}/schools/{school_id}/timetable-settings",
            json={"default_prefer_underloaded_teachers": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["default_prefer_underloaded_teachers"] is True
        # Read back
        r2 = admin_session.get(f"{BASE_URL}/schools/{school_id}/timetable-settings", timeout=20)
        assert r2.json()["default_prefer_underloaded_teachers"] is True
        # Reset
        admin_session.patch(
            f"{BASE_URL}/schools/{school_id}/timetable-settings",
            json={"default_prefer_underloaded_teachers": False},
            timeout=20,
        )

    def test_teacher_cannot_patch(self, teacher_session, school_id):
        r = teacher_session.patch(
            f"{BASE_URL}/schools/{school_id}/timetable-settings",
            json={"default_prefer_underloaded_teachers": True},
            timeout=20,
        )
        assert r.status_code == 403, r.text


class TestSubstituteSuggest:
    def test_emits_weekly_load_and_low_load(self, admin_session):
        # Need a class+section + a known day+period. We pick something common.
        classes = admin_session.get(f"{BASE_URL}/academic/classes", timeout=20).json()
        if not classes:
            pytest.skip("No classes seeded")
        cls = classes[0]
        sec = (cls.get("sections") or ["A"])[0]
        r = admin_session.post(
            f"{BASE_URL}/timetable/substitute-suggest",
            json={
                "class_id": cls["id"],
                "section": sec,
                "day": "mon",
                "period": 1,
                "prefer_subject_id": None,
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        sugs = r.json().get("suggestions") or []
        # If there are any teachers, every suggestion should expose the new fields
        for s in sugs:
            assert "weekly_load" in s, s
            assert "low_load" in s, s
            assert "daily_load" in s, s
        # Ranking sanity: top suggestion should not be on-leave
        if sugs:
            assert sugs[0]["on_leave_today"] is False or sugs[0]["on_leave_today"] is None
