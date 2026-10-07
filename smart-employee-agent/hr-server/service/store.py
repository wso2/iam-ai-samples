"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  In-Memory HR Data Store

  All user-specific data is keyed by JWT `sub` (Asgardeo user UUID).
  Users are auto-registered on first interaction from JWT claims.
  Global data (holidays, leave policy) is pre-populated seed data.
  User data (requests, balances) starts empty.
"""

import copy
from datetime import date as dt_date
from typing import Dict, List

# ─── Global Seed Data (static, same for all users) ──────────────────────────

_SEED_LEAVE_POLICY = {
    "Annual Leave": {
        "max_days_per_year": 20,
        "requires_approval": True,
        "min_notice_days": 7,
        "description": "Paid annual vacation leave",
    },
    "Sick Leave": {
        "max_days_per_year": 10,
        "requires_approval": True,
        "min_notice_days": 0,
        "description": "Medical leave. Certificate required for 3+ consecutive days.",
    },
    "Personal Leave": {
        "max_days_per_year": 5,
        "requires_approval": True,
        "min_notice_days": 3,
        "description": "Unpaid personal leave for emergencies or personal matters",
    },
}

# US federal holidays. Two years are seeded deliberately: a single-year list
# silently goes stale part-way through the year, leaving the demo with no
# upcoming holidays to show. Dates that fall on a weekend use the federal
# observed day (Saturday -> the Friday before, Sunday -> the Monday after).
_SEED_HOLIDAYS = [
    # ── 2026 ──
    {"date": "2026-01-01", "name": "New Year's Day"},
    {"date": "2026-01-19", "name": "Martin Luther King, Jr. Day"},
    {"date": "2026-02-16", "name": "Presidents' Day"},
    {"date": "2026-05-25", "name": "Memorial Day"},
    {"date": "2026-06-19", "name": "Juneteenth National Independence Day"},
    {"date": "2026-07-03", "name": "Independence Day (observed)"},
    {"date": "2026-09-07", "name": "Labor Day"},
    {"date": "2026-10-12", "name": "Columbus Day"},
    {"date": "2026-11-11", "name": "Veterans Day"},
    {"date": "2026-11-26", "name": "Thanksgiving Day"},
    {"date": "2026-12-25", "name": "Christmas Day"},
    # ── 2027 ──
    {"date": "2027-01-01", "name": "New Year's Day"},
    {"date": "2027-01-18", "name": "Martin Luther King, Jr. Day"},
    {"date": "2027-02-15", "name": "Presidents' Day"},
    {"date": "2027-05-31", "name": "Memorial Day"},
    {"date": "2027-06-18", "name": "Juneteenth National Independence Day (observed)"},
    {"date": "2027-07-05", "name": "Independence Day (observed)"},
    {"date": "2027-09-06", "name": "Labor Day"},
    {"date": "2027-10-11", "name": "Columbus Day"},
    {"date": "2027-11-11", "name": "Veterans Day"},
    {"date": "2027-11-25", "name": "Thanksgiving Day"},
    {"date": "2027-12-24", "name": "Christmas Day (observed)"},
]

_DEFAULT_LEAVE_BALANCE = {
    "annual": 20,
    "sick": 10,
    "personal": 5,
}

# ─── Mutable In-Memory Stores ────────────────────────────────────────────────

leave_policy: Dict = {}
holidays: List = []

# User data — keyed by JWT sub
users: Dict[str, Dict] = {}            # sub -> {name, sub, first_seen}
leave_balances: Dict[str, Dict] = {}   # sub -> {annual, sick, personal}
leave_requests: Dict[str, Dict] = {}   # request_id -> {user_sub, user_name, ...}
leave_request_counter: int = 0


def reset_data() -> None:
    """Reset all stores. Global data re-seeded, user data cleared."""
    global leave_policy, holidays, users, leave_balances, leave_requests
    global leave_request_counter
    leave_policy = copy.deepcopy(_SEED_LEAVE_POLICY)
    holidays = copy.deepcopy(_SEED_HOLIDAYS)
    users = {}
    leave_balances = {}
    leave_requests = {}
    leave_request_counter = 0


def next_request_id() -> str:
    """Allocate the next leave-request reference ID (e.g., LR007)."""
    global leave_request_counter
    leave_request_counter += 1
    return f"LR{leave_request_counter:03d}"


def default_balance() -> Dict[str, int]:
    """A fresh copy of the default per-user leave balance."""
    return copy.deepcopy(_DEFAULT_LEAVE_BALANCE)


def ensure_user(
    sub: str, first_name: str, last_name: str = "",
    email: str = "", username: str = "",
) -> Dict:
    """Ensure a user record exists. Creates one with defaults if new.

    Called on every identity-aware tool invocation. Returns the user record.

    `email` and `username` are how the person can be reached when they are NOT
    in a browser — CIBA needs a login_hint, and the approval notice needs an
    address. They are captured opportunistically from whatever the token
    carries, and refreshed on later calls in case the first token lacked them.
    """
    full_name = f"{first_name} {last_name}".strip()
    if sub not in users:
        users[sub] = {
            "first_name": first_name,
            "last_name": last_name,
            "name": full_name,
            "sub": sub,
            "email": email,
            "username": username,
            "first_seen": str(dt_date.today()),
        }
        leave_balances[sub] = default_balance()
    elif full_name and full_name != users[sub]["name"]:
        # Update name if it changed in the IdP
        users[sub]["first_name"] = first_name
        users[sub]["last_name"] = last_name
        users[sub]["name"] = full_name

    # Backfill regardless of branch: the token that first created the record
    # may not have carried these claims, and they are what make the user
    # reachable when they are not in a browser.
    if email and not users[sub].get("email"):
        users[sub]["email"] = email
    if username and not users[sub].get("username"):
        users[sub]["username"] = username
    return users[sub]


# Initialize on import so the server starts with seed data.
reset_data()
