"""In-process APScheduler for cron jobs.

Two jobs:
1. monthly_digest      — 1st of each month @ 09:00 IST (parent monthly digest, ?channels=whatsapp,email)
2. subscription_nudge  — every day @ 08:00 IST (sends 7-day renewal nudge to schools
                          whose subscription.valid_until falls within the next 7 days)

Gated by env var ENABLE_DIGEST_SCHEDULER=true.
"""
import os
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("scms.scheduler")

_scheduler = None

# Re-nudge cooldown: don't send another renewal nudge to the same school for this many hours.
RENEWAL_NUDGE_COOLDOWN_HOURS = 24
RENEWAL_NUDGE_WINDOW_DAYS = 7  # nudge when valid_until is within next 7 days
RENEWAL_NUDGE_TEMPLATE = "subscription_renewal"

OVER_CAPACITY_TEMPLATE = "over_capacity_alert"
OVER_CAPACITY_COOLDOWN_HOURS = 24


def is_enabled() -> bool:
    return os.environ.get("ENABLE_DIGEST_SCHEDULER", "").strip().lower() in ("1", "true", "yes")


# -------------- Monthly digest --------------
async def _run_digest_for_all_schools():
    from core.db import get_db, tenant_db
    from routes.digests import _previous_month_range, _compute_digest, _compose_message
    from core.notify import queue_notification
    from core.audit import log_action

    db = get_db()
    label, start_iso, end_iso = _previous_month_range()
    schools = await db.schools.find({"is_active": True}, {"_id": 0}).to_list(500)
    total = 0
    for school in schools:
        tdb = await tenant_db(school["id"])
        lang_default = school.get("language") or "en"
        students = await tdb.students.find({"school_id": school["id"], "status": "active"}, {"_id": 0}).to_list(5000)
        for s in students:
            parent_user = await db.users.find_one({"id": s.get("parent_user_id")}, {"_id": 0, "language": 1, "email": 1}) if s.get("parent_user_id") else None
            lang = (parent_user or {}).get("language") or lang_default
            digest = await _compute_digest(tdb, school, s, start_iso, end_iso)
            msg = _compose_message(school, s, label, digest, lang)
            phone = (s.get("parent", {}) or {}).get("whatsapp") or (s.get("parent", {}) or {}).get("phone")
            email = (s.get("parent", {}) or {}).get("email") or (parent_user or {}).get("email")
            if phone:
                await queue_notification(
                    school["id"], "parent", s.get("parent_user_id"), phone,
                    "whatsapp", "monthly_digest", msg,
                    context={"student_id": s["id"], "period": label, "language": lang, "source": "scheduler"},
                )
                total += 1
            if email:
                await queue_notification(
                    school["id"], "parent", s.get("parent_user_id"), None,
                    "email", "monthly_digest", msg,
                    context={"student_id": s["id"], "period": label, "language": lang, "source": "scheduler"},
                    email=email, subject=f"Monthly update — {s['name']} ({label})",
                )
                total += 1
        await log_action("system", "platform_admin", school["id"], "run_monthly_digest", "digest",
                         meta={"period": label, "students": len(students), "source": "scheduler"})
    log.info("[scheduler] Monthly digest run for %d students across %d schools", total, len(schools))


# -------------- Subscription renewal nudge --------------
async def _run_subscription_nudges():
    """Find schools whose subscription.valid_until is in the next RENEWAL_NUDGE_WINDOW_DAYS,
    and send a renewal nudge to the school admin via WhatsApp + Email (when available)
    AND always via in-app notification. Specifically targets the T-7 and T-1 checkpoints
    with per-checkpoint cooldown so a school admin gets one nudge at each milestone."""
    from core.db import get_db
    from core.notify import queue_notification
    from core.i18n import render
    from core.audit import log_action

    db = get_db()
    now = datetime.now(timezone.utc)

    schools = await db.schools.find({"is_active": True}, {"_id": 0}).to_list(500)
    sent_count = 0
    for school in schools:
        sub = school.get("subscription") or {}
        if sub.get("status") != "active":
            continue
        vu = sub.get("valid_until")
        if not vu:
            continue
        try:
            vu_dt = vu if isinstance(vu, datetime) else datetime.fromisoformat(str(vu).replace("Z", "+00:00"))
            if vu_dt.tzinfo is None:
                vu_dt = vu_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        days_left = (vu_dt.date() - now.date()).days
        # Specifically fire at T-7 and T-1 checkpoints (plus 0..7 fallback window).
        checkpoint = None
        if days_left == 7:
            checkpoint = "t7"
        elif days_left == 1:
            checkpoint = "t1"
        elif 0 <= days_left <= 7:
            checkpoint = "window"
        else:
            continue

        template_key = f"subscription_renewal_{checkpoint}" if checkpoint in ("t7", "t1") else RENEWAL_NUDGE_TEMPLATE

        # Cooldown — don't repeat the same checkpoint within 24h
        recent = await db.notifications.find_one({
            "school_id": school["id"],
            "template": template_key,
            "created_at": {"$gte": now - timedelta(hours=RENEWAL_NUDGE_COOLDOWN_HOURS)},
        })
        if recent:
            continue

        # Find the school super admin
        admin = await db.users.find_one(
            {"school_id": school["id"], "role": "school_admin", "is_active": True},
            {"_id": 0},
        )
        if not admin:
            continue

        lang = admin.get("language") or school.get("language") or "en"
        renew_url = (os.environ.get("FRONTEND_URL", "").rstrip("/") + "/school/subscription") or "/school/subscription"
        msg = render(
            RENEWAL_NUDGE_TEMPLATE, lang,
            school_name=school["name"],
            valid_until=vu_dt.date().isoformat(),
            days_left=max(days_left, 0),
            renew_url=renew_url,
        )
        ctx = {"valid_until": vu_dt.isoformat(), "days_left": days_left, "language": lang,
               "checkpoint": checkpoint, "source": "scheduler"}

        # In-app — always; this is the channel the user wired up for renewal nudges.
        await queue_notification(
            school["id"], "school_admin", admin["id"], None,
            "in_app", template_key, msg, context=ctx,
        )
        sent_count += 1

        # Best-effort additional channels (only fire if configured)
        phone = admin.get("phone")
        email = admin.get("email")
        if phone:
            await queue_notification(
                school["id"], "school_admin", admin["id"], phone,
                "whatsapp", template_key, msg, context=ctx,
            )
            sent_count += 1
        if email:
            await queue_notification(
                school["id"], "school_admin", admin["id"], None,
                "email", template_key, msg, context=ctx,
                email=email, subject=f"Your SCMS subscription expires in {max(days_left,0)} day(s)",
            )
            sent_count += 1
        await log_action("system", "platform_admin", school["id"], "subscription_renewal_nudge",
                         "subscription", school["id"],
                         meta={"days_left": days_left, "valid_until": vu_dt.isoformat(), "checkpoint": checkpoint})
    log.info("[scheduler] Subscription nudge sent %d messages", sent_count)
    return sent_count


