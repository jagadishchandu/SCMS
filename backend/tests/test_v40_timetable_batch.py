"""V40 batch timetable suggest/save tests."""
import os
import pytest
import requests

def _backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fallback: read from frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not configured"
    return url.rstrip("/") + "/api"


BASE_URL = _backend_url()
PRINCIPAL = {"email": "principal@sunrise.edu", "password": "School@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=PRINCIPAL, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def school_data(admin_session):
    classes = admin_session.get(f"{BASE_URL}/academic/classes", timeout=20).json()
    subjects = admin_session.get(f"{BASE_URL}/academic/subjects", timeout=20).json()
    teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
    by_name_sub = {s["name"]: s for s in subjects}
    by_name_cls = {c["name"]: c for c in classes}
    return {
        "classes": classes,
        "subjects": subjects,
        "teachers": teachers,
        "sub_by_name": by_name_sub,
        "cls_by_name": by_name_cls,
    }


def _sections_payload(school_data):
    g5 = school_data["cls_by_name"].get("Grade 5") or school_data["classes"][0]
    g6 = school_data["cls_by_name"].get("Grade 6") or school_data["classes"][1]
    return g5, g6


# --------------- /suggest single section (backwards compat) ---------------
class TestSuggestSingle:
    def test_single_section_response_shape(self, admin_session, school_data):
        g5, _ = _sections_payload(school_data)
        r = admin_session.post(
            f"{BASE_URL}/timetable/suggest",
            json={"class_id": g5["id"], "section": "A", "periods_per_day": 6,
                  "lunch_break_period": 4},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["slots", "warnings", "subject_distribution", "days",
                  "periods_per_day", "total_slots", "lunch_break_period", "break_periods"]:
            assert k in data, f"missing {k}"
        # lunch_break_period reflected
        assert data["lunch_break_period"] == 4
        # break slots present
        breaks = [s for s in data["slots"] if s.get("is_break")]
        assert all(b["period"] == 4 for b in breaks)


# --------------- /suggest-batch core tests ---------------
class TestSuggestBatch:
    def _base_request(self, school_data, **defaults_overrides):
        g5, g6 = _sections_payload(school_data)
        defaults = {
            "class_id": g5["id"], "section": "A",
            "periods_per_day": 6, "lunch_break_period": 4,
        }
        defaults.update(defaults_overrides)
        return {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": defaults,
            "reset_existing": True,
        }

    def test_batch_returns_all_fields(self, admin_session, school_data):
        payload = self._base_request(school_data)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["sections", "teacher_view", "conflict_summary", "optimization_suggestions"]:
            assert k in data
        assert len(data["sections"]) == 4
        for sec in data["sections"]:
            for k in ["slots", "warnings", "subject_distribution", "break_periods"]:
                assert k in sec, f"section missing {k}"

    def test_no_teacher_double_booking_cross_section(self, admin_session, school_data):
        payload = self._base_request(school_data)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        data = r.json()
        seen = {}
        for t in data["teacher_view"]["teachers"]:
            for day, periods in (t.get("by_day") or {}).items():
                for period in periods:
                    key = (t["teacher_id"], day, period)
                    assert key not in seen, f"Teacher {t['teacher_name']} double-booked at {key}"
                    seen[key] = True

    def test_fixed_breaks_and_lunch(self, admin_session, school_data):
        payload = self._base_request(school_data)
        payload["defaults"]["fixed_breaks"] = [{"period": 1, "label": "Assembly"}]
        payload["defaults"]["lunch_break_period"] = 4
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for sec in data["sections"]:
            days_seen = set()
            for sl in sec["slots"]:
                days_seen.add(sl["day"])
                if sl["period"] == 1:
                    assert sl.get("is_break") is True
                    assert sl.get("break_label") == "Assembly"
                    assert not sl.get("teacher_id")
                if sl["period"] == 4:
                    assert sl.get("is_break") is True
                    assert sl.get("break_label") == "Lunch"
            # all weekdays present
            assert len(days_seen) >= 5

    def test_allowed_periods_per_subject(self, admin_session, school_data):
        science = school_data["sub_by_name"].get("Science")
        if not science:
            pytest.skip("Science subject missing")
        payload = self._base_request(school_data)
        allowed = [2, 3, 5, 6]
        payload["defaults"]["allowed_periods_per_subject"] = {science["id"]: allowed}
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("subject_id") == science["id"] and not sl.get("is_break"):
                    assert sl["period"] in allowed, (
                        f"Science placed at period {sl['period']} not in allowed {allowed}"
                    )

    def test_max_consecutive_heavy(self, admin_session, school_data):
        math = school_data["sub_by_name"].get("Mathematics")
        sci = school_data["sub_by_name"].get("Science")
        if not (math and sci):
            pytest.skip("Math/Science missing")
        payload = self._base_request(school_data)
        payload["defaults"]["subject_categories"] = {math["id"]: "heavy", sci["id"]: "heavy"}
        payload["defaults"]["max_consecutive_heavy"] = 2
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        heavy = {math["id"], sci["id"]}
        for sec in data["sections"]:
            by_day = {}
            for sl in sec["slots"]:
                by_day.setdefault(sl["day"], []).append(sl)
            for day, slots in by_day.items():
                slots.sort(key=lambda x: x["period"])
                run = 0
                max_run = 0
                for sl in slots:
                    if sl.get("is_break"):
                        run = 0
                        continue
                    if sl.get("subject_id") in heavy:
                        run += 1
                        max_run = max(max_run, run)
                    else:
                        run = 0
                # warning is emitted when forced > limit; assert nominal cap holds
                # (the engine may relax soft to fill slots → warning generated)
                # We allow up to 3 only if a warning was emitted; otherwise enforce 2
                forced_warn = any("Heavy-subject run exceeded" in w for w in sec.get("warnings", []))
                if not forced_warn:
                    assert max_run <= 2, f"Heavy run {max_run} > 2 on {day} in {sec.get('class_name')}-{sec['section']}"

    def test_class_teacher_pin(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        g5, _ = _sections_payload(school_data)
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A",
                 "class_teacher": {"teacher_id": tid, "period": 7, "label": "CT"}},
                {"class_id": g5["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 7, "lunch_break_period": 4,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        section_a = next(s for s in data["sections"] if s["section"] == "A")
        days_pinned = set()
        for sl in section_a["slots"]:
            if sl["period"] == 7:
                assert sl.get("is_class_teacher_pin") is True, f"period 7 not pin: {sl}"
                assert sl.get("teacher_id") == tid
                days_pinned.add(sl["day"])
        assert len(days_pinned) >= 5
        # Teacher view should reflect those slots for tid
        t_entry = next((t for t in data["teacher_view"]["teachers"] if t["teacher_id"] == tid), None)
        assert t_entry is not None
        for day in days_pinned:
            day_periods = t_entry["by_day"].get(day) or {}
            # JSON keys are strings; accept either
            assert "7" in day_periods or 7 in day_periods, (
                f"teacher_view missing day {day} period 7. keys={list(day_periods.keys())}"
            )

    def test_subject_periods_frequency(self, admin_session, school_data):
        math = school_data["sub_by_name"].get("Mathematics")
        if not math:
            pytest.skip("Math missing")
        payload = self._base_request(school_data)
        payload["defaults"]["subject_periods"] = {math["id"]: 5}
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for sec in data["sections"]:
            assert sec["subject_distribution"].get(math["id"]) == 5, (
                f"Math count mismatch in {sec.get('class_name')}-{sec['section']}: "
                f"{sec['subject_distribution'].get(math['id'])}"
            )

    def test_no_last_period_subjects(self, admin_session, school_data):
        math = school_data["sub_by_name"].get("Mathematics")
        if not math:
            pytest.skip("Math missing")
        payload = self._base_request(school_data)
        payload["defaults"]["no_last_period_subjects"] = [math["id"]]
        payload["defaults"]["periods_per_day"] = 6
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for sec in data["sections"]:
            last_period = sec["periods_per_day"]
            for sl in sec["slots"]:
                if sl["period"] == last_period and sl.get("subject_id") == math["id"]:
                    # only ok if a relaxation warning was raised
                    assert any("last period" in w.lower() for w in sec["warnings"]), (
                        f"Math in last period in {sec.get('class_name')}-{sec['section']} without warning"
                    )

    def test_conflict_and_optimization_suggestions(self, admin_session, school_data):
        # 3 teachers cover only 5 subjects partially → expect unfilled slots
        payload = self._base_request(school_data)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        data = r.json()
        cs = data["conflict_summary"]
        assert "unfilled_slots" in cs
        # Demo school is teacher-starved → some unfilled expected
        if cs["unfilled_slots"]:
            for u in cs["unfilled_slots"]:
                for k in ["class_name", "section", "day", "period", "subject_name", "reason"]:
                    assert k in u, f"unfilled missing {k}: {u}"
                assert u["reason"] == "no_teacher"
            # Should produce optimization suggestion about adding teachers
            assert any("Add 1 more teacher" in s or "Assign at least 1 teacher" in s
                       for s in data["optimization_suggestions"]), data["optimization_suggestions"]


# --------------- /save-batch tests ---------------
class TestSaveBatch:
    def test_save_batch_persists(self, admin_session, school_data):
        g5, g6 = _sections_payload(school_data)
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": {"class_id": g5["id"], "section": "A",
                         "periods_per_day": 6, "lunch_break_period": 4},
            "reset_existing": True,
        }
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert sg.status_code == 200
        sg_data = sg.json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg_data["sections"]
            ]
        }
        r = admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["inserted", "notified_teachers", "sections_saved"]:
            assert k in data
        assert data["sections_saved"] == 4
        assert data["inserted"] > 0

        # Verify no double-booking persisted in GET /timetable
        all_tt = admin_session.get(f"{BASE_URL}/timetable", timeout=20).json()
        seen = {}
        for sl in all_tt:
            tid = sl.get("teacher_id")
            if not tid:
                continue
            key = (sl["day"], sl["period"], tid)
            assert key not in seen, (
                f"Double-booking persisted: teacher {tid} at {key} "
                f"first={seen[key]} second=({sl['class_id']},{sl['section']})"
            )
            seen[key] = (sl["class_id"], sl["section"])

    def test_save_batch_returns_409_on_intra_payload_conflict(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        g5, _ = _sections_payload(school_data)
        bogus_slot = {
            "day": "mon", "period": 2,
            "subject_id": school_data["subjects"][0]["id"],
            "teacher_id": tid,
            "start_time": "09:45", "end_time": "10:30",
        }
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A", "slots": [bogus_slot]},
                {"class_id": g5["id"], "section": "B", "slots": [bogus_slot]},
            ]
        }
        r = admin_session.post(f"{BASE_URL}/timetable/save-batch", json=payload, timeout=30)
        assert r.status_code == 409, r.text
        detail = r.json().get("detail", {})
        assert "intra_payload_conflicts" in detail
        assert "cross_class_conflicts" in detail
        assert len(detail["intra_payload_conflicts"]) >= 1


