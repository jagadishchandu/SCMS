"""SMTP email sender. Provider-agnostic — works with any SMTP server
(Gmail, AWS SES, SendGrid SMTP, Mailgun SMTP, etc.).

Environment variables:
    SMTP_HOST           — e.g. smtp.gmail.com / email-smtp.us-east-1.amazonaws.com
    SMTP_PORT           — usually 587 (STARTTLS) or 465 (SSL)
    SMTP_USER           — login username
    SMTP_PASSWORD       — login password / app password / API key
    SMTP_FROM           — from address shown to recipient (e.g. "SCMS <noreply@school.com>")
    SMTP_USE_SSL        — "true" for port 465 SSL connect; default false → STARTTLS

If `SMTP_HOST` is empty, send_email() returns (False, None) and the message stays queued.
"""
import os
import smtplib
import logging
from email.message import EmailMessage

log = logging.getLogger("scms.email")


def _enabled() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def send_email(to: str, subject: str, body: str) -> tuple[bool, str | None]:
    """Returns (sent, error_or_message_id)."""
    if not _enabled():
        return False, None  # not configured → stay queued
    if not to or "@" not in to:
        return False, "invalid_recipient"
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    sender = os.environ.get("SMTP_FROM", user or "noreply@example.com").strip()
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    try:
        if use_ssl:
            client = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            client = smtplib.SMTP(host, port, timeout=20)
            client.ehlo()
            try:
                client.starttls()
                client.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass  # plain smtp server (test only)
        if user:
            client.login(user, password)
        client.send_message(msg)
        client.quit()
        return True, msg.get("Message-ID") or "smtp_ok"
    except Exception as e:
        log.warning("SMTP send to %s failed: %s", to, e)
        return False, str(e)
