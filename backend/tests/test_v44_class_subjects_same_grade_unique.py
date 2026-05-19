"""V44 tests:
- POST/PATCH /api/users supports class_subjects {class_id: [subject_id]}
- /suggest-batch honours class_subjects per-teacher
- Backward compat: teachers without class_subjects still eligible for any class
- HARD same-grade subject uniqueness across sibling sections at same (day, period)
- Warning surfaces when uniqueness must be relaxed (capacity issue)
- Cross-section teacher uniqueness still holds
"""
import os
import uuid
import pytest
import requests


def _backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    assert url
    return url.rstrip("/") + "/api"


BASE_URL = _backend_url()
PRINCIPAL = {"email": "principal@sunrise.edu", "password": "School@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=PRINCIPAL, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def school_data(admin_session):
    classes = admin_session.get(f"{BASE_URL}/academic/classes", timeout=20).json()
    subjects = admin_session.get(f"{BASE_URL}/academic/subjects", timeout=20).json()
    # Seed Anita Sharma (all 5 subjects) — required for sufficient capacity
    teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
    all_sids = [s["id"] for s in subjects]
    anita = next((t for t in teachers if (t.get("email") or "").lower() == "anita@sunrise.edu"), None)
    if not anita:
        r = admin_session.post(
            f"{BASE_URL}/users",
            json={"email": "anita@sunrise.edu", "password": "Teacher@123",
                  "name": "Anita Sharma", "role": "teacher", "subjects": all_sids},
            timeout=20,
        )
        assert r.status_code in (200, 201) or (r.status_code == 400 and "already exists" in r.text), r.text
        teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
    g5 = next((c for c in classes if c["name"] == "Grade 5"), classes[0])
    g6 = next((c for c in classes if c["name"] == "Grade 6"), classes[1])
    return {"classes": classes, "subjects": subjects, "teachers": teachers, "g5": g5, "g6": g6}


def _batch_payload(g5, g6):
    return {
        "sections": [
            {"class_id": g5["id"], "section": "A"},
            {"class_id": g5["id"], "section": "B"},
            {"class_id": g6["id"], "section": "A"},
            {"class_id": g6["id"], "section": "B"},
        ],
        "defaults": {
            "class_id": g5["id"], "section": "A",
            "periods_per_day": 6, "lunch_break_period": 6,
        },
        "reset_existing": True,
    }


# ---------- POST/PATCH /users class_subjects ----------
class TestUserClassSubjects:
    def test_post_user_persists_class_subjects(self, admin_session, school_data):
        g5 = school_data["g5"]
        math = next(s for s in school_data["subjects"] if "Math" in s["name"] or s["name"].lower().startswith("math"))
        email = f"v44-{uuid.uuid4().hex[:6]}@sunrise.edu"
        payload = {
            "email": email, "password": "Teacher@123",
            "name": "V44 Teacher", "role": "teacher",
            "subjects": [math["id"]],
            "class_subjects": {g5["id"]: [math["id"]]},
        }
        r = admin_session.post(f"{BASE_URL}/users", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        assert created.get("class_subjects") == {g5["id"]: [math["id"]]}
        # GET roundtrip
        listed = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
        fetched = next(t for t in listed if t["id"] == created["id"])
        assert fetched["class_subjects"] == {g5["id"]: [math["id"]]}

    def test_patch_user_updates_class_subjects(self, admin_session, school_data):
        g5 = school_data["g5"]
        g6 = school_data["g6"]
        subs = school_data["subjects"]
        sci = subs[1]
        # create
        email = f"v44p-{uuid.uuid4().hex[:6]}@sunrise.edu"
        r = admin_session.post(f"{BASE_URL}/users", json={
            "email": email, "password": "Teacher@123",
            "name": "V44 Patch", "role": "teacher",
            "subjects": [sci["id"]],
        }, timeout=20)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        new_cs = {g6["id"]: [sci["id"]]}
        rp = admin_session.patch(f"{BASE_URL}/users/{uid}",
                                 json={"class_subjects": new_cs}, timeout=20)
        assert rp.status_code == 200, rp.text
        listed = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
        fetched = next(t for t in listed if t["id"] == uid)
        assert fetched["class_subjects"] == new_cs


# ---------- Scheduler honours class_subjects ----------
class TestSchedulerHonoursClassSubjects:
    @pytest.fixture(scope="class")
    def constrained_teacher(self, admin_session, school_data):
        """Teacher constrained to Grade 5 + Math only."""
        g5 = school_data["g5"]
        math = next(s for s in school_data["subjects"] if "math" in s["name"].lower())
        email = f"v44c-{uuid.uuid4().hex[:6]}@sunrise.edu"
        r = admin_session.post(f"{BASE_URL}/users", json={
            "email": email, "password": "Teacher@123",
            "name": "V44 Constrained", "role": "teacher",
            "subjects": [math["id"]],
            "class_subjects": {g5["id"]: [math["id"]]},
        }, timeout=20)
        assert r.status_code in (200, 201), r.text
        return {"id": r.json()["id"], "g5": g5, "math": math}

    def test_constrained_teacher_only_in_allowed_pairs(self, admin_session, school_data, constrained_teacher):
        g5, g6 = school_data["g5"], school_data["g6"]
        math = constrained_teacher["math"]
        tid = constrained_teacher["id"]
        payload = _batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        bad_assignments = []
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("teacher_id") == tid:
                    if sl["class_id"] != g5["id"] or sl.get("subject_id") != math["id"]:
                        bad_assignments.append({
                            "class_id": sl["class_id"], "section": sl["section"],
                            "subject_id": sl.get("subject_id"),
                        })
        assert not bad_assignments, f"Constrained teacher placed in disallowed pairs: {bad_assignments}"

    def test_backward_compat_legacy_teachers_eligible(self, admin_session, school_data):
        """Demo seed teachers (priya/rohit/kavita) have NO class_subjects mapping.
        They must still appear across Grade 5 AND Grade 6."""
        g5, g6 = school_data["g5"], school_data["g6"]
        teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
        legacy = [t for t in teachers
                  if (t.get("email") or "").split("@")[0] in ("priya", "rohit", "kavita")
                  and not (t.get("class_subjects") or {})]
        assert legacy, "expected priya/rohit/kavita seed teachers without class_subjects"
        legacy_ids = {t["id"] for t in legacy}
        payload = _batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        # At least one legacy teacher should appear in BOTH grades across the batch
        grade_hit = {tid: set() for tid in legacy_ids}
        for sec in r.json()["sections"]:
            for sl in sec["slots"]:
                tid = sl.get("teacher_id")
                if tid in legacy_ids:
                    grade_hit[tid].add(sl["class_id"])
        any_both = any(g5["id"] in v and g6["id"] in v for v in grade_hit.values())
        assert any_both, f"No legacy teacher appeared in BOTH grades: {grade_hit}"


# ---------- Same-grade subject uniqueness ----------
class TestSameGradeUniqueness:
    def test_zero_same_grade_subject_duplicates(self, admin_session, school_data):
        g5, g6 = school_data["g5"], school_data["g6"]
        payload = _batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        # Group slots by (class_id, day, period) -> list[subject_id]
        bucket: dict = {}
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break") or not sl.get("subject_id"):
                    continue
                key = (sl["class_id"], sl["day"], sl["period"])
                bucket.setdefault(key, []).append((sl["section"], sl["subject_id"]))
        violations = []
        for key, items in bucket.items():
            sids = [s for _, s in items]
            if len(sids) != len(set(sids)):
                violations.append({"key": key, "items": items})
        assert not violations, f"Same-grade subject duplicates: {violations}"

    def test_cross_section_teacher_uniqueness(self, admin_session, school_data):
        g5, g6 = school_data["g5"], school_data["g6"]
        payload = _batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        seen: dict = {}
        for sec in r.json()["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break"):
                    continue
                tid = sl.get("teacher_id")
                if not tid:
                    continue
                key = (sl["day"], sl["period"], tid)
                assert key not in seen, f"Teacher double-booking: {tid} at {key}; first={seen[key]}, second=({sec['class_id']}, {sec['section']})"
                seen[key] = (sec["class_id"], sec["section"])

    def test_relaxation_warning_when_capacity_short(self, admin_session, school_data):
        """Force the case: only 1 subject allowed at period 1 across the day
        for 2 sections of the same grade — uniqueness MUST relax. Verify the
        'Same-grade uniqueness relaxed' warning fires and schedule completes."""
        g5, g6 = school_data["g5"], school_data["g6"]
        subs = school_data["subjects"]
        only_sid = subs[0]["id"]
        payload = _batch_payload(g5, g6)
        # Constrain: only ONE subject allowed at period 1 → with 2 sections it must clash
        payload["defaults"]["allowed_periods_per_subject"] = {only_sid: [1]}
        # Also force every other subject AWAY from period 1
        for s in subs[1:]:
            payload["defaults"]["allowed_periods_per_subject"][s["id"]] = [2, 3, 4, 5]
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        all_warnings = " | ".join(data.get("conflict_summary", {}).get("warnings") or [])
        # Also gather per-section warnings
        for sec in data["sections"]:
            all_warnings += " | " + " | ".join(sec.get("warnings") or [])
        assert "Same-grade uniqueness relaxed" in all_warnings, (
            f"expected relaxation warning; got: {all_warnings[:1000]}"
        )
        # Schedule still completed (every section returns slots)
        for sec in data["sections"]:
            assert sec.get("slots"), f"section {sec['section']} produced no slots"

    def test_repair_swap_preserves_same_grade_uniqueness(self, admin_session, school_data):
        """After a repair pass (cap=4 should trigger some swaps), verify NO
        new same-grade-subject collision was introduced."""
        g5, g6 = school_data["g5"], school_data["g6"]
        payload = _batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 4
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        bucket: dict = {}
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break") or not sl.get("subject_id"):
                    continue
                key = (sl["class_id"], sl["day"], sl["period"])
                bucket.setdefault(key, []).append(sl["subject_id"])
        violations = [(k, v) for k, v in bucket.items() if len(v) != len(set(v))]
        assert not violations, f"Post-repair same-grade collisions: {violations}"
