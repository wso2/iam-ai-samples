"""
IT Agent — Email sender for admin approval notifications.

If SMTP env vars are set:  sends a real email.
Otherwise:                 prints the approval URL to the terminal (local dev fallback).
"""

import os
import logging

logger = logging.getLogger(__name__)

SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ADMIN_EMAIL   = os.environ.get("IT_ADMIN_EMAIL", "admin@company.com")


async def send_it_approval_email(
    employee_id: str,
    employee_name: str,
    resources: list[str],
    approval_url: str,
    reject_url: str = "",
) -> None:
    """
    Notify the IT admin that a new employee needs system access provisioned.

    Args:
        employee_id:    e.g. "EMP-001"
        employee_name:  e.g. "Amal"
        resources:      e.g. ["GitHub", "AWS"]
        approval_url:   click-to-approve link
        reject_url:     click-to-reject link (optional)
    """
    resource_list = ", ".join(resources) if resources else "requested resources"
    subject = f"[Action Required] IT Access Approval for {employee_name} ({employee_id})"
    body = f"""
Hi Admin,

A new employee has been onboarded and requires IT system access.

  Employee:   {employee_name} ({employee_id})
  Resources:  {resource_list}

Please review and click the link below to APPROVE provisioning:

  ✅ APPROVE: {approval_url}
{f"  ❌ REJECT:  {reject_url}" if reject_url else ""}

This link will remain valid for 7 days.

—
A2A Onboarding System
""".strip()

    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        await _send_via_smtp(
            to=ADMIN_EMAIL,
            subject=subject,
            body=body,
            employee_name=employee_name,
            employee_id=employee_id,
            resource_list=resource_list,
            approval_url=approval_url,
            reject_url=reject_url,
        )
    else:
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)


async def _send_via_smtp(
    to: str,
    subject: str,
    body: str,
    employee_name: str = "?",
    employee_id: str = "?",
    resource_list: str = "?",
    approval_url: str = "?",
    reject_url: str = "",
) -> None:
    """Send email using aiosmtplib (async SMTP)."""
    try:
        import aiosmtplib
    except ImportError:
        logger.warning("[IT_APPROVAL] aiosmtplib not installed — falling back to terminal output")
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)
        return

    try:
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = SMTP_USER
        msg["To"]      = to

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info(f"[IT_APPROVAL] Email sent to {to}")
    except Exception as e:
        logger.error(f"[IT_APPROVAL] SMTP failed: {e}")
        # Fallback to terminal with correct employee data
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)


def _print_to_terminal(
    employee_name: str,
    employee_id: str,
    resource_list: str,
    approval_url: str,
    reject_url: str,
) -> None:
    """Print approval URL to terminal when SMTP is not configured."""
    border = "=" * 72
    print(f"\n{border}")
    print(f"  📧  IT ACCESS APPROVAL REQUIRED  (no SMTP — console fallback)")
    print(border)
    print(f"  Employee : {employee_name} ({employee_id})")
    print(f"  Resources: {resource_list}")
    print(f"\n  ✅ APPROVE → {approval_url}")
    if reject_url:
        print(f"  ❌ REJECT  → {reject_url}")
    print(f"\n  Open the APPROVE link in your browser to continue the workflow.")
    print(f"{border}\n")
