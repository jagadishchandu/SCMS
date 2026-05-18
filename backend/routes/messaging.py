"""In-app real-time messaging (chat) between teachers, parents and school admins.

Storage lives in the per-school tenant DB:
  * `messages`        — id, conv_id, school_id, sender_id, recipient_id, text, created_at, read_at
  * `conversations`   — id, school_id, participants[a,b] (sorted), last_message_at, last_message_text,
                        last_sender_id, unread_for (dict: user_id -> count)

Realtime delivery is via a single WebSocket endpoint `/api/messaging/ws` that
multiplexes message + typing + read events for the connected user. Messages
are persisted by the REST POST endpoint and then fanned out over WS.
"""
from __future__ import annotations

import asyncio
import json
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
    """Check whether `user` is allowed to chat with `peer_id` under our role policy:

    * parent       ↔ class-teacher of any of their children
    * teacher      ↔ parent of any student in their class/section (via class_teacher_map),
                     OR any school_admin of the same school
    * school_admin ↔ any teacher of the same school

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

    # school_admin <-> teacher
    if role == "school_admin" and proles == "teacher":
        return True, peer
    if role == "teacher" and proles == "school_admin":
        return True, peer

    # teacher <-> parent
    if role == "teacher" and proles == "parent":
        # find any student where parent_user_id == peer.id and (class,section) is taught by this teacher
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
        # The parent's children's class-teacher
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
    }
    await tdb.conversations.insert_one(dict(conv))
    return conv


def _peer_of(conv: dict, me: str) -> str:
    return next((p for p in conv["participants"] if p != me), "")


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
    if user.get("role") not in ("parent", "teacher", "school_admin"):
        return {"contacts": []}
    school_id = user["school_id"]
    db = get_db()
    tdb = await tenant_db(school_id)
    role = user["role"]

    out: list[dict] = []

    if role == "school_admin":
        # all teachers of this school
        teachers = await db.users.find(
            {"school_id": school_id, "role": "teacher", "is_active": True},
            {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1},
        ).to_list(2000)
        out = teachers

    elif role == "teacher":
        # all school_admins + parents of students in teacher's classes
        admins = await db.users.find(
            {"school_id": school_id, "role": "school_admin", "is_active": True},
            {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1},
        ).to_list(50)
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
        # parent contacts get child labels appended
        for s in students:
            pu = parents_idx.get(s.get("parent_user_id"))
            if not pu:
                continue
            out.append({
                **pu,
                "context": f"Parent of {s.get('name')} ({s.get('student_uid')})",
            })
        # de-dup parents (a parent might have two kids in same class)
        seen = set()
        deduped: list[dict] = []
        for c in out:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            deduped.append(c)
        out = admins + deduped

    elif role == "parent":
        my_kids = await tdb.students.find(
            {"parent_user_id": user["id"]},
            {"_id": 0, "id": 1, "name": 1, "student_uid": 1, "class_id": 1, "section": 1},
        ).to_list(50)
        teacher_ids: dict[str, str] = {}  # teacher_id -> "Kid name (UID)"
        for k in my_kids:
            mappings = await tdb.class_teacher_map.find(
                {"school_id": school_id, "class_id": k["class_id"], "section": k["section"]},
                {"_id": 0, "teacher_id": 1},
            ).to_list(20)
            for m in mappings:
                teacher_ids.setdefault(m["teacher_id"], f"Class teacher of {k['name']} ({k['student_uid']})")
        teachers_idx = await _hydrate_peers(school_id, list(teacher_ids.keys()))
        for tid, ctx in teacher_ids.items():
            t = teachers_idx.get(tid)
            if t:
                out.append({**t, "context": ctx})

    # Enrich with online + has-existing-conversation flag
    conv_lookup = {}
    convs = await tdb.conversations.find(
        {"school_id": school_id, "participants": user["id"]}, {"_id": 0},
    ).to_list(5000)
    for c in convs:
        peer = _peer_of(c, user["id"])
        conv_lookup[peer] = c

    for c in out:
        c["online"] = manager.is_online(c["id"])
        conv = conv_lookup.get(c["id"])
        if conv:
            c["unread"] = (conv.get("unread_for") or {}).get(user["id"], 0)
            c["last_message_at"] = conv.get("last_message_at")
            c["last_message_text"] = conv.get("last_message_text")
        else:
            c["unread"] = 0
            c["last_message_at"] = None
            c["last_message_text"] = None
    return {"contacts": out}


@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("parent", "teacher", "school_admin"):
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


class SendMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{peer_id}/messages")
async def send_message(peer_id: str, payload: SendMessageIn, user: dict = Depends(get_current_user)):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    ok, peer = await _is_allowed_peer(user, peer_id)
    if not ok:
        raise HTTPException(status_code=403, detail="You are not allowed to chat with this user")
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    conv = await _upsert_conversation(tdb, school_id, user["id"], peer_id)

    now = utc_now()
    msg = {
        "id": new_id(),
        "conv_id": conv["id"],
        "school_id": school_id,
        "sender_id": user["id"],
        "recipient_id": peer_id,
        "text": text,
        "created_at": now.isoformat(),
        "read_at": None,
    }
    await tdb.messages.insert_one(dict(msg))
    # update conversation summary + bump unread for peer
    await tdb.conversations.update_one(
        {"id": conv["id"]},
        {
            "$set": {
                "last_message_at": msg["created_at"],
                "last_message_text": text[:160],
                "last_sender_id": user["id"],
            },
            "$inc": {f"unread_for.{peer_id}": 1},
        },
    )
    out_msg = clean_doc(dict(msg))
    # WS fanout
    payload_evt = {
        "type": "message",
        "message": out_msg,
        "sender": {"id": user["id"], "name": user.get("name"), "role": user.get("role")},
    }
    await manager.send_to_user(peer_id, payload_evt)
    await manager.send_to_user(user["id"], payload_evt)  # echo to own other tabs
    return out_msg


@router.post("/conversations/{peer_id}/read")
async def mark_read(peer_id: str, user: dict = Depends(get_current_user)):
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
        {"$set": {f"unread_for.{user['id']}": 0}},
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
    if user.get("role") not in ("parent", "teacher", "school_admin"):
        return {"count": 0}
    school_id = user["school_id"]
    tdb = await tenant_db(school_id)
    # Sum unread across all participating convs
    convs = await tdb.conversations.find(
        {"school_id": school_id, "participants": user["id"]},
        {"_id": 0, "unread_for": 1},
    ).to_list(5000)
    total = 0
    for c in convs:
        total += int((c.get("unread_for") or {}).get(user["id"], 0) or 0)
    return {"count": total}


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
