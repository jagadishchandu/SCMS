"""Utility helpers."""
import uuid
from datetime import datetime, timezone, date


def new_id() -> str:
    return uuid.uuid4().hex[:24]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat()


def parse_date(s: str) -> date:
    """Accept YYYY-MM-DD."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def clean_doc(doc: dict | None) -> dict | None:
    """Remove Mongo _id from response dicts."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc
