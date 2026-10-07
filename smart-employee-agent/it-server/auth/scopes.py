"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Scope Guards

  Helpers used by IT MCP tools to enforce scope-based access control.

  Two kinds of caller reach these tools, and they are authorized differently:

    Pattern 4 (agent token)  the IT Agent acting for itself, invoked by the HR
                             Agent. No user subject; the human travels as audit
                             data only and confers no authority.

    Pattern 7 (OBO token)    an IT admin using the service desk directly. `sub`
                             is the human, `act.sub` is the IT Agent, and the
                             scopes are the ones THAT HUMAN's role grants. A
                             federated partner-org admin arrives this way.

  The scope check is identical either way — which is the point. The tool does
  not care who the caller is, only what the presented token permits.
"""

import logging

from auth.context import (
    current_scopes,
    current_token_info,
    current_user_sub,
    current_user_first_name,
    current_user_last_name,
)

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


def calling_agent_sub() -> str | None:
    """Subject of the AGENT that carried this call.

    On an agent token that is the token's own `sub`. On an OBO token `sub` is
    the human, and the agent is the actor in `act.sub` — reading `sub` there
    would credit the user's own id as the agent in every audit line.
    """
    info = current_token_info.get()
    act = info.get("act")
    if isinstance(act, dict) and act.get("sub"):
        return act["sub"]
    if act:
        return str(act)
    return info.get("sub")




def is_user_delegated() -> bool:
    """True when the caller presented an OBO token (a human acting through an agent)."""
    return bool(current_token_info.get().get("act"))


def require_user() -> dict | None:
    """Error dict unless a human subject is attached to this call.

    Guards tools that must attribute an action to a person. An agent-only token
    (Pattern 4) has no user, so it fails here even when the scope is present.
    """
    if not is_user_delegated() or not current_user_sub.get():
        logger.warning("[USER REQUIRED] call carried no delegated user identity")
        return {
            "error": "user_required",
            "message": (
                "This action must be performed by a person. The presented token "
                "authorizes an agent acting alone, with no user on whose behalf "
                "it is acting."
            ),
        }
    return None


def current_full_name() -> str:
    """Display name of the delegated user, from the OBO token's profile claims."""
    name = f"{current_user_first_name.get()} {current_user_last_name.get()}".strip()
    return name or (current_user_sub.get() or "Unknown")


def current_home_org() -> str:
    """Which identity domain the delegated user came from.

    A federated partner-org admin carries the originating IdP here; a local user
    carries the primary org. Recorded on every action so the audit trail shows
    not just who acted, but which organization vouched for them.
    """
    return current_token_info.get().get("home_org") or "primary"


def actor_description(requester_name: str | None = None) -> str:
    """Audit string for who performed an action, and on whose authority.

    A user-delegated call names the human and their home organization, with the
    agent recorded as the actor that carried the authority. An agent-only call
    names the agent alone — it cannot claim a person's authority.
    """
    agent = calling_agent_sub() or "unknown-agent"
    if is_user_delegated():
        return f"{current_full_name()} [{current_home_org()}] via IT Agent {agent}"
    if requester_name:
        return f"IT Agent {agent} (requested by {requester_name})"
    return f"IT Agent {agent}"
