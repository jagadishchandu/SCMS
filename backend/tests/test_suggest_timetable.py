"""Regression tests for POST /api/timetable/suggest (auto-balanced timetable generator)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://class-roster-77.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# DEMO seed snapshot (per iteration_15 context / problem statement)
CLASS_ID_GRADE5 = "9c33b98760fb4a82b63f44de"
CLASS_ID_GRADE6 = "6573544e9b3648d68198fa44"


# ---- shared session fixtures (HttpOnly-cookie auth) ----
def _login_session(email: str, password: str, role: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role})
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_headers():
    return _login_session("principal@sunrise.edu", "School@123", "school_admin")


@pytest.fixture(scope="module")
def teacher_headers():
    return _login_session("priya@sunrise.edu", "Teacher@123", "teacher")


@pytest.fixture(scope="module")
def accounts_headers():
    return _login_session("accounts@sunrise.edu", "Accounts@123", "accounts")


@pytest.fixture(scope="module")
def school_subjects(admin_headers):
    r = admin_headers.get(f"{API}/academic/subjects")
    assert r.status_code == 200
    return r.json()


# ---- Happy path: defaults ----
class TestSuggestDefaults:
    def test_happy_path_defaults_grade5_b(self, admin_headers):
        payload = {"class_id": CLASS_ID_GRADE5, "section": "B"}
        r = admin_headers.post(f"{API}/timetable/suggest", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        # Shape
        for k in ("slots", "warnings", "subject_distribution", "days", "periods_per_day", "total_slots"):
            assert k in body, f"missing {k}"
        # Defaults: Mon-Fri × 6 periods
        assert body["days"] == ["mon", "tue", "wed", "thu", "fri"]
        assert body["periods_per_day"] == 6
        assert body["total_slots"] == 30
        assert len(body["slots"]) == 30
        # Subject_distribution sums to total_slots
        assert sum(body["subject_distribution"].values()) == 30

    def test_slot_shape_and_times(self, admin_headers):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r.status_code == 200
        slots = r.json()["slots"]
        for s in slots:
            for k in ("day", "period", "subject_id", "teacher_id", "class_id", "section", "start_time", "end_time"):
                assert k in s
            assert s["class_id"] == CLASS_ID_GRADE5
            assert s["section"] == "B"
            assert len(s["start_time"]) == 5 and s["start_time"][2] == ":"
            assert len(s["end_time"]) == 5 and s["end_time"][2] == ":"
        # First slot starts at 09:00, end at 09:45 (45 min default)
        first = [s for s in slots if s["day"] == "mon" and s["period"] == 1][0]
        assert first["start_time"] == "09:00"
        assert first["end_time"] == "09:45"
        # Period 2 advances by 45 min
        second = [s for s in slots if s["day"] == "mon" and s["period"] == 2][0]
        assert second["start_time"] == "09:45"
        assert second["end_time"] == "10:30"

    def test_no_back_to_back_same_subject_when_possible(self, admin_headers, school_subjects):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE6, "section": "A"},
)
        slots = r.json()["slots"]
        # Group by day, sort by period
        from collections import defaultdict
        by_day = defaultdict(list)
        for s in slots:
            by_day[s["day"]].append(s)
        # When subject count > 1, expect very few back-to-back repeats
        bb = 0
        for d, lst in by_day.items():
            lst.sort(key=lambda x: x["period"])
            for i in range(len(lst) - 1):
                if lst[i]["subject_id"] == lst[i + 1]["subject_id"]:
                    bb += 1
        # 5 subjects × 6 periods/day → impossible to need any back-to-back
        assert bb == 0, f"unexpected back-to-back same-subject pairs: {bb}"

    def test_teacher_no_double_booking_within_grid(self, admin_headers):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE6, "section": "B"},
)
        slots = r.json()["slots"]
        # No (day,period,teacher_id) duplicate within the generated grid (excluding empty teacher)
        seen = set()
        for s in slots:
            if not s["teacher_id"]:
                continue
            key = (s["day"], s["period"], s["teacher_id"])
            assert key not in seen, f"duplicate teacher slot in own grid: {key}"
            seen.add(key)


# ---- Subject overrides ----
class TestSubjectOverrides:
    def test_override_pins_count_and_distributes_rest(self, admin_headers, school_subjects):
        # Pin first subject to 10 periods, rest auto
        sid = school_subjects[0]["id"]
        r = admin_headers.post(f"{API}/timetable/suggest", json={
                "class_id": CLASS_ID_GRADE5,
                "section": "B",
                "subject_periods": {sid: 10},
            },
)
        assert r.status_code == 200
        body = r.json()
        assert body["subject_distribution"][sid] == 10
        assert sum(body["subject_distribution"].values()) == body["total_slots"]

    def test_override_sum_overflow_returns_400(self, admin_headers, school_subjects):
        sid = school_subjects[0]["id"]
        r = admin_headers.post(f"{API}/timetable/suggest", json={
                "class_id": CLASS_ID_GRADE5,
                "section": "B",
                "periods_per_day": 6,
                "subject_periods": {sid: 9999},
            },
)
        assert r.status_code == 400


# ---- Error handling ----
class TestSuggestErrors:
    def test_invalid_class_id_404(self, admin_headers):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": "ffffffffffffffffffffffff", "section": "A"},
)
        assert r.status_code == 404

    def test_invalid_section_400(self, admin_headers):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "Z"},
)
        assert r.status_code == 400
        assert "section" in r.json().get("detail", "").lower()


# ---- RBAC ----
class TestSuggestRBAC:
    def test_teacher_forbidden(self, teacher_headers):
        r = teacher_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r.status_code == 403

    def test_accounts_forbidden(self, accounts_headers):
        r = accounts_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r.status_code == 403

    def test_unauthenticated_blocked(self):
        r = requests.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"})
        assert r.status_code in (401, 403)


# ---- Existing-timetable awareness ----
class TestExistingTimetable:
    def test_ignores_own_section_when_regenerating(self, admin_headers):
        # Grade 5 B starts empty per seed. First suggestion:
        r1 = admin_headers.post(
            f"{API}/timetable/suggest",
            json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r1.status_code == 200
        first_total = r1.json()["total_slots"]
        # Save it via bulk (only slots with teacher_id)
        slots_to_save = [s for s in r1.json()["slots"] if s.get("teacher_id")]
        save = admin_headers.post(f"{API}/timetable/bulk", json={
                "class_id": CLASS_ID_GRADE5,
                "section": "B",
                "slots": slots_to_save,
            },
)
        assert save.status_code == 200, save.text
        # Re-suggest for Grade 5 B → should give same total_slots and not warn about own teachers
        r2 = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["total_slots"] == first_total
        # Warnings shouldn't mention Grade 5 B itself (warnings reference subjects, not sections,
        # but at minimum the suggestion must succeed and length must match)
        assert len(body2["slots"]) == first_total

    def test_save_flow_persists_via_bulk_and_reads_back(self, admin_headers):
        # Generate for Grade 6 A
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE6, "section": "A"},
)
        assert r.status_code == 200
        slots = [s for s in r.json()["slots"] if s.get("teacher_id")]
        assert len(slots) > 0
        save = admin_headers.post(f"{API}/timetable/bulk", json={"class_id": CLASS_ID_GRADE6, "section": "A", "slots": slots},
)
        assert save.status_code == 200
        assert save.json()["inserted"] == len(slots)
        # Read back
        got = admin_headers.get(f"{API}/timetable", params={"class_id": CLASS_ID_GRADE6, "section": "A"},
)
        assert got.status_code == 200
        rows = got.json()
        assert len(rows) == len(slots)


# ---- Empty-teacher-subject warning surfacing ----
class TestWarnings:
    def test_warnings_are_strings_when_present(self, admin_headers):
        r = admin_headers.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"},
)
        assert r.status_code == 200
        warnings = r.json()["warnings"]
        assert isinstance(warnings, list)
        for w in warnings:
            assert isinstance(w, str)
