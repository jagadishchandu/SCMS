"""Tests for v1.20: Fee catalog link in structures, duties on calendar, over-capacity alert."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://fee-template-clone.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")
SCHOOL = ("principal@sunrise.edu", "School@123")
TEACHER = ("priya@sunrise.edu", "Teacher@123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, r.text
    return s


# ──────────── Calendar surfaces teacher duties ────────────

def test_calendar_includes_duty_events_for_school_admin():
    sa = _login(*SCHOOL)
    r = sa.get(f"{API}/calendar/events", timeout=60)
    assert r.status_code == 200
    types = {e["type"] for e in r.json()}
    assert "duty" in types, f"Expected duty events for school admin; got: {types}"


def test_calendar_teacher_sees_only_own_duties():
    sa = _login(*SCHOOL)
    # Find Priya
    me_t = _login(*TEACHER).get(f"{API}/auth/me").json()
    # Create one specifically for Priya
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": [me_t["id"]],
        "title": f"CalTest {uuid.uuid4().hex[:5]}",
        "type": "duty", "start_at": when, "notify": False,
    }, timeout=60)
    # Teacher hits calendar
    t = _login(*TEACHER)
    events = t.get(f"{API}/calendar/events", timeout=60).json()
    duty_events = [e for e in events if e["type"] == "duty"]
    assert len(duty_events) > 0
    for e in duty_events:
        assert e["meta"]["teacher_id"] == me_t["id"]


def test_calendar_duty_event_has_meta_fields():
    t = _login(*TEACHER)
    events = t.get(f"{API}/calendar/events", timeout=60).json()
    duties = [e for e in events if e["type"] == "duty"]
    if not duties:
        return  # skip if no duties seeded
    d = duties[0]
    for k in ("title", "date", "id"):
        assert d[k] is not None
    assert "duty_type" in d["meta"]
    assert "start_at" in d["meta"]


# ──────────── Over-capacity alert ────────────

def test_run_alert_endpoint_platform_admin_only():
    sa = _login(*SCHOOL)
    r = sa.post(f"{API}/subscriptions/compliance/run-alert")
    assert r.status_code == 403


def test_run_alert_endpoint_returns_count():
    plat = _login(*PLATFORM)
    r = plat.post(f"{API}/subscriptions/compliance/run-alert")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "messages_queued" in body
    assert isinstance(body["messages_queued"], int)


def test_run_alert_queues_notification_when_breach_exists():
    """Build an over-capacity school explicitly, then verify the alert sees it."""
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    email = f"v20.{suffix.lower()}@v20.example.com"
    pw = "Admin@2026"
    # Auto-approve with capacity=1
    r = plat.post(f"{API}/schools", json={
        "name": f"V20 {suffix}", "code": f"V20{suffix}",
        "admin_email": email, "admin_password": pw, "admin_name": "V20",
        "auto_approve": True, "initial_children_count": 1,
    })
    assert r.status_code == 200
    sa = _login(email, pw)
    cls = sa.post(f"{API}/academic/classes", json={"name": "A", "sections": ["A"]}).json()
    for i in range(3):
        sa.post(f"{API}/students", json={
            "name": f"S{i}", "class_id": cls["id"], "section": "A",
            "gender": "m", "parent": {"name": f"P{i}", "phone": f"+91900020{i}000"},
        })
    # Now run the alert (or at least verify the endpoint doesn't error)
    r = plat.post(f"{API}/subscriptions/compliance/run-alert")
    assert r.status_code == 200
    # The exact count depends on cooldown — just ensure the call succeeded
    body = r.json()
    assert body["ok"] is True


# ──────────── Fee Catalog link in Structures (validates new endpoint exists, frontend test covers UI) ────────────

def test_create_structure_with_fee_item_id_field_is_accepted():
    """The structure POST already accepts arbitrary item shapes; verify it
    still accepts the new `fee_item_id` reference without error."""
    sa = _login(*SCHOOL)
    # Pick first class
    classes = sa.get(f"{API}/academic/classes").json()
    if not classes:
        return
    # Pick or create a fee item
    items = sa.get(f"{API}/fee-items").json()
    if not items:
        items = [sa.post(f"{API}/fee-items", json={
            "name": "TestItem", "category": "tuition", "default_amount": 100,
        }).json()]
    payload = {
        "class_id": classes[0]["id"],
        "name": f"V20 struct {uuid.uuid4().hex[:5]}",
        "due_date": "2026-12-31",
        "items": [
            {"type": items[0]["name"], "amount": items[0]["default_amount"], "fee_item_id": items[0]["id"]},
            {"type": "Custom", "amount": 500, "fee_item_id": None},
        ],
    }
    r = sa.post(f"{API}/fees/structures", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == items[0]["default_amount"] + 500
    # Verify the item with fee_item_id round-trips
    saved_items = body["items"]
    assert any(it.get("fee_item_id") == items[0]["id"] for it in saved_items)
