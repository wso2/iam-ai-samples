"""
IT Agent — Shared in-memory store for pending IT access approval requests.

Keyed by approval_token (UUID).  Thread/task-safe via asyncio.Lock.
Entries expire automatically after IT_APPROVAL_TIMEOUT seconds (default 7 days).
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

_store: dict[str, dict] = {}
_lock = asyncio.Lock()

TIMEOUT_SECONDS = int(os.environ.get("IT_APPROVAL_TIMEOUT", str(7 * 24 * 3600)))  # 7 days


async def create_pending(
    employee_id: str,
    employee_name: str,
    resources: list[str],
) -> str:
    """
    Create a new pending approval entry and return its token.
    """
    token = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(seconds=TIMEOUT_SECONDS)

    async with _lock:
        _store[token] = {
            "token":         token,
            "employee_id":   employee_id,
            "employee_name": employee_name,
            "resources":     resources,
            "status":        "pending",      # pending | approved | rejected | expired
            "created_at":    datetime.utcnow().isoformat(),
            "expires_at":    expires_at.isoformat(),
            "decided_at":    None,
        }
    return token


async def get_pending(token: str) -> Optional[dict]:
    async with _lock:
        entry = _store.get(token)
        if entry and entry["status"] == "pending":
            # Auto-expire check
            if datetime.utcnow() > datetime.fromisoformat(entry["expires_at"]):
                entry["status"] = "expired"
        return entry


async def approve(token: str) -> bool:
    async with _lock:
        entry = _store.get(token)
        if not entry:
            return False
        if entry["status"] not in ("pending",):
            return False
        entry["status"] = "approved"
        entry["decided_at"] = datetime.utcnow().isoformat()
        return True


async def reject(token: str) -> bool:
    async with _lock:
        entry = _store.get(token)
        if not entry:
            return False
        if entry["status"] not in ("pending",):
            return False
        entry["status"] = "rejected"
        entry["decided_at"] = datetime.utcnow().isoformat()
        return True


async def wait_for_approval(token: str, poll_interval: float = 5.0) -> str:
    """
    Poll until the entry is approved/rejected/expired.
    Returns the final status string.
    Raises asyncio.TimeoutError if TIMEOUT_SECONDS elapses.
    """
    deadline = datetime.utcnow() + timedelta(seconds=TIMEOUT_SECONDS)
    while datetime.utcnow() < deadline:
        entry = await get_pending(token)
        if entry is None:
            return "not_found"
        if entry["status"] != "pending":
            return entry["status"]
        await asyncio.sleep(poll_interval)
    # Mark expired
    async with _lock:
        if token in _store and _store[token]["status"] == "pending":
            _store[token]["status"] = "expired"
    return "expired"
