"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Scope and Identity Guards

  Helpers used by MCP tools to enforce scope-based access control and to
  resolve the current user's identity from per-request context variables.
"""

import logging

from auth.context import (
    current_scopes,
    current_token_info,
    current_user_sub,
    current_user_first_name,
    current_user_last_name,
)
from service import store

logger = logging.getLogger(__name__)


def require_scope(scope: str) -> dict | None:
    """Return an error dict if the current request lacks the required scope, else None."""
    scopes = current_scopes.get()
    if scope not in scopes:
        logger.warning(f"[SCOPE DENIED] Required: '{scope}' | Present: {scopes}")
        return {
            "error": "insufficient_scope",
            "required_scope": scope,
            "available_scopes": scopes,
            "message": f"Access denied. This action requires '{scope}' permission.",
        }
    return None


def require_user() -> dict | None:
    """Return an error dict if the JWT did not resolve a sub, else None."""
    sub = current_user_sub.get()
    if not sub:
        return {
            "error": "unknown_user",
            "message": "Your identity could not be determined from the token.",
        }
    return None


def ensure_current_user() -> None:
    """Auto-register the current user from JWT claims into the in-memory store."""
    sub = current_user_sub.get()
    first_name = current_user_first_name.get() or "Unknown"
    last_name = current_user_last_name.get() or ""
    if sub:
        store.ensure_user(sub, first_name, last_name)


def current_full_name() -> str:
    """Combined first + last name from context, or 'Unknown'."""
    first = current_user_first_name.get() or ""
    last = current_user_last_name.get() or ""
    return f"{first} {last}".strip() or "Unknown"


def get_actor_description() -> str:
    """Audit-log description identifying who performed an action."""
    info = current_token_info.get()
    act = info.get("act")
    name = current_full_name()
    if act:
        actor_sub = act.get("sub") if isinstance(act, dict) else str(act)
        return f"Agent {actor_sub} (on behalf of {name})"
    return f"AI Agent ({name})"
