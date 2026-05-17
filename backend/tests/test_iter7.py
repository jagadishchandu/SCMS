"""Iteration 7 — Audit CSV export, Multilingual templates, Email digest channel."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://school-health-portal-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "platform_admin": ("jagadishchandu789@gmail.com", "Manasa@123"),
    "school_admin":   ("principal@sunrise.edu", "School@123"),
    "teacher":        ("priya@sunrise.edu", "Teacher@123"),
    "accounts":       ("accounts@sunrise.edu", "Accounts@123"),
    "parent":         ("parent.stu-00001@sunrise.edu", "Parent@123"),
}


def login(role):
    s = requests.Session()
    e, p = CREDS[role]
    r = s.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def school_session(): return login("school_admin")
@pytest.fixture(scope="module")
def platform_session(): return login("platform_admin")
@pytest.fixture(scope="module")
def teacher_session(): return login("teacher")
@pytest.fixture(scope="module")
def accounts_session(): return login("accounts")
@pytest.fixture(scope="module")
def parent_session(): return login("parent")


def _school_id(school_session):
    me = school_session.get(f"{API}/auth/me", timeout=15).json()
    return me["school_id"]


# ---------- AUDIT CSV EXPORT ----------

class TestAuditCSVExport:
    EXPECTED_HEADER = ("When (UTC),Actor Name,Actor Email,Actor Role,School ID,"
                       "Action,Resource,Resource ID,Details (JSON)")

    def test_school_admin_csv(self, school_session):
        r = school_session.get(f"{API}/audit/export.csv", timeout=20)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, ct
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower() and ".csv" in cd, cd
        # BOM check
        assert r.content.startswith(b"\xef\xbb\xbf"), r.content[:10]
        text = r.content.decode("utf-8-sig")
        first_line = text.splitlines()[0] if text else ""
        assert first_line == self.EXPECTED_HEADER, first_line

    def test_platform_admin_csv(self, platform_session):
        r = platform_session.get(f"{API}/audit/export.csv", timeout=20)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert r.content.startswith(b"\xef\xbb\xbf")

    def test_csv_respects_action_filter(self, school_session):
        r = school_session.get(f"{API}/audit/export.csv", params={"action": "create"}, timeout=20)
        assert r.status_code == 200
        text = r.content.decode("utf-8-sig")
        lines = text.splitlines()
        # header + zero or more rows; every data row's Action column must be "create"
        for line in lines[1:]:
            # naive CSV split (action is 6th column index 5)
            parts = next(__import__("csv").reader([line]))
            if len(parts) >= 6:
                assert parts[5] == "create", parts

    def test_csv_respects_actor_role_filter(self, school_session):
        r = school_session.get(f"{API}/audit/export.csv",
                               params={"actor_role": "school_admin"}, timeout=20)
        assert r.status_code == 200
        text = r.content.decode("utf-8-sig")
        for line in text.splitlines()[1:]:
            parts = next(__import__("csv").reader([line]))
            if len(parts) >= 4:
                assert parts[3] == "school_admin", parts

    def test_csv_respects_date_filter(self, school_session):
        r = school_session.get(f"{API}/audit/export.csv",
                               params={"date_from": "2024-01-01", "date_to": "2030-12-31"}, timeout=20)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    @pytest.mark.parametrize("role", ["teacher", "accounts", "parent"])
    def test_csv_forbidden_for_non_admins(self, role):
        s = login(role)
        r = s.get(f"{API}/audit/export.csv", timeout=15)
        assert r.status_code == 403, r.status_code


# ---------- SCHOOL LANGUAGE ----------

class TestSchoolLanguage:
    EXPECTED = {"en", "hi", "ta", "te", "kn", "mr", "bn", "gu"}

    def test_get_returns_supported(self, school_session):
        sid = _school_id(school_session)
        r = school_session.get(f"{API}/schools/{sid}/language", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "language" in body and "supported" in body
        codes = {x["code"] for x in body["supported"]}
        assert codes == self.EXPECTED, codes
        assert len(body["supported"]) == 8
        for item in body["supported"]:
            assert "code" in item and "label" in item

    def test_patch_valid(self, school_session):
        sid = _school_id(school_session)
        r = school_session.patch(f"{API}/schools/{sid}/language", json={"language": "hi"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("language") == "hi"
        # verify
        g = school_session.get(f"{API}/schools/{sid}/language", timeout=15).json()
        assert g["language"] == "hi"

    def test_patch_invalid(self, school_session):
        sid = _school_id(school_session)
        r = school_session.patch(f"{API}/schools/{sid}/language", json={"language": "xx"}, timeout=15)
        assert r.status_code == 400, r.status_code
        body = r.text.lower()
        for code in ("en", "hi", "ta", "te", "kn", "mr", "bn", "gu"):
            assert code in body, body

    def test_patch_rbac(self, teacher_session, parent_session, school_session):
        sid = _school_id(school_session)
        for s in (teacher_session, parent_session):
            r = s.patch(f"{API}/schools/{sid}/language", json={"language": "en"}, timeout=15)
            assert r.status_code == 403, r.status_code


# ---------- USER LANGUAGE ----------

class TestUserLanguage:
    def test_parent_can_set_own(self, parent_session):
        r = parent_session.patch(f"{API}/users/me/language", json={"language": "ta"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("language") == "ta"

    def test_teacher_can_set_own(self, teacher_session):
        r = teacher_session.patch(f"{API}/users/me/language", json={"language": "bn"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_invalid_lang(self, parent_session):
        r = parent_session.patch(f"{API}/users/me/language", json={"language": "zz"}, timeout=15)
        assert r.status_code == 400


# ---------- DIGEST PREVIEW MULTILINGUAL ----------

# Unicode script ranges to sanity-check translated content
SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi/Marathi)
    "mr": (0x0900, 0x097F),
    "ta": (0x0B80, 0x0BFF),
    "te": (0x0C00, 0x0C7F),
    "kn": (0x0C80, 0x0CFF),
    "bn": (0x0980, 0x09FF),
    "gu": (0x0A80, 0x0AFF),
}


def _has_script(msg, lang):
    lo, hi = SCRIPT_RANGES[lang]
    return any(lo <= ord(ch) <= hi for ch in msg)


class TestDigestI18n:
    def test_preview_en_after_school_set_hi(self, school_session, parent_session):
        # set both school language AND parent language to hi (parent pref takes precedence per digest)
        sid = _school_id(school_session)
        school_session.patch(f"{API}/schools/{sid}/language", json={"language": "hi"}, timeout=15)
        parent_session.patch(f"{API}/users/me/language", json={"language": "hi"}, timeout=15)
        # Preview without lang override → should be Hindi (Devanagari) for STU-00001
        r = school_session.get(f"{API}/digests/preview/STU-00001", timeout=20)
        assert r.status_code == 200
        msg = r.json()["message"]
        assert _has_script(msg, "hi"), msg[:200]

    def test_preview_override_en(self, school_session):
        r = school_session.get(f"{API}/digests/preview/STU-00001", params={"lang": "en"}, timeout=20)
        assert r.status_code == 200
        msg = r.json()["message"]
        # English: should have ASCII letters and NO Devanagari
        assert any(ch.isascii() and ch.isalpha() for ch in msg), msg[:200]
        assert not _has_script(msg, "hi"), msg[:200]

    @pytest.mark.parametrize("lang", ["hi", "ta", "te", "kn", "mr", "bn", "gu"])
    def test_preview_each_language(self, school_session, lang):
        r = school_session.get(f"{API}/digests/preview/STU-00001", params={"lang": lang}, timeout=20)
        assert r.status_code == 200, r.text
        msg = r.json()["message"]
        assert _has_script(msg, lang), f"lang={lang} msg={msg[:200]}"


# ---------- DIGEST RUN-MONTHLY CHANNELS ----------

class TestDigestChannels:
    def test_run_whatsapp_and_email(self, school_session):
        r = school_session.post(f"{API}/digests/run-monthly",
                                params={"channels": "whatsapp,email"}, timeout=120)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        chs = body.get("channels") or []
        assert "whatsapp" in chs and "email" in chs, body
        # totals should be doubled vs single channel since both queued
        assert body["totals"]["queued"] >= 1
        # check notifications collection has email rows
        notifs = school_session.get(f"{API}/notifications",
                                    params={"limit": 200}, timeout=20).json()
        md = [n for n in notifs if n.get("template") == "monthly_digest"]
        emails = [n for n in md if n.get("channel") == "email"]
        assert len(emails) > 0, [n.get("channel") for n in md[:5]]
        # shape check: subject + delivery_note='smtp_not_configured' + status=queued
        e0 = emails[0]
        assert e0.get("status") == "queued", e0
        assert "smtp" in (e0.get("delivery_note") or "").lower(), e0
        assert e0.get("subject"), e0
        assert e0.get("email"), e0

    def test_run_email_only(self, school_session):
        r = school_session.post(f"{API}/digests/run-monthly",
                                params={"channels": "email"}, timeout=120)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("channels") == ["email"], body
        # verify notifications: latest email-channel monthly_digest rows present
        notifs = school_session.get(f"{API}/notifications",
                                    params={"limit": 200}, timeout=20).json()
        emails = [n for n in notifs if n.get("template") == "monthly_digest" and n.get("channel") == "email"]
        assert len(emails) > 0


# ---------- REGRESSION quick smoke ----------

class TestRegressionSmoke:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200

    def test_students_list(self, school_session):
        r = school_session.get(f"{API}/students", timeout=15)
        assert r.status_code == 200 and len(r.json()) >= 8

    def test_audit_facets(self, school_session):
        r = school_session.get(f"{API}/audit/facets", timeout=15)
        assert r.status_code == 200
        for k in ("actions", "resources", "roles"):
            assert k in r.json()

    def test_subscription_pricing(self, school_session):
        r = school_session.get(f"{API}/subscriptions/pricing", timeout=15)
        assert r.status_code == 200