# --------------- /bulk backwards-compat ---------------
class TestBulkBackwardsCompat:
    def test_bulk_conflict_409(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        g5, _ = _sections_payload(school_data)
        sid = school_data["subjects"][0]["id"]
        # First save a baseline for section A
        baseline = {
            "class_id": g5["id"], "section": "A",
            "slots": [
                {"day": "mon", "period": 2, "subject_id": sid, "teacher_id": tid,
                 "class_id": g5["id"], "section": "A",
                 "start_time": "09:45", "end_time": "10:30"},
            ],
        }
        r = admin_session.post(f"{BASE_URL}/timetable/bulk", json=baseline, timeout=30)
        # may 200 or 409 if prior data clashes; ensure either way our subsequent conflict test fires
        if r.status_code not in (200, 409):
            pytest.fail(f"bulk baseline unexpected {r.status_code}: {r.text}")

        # Now try to save the SAME teacher at same (day,period) for a DIFFERENT section
        conflict = {
            "class_id": g5["id"], "section": "B",
            "slots": [
                {"day": "mon", "period": 2, "subject_id": sid, "teacher_id": tid,
                 "class_id": g5["id"], "section": "B",
                 "start_time": "09:45", "end_time": "10:30"},
            ],
        }
        r2 = admin_session.post(f"{BASE_URL}/timetable/bulk", json=conflict, timeout=30)
        assert r2.status_code == 409, f"expected 409, got {r2.status_code}: {r2.text}"
        detail = r2.json().get("detail", {})
        assert "cross_class_conflicts" in detail
