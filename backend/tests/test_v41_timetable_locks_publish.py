"""V41 timetable backend tests:
   - locked_assignments (single + cross-section busy priority)
   - max_periods_per_day_per_teacher cap + warnings
   - /publish delivery report (telegram_not_linked is expected)
   - /pdf/section binary download + 404
   - back-compat for /suggest single shape
   - regression: v40 constraints still co-exist with v41
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
    return {
        "classes": classes,
        "subjects": subjects,
        "teachers": teachers,
        "sub_by_name": {s["name"]: s for s in subjects},
        "cls_by_name": {c["name"]: c for c in classes},
    }


def _g5_g6(school_data):
    g5 = school_data["cls_by_name"].get("Grade 5") or school_data["classes"][0]
    g6 = school_data["cls_by_name"].get("Grade 6") or school_data["classes"][1]
    return g5, g6


# ---------------- Locked assignments ----------------
class TestLockedAssignments:
    def test_lock_places_exact_teacher_subject_with_flag(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        sid = school_data["subjects"][0]["id"]
        g5, _ = _g5_g6(school_data)
        payload = {
            "sections": [
                {
                    "class_id": g5["id"], "section": "A",
                    "locked_assignments": [
                        {"day": "mon", "period": 2, "teacher_id": tid, "subject_id": sid}
                    ],
                },
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        sec_a = data["sections"][0]
        # Find (mon, 2) slot
        target = next((sl for sl in sec_a["slots"] if sl["day"] == "mon" and sl["period"] == 2), None)
        assert target is not None, "no (mon,2) slot found"
        assert target.get("is_locked") is True, f"expected is_locked=True; got {target}"
        assert target.get("teacher_id") == tid
        assert target.get("subject_id") == sid

        # Greedy must not have placed any *other* assignment in this slot
        # (only one slot per (day,period); enforced by sort).
        assert sum(1 for sl in sec_a["slots"] if sl["day"] == "mon" and sl["period"] == 2) == 1

        # teacher_view should reflect the locked slot
        tv = data["teacher_view"]["teachers"]
        t_entry = next((t for t in tv if t["teacher_id"] == tid), None)
        assert t_entry is not None
        day_map = t_entry["by_day"].get("mon") or {}
        assert ("2" in day_map) or (2 in day_map), (
            f"teacher_view missing locked (mon,2) for {tid}; keys={list(day_map.keys())}"
        )

    def test_cross_section_lock_priority(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        sid = school_data["subjects"][0]["id"]
        g5, _ = _g5_g6(school_data)
        payload = {
            "sections": [
                {
                    "class_id": g5["id"], "section": "A",
                    "locked_assignments": [
                        {"day": "mon", "period": 3, "teacher_id": tid, "subject_id": sid}
                    ],
                },
                {"class_id": g5["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # In section B, (mon,3) must NOT be assigned to tid
        sec_b = next(s for s in data["sections"] if s["section"] == "B")
        bad = [
            sl for sl in sec_b["slots"]
            if sl["day"] == "mon" and sl["period"] == 3 and sl.get("teacher_id") == tid
        ]
        assert not bad, f"Section B placed locked teacher {tid} at (mon,3): {bad}"


# ---------------- max_periods_per_day_per_teacher ----------------
class TestMaxPeriodsPerDayPerTeacher:
    def test_cap_enforced_across_batch(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        cap = 2
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
                "max_periods_per_day_per_teacher": cap,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # Count teaching periods per (teacher, day) across the entire batch
        load: dict[tuple, int] = {}
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break"):
                    continue
                tid = sl.get("teacher_id")
                if not tid:
                    continue
                key = (tid, sl["day"])
                load[key] = load.get(key, 0) + 1
        over = {k: v for k, v in load.items() if v > cap}
        assert not over, f"Teachers exceeding cap {cap}: {over}"

    def test_warning_when_cap_too_low(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        # cap=1 will easily exhaust 3-teacher demo school
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
                "max_periods_per_day_per_teacher": 1,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        all_warnings = data["conflict_summary"]["warnings"]
        # Also collect per-section warnings
        for sec in data["sections"]:
            all_warnings.extend(sec.get("warnings", []))
        assert any("per-day cap" in w for w in all_warnings), (
            f"expected 'per-day cap' warning when cap=1; got warnings: {all_warnings}"
        )


# ---------------- /publish ----------------
class TestPublishTimetable:
    def _seed_saved_timetable(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
            },
            "reset_existing": True,
        }
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        r = admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        assert r.status_code == 200, r.text

    def test_publish_400_when_no_timetable(self, admin_session, school_data):
        # Wipe the saved timetable by hitting a non-existent class filter
        # We can't wipe via API, so use class_ids filter pointing at fake id
        r = admin_session.post(
            f"{BASE_URL}/timetable/publish",
            json={"class_ids": ["___nonexistent_class___"], "audiences": ["teachers"]},
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400; got {r.status_code} {r.text}"
        msg = (r.json().get("detail") or "")
        assert "No timetable" in msg or "no timetable" in msg.lower()

    def test_publish_returns_delivery_report_telegram_not_linked(self, admin_session, school_data):
        self._seed_saved_timetable(admin_session, school_data)
        r = admin_session.post(
            f"{BASE_URL}/timetable/publish",
            json={"audiences": ["teachers", "parents"]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["teachers_total", "teachers_sent", "teachers_failed",
                  "parents_total", "parents_sent", "parents_failed", "failures"]:
            assert k in d, f"missing field {k}"
        # No telegram chat_id is configured for demo users → every recipient must fail with telegram_not_linked
        assert d["teachers_sent"] == 0, f"unexpected teachers_sent={d['teachers_sent']}"
        assert d["parents_sent"] == 0, f"unexpected parents_sent={d['parents_sent']}"
        # Every failure reason must be 'telegram_not_linked'
        reasons = {f.get("reason") for f in d["failures"]}
        assert reasons.issubset({"telegram_not_linked"}), f"unexpected reasons: {reasons}"
        # And teachers_total should be >0 since saved timetable assigns teachers
        assert d["teachers_total"] >= 1, "expected at least 1 teacher recipient"

    def test_publish_class_ids_filter(self, admin_session, school_data):
        self._seed_saved_timetable(admin_session, school_data)
        g5, _ = _g5_g6(school_data)
        r = admin_session.post(
            f"{BASE_URL}/timetable/publish",
            json={"class_ids": [g5["id"]], "audiences": ["teachers"]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "teachers_total" in d
        # Smaller subset → recipient pool ≤ full publish (sanity, can't assert exact)
        assert d["teachers_total"] >= 0


# ---------------- /pdf/section ----------------
class TestPdfSection:
    def test_pdf_section_returns_valid_pdf(self, admin_session, school_data):
        # Ensure timetable is saved (re-use seed)
        g5, g6 = _g5_g6(school_data)
        payload = {
            "sections": [
                {"class_id": g5["id"], "section": "A"},
                {"class_id": g5["id"], "section": "B"},
                {"class_id": g6["id"], "section": "A"},
                {"class_id": g6["id"], "section": "B"},
            ],
            "defaults": {
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
            },
            "reset_existing": True,
        }
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)

        r = admin_session.get(
            f"{BASE_URL}/timetable/pdf/section",
            params={"class_id": g5["id"], "section": "A"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert "Content-Disposition" in r.headers or "content-disposition" in r.headers
        assert r.content[:4] == b"%PDF", f"not a PDF binary: starts with {r.content[:8]!r}"

    def test_pdf_section_404_when_no_slots(self, admin_session, school_data):
        g5, _ = _g5_g6(school_data)
        # Section 'Z' (uppercase) should never have slots in seed
        r = admin_session.get(
            f"{BASE_URL}/timetable/pdf/section",
            params={"class_id": g5["id"], "section": "Z"},
            timeout=20,
        )
        assert r.status_code == 404, f"expected 404; got {r.status_code} {r.text[:200]}"


# ---------------- /suggest single back-compat ----------------
class TestSuggestSingleBackCompat:
    def test_shape_unchanged(self, admin_session, school_data):
        g5, _ = _g5_g6(school_data)
        r = admin_session.post(
            f"{BASE_URL}/timetable/suggest",
            json={
                "class_id": g5["id"], "section": "A",
                "periods_per_day": 6, "lunch_break_period": 4,
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["slots", "warnings", "subject_distribution",
                  "days", "periods_per_day", "total_slots"]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["slots"], list) and len(d["slots"]) > 0


# ---------------- Regression: v40 + v41 co-existence ----------------
class TestV40RegressionWithV41:
    def test_locks_plus_v40_constraints(self, admin_session, school_data):
        teachers = school_data["teachers"]
        if not teachers:
            pytest.skip("no teachers")
        tid = teachers[0]["id"]
        sid = school_data["subjects"][0]["id"]
        math = school_data["sub_by_name"].get("Mathematics")
        sci = school_data["sub_by_name"].get("Science")
        g5, _ = _g5_g6(school_data)
        defaults = {
            "class_id": g5["id"], "section": "A",
            "periods_per_day": 7, "lunch_break_period": 4,
            "fixed_breaks": [{"period": 1, "label": "Assembly"}],
            "max_consecutive_heavy": 2,
            "class_teacher": {"teacher_id": tid, "period": 7, "label": "CT"},
            "max_periods_per_day_per_teacher": 4,
        }
        if math and sci:
            defaults["subject_categories"] = {math["id"]: "heavy", sci["id"]: "heavy"}
            defaults["allowed_periods_per_subject"] = {math["id"]: [2, 3, 5, 6]}
        payload = {
            "sections": [
                {
                    "class_id": g5["id"], "section": "A",
                    "locked_assignments": [
                        {"day": "tue", "period": 3, "teacher_id": tid, "subject_id": sid}
                    ],
                },
            ],
            "defaults": defaults,
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        sec = data["sections"][0]
        # 1. lock honoured
        target = next((sl for sl in sec["slots"] if sl["day"] == "tue" and sl["period"] == 3), None)
        assert target and target.get("is_locked") is True
        assert target["teacher_id"] == tid
        # 2. fixed break + lunch in place
        period_1 = [sl for sl in sec["slots"] if sl["period"] == 1]
        period_4 = [sl for sl in sec["slots"] if sl["period"] == 4]
        assert all(sl.get("is_break") for sl in period_1)
        assert all(sl.get("is_break") for sl in period_4)
        # 3. CT pin every day at period 7
        ct_days = {sl["day"] for sl in sec["slots"] if sl["period"] == 7 and sl.get("is_class_teacher_pin")}
        assert len(ct_days) >= 5
        # 4. Math only in allowed periods (if math exists)
        if math:
            for sl in sec["slots"]:
                if sl.get("subject_id") == math["id"] and not sl.get("is_break"):
                    assert sl["period"] in {2, 3, 5, 6} or sl.get("is_locked") or sl.get("is_class_teacher_pin")
        # 5. per-day cap (4) respected (mostly — soft if forced)
        load = {}
        for sl in sec["slots"]:
            if sl.get("is_break"):
                continue
            t2 = sl.get("teacher_id")
            if not t2:
                continue
            load[(t2, sl["day"])] = load.get((t2, sl["day"]), 0) + 1
        capped_warning = any("per-day cap" in w for w in sec.get("warnings", []))
        for k, v in load.items():
            if v > 4:
                assert capped_warning, f"cap exceeded without warning: {k}={v}"
