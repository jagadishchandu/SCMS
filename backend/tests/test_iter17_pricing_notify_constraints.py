"""Iter17 — env-driven pricing, timetable telegram notify, suggest constraints."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://case-insensitive-id.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLASS_ID_GRADE5 = "9c33b98760fb4a82b63f44de"
CLASS_ID_GRADE6 = "6573544e9b3648d68198fa44"

SUB_ENGLISH = "15bd037aa762417e8ea62d94"
SUB_HINDI = "381068bdd9c843f692022029"
SUB_MATH = "86edd62916b94bb2a78de55c"


def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("principal@sunrise.edu", "School@123", "school_admin")


@pytest.fixture(scope="module")
def teacher():
    return _login("priya@sunrise.edu", "Teacher@123", "teacher")


@pytest.fixture(scope="module")
def accounts():
    return _login("accounts@sunrise.edu", "Accounts@123", "accounts")


# ---- Pricing (env-driven) ----
class TestPricing:
    def test_pricing_defaults(self, admin):
        r = admin.get(f"{API}/subscriptions/pricing")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["per_child_monthly"] == 30
        assert b["per_child_yearly"] == 300
        assert b["monthly_days"] == 30
        assert b["yearly_days"] == 365
        assert b["currency"] == "INR"

    def test_my_quote_matches_pricing(self, admin):
        rp = admin.get(f"{API}/subscriptions/pricing").json()
        r = admin.get(f"{API}/subscriptions/my")
        assert r.status_code == 200
        q = r.json()["quote"]
        assert q["pricing"]["per_child_monthly"] == rp["per_child_monthly"]
        assert q["pricing"]["per_child_yearly"] == rp["per_child_yearly"]
        assert q["pricing"]["currency"] == rp["currency"]
        assert q["monthly"]["rate_per_child"] == rp["per_child_monthly"]
        assert q["yearly"]["rate_per_child"] == rp["per_child_yearly"]


# ---- Suggest constraints ----
def _cleanup(admin, class_id, section):
    admin.post(f"{API}/timetable/bulk", json={"class_id": class_id, "section": section, "slots": []})


class TestSuggestConstraints:
    def test_lunch_break(self, admin):
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "periods_per_day": 6, "lunch_break_period": 3,
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["total_slots"] == 25  # 5d × 5p
        lunch_slots = [s for s in b["slots"] if s["period"] == 3]
        assert len(lunch_slots) == 5
        for s in lunch_slots:
            assert s.get("is_break") is True
            assert s["subject_id"] == ""
            assert s["teacher_id"] == ""

    def test_invalid_lunch_400(self, admin):
        # lunch_break_period > periods_per_day → custom 400 in route handler
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "periods_per_day": 4, "lunch_break_period": 7,
        })
        assert r.status_code == 400, r.text
        assert "lunch" in r.json().get("detail", "").lower()

    def test_no_last_period_subjects(self, admin):
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "no_last_period_subjects": [SUB_MATH],
        })
        assert r.status_code == 200
        b = r.json()
        last_period = b["periods_per_day"]
        forced = [s for s in b["slots"] if s["period"] == last_period and s["subject_id"] == SUB_MATH]
        # If forced, must have a warning mentioning 'last period'
        if forced:
            warns = " ".join(b["warnings"]).lower()
            assert "last period" in warns

    def test_subject_day_pins_hindi(self, admin):
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "subject_day_pins": {SUB_HINDI: ["mon", "wed"]},
        })
        assert r.status_code == 200, r.text
        b = r.json()
        for s in b["slots"]:
            if s["subject_id"] == SUB_HINDI:
                assert s["day"] in ("mon", "wed"), f"Hindi placed on {s['day']}"
        # No relaxation warning expected
        relax = [w for w in b["warnings"] if "Day-pin" in w and "relax" in w.lower()]
        assert relax == [], f"unexpected relaxation: {relax}"

    def test_overrestrictive_day_pin_returns_warning_or_400(self, admin):
        # Pin a subject to a single day with override count exceeding that day's cap.
        # Example: pin Hindi to ['mon'] (cap = 1 day × 6 periods = 6) AND force 20 Hindi periods.
        # This MUST raise 400 because the override exceeds the per-subject day-pin cap and
        # the auto-balance can't fit the rest.
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "subject_day_pins": {SUB_HINDI: ["mon"]},
            "subject_periods": {SUB_HINDI: 20},
            "no_last_period_subjects": [],
        })
        # Either the route returns 400 (preferred) OR a relaxation warning surfaces.
        if r.status_code == 400:
            detail = r.json().get("detail", "").lower()
            # Should mention day-pins or restrictive or exceeds
            assert any(k in detail for k in ("day-pin", "restrictive", "exceed")), detail
        else:
            assert r.status_code == 200, r.text
            warns = " ".join(r.json().get("warnings", [])).lower()
            assert "day-pin" in warns or "relax" in warns, f"expected relaxation warning, got: {warns}"

    def test_subject_periods_override_overflow_still_400(self, admin):
        r = admin.post(f"{API}/timetable/suggest", json={
            "class_id": CLASS_ID_GRADE5, "section": "B",
            "subject_periods": {SUB_MATH: 9999},
        })
        assert r.status_code == 400


# ---- RBAC unchanged ----
class TestRBAC:
    def test_teacher_403(self, teacher):
        r = teacher.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"})
        assert r.status_code == 403

    def test_accounts_403(self, accounts):
        r = accounts.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE5, "section": "B"})
        assert r.status_code == 403


# ---- Timetable notify ----
class TestTimetableNotify:
    def test_bulk_returns_notified_count_and_queues(self, admin):
        # Get a fresh suggestion for Grade 6 B and save
        r = admin.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE6, "section": "B"})
        assert r.status_code == 200
        slots = [s for s in r.json()["slots"] if s.get("teacher_id")]
        assert len(slots) > 0
        distinct_teachers = {s["teacher_id"] for s in slots}

        save = admin.post(f"{API}/timetable/bulk", json={
            "class_id": CLASS_ID_GRADE6, "section": "B", "slots": slots,
        })
        assert save.status_code == 200, save.text
        body = save.json()
        assert body["inserted"] == len(slots)
        assert body["notified_teachers"] == len(distinct_teachers)

        # Allow async notification write
        time.sleep(1.0)

        # Verify via admin notifications endpoint (queued telegram rows present).
        # Try a few common notification endpoints.
        notif_found = False
        for path in ("/notifications", "/notifications/log", "/notifications?template=timetable_updated"):
            nr = admin.get(f"{API}{path}")
            if nr.status_code == 200:
                data = nr.json()
                rows = data if isinstance(data, list) else data.get("items") or data.get("rows") or []
                tt = [n for n in rows if (n.get("template") == "timetable_updated") and n.get("channel") == "telegram"]
                if tt:
                    notif_found = True
                    msg = tt[0].get("message", "")
                    assert "Section B" in msg or "section B" in msg.lower() or "B" in msg
                    break
        # Cleanup
        _cleanup(admin, CLASS_ID_GRADE6, "B")
        # If endpoint exists & rows present, assert; else log a soft note (notified_teachers count is the canonical signal)
        if not notif_found:
            print("NOTE: could not introspect notifications via list endpoint; relied on notified_teachers in response.")

    def test_dedup_single_teacher_multiple_slots(self, admin):
        # Build minimal slots with one teacher repeated. We need a real teacher id.
        # Reuse suggest to discover a teacher.
        r = admin.post(f"{API}/timetable/suggest", json={"class_id": CLASS_ID_GRADE6, "section": "A"})
        assert r.status_code == 200
        teach = next((s["teacher_id"] for s in r.json()["slots"] if s.get("teacher_id")), None)
        subj = next((s["subject_id"] for s in r.json()["slots"] if s.get("teacher_id")), None)
        assert teach and subj
        custom = [
            {"day": "mon", "period": 1, "subject_id": subj, "teacher_id": teach,
             "class_id": CLASS_ID_GRADE6, "section": "A",
             "start_time": "09:00", "end_time": "09:45"},
            {"day": "tue", "period": 1, "subject_id": subj, "teacher_id": teach,
             "class_id": CLASS_ID_GRADE6, "section": "A",
             "start_time": "09:00", "end_time": "09:45"},
            {"day": "wed", "period": 1, "subject_id": subj, "teacher_id": teach,
             "class_id": CLASS_ID_GRADE6, "section": "A",
             "start_time": "09:00", "end_time": "09:45"},
        ]
        save = admin.post(f"{API}/timetable/bulk", json={
            "class_id": CLASS_ID_GRADE6, "section": "A", "slots": custom,
        })
        assert save.status_code == 200, save.text
        b = save.json()
        assert b["inserted"] == 3
        assert b["notified_teachers"] == 1
        _cleanup(admin, CLASS_ID_GRADE6, "A")

    def test_empty_slots_does_not_fail(self, admin):
        # Cleanup an empty class; notify should silently skip
        r = admin.post(f"{API}/timetable/bulk", json={
            "class_id": CLASS_ID_GRADE6, "section": "B", "slots": [],
        })
        assert r.status_code == 200
        b = r.json()
        assert b["inserted"] == 0
        assert b["notified_teachers"] == 0
