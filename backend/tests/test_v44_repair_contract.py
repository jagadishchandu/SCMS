"""V44 follow-up: verify conflict_summary.same_grade_collisions_repaired
and repair pass preserves max_periods_per_day_per_teacher + no_last_period_subjects.
"""
import os
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
    g5 = next((c for c in classes if c["name"] == "Grade 5"), classes[0])
    g6 = next((c for c in classes if c["name"] == "Grade 6"), classes[1])
    return {"subjects": subjects, "g5": g5, "g6": g6}


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


class TestConflictSummaryField:
    def test_same_grade_collisions_repaired_field_present(self, admin_session, school_data):
        g5, g6 = school_data["g5"], school_data["g6"]
        payload = _batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        cs = r.json().get("conflict_summary") or {}
        assert "same_grade_collisions_repaired" in cs, f"missing field; conflict_summary keys: {list(cs.keys())}"
        v = cs["same_grade_collisions_repaired"]
        assert isinstance(v, int), f"expected int, got {type(v).__name__} = {v!r}"
        assert v >= 0


class TestRepairRespectsCap:
    def test_no_teacher_exceeds_cap_after_repair(self, admin_session, school_data):
        """With cap=4, repair may swap subjects to fix same-grade collisions —
        verify NO teacher ends up with >4 periods on any single day."""
        g5, g6 = school_data["g5"], school_data["g6"]
        payload = _batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 4
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        # Count (teacher, day) periods across the entire batch
        counts: dict = {}
        for sec in r.json()["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break"):
                    continue
                tid = sl.get("teacher_id")
                if not tid:
                    continue
                key = (tid, sl["day"])
                counts[key] = counts.get(key, 0) + 1
        violations = {k: v for k, v in counts.items() if v > 4}
        assert not violations, f"Teachers over cap=4 after repair: {violations}"


class TestRepairRespectsNoLastPeriod:
    def test_no_last_period_subjects_not_in_last_period_after_repair(self, admin_session, school_data):
        """A subject in no_last_period_subjects[] must not end up in the
        last instructional period unless a warning fires."""
        g5, g6 = school_data["g5"], school_data["g6"]
        subs = school_data["subjects"]
        # Pick first subject as "no last period"
        nlp_sid = subs[0]["id"]
        payload = _batch_payload(g5, g6)
        payload["defaults"]["no_last_period_subjects"] = [nlp_sid]
        # Trigger repair pass with tight cap
        payload["defaults"]["max_periods_per_day_per_teacher"] = 4
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        ppd = payload["defaults"]["periods_per_day"]  # 6
        lunch = payload["defaults"]["lunch_break_period"]  # 6
        # Last instructional period = max period that is not the lunch break
        # periods 1..6 with 6 = lunch, so last instructional = 5
        last_period = ppd - 1 if lunch == ppd else ppd

        violations = []
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break"):
                    continue
                if sl.get("subject_id") == nlp_sid and sl.get("period") == last_period:
                    violations.append({"section": sec["section"], "day": sl["day"], "period": sl["period"]})
        # If any violations exist, a warning must accompany
        if violations:
            all_warnings = " | ".join(data.get("conflict_summary", {}).get("warnings") or [])
            for sec in data["sections"]:
                all_warnings += " | " + " | ".join(sec.get("warnings") or [])
            assert ("last period" in all_warnings.lower()) or ("no_last_period" in all_warnings.lower()), \
                f"no_last_period violations without warning: {violations}; warnings: {all_warnings[:400]}"
