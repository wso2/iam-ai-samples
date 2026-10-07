"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Outbound Email

  Used when the agent has something to tell a person who is not in a browser.

  Falls back to printing the message to the log when SMTP is not configured,
  so the flow can be demonstrated end to end without a mail server. That
  fallback is deliberate and loud: a silently-dropped notification would look
  identical to a delivered one, and the whole point of this path is that the
  user is not present to notice.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Corporate Concierge <no-reply@example.com>")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() == "true"


def configured() -> bool:
    return bool(SMTP_HOST)


def send(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True if it was actually delivered.

    Never raises: a failure to notify must not break whatever produced the
    notification.
    """
    if not to:
        logger.warning("[MAIL] no address for this recipient — dropping: %s", subject)
        return False

    if not configured():
        # The demo path. Printed in full so the link can be copied out of the
        # log and followed by hand.
        logger.info(
            "[MAIL] SMTP not configured — would have sent:\n"
            "  To      : %s\n  Subject : %s\n%s",
            to, subject, "\n".join("  | " + ln for ln in body.splitlines()),
        )
        return False

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            if SMTP_STARTTLS:
                smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
        logger.info("[MAIL >> %s] sent: %s", to, subject)
        return True
    except Exception as e:
        logger.error("[MAIL] could not send to %s: %s", to, e)
        return False
