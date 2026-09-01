"""Sends transactional email (verification, password reset) via stdlib
smtplib - no new dependency for "connect and send one text email".

Env: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM
(defaults to SMTP_USER). When SMTP_HOST is unset, is_enabled() is False and
send() just logs the message instead of sending it - so a not-yet-configured
deploy (or local dev) doesn't hang/error on registration; the owner can read
the pending verification/reset link straight from the log.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send(to: str, subject: str, body: str) -> None:
    if not is_enabled():
        logger.warning("SMTP_HOST not set - email to %s not sent:\nSubject: %s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
