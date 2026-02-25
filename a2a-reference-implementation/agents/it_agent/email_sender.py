"""
IT Agent — Email sender for admin approval notifications.

If SMTP env vars are set:  sends a real email.
Otherwise:                 prints the approval URL to the terminal (local dev fallback).
"""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _smtp_config() -> dict:
    """Read SMTP config fresh from env on every call so .env changes are picked up
    without restarting the process and module-level caching never hides missing vars."""
    load_dotenv(override=True)
    return {
        "host":        os.environ.get("SMTP_HOST", ""),
        "port":        int(os.environ.get("SMTP_PORT", "587")),
        "user":        os.environ.get("SMTP_USER", ""),
        "password":    os.environ.get("SMTP_PASSWORD", ""),
        "admin_email": os.environ.get("IT_ADMIN_EMAIL", "admin@company.com"),
    }


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
    resource_badges = "".join(
        f'<span style="display:inline-block;background:#fff3e0;color:#ff7300;'
        f'border:1px solid #ffe0b2;border-radius:4px;padding:4px 12px;'
        f'margin:3px 4px;font-size:12px;font-weight:600;letter-spacing:0.5px;">{r}</span>'
        for r in (resources or ["IT Resources"])
    )

    subject = f"[Action Required] IT Access Approval for {employee_name} ({employee_id})"

    # ── Plain-text fallback ──────────────────────────────────────────────────
    plain_body = (
        f"Hi Admin,\n\n"
        f"A new employee requires IT system access provisioning.\n\n"
        f"  Employee : {employee_name} ({employee_id})\n"
        f"  Resources: {resource_list}\n\n"
        f"APPROVE: {approval_url}\n"
        + (f"REJECT:  {reject_url}\n" if reject_url else "")
        + "\nThis link is valid for 7 days.\n\n— A2A Onboarding System"
    )

    # ── HTML body ────────────────────────────────────────────────────────────
    reject_btn = (
        f'<a href="{reject_url}" style="display:inline-block;background:#ffffff;'
        f'color:#424242;border:1px solid #cfd8dc;border-radius:4px;padding:12px 32px;'
        f'font-size:14px;font-weight:600;text-decoration:none;margin:0 8px;'
        f'transition:all 0.2s ease;">Reject</a>'
        if reject_url else ""
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 12px rgba(0,0,0,0.05);max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:#222222;padding:32px 40px;text-align:left;border-bottom:4px solid #ff7300;">
            <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:0.5px;">
              A2A Onboarding
            </div>
            <div style="font-size:13px;color:#9e9e9e;margin-top:4px;letter-spacing:1px;text-transform:uppercase;">
              Access Request
            </div>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px;">
            <p style="margin:0 0 16px;font-size:16px;color:#212121;font-weight:600;">Hello Admin,</p>
            <p style="margin:0 0 32px;font-size:15px;color:#616161;line-height:1.6;">
              A new team member has been onboarded and requires IT system access.
              Please review the details below and approve or reject the provisioning request.
            </p>

            <!-- Employee Card -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#fafafa;border:1px solid #eeeeee;border-radius:6px;
                          margin-bottom:32px;">
              <tr>
                <td style="padding:24px;">
                  <table cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td style="padding:8px 0;font-size:13px;color:#757575;
                                 width:120px;font-weight:500;text-transform:uppercase;letter-spacing:0.5px;">Name</td>
                      <td style="padding:8px 0;font-size:15px;color:#212121;
                                 font-weight:600;">{employee_name}</td>
                    </tr>
                    <tr>
                      <td style="padding:8px 0;font-size:13px;color:#757575;
                                 font-weight:500;text-transform:uppercase;letter-spacing:0.5px;">Employee ID</td>
                      <td style="padding:8px 0;font-size:15px;color:#212121;">
                        <span style="background:#eeeeee;color:#424242;padding:3px 8px;
                                     border-radius:3px;font-size:13px;font-family:monospace;">{employee_id}</span>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 0 4px;font-size:13px;color:#757575;
                                 font-weight:500;vertical-align:top;text-transform:uppercase;letter-spacing:0.5px;">Access</td>
                      <td style="padding:12px 0 4px;">{resource_badges}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- Buttons -->
            <div style="text-align:left;margin-bottom:24px;">
              <a href="{approval_url}"
                 style="display:inline-block;background:#ff7300;
                        color:#ffffff;border-radius:4px;padding:12px 32px;font-size:14px;
                        font-weight:600;text-decoration:none;margin:0 12px 0 0;
                        box-shadow:0 2px 4px rgba(255,115,0,0.2);">
                Approve Access
              </a>
              {reject_btn}
            </div>

            <p style="font-size:13px;color:#9e9e9e;margin:0;line-height:1.5;">
              These links are valid for <strong>7 days</strong>.<br>
              Once approved, provisioning will start automatically.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#fafafa;border-top:1px solid #eeeeee;
                     padding:24px 40px;text-align:left;">
            <p style="margin:0;font-size:12px;color:#9e9e9e;">
              Sent by <strong>A2A Onboarding System</strong><br>
              This is an automated message, please do not reply.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    cfg = _smtp_config()
    if cfg["host"] and cfg["user"] and cfg["password"]:
        await _send_via_smtp(
            to=cfg["admin_email"],
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
            cfg=cfg,
            employee_name=employee_name,
            employee_id=employee_id,
            resource_list=resource_list,
            approval_url=approval_url,
            reject_url=reject_url,
        )
    else:
        logger.warning("[IT_APPROVAL] SMTP not configured — printing approval URL to terminal.")
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)


async def _send_via_smtp(
    to: str,
    subject: str,
    plain_body: str,
    html_body: str,
    cfg: dict,
    employee_name: str = "?",
    employee_id: str = "?",
    resource_list: str = "?",
    approval_url: str = "?",
    reject_url: str = "",
) -> None:
    """Send a multipart/alternative HTML + plain-text email via aiosmtplib."""
    try:
        import aiosmtplib
    except ImportError:
        logger.warning("[IT_APPROVAL] aiosmtplib not installed — install it with: pip install aiosmtplib")
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)
        return

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["user"]
        msg["To"]      = to

        # Attach plain text first, HTML second (email clients prefer the last part)
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,  "html",  "utf-8"))

        # Port 465 uses implicit TLS (use_tls); port 587 uses STARTTLS (start_tls)
        use_ssl = cfg["port"] == 465
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            username=cfg["user"],
            password=cfg["password"],
            use_tls=use_ssl,
            start_tls=not use_ssl,
        )
        logger.info(f"[IT_APPROVAL] ✅ Email sent to {to}")
    except Exception as e:
        logger.error(f"[IT_APPROVAL] SMTP failed: {e}")
        _print_to_terminal(employee_name, employee_id, resource_list, approval_url, reject_url)


def _print_to_terminal(
    employee_name: str,
    employee_id: str,
    resource_list: str,
    approval_url: str,
    reject_url: str,
) -> None:
    """Print approval URL to terminal when SMTP is not configured, and broadcast to visualizer."""
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

    # Also broadcast to visualizer so the approval URL is visible in the UI log
    try:
        from src.log_broadcaster import broadcast_log_sync
        broadcast_log_sync(
            f"[IT_APPROVAL] 📧 Admin action required for {employee_name} ({employee_id}) | "
            f"Resources: {resource_list} | ✅ APPROVE: {approval_url}"
        )
    except Exception:
        pass
