"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  In-Memory IT Store

  Demo data for the IT service desk. Mirrors hr-server/service/store.py:
  process-local, reset via /reset, no database.
"""

import itertools
import threading

_lock = threading.Lock()
_ticket_seq = itertools.count(1)

IT_POLICIES = [
    {
        "topic": "VPN Access",
        "summary": "Corporate VPN is required for any access to internal systems "
                   "from outside the office network.",
        "details": "Install the Ivanti client, sign in with your corporate account, "
                   "and approve the MFA prompt. Sessions expire after 12 hours.",
    },
    {
        "topic": "Password Policy",
        "summary": "Minimum 12 characters, rotated every 180 days, MFA mandatory.",
        "details": "Passwords must include upper, lower, digit, and symbol. "
                   "Reuse of the last 5 passwords is blocked.",
    },
    {
        "topic": "Software Requests",
        "summary": "Licensed software is requested through the IT service desk.",
        "details": "Standard catalog items are auto-approved. Anything outside the "
                   "catalog needs manager plus IT security approval.",
    },
    {
        "topic": "Device Replacement",
        "summary": "Laptops are refreshed every 3 years, or sooner on hardware failure.",
        "details": "Raise a ticket with the asset tag. Loaner devices are available "
                   "same-day from the IT desk.",
    },
]

SOFTWARE_CATALOG = [
    {"name": "IntelliJ IDEA Ultimate", "category": "Development", "auto_approved": True},
    {"name": "Docker Desktop", "category": "Development", "auto_approved": True},
    {"name": "Figma", "category": "Design", "auto_approved": True},
    {"name": "Tableau Desktop", "category": "Analytics", "auto_approved": False},
    {"name": "Adobe Creative Cloud", "category": "Design", "auto_approved": False},
]

SERVICE_STATUS = [
    {"service": "Email", "status": "Operational", "updated": "2026-08-30T08:00:00Z"},
    {"service": "VPN", "status": "Degraded", "updated": "2026-08-30T09:15:00Z",
     "note": "Elevated latency on the EU gateway. Mitigation in progress."},
    {"service": "Wiki", "status": "Operational", "updated": "2026-08-30T08:00:00Z"},
    {"service": "CI Pipelines", "status": "Operational", "updated": "2026-08-30T08:00:00Z"},
]

# ticket_id -> ticket dict
tickets: dict[str, dict] = {}


def _default_tickets() -> dict[str, dict]:
    return {
        "IT001": {
            "ticket_id": "IT001",
            "subject": "VPN disconnects every few minutes",
            "category": "Network",
            "status": "In Progress",
            "requested_for": "Alex Fernando",
            "created_by": "seed",
            "owner_sub": None,
            "home_org": "primary",
            "resolution": None,
            "resolved_by": None,
        },
    }


def reset() -> None:
    """Restore the store to its default demo state."""
    global _ticket_seq
    with _lock:
        tickets.clear()
        tickets.update(_default_tickets())
        _ticket_seq = itertools.count(2)


def next_ticket_id() -> str:
    with _lock:
        return f"IT{next(_ticket_seq):03d}"


reset()
