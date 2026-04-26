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

_SEED_HOLIDAYS = [
    {"date": "2026-01-01", "name": "New Year's Day"},
    {"date": "2026-03-20", "name": "Eid Al Fitr (expected)"},
    {"date": "2026-05-27", "name": "Arafat Day (expected)"},
    {"date": "2026-05-28", "name": "Eid Al Adha (expected)"},
    {"date": "2026-07-18", "name": "Islamic New Year (expected)"},
    {"date": "2026-12-01", "name": "Commemoration Day"},
    {"date": "2026-12-02", "name": "UAE National Day"},
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


def ensure_user(sub: str, first_name: str, last_name: str = "") -> Dict:
    """Ensure a user record exists. Creates one with defaults if new.

    Called on every identity-aware tool invocation. Returns the user record.
    """
    full_name = f"{first_name} {last_name}".strip()
    if sub not in users:
        users[sub] = {
            "first_name": first_name,
            "last_name": last_name,
            "name": full_name,
            "sub": sub,
            "first_seen": str(dt_date.today()),
        }
        leave_balances[sub] = default_balance()
    elif full_name and full_name != users[sub]["name"]:
        # Update name if it changed in the IdP
        users[sub]["first_name"] = first_name
        users[sub]["last_name"] = last_name
        users[sub]["name"] = full_name
    return users[sub]


# Initialize on import so the server starts with seed data.
reset_data()
