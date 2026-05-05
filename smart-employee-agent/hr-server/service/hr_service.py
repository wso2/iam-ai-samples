"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR Business Logic

  Pure async functions that operate against the in-memory `store`.
  Shared by the MCP tool layer and the REST dashboard handler — no
  framework imports here, just data and policy.
"""

from datetime import date as dt_date
from typing import Dict, List, Optional

from service import store


# ─── hr_basic ───────────────────────────────────────────────────────────────

async def get_holidays() -> List[Dict]:
    """Return all company holidays."""
    return [{"date": h["date"], "name": h["name"]} for h in store.holidays]


async def get_leave_policy() -> List[Dict]:
    """Return all leave policy types with their rules."""
    return [
        {
            "leave_type": lt,
            "max_days_per_year": p["max_days_per_year"],
            "requires_approval": p["requires_approval"],
            "min_notice_days": p["min_notice_days"],
            "description": p["description"],
        }
        for lt, p in store.leave_policy.items()
    ]


# ─── hr_self ────────────────────────────────────────────────────────────────

async def get_my_leave_balance(sub: str, first_name: str, last_name: str = "") -> Dict:
    """Get leave balance for the authenticated user. Auto-registers if new."""
    user = store.ensure_user(sub, first_name, last_name)
    balance = store.leave_balances[sub]
    return {
        "employee": user["name"],
        "balance": {
            "annual": balance["annual"],
            "sick": balance["sick"],
            "personal": balance["personal"],
        },
    }


async def get_my_leave_requests(sub: str, first_name: str, last_name: str = "") -> List[Dict]:
    """Get all leave requests for the authenticated user."""
    store.ensure_user(sub, first_name, last_name)
    return [
        {
            "request_id": req_id,
            "type": req["leave_type"],
            "start_date": req["start_date"],
            "end_date": req["end_date"],
            "days_requested": req["days_requested"],
            "status": req["status"],
            "reason": req["reason"],
        }
        for req_id, req in store.leave_requests.items()
        if req["user_sub"] == sub
    ]


async def apply_leave(
    sub: str,
    first_name: str,
    last_name: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str,
) -> Dict:
    """Submit a new leave request for the authenticated user."""
    user = store.ensure_user(sub, first_name, last_name)

    if leave_type not in store.leave_policy:
        valid_types = ", ".join(store.leave_policy.keys())
        return {
            "error": "invalid_leave_type",
            "message": f"'{leave_type}' is not a valid leave type. Valid types: {valid_types}",
        }

    try:
        start = dt_date.fromisoformat(start_date)
        end = dt_date.fromisoformat(end_date)
    except ValueError:
        return {
            "error": "invalid_dates",
            "message": "Dates must be in YYYY-MM-DD format.",
        }

    days = (end - start).days + 1
    if days <= 0:
        return {
            "error": "invalid_dates",
            "message": "End date must be on or after start date.",
        }

    min_notice_days = store.leave_policy[leave_type].get("min_notice_days", 0)
    notice_days = (start - dt_date.today()).days
    if notice_days < min_notice_days:
        return {
            "error": "insufficient_notice",
            "message": (
                f"{leave_type} requires at least {min_notice_days} days notice; "
                f"start date is {notice_days} day(s) away."
            ),
        }

    balance = store.leave_balances[sub]
    balance_key = leave_type.split()[0].lower()  # "Annual Leave" -> "annual"
    if balance.get(balance_key, 0) < days:
        return {
            "error": "insufficient_balance",
            "message": (
                f"You only have {balance.get(balance_key, 0)} {leave_type} days remaining, "
                f"but requested {days} days."
            ),
        }

    new_id = store.next_request_id()
    store.leave_requests[new_id] = {
        "user_sub": sub,
        "user_name": user["name"],
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "days_requested": days,
        "status": "Pending",
        "reason": reason,
        "reviewed_by_sub": None,
        "reviewed_by_name": None,
        "rejection_reason": None,
    }
    return {"success": True, "request_id": new_id}


# ─── hr_read ────────────────────────────────────────────────────────────────

async def get_all_leave_requests(
    status: Optional[str] = None,
    employee_name: Optional[str] = None,
) -> List[Dict]:
    """Get all leave requests with optional status and employee name filters."""
    results = []
    for req_id, req in store.leave_requests.items():
        if status and req["status"].lower() != status.lower():
            continue
        if employee_name and employee_name.lower() not in req["user_name"].lower():
            continue
        results.append({
            "request_id": req_id,
            "employee": req["user_name"],
            "type": req["leave_type"],
            "start_date": req["start_date"],
            "end_date": req["end_date"],
            "days_requested": req["days_requested"],
            "status": req["status"],
        })
    return results


async def get_leave_request_details(request_id: str) -> Optional[Dict]:
    """Get detailed info about a specific leave request."""
    req = store.leave_requests.get(request_id)
    if not req:
        return None
    balance = store.leave_balances.get(req["user_sub"], {})
    return {
        "request_id": request_id,
        "employee": req["user_name"],
        "type": req["leave_type"],
        "start_date": req["start_date"],
        "end_date": req["end_date"],
        "days_requested": req["days_requested"],
        "status": req["status"],
        "reason": req["reason"],
        "leave_balance": {
            "annual": balance.get("annual", 0),
            "sick": balance.get("sick", 0),
            "personal": balance.get("personal", 0),
        },
    }


# ─── hr_approve ─────────────────────────────────────────────────────────────

async def approve_leave_request(
    request_id: str, reviewer_sub: str, reviewer_name: str
) -> Dict:
    """Approve a pending leave request. Deducts from employee's balance."""
    req = store.leave_requests.get(request_id)
    if not req:
        return {
            "error": "not_found",
            "message": f"Leave request '{request_id}' not found.",
        }
    if req["status"] != "Pending":
        return {
            "error": "invalid_status",
            "message": f"Leave request {request_id} is already {req['status']}.",
        }

    # Deduct leave balance — reject if it would overdraw.
    balance = store.leave_balances.get(req["user_sub"])
    if balance:
        balance_key = req["leave_type"].split()[0].lower()
        if balance_key in balance:
            remaining = balance[balance_key]
            if remaining < req["days_requested"]:
                return {
                    "error": "insufficient_balance",
                    "message": (
                        f"Cannot approve {request_id}: {req['user_name']} only has "
                        f"{remaining} {balance_key} day(s) remaining, but the request "
                        f"is for {req['days_requested']} day(s)."
                    ),
                }
            balance[balance_key] = remaining - req["days_requested"]

    req["status"] = "Approved"
    req["reviewed_by_sub"] = reviewer_sub
    req["reviewed_by_name"] = reviewer_name

    return {
        "success": True,
        "request_id": request_id,
        "new_status": "Approved",
        "employee": req["user_name"],
        "notification": f"Leave request {request_id} for {req['user_name']} has been approved.",
    }


