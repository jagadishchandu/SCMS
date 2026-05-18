"""In-app real-time messaging (chat) between teachers, parents and school admins.

Storage lives in the per-school tenant DB:
  * `messages`              — id, conv_id, school_id, sender_id, recipient_id, text,
                              attachment (optional {name,type,size,data_url}),
                              mentions (list of user_ids @-mentioned), created_at, read_at
  * `conversations`         — id, school_id, participants[a,b] (sorted), last_message_at,
                              last_message_text, last_sender_id,
                              unread_for (dict: user_id -> count),
                              mention_for (dict: user_id -> count of unread @-mentions)
  * `conv_settings`         — per-user settings on a conversation (mute toggle).
                              key: (user_id, conv_id) unique. fields: muted (bool)
  * `push_subscriptions`    — id, user_id, endpoint, keys{p256dh,auth}, created_at.

History cap: after every successful send the conversation is trimmed to keep
only the `CHAT_HISTORY_MAX` (default 10) most recent messages combined from
both sides — older rows are auto-deleted to keep DB storage tight.

Realtime delivery is via a single WebSocket endpoint `/api/messaging/ws` that
multiplexes message + typing + read events for the connected user. Messages
are persisted by the REST POST endpoint and then fanned out over WS. If the
peer is NOT connected (offline) and has NOT muted the thread, a Web Push
notification is sent via VAPID.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from typing import Optional

import jwt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from pydantic import BaseModel, Field

from core.auth import JWT_ALGORITHM, _secret, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now, clean_doc


router = APIRouter(prefix="/messaging", tags=["messaging"])


# ---------- WebSocket connection registry ----------

class ConnectionManager:
    """Tracks active WebSocket connections per user_id. A user can have multiple
    tabs / devices open — all of them receive the same events."""

    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._conns.get(user_id)
            if bucket:
                bucket.discard(ws)
                if not bucket:
                    self._conns.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        """Best-effort fan-out to every socket for `user_id`. Dead sockets are
        silently dropped — the next reconnect rebuilds the set."""
        sockets = list(self._conns.get(user_id, ()))
        if not sockets:
            return
        dead: list[WebSocket] = []
        for s in sockets:
            try:
                await s.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(s)
        if dead:
            async with self._lock:
                bucket = self._conns.get(user_id)
                if bucket:
                    for s in dead:
                        bucket.discard(s)
                    if not bucket:
                        self._conns.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return bool(self._conns.get(user_id))


manager = ConnectionManager()


# ---------- Helpers ----------

def _conv_participants(a: str, b: str) -> list[str]:
    """Conversation key is the sorted pair so either side resolves to the same row."""
    return sorted([a, b])


async def _is_allowed_peer(user: dict, peer_id: str) -> tuple[bool, Optional[dict]]:
    """Check whether `user` is allowed to chat with `peer_id` under our role policy.

    Allowed pairs (same school, both active):
      • school_admin ↔ teacher
      • school_admin ↔ parent       (principal ↔ any parent)
      • school_admin ↔ accounts
      • accounts     ↔ parent       (fee chases)
      • teacher      ↔ parent       (only parents of a student in teacher's class/section)
      • parent       ↔ teacher      (only their child's class teacher)
    Returns (allowed, peer_user_dict_or_None).
    """
    if user["id"] == peer_id:
        return False, None
    db = get_db()
    peer = await db.users.find_one({"id": peer_id, "is_active": True}, {"_id": 0, "password_hash": 0})
    if not peer:
        return False, None
    if peer.get("school_id") != user.get("school_id"):
        return False, None

    role = user["role"]
    proles = peer["role"]
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)

    pair = frozenset({role, proles}) if role != proles else None

    # Symmetric staff <-> staff / staff <-> parent pairs that don't need
    # class-mapping checks.
    OPEN_PAIRS: list[frozenset] = [
        frozenset({"school_admin", "teacher"}),
        frozenset({"school_admin", "parent"}),
        frozenset({"school_admin", "accounts"}),
        frozenset({"accounts", "parent"}),
    ]
    if pair and pair in OPEN_PAIRS:
        return True, peer

    # teacher <-> parent — restricted to parents of students in this teacher's classes
    if role == "teacher" and proles == "parent":
        students = await tdb.students.find({"parent_user_id": peer_id}, {"_id": 0, "class_id": 1, "section": 1}).to_list(50)
        if not students:
            return False, None
        mappings = await tdb.class_teacher_map.find(
            {"school_id": school_id, "teacher_id": user["id"]}, {"_id": 0, "class_id": 1, "section": 1},
        ).to_list(100)
        allowed = {(m["class_id"], m["section"]) for m in mappings}
        for s in students:
            if (s.get("class_id"), s.get("section")) in allowed:
                return True, peer
        return False, None

    if role == "parent" and proles == "teacher":
        my_kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "class_id": 1, "section": 1}).to_list(50)
        if not my_kids:
            return False, None
        mappings = await tdb.class_teacher_map.find(
            {"school_id": school_id, "teacher_id": peer_id}, {"_id": 0, "class_id": 1, "section": 1},
        ).to_list(100)
        allowed = {(m["class_id"], m["section"]) for m in mappings}
        for k in my_kids:
            if (k.get("class_id"), k.get("section")) in allowed:
                return True, peer
        return False, None

    return False, None


async def _upsert_conversation(tdb, school_id: str, a: str, b: str) -> dict:
    parts = _conv_participants(a, b)
    conv = await tdb.conversations.find_one({"participants": parts, "school_id": school_id}, {"_id": 0})
    if conv:
        return conv
    conv = {
        "id": new_id(),
        "school_id": school_id,
        "participants": parts,
        "created_at": utc_now(),
        "last_message_at": None,
        "last_message_text": None,
        "last_sender_id": None,
        "unread_for": {parts[0]: 0, parts[1]: 0},
        "mention_for": {parts[0]: 0, parts[1]: 0},
    }
    await tdb.conversations.insert_one(dict(conv))
    return conv


def _peer_of(conv: dict, me: str) -> str:
    return next((p for p in conv["participants"] if p != me), "")


# ---------- History cap ----------

def _history_max() -> int:
    try:
        n = int(os.environ.get("CHAT_HISTORY_MAX", "10"))
        return max(1, n)
    except Exception:
        return 10


async def _trim_conversation_history(tdb, conv_id: str) -> int:
    """Keep only the latest `_history_max()` messages for this conversation.
    Returns the count of rows deleted. Safe to call after every insert.

    We sort by created_at DESC, take the IDs to keep, then delete EVERY
    other row. This is safer than a `$lte cutoff` cutoff because identical
    `created_at` timestamps cannot accidentally evict one of the kept rows.
    """
    cap = _history_max()
    keep_cursor = tdb.messages.find({"conv_id": conv_id}, {"_id": 0, "id": 1}).sort("created_at", -1).limit(cap)
    keep = await keep_cursor.to_list(cap)
    if len(keep) < cap:
        return 0  # nothing to trim
    keep_ids = [k["id"] for k in keep]
    res = await tdb.messages.delete_many({"conv_id": conv_id, "id": {"$nin": keep_ids}})
    return res.deleted_count


# ---------- Mute settings ----------

async def _is_muted(tdb, user_id: str, conv_id: str) -> bool:
    row = await tdb.conv_settings.find_one(
        {"user_id": user_id, "conv_id": conv_id}, {"_id": 0, "muted": 1},
    )
    return bool(row and row.get("muted"))


# ---------- Web Push ----------

def _vapid_claims() -> dict:
    return {
        "sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@scms.local"),
    }


def _vapid_private_pem() -> str | None:
    """Build a PEM-encoded private key from the urlsafe base64 raw scalar in VAPID_PRIVATE_KEY."""
    raw = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    try:
        # pad
        pad = "=" * (-len(raw) % 4)
        scalar = base64.urlsafe_b64decode(raw + pad)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        priv = ec.derive_private_key(int.from_bytes(scalar, "big"), ec.SECP256R1())
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        return pem
    except Exception as _e:
        return None


async def _send_web_push(user_id: str, school_id: str, payload: dict) -> None:
    """Send a Web Push notification to every subscription the user registered.
    Silently no-ops if VAPID keys are not configured or the library is missing.
    Dead subscriptions (410/404) are auto-deleted."""
    priv_pem = _vapid_private_pem()
    if not priv_pem:
        return
    db = get_db()
    subs = await db.push_subscriptions.find(
        {"user_id": user_id}, {"_id": 0},
    ).to_list(20)
    if not subs:
        return
    try:
        from pywebpush import webpush, WebPushException  # type: ignore
    except Exception:
        return

    def _send_one(sub: dict) -> tuple[bool, int]:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=json.dumps(payload, default=str),
                vapid_private_key=priv_pem,
                vapid_claims=dict(_vapid_claims()),
                ttl=600,
            )
            return True, 0
        except WebPushException as e:
            status = getattr(e.response, "status_code", 0) if getattr(e, "response", None) else 0
            return False, status
        except Exception:
            return False, 0

    loop = asyncio.get_event_loop()
    for sub in subs:
        ok, status = await loop.run_in_executor(None, _send_one, sub)
        if not ok and status in (404, 410):
            await db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})


# ---------- Mention extraction ----------

_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})")


def _detect_mentions(text: str, peer_name: str | None) -> list[str]:
    """Return a list of full names mentioned in `text`. We match @<First> or
    @<First Last> and check against peer_name (case-insensitive) — the only
    user we can mention in a 1-1 chat is the other participant."""
    if not text or not peer_name:
        return []
    matches = []
    for m in _MENTION_RE.finditer(text):
        candidate = m.group(1).strip()
        if not candidate:
            continue
        if candidate.lower() == peer_name.lower():
            matches.append(peer_name)
            continue
        # Also match first name only
        first_token = candidate.split()[0].lower()
        if first_token == peer_name.split()[0].lower():
            matches.append(peer_name)
    return matches


# ---------- System "School Notifications" virtual peer ----------
#
# Parents (and any user receiving channel notifications) get a synthetic
# contact whose id is the constant below. When a chat request targets this
# id we synthesise messages from the `chat_updates` collection instead of
# reading the `messages` collection. There is no DB row for the "user".
SYSTEM_PEER_ID = "system::school-notifications"


def _system_contact() -> dict:
    return {
        "id": SYSTEM_PEER_ID,
        "name": "School Notifications",
        "role": "system",
        "email": "",
        "context": "Attendance, fees, exam & sick-leave alerts",
        "online": True,
        "muted": False,
        "unread": 0,
        "mentions": 0,
        "last_message_at": None,
        "last_message_text": None,
        "is_system": True,
    }


_KIND_BY_TEMPLATE: dict[str, dict] = {
    # template ↔ (kind, label, color, suggested quick replies)
    "attendance_alert":        {"kind": "attendance", "label": "Attendance Alert",     "color": "warning"},
    "absent_alert":            {"kind": "attendance", "label": "Absence Notice",       "color": "warning"},
    "fee_due_reminder":        {"kind": "fee",        "label": "Fee Reminder",         "color": "danger"},
    "fee_invoice":             {"kind": "fee",        "label": "Fee Invoice",          "color": "danger"},
    "fee_paid_receipt":        {"kind": "fee",        "label": "Payment Receipt",      "color": "success"},
    "exam_alert":              {"kind": "exam",       "label": "Exam Update",          "color": "info"},
    "exam_result":             {"kind": "exam",       "label": "Exam Result",          "color": "info"},
    "sick_leave_response":     {"kind": "sick",       "label": "Sick-leave Update",    "color": "info"},
    "sick_leave_submitted":    {"kind": "sick",       "label": "Sick-leave Submitted", "color": "info"},
    "holiday_alert":           {"kind": "holiday",    "label": "Holiday Notice",       "color": "success"},
    "trip_announcement":       {"kind": "trip",       "label": "Trip Announcement",    "color": "info"},
    "trip_rsvp":               {"kind": "trip",       "label": "Trip RSVP",            "color": "info"},
    "syllabus_update":         {"kind": "exam",       "label": "Syllabus Update",      "color": "info"},
    "general":                 {"kind": "general",    "label": "School Notice",        "color": "neutral"},
}


_QUICK_REPLIES_BY_KIND: dict[str, list[str]] = {
    "attendance": ["Acknowledged", "My child is unwell", "Will be there tomorrow"],
    "fee":        ["Will pay today", "Need extension", "Already paid — sharing receipt"],
    "exam":       ["Acknowledged", "Have a doubt", "Need help with prep"],
    "sick":       ["Thank you", "Will share update tomorrow"],
    "holiday":    ["Got it, thanks"],
    "trip":       ["Yes, count us in", "Need more details", "Cannot attend this time"],
    "general":    ["Acknowledged", "Need more info"],
}


def _classify_update(upd: dict) -> dict:
    """Return {kind, label, color, quick_replies} for a chat_updates row."""
    tpl = (upd.get("template") or "general").lower()
    info = _KIND_BY_TEMPLATE.get(tpl)
    if not info:
        # Best-effort partial match (e.g., "fee_*", "attendance_*")
        if "fee" in tpl:
            info = _KIND_BY_TEMPLATE["fee_due_reminder"]
        elif "attend" in tpl or "absent" in tpl:
            info = _KIND_BY_TEMPLATE["attendance_alert"]
        elif "exam" in tpl or "result" in tpl:
            info = _KIND_BY_TEMPLATE["exam_alert"]
        elif "sick" in tpl:
            info = _KIND_BY_TEMPLATE["sick_leave_response"]
        elif "holiday" in tpl:
            info = _KIND_BY_TEMPLATE["holiday_alert"]
        elif "trip" in tpl:
            info = _KIND_BY_TEMPLATE["trip_announcement"]
        else:
            info = _KIND_BY_TEMPLATE["general"]
    return {
        "kind": info["kind"],
        "label": info["label"],
        "color": info["color"],
        "quick_replies": _QUICK_REPLIES_BY_KIND.get(info["kind"], _QUICK_REPLIES_BY_KIND["general"]),
    }


def _chat_update_to_message(upd: dict, recipient_id: str) -> dict:
    """Render a chat_updates row as a chat-message-shaped dict. The bubble is
    purposely channel-agnostic — we no longer surface 'TELEGRAM' / 'WHATSAPP'
    labels. Instead we surface the SEMANTIC kind (Attendance / Fee / Exam /
    Sick-leave / Holiday / Trip / Notice) along with suggested quick replies."""
    info = _classify_update(upd)
    return {
        "id": upd.get("id"),
        "conv_id": SYSTEM_PEER_ID,
        "school_id": upd.get("school_id"),
        "sender_id": SYSTEM_PEER_ID,
        "recipient_id": recipient_id,
        "subject": upd.get("subject"),
        "text": upd.get("body") or upd.get("subject") or "",
        "attachment": None,
        "mentions": [],
        "created_at": upd.get("created_at"),
        "read_at": upd.get("read_at"),
        "kind": info["kind"],
        "kind_label": info["label"],
        "kind_color": info["color"],
        "quick_replies": info["quick_replies"],
        "replied_at": upd.get("replied_at"),
        "reply_text": upd.get("reply_text"),
        "student_name": upd.get("student_name"),
        "student_uid": upd.get("student_uid"),
    }


async def _hydrate_peers(school_id: str, peer_ids: list[str]) -> dict[str, dict]:
    if not peer_ids:
        return {}
    db = get_db()
    users = await db.users.find(
        {"id": {"$in": peer_ids}},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1, "school_id": 1},
    ).to_list(len(peer_ids))
    return {u["id"]: u for u in users}


# ---------- REST endpoints ----------

@router.get("/contacts")
async def list_contacts(user: dict = Depends(get_current_user)):
    """Return the list of users this user is allowed to start a chat with."""
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"contacts": []}
    school_id = user["school_id"]
    db = get_db()
    tdb = await tenant_db(school_id)
    role = user["role"]

    out: list[dict] = []

    async def _all_users_of(roles: list[str], context: str | None = None) -> list[dict]:
        rows = await db.users.find(
            {"school_id": school_id, "role": {"$in": roles}, "is_active": True, "id": {"$ne": user["id"]}},
            {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1},
        ).to_list(5000)
        if context:
            for r in rows:
                r["context"] = context
        return rows

    if role == "school_admin":
        # School admins can reach every teacher, parent, and accounts user.
        out = (
            await _all_users_of(["teacher"])
            + await _all_users_of(["accounts"])
            + await _all_users_of(["parent"])
        )

    elif role == "teacher":
        # all school_admins + parents of students in teacher's classes
        admins = await _all_users_of(["school_admin"])
        mappings = await tdb.class_teacher_map.find(
            {"school_id": school_id, "teacher_id": user["id"]}, {"_id": 0, "class_id": 1, "section": 1},
        ).to_list(100)
        class_section_pairs = [(m["class_id"], m["section"]) for m in mappings]
        students: list[dict] = []
        for cid, sec in class_section_pairs:
            students.extend(
                await tdb.students.find(
                    {"class_id": cid, "section": sec, "parent_user_id": {"$ne": None}},
                    {"_id": 0, "name": 1, "student_uid": 1, "parent_user_id": 1, "class_id": 1, "section": 1},
                ).to_list(2000)
            )
        parent_ids = list({s["parent_user_id"] for s in students if s.get("parent_user_id")})
        parents_idx = await _hydrate_peers(school_id, parent_ids)
        parents_with_ctx: list[dict] = []
        for s in students:
            pu = parents_idx.get(s.get("parent_user_id"))
            if not pu:
                continue
            parents_with_ctx.append({**pu, "context": f"Parent of {s.get('name')} ({s.get('student_uid')})"})
        # de-dup parents (a parent might have two kids in same class)
        seen = set()
        deduped: list[dict] = []
        for c in parents_with_ctx:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            deduped.append(c)
        out = admins + deduped

    elif role == "parent":
        # 1. Class teachers of the parent's children
        my_kids = await tdb.students.find(
            {"parent_user_id": user["id"]},
            {"_id": 0, "id": 1, "name": 1, "student_uid": 1, "class_id": 1, "section": 1},
        ).to_list(50)
        teacher_ids: dict[str, str] = {}  # teacher_id -> ctx
        for k in my_kids:
            mappings = await tdb.class_teacher_map.find(
                {"school_id": school_id, "class_id": k["class_id"], "section": k["section"]},
                {"_id": 0, "teacher_id": 1},
            ).to_list(20)
            for m in mappings:
                teacher_ids.setdefault(m["teacher_id"], f"Class teacher of {k['name']} ({k['student_uid']})")
        teachers_idx = await _hydrate_peers(school_id, list(teacher_ids.keys()))
        teachers = []
        for tid, ctx in teacher_ids.items():
            t = teachers_idx.get(tid)
            if t:
                teachers.append({**t, "context": ctx})
        # 2. Principal(s) — school admins
        principals = await _all_users_of(["school_admin"], "Principal · School office")
        # 3. Accounts (fees, dues)
        accounts = await _all_users_of(["accounts"], "Accounts · Fees & dues")
        out = principals + teachers + accounts

    elif role == "accounts":
        # Accounts users chat with every parent + admins.
        admins = await _all_users_of(["school_admin"])
        parents = await _all_users_of(["parent"], "Parent")
        # Enrich each parent contact with their child names for quick triage.
        if parents:
            pids = [p["id"] for p in parents]
            students = await tdb.students.find(
                {"parent_user_id": {"$in": pids}},
                {"_id": 0, "name": 1, "student_uid": 1, "parent_user_id": 1},
            ).to_list(5000)
            by_pid: dict[str, list[str]] = {}
            for s in students:
                by_pid.setdefault(s["parent_user_id"], []).append(f"{s['name']} ({s['student_uid']})")
            for p in parents:
                kids = by_pid.get(p["id"], [])
                if kids:
                    p["context"] = "Parent of " + ", ".join(kids[:2]) + (f" +{len(kids)-2} more" if len(kids) > 2 else "")
        out = admins + parents

    # Enrich with online + has-existing-conversation flag
    conv_lookup = {}
    convs = await tdb.conversations.find(
        {"school_id": school_id, "participants": user["id"]}, {"_id": 0},
    ).to_list(5000)
    conv_ids = [c["id"] for c in convs]
    muted_rows = await tdb.conv_settings.find(
        {"user_id": user["id"], "conv_id": {"$in": conv_ids}, "muted": True},
        {"_id": 0, "conv_id": 1},
    ).to_list(5000) if conv_ids else []
    muted_set = {r["conv_id"] for r in muted_rows}
    for c in convs:
        peer = _peer_of(c, user["id"])
        conv_lookup[peer] = {**c, "_muted": c["id"] in muted_set}

    for c in out:
        c["online"] = manager.is_online(c["id"])
        conv = conv_lookup.get(c["id"])
        if conv:
            c["unread"] = (conv.get("unread_for") or {}).get(user["id"], 0)
            c["mentions"] = (conv.get("mention_for") or {}).get(user["id"], 0)
            c["last_message_at"] = conv.get("last_message_at")
            c["last_message_text"] = conv.get("last_message_text")
            c["muted"] = bool(conv.get("_muted"))
        else:
            c["unread"] = 0
            c["mentions"] = 0
            c["last_message_at"] = None
            c["last_message_text"] = None
            c["muted"] = False

    # Inject the system "School Notifications" virtual contact at the top
    # for every chat user — backed by the `chat_updates` collection.
    sys_contact = _system_contact()
    latest = await tdb.chat_updates.find(
        {"recipient_id": user["id"], "school_id": school_id},
        {"_id": 0, "body": 1, "created_at": 1, "read_at": 1},
    ).sort("created_at", -1).limit(1).to_list(1)
    unread_sys = await tdb.chat_updates.count_documents(
        {"recipient_id": user["id"], "school_id": school_id, "read_at": None},
    )
    if latest:
        sys_contact["last_message_at"] = latest[0].get("created_at")
        sys_contact["last_message_text"] = (latest[0].get("body") or "")[:160]
    sys_contact["unread"] = unread_sys
    out = [sys_contact] + out

    return {"contacts": out}


@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"conversations": []}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    convs = await tdb.conversations.find(
        {"school_id": school_id, "participants": user["id"]}, {"_id": 0},
    ).sort("last_message_at", -1).to_list(2000)
    peer_ids = list({_peer_of(c, user["id"]) for c in convs})
    peers = await _hydrate_peers(school_id, peer_ids)
    out = []
    for c in convs:
        pid = _peer_of(c, user["id"])
        peer = peers.get(pid) or {"id": pid, "name": "Unknown", "role": ""}
        out.append({
            "id": c["id"],
            "peer": peer,
            "last_message_at": c.get("last_message_at"),
            "last_message_text": c.get("last_message_text"),
            "last_sender_id": c.get("last_sender_id"),
            "unread": (c.get("unread_for") or {}).get(user["id"], 0),
            "online": manager.is_online(pid),
        })
    return {"conversations": out}


@router.get("/conversations/{peer_id}/messages")
async def list_messages(
    peer_id: str,
    limit: int = 100,
    before: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    # System "School Notifications" virtual conversation — synthesise messages
    # from the `chat_updates` collection. Read-only on the user side.
    if peer_id == SYSTEM_PEER_ID:
        school_id = user["school_id"]
        tdb = await tenant_db(school_id)
        rows = await tdb.chat_updates.find(
            {"recipient_id": user["id"], "school_id": school_id},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
        rows.reverse()
        # Hydrate student names for parent-side rendering
        if user.get("role") == "parent" and rows:
            sids = list({r.get("related_student_id") for r in rows if r.get("related_student_id")})
            kids = await tdb.students.find(
                {"id": {"$in": sids}}, {"_id": 0, "id": 1, "name": 1, "student_uid": 1},
            ).to_list(len(sids)) if sids else []
            by_sid = {k["id"]: k for k in kids}
            for r in rows:
                k = by_sid.get(r.get("related_student_id"))
                if k:
                    r["student_name"] = k["name"]
                    r["student_uid"] = k["student_uid"]
        # Mark them all read while we're here
        await tdb.chat_updates.update_many(
            {"recipient_id": user["id"], "school_id": school_id, "read_at": None},
            {"$set": {"read_at": utc_now().isoformat()}},
        )
        msgs = [_chat_update_to_message(r, user["id"]) for r in rows]
        return {
            "conversation_id": SYSTEM_PEER_ID,
            "peer": _system_contact(),
            "messages": msgs,
        }

    ok, peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="You are not allowed to chat with this user")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await _upsert_conversation(tdb, school_id, user["id"], peer_id)
    flt: dict = {"conv_id": conv["id"]}
    if before:
        flt["created_at"] = {"$lt": before}
    msgs = await tdb.messages.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    msgs.reverse()
    return {
        "conversation_id": conv["id"],
        "peer": {k: peer.get(k) for k in ("id", "name", "role", "email")} if peer else None,
        "messages": msgs,
    }


class AttachmentIn(BaseModel):
    name: str = Field(max_length=160)
    type: str = Field(max_length=80)  # mime
    size: int = Field(ge=0, le=2_500_000)  # ≤ ~2.5 MB after base64 inflate (~1.8 MB raw)
    data_url: str = Field(min_length=10, max_length=4_000_000)


class SendMessageIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    attachment: Optional[AttachmentIn] = None


_ALLOWED_ATT_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
}


@router.post("/conversations/{peer_id}/messages")
async def send_message(peer_id: str, payload: SendMessageIn, user: dict = Depends(get_current_user)):
    text = (payload.text or "").strip()
    att = payload.attachment
    if not text and not att:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if att:
        if att.type not in _ALLOWED_ATT_MIMES:
            raise HTTPException(status_code=400, detail="Unsupported file type. Allowed: jpg, png, webp, gif, pdf")
        if not att.data_url.startswith(f"data:{att.type}"):
            raise HTTPException(status_code=400, detail="Attachment data URL must match its declared type")
    ok, peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="You are not allowed to chat with this user")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await _upsert_conversation(tdb, school_id, user["id"], peer_id)

    # Detect @mentions of the peer's name
    mentions: list[str] = []
    if text and peer:
        if _detect_mentions(text, peer.get("name") or ""):
            mentions.append(peer_id)

    now = utc_now()
    msg = {
        "id": new_id(),
        "conv_id": conv["id"],
        "school_id": school_id,
        "sender_id": user["id"],
        "recipient_id": peer_id,
        "text": text,
        "attachment": dict(att) if att else None,
        "mentions": mentions,
        "created_at": now.isoformat(),
        "read_at": None,
    }
    await tdb.messages.insert_one(dict(msg))

    # Build a friendly preview for the contact list summary
    preview = text[:160] if text else (f"📎 {att.name}" if att else "")
    # update conversation summary + bump unread for peer
    inc: dict = {f"unread_for.{peer_id}": 1}
    if mentions:
        inc[f"mention_for.{peer_id}"] = 1
    await tdb.conversations.update_one(
        {"id": conv["id"]},
        {
            "$set": {
                "last_message_at": msg["created_at"],
                "last_message_text": preview,
                "last_sender_id": user["id"],
            },
            "$inc": inc,
        },
    )

    # Trim history (keep only the latest CHAT_HISTORY_MAX rows for this conv)
    try:
        await _trim_conversation_history(tdb, conv["id"])
    except Exception as _e:
        pass

    out_msg = clean_doc(dict(msg))
    payload_evt = {
        "type": "message",
        "message": out_msg,
        "sender": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
    }
    await manager.send_to_user(peer_id, payload_evt)
    await manager.send_to_user(user["id"], payload_evt)  # echo to own other tabs

    # Offline push notification: send only when peer is NOT connected via WS
    # and has NOT muted this conversation. Mentions break through mute.
    try:
        muted = await _is_muted(tdb, peer_id, conv["id"])
        if (not manager.is_online(peer_id)) and (not muted or mentions):
            push_body = preview if preview else "Sent you a message"
            await _send_web_push(peer_id, school_id, {
                "title": f"{user.get('name') or 'Someone'}{' mentioned you' if mentions else ''}",
                "body": push_body,
                "url": "/chat",
                "conversation_id": conv["id"],
                "from": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
                "is_mention": bool(mentions),
            })
    except Exception as _e:
        pass

    return out_msg


@router.post("/conversations/{peer_id}/read")
async def mark_read(peer_id: str, user: dict = Depends(get_current_user)):
    # System peer: mark all chat_updates as read
    if peer_id == SYSTEM_PEER_ID:
        school_id = user["school_id"]
        tdb = await tenant_db(school_id)
        res = await tdb.chat_updates.update_many(
            {"recipient_id": user["id"], "school_id": school_id, "read_at": None},
            {"$set": {"read_at": utc_now().isoformat()}},
        )
        return {"ok": True, "marked": res.modified_count}

    ok, _peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await tdb.conversations.find_one(
        {"school_id": school_id, "participants": _conv_participants(user["id"], peer_id)},
        {"_id": 0, "id": 1},
    )
    if not conv:
        return {"ok": True, "marked": 0}
    now = utc_now().isoformat()
    res = await tdb.messages.update_many(
        {"conv_id": conv["id"], "recipient_id": user["id"], "read_at": None},
        {"$set": {"read_at": now}},
    )
    await tdb.conversations.update_one(
        {"id": conv["id"]},
        {"$set": {f"unread_for.{user['id']}": 0, f"mention_for.{user['id']}": 0}},
    )
    # Notify the other side so they can flip their ticks to "read"
    await manager.send_to_user(peer_id, {
        "type": "read",
        "conversation_id": conv["id"],
        "by": user["id"],
        "at": now,
    })
    return {"ok": True, "marked": res.modified_count}


class TypingIn(BaseModel):
    is_typing: bool = True


@router.post("/conversations/{peer_id}/typing")
async def typing(peer_id: str, payload: TypingIn, user: dict = Depends(get_current_user)):
    ok, _peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed")
    await manager.send_to_user(peer_id, {
        "type": "typing",
        "from": user["id"],
        "is_typing": bool(payload.is_typing),
    })
    return {"ok": True}


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"count": 0, "mentions": 0}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    # Sum unread + mentions across all participating convs. Muted threads
    # don't count toward the regular unread badge (but mentions still do).
    convs = await tdb.conversations.find(
        {"school_id": school_id, "participants": user["id"]},
        {"_id": 0, "id": 1, "unread_for": 1, "mention_for": 1},
    ).to_list(5000)
    if not convs:
        return {"count": 0, "mentions": 0}
    muted_rows = await tdb.conv_settings.find(
        {"user_id": user["id"], "muted": True}, {"_id": 0, "conv_id": 1},
    ).to_list(5000)
    muted_set = {r["conv_id"] for r in muted_rows}
    total = 0
    mentions = 0
    for c in convs:
        u = int((c.get("unread_for") or {}).get(user["id"], 0) or 0)
        m = int((c.get("mention_for") or {}).get(user["id"], 0) or 0)
        mentions += m
        if c["id"] in muted_set:
            # muted: only mentions break through to the count badge
            total += m
        else:
            total += u
    return {"count": total, "mentions": mentions}


# ---------- Mute toggle ----------

class MuteIn(BaseModel):
    muted: bool


@router.post("/conversations/{peer_id}/mute")
async def set_mute(peer_id: str, payload: MuteIn, user: dict = Depends(get_current_user)):
    ok, _peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await _upsert_conversation(tdb, school_id, user["id"], peer_id)
    await tdb.conv_settings.update_one(
        {"user_id": user["id"], "conv_id": conv["id"]},
        {"$set": {
            "user_id": user["id"],
            "conv_id": conv["id"],
            "school_id": school_id,
            "muted": bool(payload.muted),
            "updated_at": utc_now(),
        }},
        upsert=True,
    )
    return {"ok": True, "muted": bool(payload.muted)}


@router.get("/conversations/{peer_id}/settings")
async def get_conv_settings(peer_id: str, user: dict = Depends(get_current_user)):
    if peer_id == SYSTEM_PEER_ID:
        return {"conversation_id": SYSTEM_PEER_ID, "muted": False}
    ok, _peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await _upsert_conversation(tdb, school_id, user["id"], peer_id)
    row = await tdb.conv_settings.find_one(
        {"user_id": user["id"], "conv_id": conv["id"]}, {"_id": 0, "muted": 1},
    )
    return {
        "conversation_id": conv["id"],
        "muted": bool(row and row.get("muted")),
    }


# ---------- Web Push subscription ----------

class PushSubKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushSubKeys


@router.get("/push/config")
async def push_config(user: dict = Depends(get_current_user)):  # noqa: ARG001
    """Return the public VAPID key so the browser can subscribe."""
    return {
        "public_key": os.environ.get("VAPID_PUBLIC_KEY", ""),
        "enabled": bool(os.environ.get("VAPID_PRIVATE_KEY")),
    }


@router.post("/push/subscribe")
async def push_subscribe(payload: PushSubscribeIn, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.push_subscriptions.update_one(
        {"endpoint": payload.endpoint},
        {"$set": {
            "id": new_id(),
            "user_id": user["id"],
            "school_id": user.get("school_id"),
            "endpoint": payload.endpoint,
            "keys": {"p256dh": payload.keys.p256dh, "auth": payload.keys.auth},
            "user_agent": "",
            "updated_at": utc_now(),
        }, "$setOnInsert": {"created_at": utc_now()}},
        upsert=True,
    )
    return {"ok": True}


class PushUnsubscribeIn(BaseModel):
    endpoint: str


@router.post("/push/unsubscribe")
async def push_unsubscribe(payload: PushUnsubscribeIn, user: dict = Depends(get_current_user)):
    db = get_db()
    res = await db.push_subscriptions.delete_one(
        {"endpoint": payload.endpoint, "user_id": user["id"]},
    )
    return {"ok": True, "removed": res.deleted_count}


# ---------- WebSocket ----------

async def _ws_user_from_token(ws: WebSocket) -> Optional[dict]:
    """Resolve user from access_token cookie or `?token=` query param."""
    token = ws.cookies.get("access_token")
    if not token:
        token = ws.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
    except Exception:
        return None
    db = get_db()
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        return None
    return user


@router.websocket("/ws")
async def messaging_ws(websocket: WebSocket, token: Optional[str] = Query(default=None)):  # noqa: ARG001
    user = await _ws_user_from_token(websocket)
    if not user:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await manager.connect(user["id"], websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected", "user_id": user["id"]}))
        # Keep the connection open. Client may send `ping` or `typing` events;
        # we accept them but the typing event is also exposed as a REST POST.
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            t = data.get("type")
            if t == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif t == "typing":
                peer_id = data.get("to")
                if peer_id:
                    ok, _p = await _is_allowed_peer(user, peer_id)
                    if ok:
                        await manager.send_to_user(peer_id, {
                            "type": "typing",
                            "from": user["id"],
                            "is_typing": bool(data.get("is_typing")),
                        })
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(user["id"], websocket)


# =========================================================================
#  Chat Updates feed (mirrors of WhatsApp / Telegram / SMS / Email notifs)
# =========================================================================

@router.get("/updates")
async def list_updates(user: dict = Depends(get_current_user)):
    """List the latest channel updates addressed to the current user. For
    parents, also grouped by child (limit 7 per child). The notify pipeline
    already trims to 7 per (recipient_id, related_student_id) on insert."""
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"updates": [], "by_student": {}}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    rows = await tdb.chat_updates.find(
        {"recipient_id": user["id"], "school_id": school_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)

    # For parents we also surface a child-label so the UI can group by kid.
    by_student: dict[str, dict] = {}
    if user.get("role") == "parent" and rows:
        sids = list({r.get("related_student_id") for r in rows if r.get("related_student_id")})
        if sids:
            kids = await tdb.students.find(
                {"id": {"$in": sids}}, {"_id": 0, "id": 1, "name": 1, "student_uid": 1},
            ).to_list(len(sids))
            by_student = {k["id"]: k for k in kids}
        for r in rows:
            sid = r.get("related_student_id")
            if sid and sid in by_student:
                r["student_name"] = by_student[sid]["name"]
                r["student_uid"] = by_student[sid]["student_uid"]
    return {"updates": rows, "by_student": by_student}


@router.get("/updates/unread-count")
async def updates_unread_count(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"count": 0}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    n = await tdb.chat_updates.count_documents(
        {"recipient_id": user["id"], "school_id": school_id, "read_at": None},
    )
    return {"count": n}


@router.post("/updates/mark-all-read")
async def mark_all_updates_read(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"ok": True, "marked": 0}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    res = await tdb.chat_updates.update_many(
        {"recipient_id": user["id"], "school_id": school_id, "read_at": None},
        {"$set": {"read_at": utc_now().isoformat()}},
    )
    return {"ok": True, "marked": res.modified_count}


# =========================================================================
#  Group chat (broadcast) — admin→all teachers, teacher→all class parents
# =========================================================================

async def _ensure_admin_to_teachers_group(tdb, school_id: str, admin: dict) -> dict:
    """Auto-provision one group per school_admin → all teachers in their school."""
    key = f"admin_to_teachers::{admin['id']}"
    g = await tdb.groups.find_one({"school_id": school_id, "key": key}, {"_id": 0})
    db = get_db()
    teachers = await db.users.find(
        {"school_id": school_id, "role": "teacher", "is_active": True},
        {"_id": 0, "id": 1},
    ).to_list(2000)
    member_ids = sorted({t["id"] for t in teachers})
    if g:
        # refresh members each time so newly added teachers see broadcasts
        if set(g.get("members", [])) != set(member_ids):
            await tdb.groups.update_one({"id": g["id"]}, {"$set": {"members": member_ids}})
            g["members"] = member_ids
        return g
    g = {
        "id": new_id(),
        "school_id": school_id,
        "key": key,
        "scope": "admin_to_teachers",
        "name": "All Teachers (Broadcast)",
        "owner_id": admin["id"],
        "members": member_ids,
        "created_at": utc_now().isoformat(),
        "last_message_at": None,
        "last_message_text": None,
        "last_sender_id": None,
    }
    await tdb.groups.insert_one(dict(g))
    return g


async def _ensure_teacher_to_class_parents_groups(tdb, school_id: str, teacher: dict) -> list[dict]:
    """One group per (teacher, class, section) populated with parents."""
    mappings = await tdb.class_teacher_map.find(
        {"school_id": school_id, "teacher_id": teacher["id"]},
        {"_id": 0, "class_id": 1, "section": 1},
    ).to_list(100)
    classes = await tdb.classes.find({"school_id": school_id}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    class_name = {c["id"]: c["name"] for c in classes}
    groups: list[dict] = []
    for m in mappings:
        students = await tdb.students.find(
            {"class_id": m["class_id"], "section": m["section"], "parent_user_id": {"$ne": None}},
            {"_id": 0, "parent_user_id": 1},
        ).to_list(2000)
        member_ids = sorted({s["parent_user_id"] for s in students if s.get("parent_user_id")})
        key = f"teacher_to_parents::{teacher['id']}::{m['class_id']}::{m['section']}"
        name = f"{class_name.get(m['class_id'], m['class_id'])} {m['section']} — Parents"
        existing = await tdb.groups.find_one({"school_id": school_id, "key": key}, {"_id": 0})
        if existing:
            if set(existing.get("members", [])) != set(member_ids):
                await tdb.groups.update_one({"id": existing["id"]}, {"$set": {"members": member_ids}})
                existing["members"] = member_ids
            groups.append(existing)
            continue
        g = {
            "id": new_id(),
            "school_id": school_id,
            "key": key,
            "scope": "teacher_to_parents",
            "name": name,
            "owner_id": teacher["id"],
            "members": member_ids,
            "class_id": m["class_id"],
            "section": m["section"],
            "created_at": utc_now().isoformat(),
            "last_message_at": None,
            "last_message_text": None,
            "last_sender_id": None,
        }
        await tdb.groups.insert_one(dict(g))
        groups.append(g)
    return groups


@router.get("/groups")
async def list_groups(user: dict = Depends(get_current_user)):
    """Return groups visible to the current user (owner or member). Auto-creates
    the user's owned groups on the fly so the UI is always up to date."""
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        return {"groups": []}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)

    if user["role"] == "school_admin":
        await _ensure_admin_to_teachers_group(tdb, school_id, user)
    elif user["role"] == "teacher":
        await _ensure_teacher_to_class_parents_groups(tdb, school_id, user)

    # Find every group where the user is owner OR member
    flt = {"school_id": school_id, "$or": [{"owner_id": user["id"]}, {"members": user["id"]}]}
    rows = await tdb.groups.find(flt, {"_id": 0}).sort("last_message_at", -1).to_list(500)
    # Per-user mute states
    group_conv_keys = [f"group:{g['id']}" for g in rows]
    muted_rows = await tdb.conv_settings.find(
        {"user_id": user["id"], "conv_id": {"$in": group_conv_keys}, "muted": True},
        {"_id": 0, "conv_id": 1},
    ).to_list(500) if group_conv_keys else []
    muted_set = {r["conv_id"] for r in muted_rows}
    now_iso = utc_now().isoformat()
    # Unread counts (simple: count messages where read_by lacks me + sender != me)
    out = []
    for g in rows:
        unread = await tdb.group_messages.count_documents(
            {"group_id": g["id"], "sender_id": {"$ne": user["id"]}, "read_by": {"$ne": user["id"]}},
        )
        # Auto-expire pin
        pin_id = g.get("pinned_message_id")
        pin_text = g.get("pinned_message_text")
        pin_until = g.get("pinned_until")
        if pin_until and pin_until < now_iso:
            await tdb.groups.update_one({"id": g["id"]}, {"$unset": {
                "pinned_message_id": "", "pinned_message_text": "",
                "pinned_message_sender_id": "", "pinned_at": "",
                "pinned_until": "", "pinned_by": "",
            }})
            pin_id, pin_text, pin_until = None, None, None
        out.append({
            "id": g["id"],
            "key": g.get("key"),
            "name": g.get("name"),
            "scope": g.get("scope"),
            "owner_id": g.get("owner_id"),
            "is_owner": g.get("owner_id") == user["id"],
            "member_count": len(g.get("members") or []),
            "last_message_at": g.get("last_message_at"),
            "last_message_text": g.get("last_message_text"),
            "last_sender_id": g.get("last_sender_id"),
            "unread": unread,
            "muted": f"group:{g['id']}" in muted_set,
            "pinned_message_id": pin_id,
            "pinned_message_text": pin_text,
            "pinned_until": pin_until,
        })
    return {"groups": out}


@router.get("/groups/{group_id}/messages")
async def list_group_messages(group_id: str, limit: int = 100, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if g["owner_id"] != user["id"] and user["id"] not in (g.get("members") or []):
        raise HTTPException(status_code=403, detail="Not a member of this group")
    msgs = await tdb.group_messages.find({"group_id": group_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    msgs.reverse()
    return {"group": g, "messages": msgs}


class GroupSendIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    attachment: Optional[AttachmentIn] = None


@router.post("/groups/{group_id}/messages")
async def send_group_message(group_id: str, payload: GroupSendIn, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if g["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the group owner can send broadcasts")
    text = (payload.text or "").strip()
    att = payload.attachment
    if not text and not att:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if att and att.type not in _ALLOWED_ATT_MIMES:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    now = utc_now()
    msg = {
        "id": new_id(),
        "group_id": group_id,
        "school_id": school_id,
        "sender_id": user["id"],
        "text": text,
        "attachment": dict(att) if att else None,
        "created_at": now.isoformat(),
        "read_by": [user["id"]],
    }
    await tdb.group_messages.insert_one(dict(msg))
    preview = text[:160] if text else (f"📎 {att.name}" if att else "")
    await tdb.groups.update_one(
        {"id": group_id},
        {"$set": {
            "last_message_at": msg["created_at"],
            "last_message_text": preview,
            "last_sender_id": user["id"],
        }},
    )
    # Trim: keep latest 10
    keep_cursor = tdb.group_messages.find(
        {"group_id": group_id}, {"_id": 0, "id": 1},
    ).sort("created_at", -1).limit(_history_max())
    keep_ids = [k["id"] for k in await keep_cursor.to_list(_history_max())]
    if len(keep_ids) >= _history_max():
        await tdb.group_messages.delete_many({"group_id": group_id, "id": {"$nin": keep_ids}})
    out = clean_doc(dict(msg))
    # WS fanout to each member
    payload_evt = {
        "type": "group_message",
        "group_id": group_id,
        "message": out,
        "sender": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
    }
    for member_id in g.get("members") or []:
        await manager.send_to_user(member_id, payload_evt)

    # Offline web-push to every member who isn't connected and hasn't muted
    # the group. Skip the sender.
    try:
        muted_rows = await tdb.conv_settings.find(
            {"conv_id": f"group:{group_id}", "muted": True}, {"_id": 0, "user_id": 1},
        ).to_list(5000)
        muted_users = {r["user_id"] for r in muted_rows}
        push_body = preview if preview else "New broadcast"
        for member_id in g.get("members") or []:
            if member_id == user["id"]:
                continue
            if member_id in muted_users:
                continue
            if manager.is_online(member_id):
                continue
            await _send_web_push(member_id, school_id, {
                "title": f"📣 {g.get('name') or 'Broadcast'}",
                "body": push_body,
                "url": "/chat",
                "group_id": group_id,
                "from": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
            })
    except Exception as _e:
        pass

    return out


@router.post("/groups/{group_id}/read")
async def mark_group_read(group_id: str, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0, "members": 1, "owner_id": 1})
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if g["owner_id"] != user["id"] and user["id"] not in (g.get("members") or []):
        raise HTTPException(status_code=403, detail="Not a member")
    res = await tdb.group_messages.update_many(
        {"group_id": group_id, "read_by": {"$ne": user["id"]}},
        {"$addToSet": {"read_by": user["id"]}},
    )
    return {"ok": True, "marked": res.modified_count}


# =========================================================================
#  Group mute (per member) + Pinned broadcast
# =========================================================================

def _group_conv_key(group_id: str) -> str:
    return f"group:{group_id}"


async def _is_group_member(tdb, school_id: str, group_id: str, user_id: str) -> tuple[bool, Optional[dict]]:
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0})
    if not g:
        return False, None
    if g["owner_id"] == user_id or user_id in (g.get("members") or []):
        return True, g
    return False, g


@router.get("/groups/{group_id}/settings")
async def get_group_settings(group_id: str, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    ok, _g = await _is_group_member(tdb, school_id, group_id, user["id"])
    if not ok:
        raise HTTPException(status_code=403, detail="Not a member")
    row = await tdb.conv_settings.find_one(
        {"user_id": user["id"], "conv_id": _group_conv_key(group_id)},
        {"_id": 0, "muted": 1},
    )
    return {"group_id": group_id, "muted": bool(row and row.get("muted"))}


@router.post("/groups/{group_id}/mute")
async def set_group_mute(group_id: str, payload: MuteIn, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    ok, _g = await _is_group_member(tdb, school_id, group_id, user["id"])
    if not ok:
        raise HTTPException(status_code=403, detail="Not a member")
    await tdb.conv_settings.update_one(
        {"user_id": user["id"], "conv_id": _group_conv_key(group_id)},
        {"$set": {
            "user_id": user["id"],
            "conv_id": _group_conv_key(group_id),
            "school_id": school_id,
            "muted": bool(payload.muted),
            "updated_at": utc_now(),
        }},
        upsert=True,
    )
    return {"ok": True, "muted": bool(payload.muted)}


class PinIn(BaseModel):
    message_id: str
    hours: int = Field(default=24, ge=1, le=168)  # default 24h, max 7 days


@router.post("/groups/{group_id}/pin")
async def pin_group_message(group_id: str, payload: PinIn, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if g["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the group owner can pin a message")
    msg = await tdb.group_messages.find_one({"id": payload.message_id, "group_id": group_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    from datetime import timedelta
    pinned_until = (utc_now() + timedelta(hours=payload.hours)).isoformat()
    await tdb.groups.update_one(
        {"id": group_id},
        {"$set": {
            "pinned_message_id": payload.message_id,
            "pinned_message_text": (msg.get("text") or "")[:240],
            "pinned_message_sender_id": msg.get("sender_id"),
            "pinned_at": utc_now().isoformat(),
            "pinned_until": pinned_until,
            "pinned_by": user["id"],
        }},
    )
    # WS broadcast so members see the pin instantly
    evt = {
        "type": "group_pin",
        "group_id": group_id,
        "pinned_message_id": payload.message_id,
        "pinned_message_text": (msg.get("text") or "")[:240],
        "pinned_until": pinned_until,
    }
    for member_id in g.get("members") or []:
        await manager.send_to_user(member_id, evt)
    await manager.send_to_user(user["id"], evt)
    return {"ok": True, "pinned_message_id": payload.message_id, "pinned_until": pinned_until}


@router.delete("/groups/{group_id}/pin")
async def unpin_group_message(group_id: str, user: dict = Depends(get_current_user)):
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    g = await tdb.groups.find_one({"id": group_id, "school_id": school_id}, {"_id": 0, "owner_id": 1, "members": 1})
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if g["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the group owner can unpin")
    await tdb.groups.update_one(
        {"id": group_id},
        {"$unset": {
            "pinned_message_id": "",
            "pinned_message_text": "",
            "pinned_message_sender_id": "",
            "pinned_at": "",
            "pinned_until": "",
            "pinned_by": "",
        }},
    )
    evt = {"type": "group_pin", "group_id": group_id, "pinned_message_id": None}
    for member_id in g.get("members") or []:
        await manager.send_to_user(member_id, evt)
    await manager.send_to_user(user["id"], evt)
    return {"ok": True}



# =========================================================================
#  Quick replies on a School Notifications message
# =========================================================================

class QuickReplyIn(BaseModel):
    update_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=600)


async def _resolve_reply_recipient(user: dict, upd: dict, tdb) -> Optional[dict]:
    """Decide whom the parent's quick reply goes to:

      * Attendance / sick-leave  →  child's class teacher (single-best match)
      * Fee                     →  first accounts user, else school admin
      * Anything else           →  first school_admin

    Returns the recipient user dict (db.users) or None.
    """
    db = get_db()
    kind = _classify_update(upd).get("kind")
    school_id = user["school_id"]
    sid = upd.get("related_student_id")

    async def _first(role: str) -> Optional[dict]:
        return await db.users.find_one(
            {"school_id": school_id, "role": role, "is_active": True},
            {"_id": 0, "password_hash": 0},
        )

    if kind in ("attendance", "sick", "exam") and sid:
        student = await tdb.students.find_one({"id": sid}, {"_id": 0, "class_id": 1, "section": 1})
        if student:
            mapping = await tdb.class_teacher_map.find_one(
                {"school_id": school_id, "class_id": student["class_id"], "section": student["section"]},
                {"_id": 0, "teacher_id": 1},
            )
            if mapping:
                t = await db.users.find_one({"id": mapping["teacher_id"], "is_active": True},
                                            {"_id": 0, "password_hash": 0})
                if t:
                    return t
    if kind == "fee":
        # Fee matters are routed to the school admin (accounts users aren't
        # chat-enabled in this app). The admin can forward to accounts if needed.
        return await _first("school_admin")
    return await _first("school_admin")


@router.post("/system/reply")
async def post_system_quick_reply(payload: QuickReplyIn, user: dict = Depends(get_current_user)):
    """Send a quick-reply to whomever owns the school notification topic.

    Persists as a normal 1-1 chat message (so it shows up in the recipient's
    Chat tab) and stamps the originating chat_updates row as `replied_at`
    so the UI can hide the quick-reply buttons on subsequent loads.
    """
    if user.get("role") not in ("parent", "teacher", "school_admin", "accounts"):
        raise HTTPException(status_code=403, detail="Not allowed")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    upd = await tdb.chat_updates.find_one(
        {"id": payload.update_id, "recipient_id": user["id"], "school_id": school_id},
        {"_id": 0},
    )
    if not upd:
        raise HTTPException(status_code=404, detail="School notification not found")
    if upd.get("replied_at"):
        raise HTTPException(status_code=409, detail="Already replied")

    recipient = await _resolve_reply_recipient(user, upd, tdb)
    if not recipient:
        raise HTTPException(status_code=400, detail="No staff available to receive the reply right now")

    # Prepend a clear context line so staff knows what the parent is replying to.
    subject = upd.get("subject") or _classify_update(upd).get("label") or "School Notice"
    student_label = ""
    if upd.get("related_student_id"):
        s = await tdb.students.find_one({"id": upd["related_student_id"]},
                                        {"_id": 0, "name": 1, "student_uid": 1})
        if s:
            student_label = f" · {s.get('name')} ({s.get('student_uid')})"
    composed = f"↩︎ Re: {subject}{student_label}\n\n{payload.text}"

    # ---- Smart action suggestions for the recipient ----
    # We embed structured hints on the 1-1 message so the recipient's UI can
    # render one-tap follow-up actions ("Mark absent today", "Approve sick
    # leave", "Send payment link", …). The set is keyed off the original
    # update kind + the parent's chosen reply phrase.
    upd_info = _classify_update(upd)
    kind = upd_info.get("kind")
    sid = upd.get("related_student_id")
    reply_lc = (payload.text or "").lower()
    smart_actions: list[dict] = []
    if kind in ("attendance", "sick") and sid:
        if "unwell" in reply_lc or "sick" in reply_lc:
            smart_actions = [
                {"action": "mark_absent_today",  "label": "Mark absent today",       "kind": "attendance", "student_id": sid},
                {"action": "approve_sick_leave", "label": "Approve sick-leave (3d)", "kind": "sick",       "student_id": sid, "days": 3},
                {"action": "send_wellness_check", "label": "Send wellness check tomorrow", "kind": "wellness", "student_id": sid},
            ]
        elif "be there" in reply_lc or "tomorrow" in reply_lc:
            smart_actions = [
                {"action": "mark_absent_today", "label": "Mark absent today only", "kind": "attendance", "student_id": sid},
            ]
        else:
            smart_actions = [
                {"action": "acknowledge_reply", "label": "Acknowledge", "kind": "ack"},
            ]
    elif kind == "fee":
        if "pay today" in reply_lc or "paying" in reply_lc:
            smart_actions = [
                {"action": "send_payment_link", "label": "Send payment link",        "kind": "fee", "student_id": sid},
                {"action": "acknowledge_reply", "label": "Acknowledge",              "kind": "ack"},
            ]
        elif "extension" in reply_lc or "later" in reply_lc:
            smart_actions = [
                {"action": "grant_fee_extension", "label": "Grant 7-day extension", "kind": "fee", "student_id": sid, "days": 7},
                {"action": "acknowledge_reply",   "label": "Acknowledge",           "kind": "ack"},
            ]
        else:
            smart_actions = [
                {"action": "acknowledge_reply", "label": "Acknowledge", "kind": "ack"},
            ]

    # Reuse the standard 1-1 send flow so all WS / push / trim plumbing fires.
    conv = await _upsert_conversation(tdb, school_id, user["id"], recipient["id"])
    now = utc_now()
    msg = {
        "id": new_id(),
        "conv_id": conv["id"],
        "school_id": school_id,
        "sender_id": user["id"],
        "recipient_id": recipient["id"],
        "text": composed,
        "attachment": None,
        "mentions": [],
        "created_at": now.isoformat(),
        "read_at": None,
        "is_quick_reply": True,
        "system_update_id": upd["id"],
        "quick_reply_text": payload.text,
        "source_kind": kind,
        "source_student_id": sid,
        "smart_actions": smart_actions,
    }
    await tdb.messages.insert_one(dict(msg))
    await tdb.conversations.update_one(
        {"id": conv["id"]},
        {
            "$set": {
                "last_message_at": msg["created_at"],
                "last_message_text": composed[:160],
                "last_sender_id": user["id"],
            },
            "$inc": {f"unread_for.{recipient['id']}": 1},
        },
    )
    try:
        await _trim_conversation_history(tdb, conv["id"])
    except Exception:
        pass

    # Stamp the update so the UI hides the quick-reply chips
    await tdb.chat_updates.update_one(
        {"id": upd["id"]},
        {"$set": {"replied_at": now.isoformat(), "reply_text": payload.text, "reply_recipient_id": recipient["id"]}},
    )

    out_msg = clean_doc(dict(msg))
    payload_evt = {
        "type": "message",
        "message": out_msg,
        "sender": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
    }
    await manager.send_to_user(recipient["id"], payload_evt)
    await manager.send_to_user(user["id"], payload_evt)

    # Web-push to the staff if offline
    try:
        if not manager.is_online(recipient["id"]):
            await _send_web_push(recipient["id"], school_id, {
                "title": f"{user.get('name') or 'Parent'} replied",
                "body": payload.text[:120],
                "url": "/chat",
                "from": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
            })
    except Exception:
        pass

    return {
        "ok": True,
        "update_id": upd["id"],
        "replied_at": msg["created_at"],
        "reply_text": payload.text,
        "recipient": {"id": recipient["id"], "name": recipient.get("name"), "role": recipient.get("role")},
    }


# =========================================================================
#  Smart-action execution
# =========================================================================

class SmartActionIn(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    student_id: Optional[str] = None
    days: Optional[int] = Field(default=None, ge=1, le=30)
    note: Optional[str] = Field(default=None, max_length=400)


_SMART_ACTION_ROLES = {
    "mark_absent_today": {"teacher", "school_admin"},
    "approve_sick_leave": {"teacher", "school_admin"},
    "send_wellness_check": {"teacher", "school_admin"},
    "send_payment_link": {"school_admin", "accounts"},
    "grant_fee_extension": {"school_admin", "accounts"},
    "acknowledge_reply": {"teacher", "school_admin", "accounts"},
}


async def _send_followup_to_parent(tdb, school_id: str, sender: dict, parent_id: str, text: str) -> None:
    """Send a 1-1 chat message from `sender` to `parent_id` reusing all the
    standard plumbing (conversation upsert + WS fan-out + trim)."""
    if not parent_id:
        return
    conv = await _upsert_conversation(tdb, school_id, sender["id"], parent_id)
    now = utc_now()
    msg = {
        "id": new_id(),
        "conv_id": conv["id"],
        "school_id": school_id,
        "sender_id": sender["id"],
        "recipient_id": parent_id,
        "text": text,
        "attachment": None,
        "mentions": [],
        "created_at": now.isoformat(),
        "read_at": None,
    }
    await tdb.messages.insert_one(dict(msg))
    await tdb.conversations.update_one(
        {"id": conv["id"]},
        {"$set": {
            "last_message_at": msg["created_at"],
            "last_message_text": text[:160],
            "last_sender_id": sender["id"],
        }, "$inc": {f"unread_for.{parent_id}": 1}},
    )
    try:
        await _trim_conversation_history(tdb, conv["id"])
    except Exception:
        pass
    out_msg = clean_doc(dict(msg))
    payload_evt = {
        "type": "message",
        "message": out_msg,
        "sender": {"id": sender["id"], "name": sender.get("name"), "role": sender.get("role")},
    }
    await manager.send_to_user(parent_id, payload_evt)
    await manager.send_to_user(sender["id"], payload_evt)


@router.post("/messages/{message_id}/smart-action")
async def run_smart_action(message_id: str, payload: SmartActionIn, user: dict = Depends(get_current_user)):
    """Execute one of the suggested smart actions attached to a quick-reply
    message. The current user must be the message recipient AND have the role
    allowed for that action."""
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    msg = await tdb.messages.find_one(
        {"id": message_id, "school_id": school_id, "recipient_id": user["id"]},
        {"_id": 0},
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.get("is_quick_reply"):
        raise HTTPException(status_code=400, detail="Not a quick-reply message")
    if msg.get("smart_action_done"):
        raise HTTPException(status_code=409, detail="Action already taken")

    action = payload.action
    if action not in _SMART_ACTION_ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown smart action '{action}'")
    if user.get("role") not in _SMART_ACTION_ROLES[action]:
        raise HTTPException(status_code=403, detail="Your role cannot perform this action")

    sid = payload.student_id or msg.get("source_student_id")
    student = None
    if sid:
        student = await tdb.students.find_one({"id": sid}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

    now = utc_now()
    today = now.date().isoformat()
    outcome_text = ""

    if action == "mark_absent_today":
        if not student:
            raise HTTPException(status_code=400, detail="student_id required")
        await tdb.attendance.update_one(
            {"student_id": sid, "date": today, "school_id": school_id},
            {"$set": {
                "student_id": sid, "date": today, "school_id": school_id,
                "class_id": student.get("class_id"), "section": student.get("section"),
                "status": "absent", "note": payload.note or "Auto-marked from chat reply",
                "marked_by": user["id"], "marked_at": now.isoformat(),
            }, "$setOnInsert": {"id": new_id(), "created_at": now.isoformat()}},
            upsert=True,
        )
        outcome_text = f"✅ Marked {student['name']} absent for {today}."

    elif action == "approve_sick_leave":
        if not student:
            raise HTTPException(status_code=400, detail="student_id required")
        from datetime import timedelta
        days = max(1, payload.days or 3)
        end = (now + timedelta(days=days - 1)).date().isoformat()
        await tdb.sick_leaves.insert_one({
            "id": new_id(), "school_id": school_id, "student_id": sid,
            "student_name": student.get("name"),
            "class_id": student.get("class_id"), "section": student.get("section"),
            "from_date": today, "to_date": end,
            "reason": payload.note or "Sick (auto-approved from chat reply)",
            "status": "approved",
            "approved_by": user["id"], "approved_at": now.isoformat(),
            "created_at": now.isoformat(),
            "submitted_by": msg.get("sender_id"),
        })
        outcome_text = f"✅ Approved sick-leave for {student['name']}: {today} → {end} ({days}d)."

    elif action == "send_wellness_check":
        await tdb.wellness_checks.insert_one({
            "id": new_id(), "school_id": school_id, "student_id": sid,
            "due_at": now.isoformat(), "created_by": user["id"],
            "status": "pending", "note": payload.note, "created_at": now.isoformat(),
        })
        outcome_text = f"✅ Scheduled a wellness check for {student['name'] if student else 'student'} tomorrow."

    elif action == "send_payment_link":
        public_url = os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
        base = public_url.rstrip("/") if public_url else ""
        url = f"{base}/parent/fees" if base else "/parent/fees"
        await _send_followup_to_parent(
            tdb, school_id, user, msg.get("sender_id"),
            f"You can pay the pending fees here: {url}",
        )
        outcome_text = "✅ Payment link sent to the parent."

    elif action == "grant_fee_extension":
        days = max(1, payload.days or 7)
        await _send_followup_to_parent(
            tdb, school_id, user, msg.get("sender_id"),
            f"We've granted a {days}-day extension on the pending fees. Please pay before then to avoid late charges.",
        )
        outcome_text = f"✅ Granted {days}-day fee extension."

    elif action == "acknowledge_reply":
        await _send_followup_to_parent(
            tdb, school_id, user, msg.get("sender_id"),
            payload.note or "👍 Got it, thanks for letting us know.",
        )
        outcome_text = "✅ Acknowledged."

    await tdb.messages.update_one(
        {"id": message_id},
        {"$set": {
            "smart_action_done": action,
            "smart_action_outcome": outcome_text,
            "smart_action_at": now.isoformat(),
            "smart_action_by": user["id"],
        }},
    )
    conv_id = msg.get("conv_id")
    if conv_id:
        conv = await tdb.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
        for pid in (conv or {}).get("participants") or []:
            await manager.send_to_user(pid, {
                "type": "smart_action_done",
                "message_id": message_id,
                "action": action,
                "outcome": outcome_text,
            })
    return {"ok": True, "action": action, "outcome": outcome_text}