# -------------- Over-capacity alert --------------
async def _run_over_capacity_alerts():
    """For each school whose actual active student count exceeds approved
    children count, notify the Platform Super Admin via email + Telegram (when
    configured). 24-hour cooldown per school to avoid spam.
    """
    from core.db import get_db, tenant_db
    from core.notify import queue_notification
    from core.audit import log_action

    db = get_db()
    now = datetime.now(timezone.utc)
    schools = await db.schools.find({"is_active": True}, {"_id": 0}).to_list(1000)
    breaches = []
    for school in schools:
        approval = school.get("subscription_approval") or {}
        if approval.get("status") != "approved":
            continue
        cap = approval.get("approved_children_count") or approval.get("requested_children_count")
        if not cap:
            continue
        tdb = await tenant_db(school["id"])
        actual = await tdb.students.count_documents({"status": "active"})
        if actual <= cap:
            continue
        breaches.append({
            "school_id": school["id"],
            "school_name": school["name"],
            "school_code": school.get("code"),
            "actual": actual,
            "cap": cap,
            "variance": actual - cap,
        })

    if not breaches:
        log.info("[scheduler] Over-capacity check: no breaches")
        return 0

    # Cooldown — only alert if no notification fired in the last 24h
    recent = await db.notifications.find_one({
        "template": OVER_CAPACITY_TEMPLATE,
        "created_at": {"$gte": now - timedelta(hours=OVER_CAPACITY_COOLDOWN_HOURS)},
    })
    if recent:
        log.info("[scheduler] Over-capacity alert skipped (cooldown active)")
        return 0

    # Build the alert message
    breaches_sorted = sorted(breaches, key=lambda b: b["variance"], reverse=True)
    lines = [f"{b['school_name']} ({b['school_code']}): {b['actual']} / {b['cap']}  →  +{b['variance']} over"
             for b in breaches_sorted]
    body = (
        f"🚨 SCMS — Over-capacity alert\n\n"
        f"{len(breaches)} school(s) currently exceed their approved children count:\n\n"
        + "\n".join(lines)
        + "\n\nReview the Compliance dashboard: /platform/compliance"
    )

    platform_admin = await db.users.find_one(
        {"role": "platform_admin", "is_active": True}, {"_id": 0},
    )
    if not platform_admin:
        log.warning("[scheduler] Over-capacity: no platform admin found")
        return 0

    sent = 0
    if platform_admin.get("telegram_chat_id"):
        await queue_notification(
            None, "platform_admin", platform_admin["id"],
            platform_admin["telegram_chat_id"], "telegram",
            OVER_CAPACITY_TEMPLATE, body,
            context={"breach_count": len(breaches), "breaches": breaches_sorted, "source": "scheduler"},
        )
        sent += 1
    if platform_admin.get("email"):
        await queue_notification(
            None, "platform_admin", platform_admin["id"], None,
            "email", OVER_CAPACITY_TEMPLATE, body,
            context={"breach_count": len(breaches), "breaches": breaches_sorted, "source": "scheduler"},
            email=platform_admin["email"],
            subject=f"SCMS · {len(breaches)} school(s) over capacity",
        )
        sent += 1
    await log_action(
        "system", "platform_admin", None, "over_capacity_alert", "compliance",
        meta={"breach_count": len(breaches), "messages_sent": sent},
    )
    log.info("[scheduler] Over-capacity alert: %d schools, %d messages sent", len(breaches), sent)
    return sent


def start():
    global _scheduler
    if _scheduler is not None or not is_enabled():
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("APScheduler not installed; scheduler disabled")
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    # 1st of each month at 09:00 IST → monthly parent digest
    _scheduler.add_job(_run_digest_for_all_schools, CronTrigger(day=1, hour=9, minute=0), id="monthly_digest")
    # Every day at 08:00 IST → subscription renewal nudge
    _scheduler.add_job(_run_subscription_nudges, CronTrigger(hour=8, minute=0), id="subscription_nudge")
    # Every day at 09:00 IST → over-capacity alert to platform admin
    _scheduler.add_job(_run_over_capacity_alerts, CronTrigger(hour=9, minute=0), id="over_capacity_alert")
    _scheduler.start()
    log.info("[scheduler] Started — monthly digest (1st @ 09:00 IST) + subscription nudge (daily @ 08:00 IST) + over-capacity alert (daily @ 09:00 IST)")


def shutdown():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
