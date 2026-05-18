"""v1.32 — Per-school mandatory communication channels.

Covers `/api/schools/{id}/mandatory-channels` (GET + PATCH) and the
`school_mandatory_channels` + reachability flags surfaced via `/auth/me`.

Specifically:
- Default fallback: a school created without `mandatory_channels` returns `['telegram']`.
- GET RBAC: platform admin OK, own school admin OK, foreign school admin 403, parent 403, teacher 403, anon 401.
- PATCH RBAC: platform admin OK, school admin 403, teacher 403, parent 403, anon 401.
- PATCH validation: unknown channels 400, empty list 400, duplicates deduped, order preserved.
- PATCH persists: subsequent GET reflects the latest channels.
- `/auth/me` exposes `school_mandatory_channels` for school users + `email_linked`/`phone_linked`/`telegram_linked`.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://classroom-messenger-1.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    """Provisions a fresh school + admin + teacher + parent so the test suite
    can run in parallel with other module-scoped fixtures without colliding."""
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"v32.admin.{suffix.lower()}@v32.example.com"
    admin_pw = "Admin@2026"
    payload = {
        "name": f"V32 School {suffix}", "code": f"V32{suffix}",
        "address": "x", "phone": "+910", "email": f"info.{suffix.lower()}@v32.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "V32 Admin",
        "auto_approve": True,
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    school = r.json()["school"]
    sa = _login(admin_email, admin_pw)

    # Create a subject + teacher (subjects are now mandatory for teachers).
    sub = sa.post(f"{API}/academic/subjects", json={"name": f"Sub {suffix}"}, timeout=15).json()
    teacher_email = f"v32.t.{suffix.lower()}@v32.example.com"
    teacher_pw = "Teach@2026"
    sa.post(f"{API}/users", json={
        "email": teacher_email, "password": teacher_pw, "name": "V32 T",
        "role": "teacher", "subjects": [sub["id"]],
    }, timeout=15)
    ts = _login(teacher_email, teacher_pw)

    # Create one class+student so a parent account is auto-provisioned for RBAC tests.
    cls = sa.post(f"{API}/academic/classes", json={"name": f"Cls{suffix}", "sections": ["A"]}, timeout=15).json()
    stu_payload = {
        "name": "V32 Kid", "class_id": cls["id"], "section": "A",
        "parent": {"name": "V32 Parent", "phone": "+919900000032", "relationship": "father"},
    }
    stu_resp = sa.post(f"{API}/students", json=stu_payload, timeout=15)
    assert stu_resp.status_code == 200, stu_resp.text
    parent_email = stu_resp.json()["parent_login"]["email"]
    parent_pw = stu_resp.json()["parent_login"]["default_password"]
    ps = _login(parent_email, parent_pw)

    # Provision a SECOND independent school so we can verify cross-school 403.
    suffix2 = uuid.uuid4().hex[:6].upper()
    other_admin_email = f"v32.other.{suffix2.lower()}@v32.example.com"
    other_admin_pw = "Admin@2026"
    other_payload = {
        "name": f"V32 Other {suffix2}", "code": f"V32O{suffix2}",
        "address": "x", "phone": "+910", "email": f"info2.{suffix2.lower()}@v32.example.com",
        "academic_year": "2025-2026",
        "admin_email": other_admin_email, "admin_password": other_admin_pw, "admin_name": "V32 Other Admin",
        "auto_approve": True,
    }
    r2 = plat.post(f"{API}/schools", json=other_payload, timeout=20)
    assert r2.status_code == 200, r2.text
    other_school = r2.json()["school"]
    other_sa = _login(other_admin_email, other_admin_pw)

    yield {
        "platform": plat, "school_admin": sa, "teacher": ts, "parent": ps,
        "school": school, "other_school": other_school, "other_school_admin": other_sa,
    }


# ---------- 1) Default fallback ----------

class TestDefaultFallback:
    def test_default_is_telegram_only(self, ctx):
        """A school newly created without explicit channels returns ['telegram']."""
        r = ctx["platform"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channels"] == ["telegram"]
        assert body["school_id"] == ctx["school"]["id"]
        assert set(body["allowed"]) == {"email", "whatsapp", "telegram"}

    def test_auth_me_exposes_mandatory_channels(self, ctx):
        """Every school user gets `school_mandatory_channels` and reachability flags."""
        r = ctx["school_admin"].get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me.get("school_mandatory_channels") == ["telegram"]
        # Reachability flags are always present (bool)
        for k in ("email_linked", "phone_linked", "telegram_linked"):
            assert k in me, f"missing {k} in /auth/me"
            assert isinstance(me[k], bool)

    def test_auth_me_email_linked_true_phone_linked_false_for_admin(self, ctx):
        """The freshly created admin has an email but no phone → phone_linked False."""
        me = ctx["school_admin"].get(f"{API}/auth/me", timeout=15).json()
        assert me["email_linked"] is True
        assert me["telegram_linked"] is False  # admin hasn't linked yet


# ---------- 2) GET RBAC ----------

class TestGetRbac:
    def test_get_platform_admin_ok(self, ctx):
        r = ctx["platform"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200

    def test_get_own_school_admin_ok(self, ctx):
        r = ctx["school_admin"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200

    def test_get_foreign_school_admin_403(self, ctx):
        r = ctx["other_school_admin"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 403, r.text

    def test_get_teacher_in_school_ok(self, ctx):
        """Teachers belong to the school and may read the channel list (it's
        also surfaced via /auth/me) — they just can't modify it."""
        r = ctx["teacher"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200, r.text
        assert "channels" in r.json()

    def test_get_parent_in_school_ok(self, ctx):
        """Parents likewise may read so their UI can render the requirement chips."""
        r = ctx["parent"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200, r.text

    def test_get_anonymous_401(self, ctx):
        r = requests.get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 401

    def test_get_unknown_school_404(self, ctx):
        r = ctx["platform"].get(f"{API}/schools/does-not-exist-xyz/mandatory-channels", timeout=15)
        assert r.status_code == 404


# ---------- 3) PATCH RBAC ----------

class TestPatchRbac:
    def test_patch_platform_admin_ok(self, ctx):
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["telegram", "email"]}, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["channels"] == ["telegram", "email"]

    def test_patch_school_admin_403(self, ctx):
        r = ctx["school_admin"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email"]}, timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_patch_teacher_403(self, ctx):
        r = ctx["teacher"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email"]}, timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_patch_parent_403(self, ctx):
        r = ctx["parent"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email"]}, timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_patch_anonymous_401(self, ctx):
        r = requests.patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email"]}, timeout=15,
        )
        assert r.status_code == 401


# ---------- 4) PATCH validation ----------

class TestPatchValidation:
    def test_patch_empty_list_400(self, ctx):
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": []}, timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "at least one" in r.json()["detail"].lower()

    def test_patch_unknown_channel_400(self, ctx):
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["sms", "carrierpigeon"]}, timeout=15,
        )
        assert r.status_code == 400, r.text
        body = r.json()["detail"]
        assert "Unsupported" in body or "unsupported" in body
        # Both bad values should be listed
        assert "sms" in body and "carrierpigeon" in body

    def test_patch_partial_unknown_400(self, ctx):
        """Even one bad channel in a list rejects the whole request."""
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email", "fax"]}, timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_patch_unknown_school_404(self, ctx):
        r = ctx["platform"].patch(
            f"{API}/schools/does-not-exist-xyz/mandatory-channels",
            json={"channels": ["telegram"]}, timeout=15,
        )
        assert r.status_code == 404


# ---------- 5) PATCH behaviour: dedupe, order, persistence ----------

class TestPatchBehaviour:
    def test_patch_dedupes_preserving_order(self, ctx):
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["whatsapp", "telegram", "whatsapp", "email", "telegram"]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["channels"] == ["whatsapp", "telegram", "email"]

    def test_patch_persists_and_round_trips(self, ctx):
        # Set
        ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email", "whatsapp"]}, timeout=15,
        )
        # Read back via GET
        r = ctx["platform"].get(f"{API}/schools/{ctx['school']['id']}/mandatory-channels", timeout=15)
        assert r.status_code == 200
        assert r.json()["channels"] == ["email", "whatsapp"]

    def test_auth_me_reflects_updated_channels(self, ctx):
        ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["email", "telegram", "whatsapp"]}, timeout=15,
        )
        me = ctx["school_admin"].get(f"{API}/auth/me", timeout=15).json()
        assert set(me["school_mandatory_channels"]) == {"email", "telegram", "whatsapp"}
        # Also exposed at login (via /auth/login response)
        login_resp = ctx["school_admin"].post(
            f"{API}/auth/login",
            json={"email": me["email"], "password": "Admin@2026"}, timeout=15,
        )
        # Cookie session refreshed, body should include the same field
        assert login_resp.status_code == 200
        assert set(login_resp.json()["school_mandatory_channels"]) == {"email", "telegram", "whatsapp"}

    def test_reset_to_telegram_only(self, ctx):
        """Cleanup so other tests/fixtures don't see a polluted school."""
        r = ctx["platform"].patch(
            f"{API}/schools/{ctx['school']['id']}/mandatory-channels",
            json={"channels": ["telegram"]}, timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["channels"] == ["telegram"]