async def reject_leave_request(
    request_id: str, reason: str, reviewer_sub: str, reviewer_name: str
) -> Dict:
    """Reject a pending leave request with a reason."""
    req = store.leave_requests.get(request_id)
    if not req:
        return {
            "error": "not_found",
            "message": f"Leave request '{request_id}' not found.",
        }
    if req["status"] != "Pending":
        return {
            "error": "invalid_status",
            "message": f"Leave request {request_id} is already {req['status']}.",
        }

    req["status"] = "Rejected"
    req["reviewed_by_sub"] = reviewer_sub
    req["reviewed_by_name"] = reviewer_name
    req["rejection_reason"] = reason

    return {
        "success": True,
        "request_id": request_id,
        "new_status": "Rejected",
        "employee": req["user_name"],
        "notification": f"Leave request {request_id} for {req['user_name']} has been rejected.",
    }


# ─── Dashboard REST ─────────────────────────────────────────────────────────

async def get_leaves_for_dashboard(
    user_sub: Optional[str] = None,
    status: Optional[str] = None,
    employee_name: Optional[str] = None,
) -> List[Dict]:
    """Get leaves for dashboard.
    If user_sub is provided, returns only that user's requests (hr_self).
    Otherwise returns all requests with optional filters (hr_read).
    """
    results = []
    for req_id, req in store.leave_requests.items():
        if user_sub and req["user_sub"] != user_sub:
            continue
        if status and req["status"].lower() != status.lower():
            continue
        if employee_name and employee_name.lower() not in req["user_name"].lower():
            continue
        results.append({
            "employee": req["user_name"],
            "type": req["leave_type"],
            "start_date": req["start_date"],
            "end_date": req["end_date"],
            "days_requested": req["days_requested"],
            "status": req["status"],
        })
    return results
