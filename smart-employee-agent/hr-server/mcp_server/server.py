"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR MCP Server

  FastMCP application exposing 9 HR tools with scope-based access control
  and dynamic user registration from JWT claims. The token verifier
  populates per-request context vars (auth.context) that the tool
  implementations read to attribute actions to the authenticated user.

  MCP Scopes:
    hr_basic_mcp   - Company holidays, leave policy
    hr_self_mcp    - Own leave balance, own leave requests, apply for leave
    hr_read_mcp    - All leave requests, leave request details
    hr_approve_mcp - Approve/reject leave requests
"""

import logging

from pydantic import AnyHttpUrl

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import config
from auth.jwt_validator import JWTValidator, TokenError
from auth.context import (
    current_scopes,
    current_token_info,
    current_user_sub,
    current_user_first_name,
    current_user_last_name,
)
from auth.scopes import (
    require_scope,
    require_user,
    ensure_current_user,
    current_full_name,
    get_actor_description,
)
from service import hr_service, store

logger = logging.getLogger(__name__)


# ─── JWT Token Verifier ─────────────────────────────────────────────────────

class JWTTokenVerifier(TokenVerifier):
    """Verifies JWTs and propagates identity/scopes into per-request context vars."""

    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=config.SSL_VERIFY,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = await self.jwt_validator.validate_token(token)

            expires_at = payload.get("exp")
            scopes = payload.get("scope", "").split() if payload.get("scope") else []
            subject = payload.get("sub")
            audience = payload.get("aud")
            aut = payload.get("aut")
            act = payload.get("act")

            # Extract user name from token claims — prefer given_name + last_name
            first_name = payload.get("given_name") or ""
            last_name = payload.get("last_name") or ""

            if not first_name and not last_name:
                full = (
                    payload.get("name")
                    or payload.get("preferred_username")
                    or payload.get("username")
                    or ""
                )
                if full:
                    parts = full.split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""

            if not first_name:
                # Look up from previously registered data
                existing = store.users.get(subject)
                if existing:
                    first_name = existing.get("first_name", "")
                    last_name = existing.get("last_name", "")
                else:
                    first_name = subject  # UUID as last resort

            full_name = f"{first_name} {last_name}".strip()

            current_scopes.set(scopes)
            current_token_info.set({
                "sub": subject,
                "aut": aut,
                "act": act,
                "scopes": scopes,
            })
            current_user_sub.set(subject)
            current_user_first_name.set(first_name)
            current_user_last_name.set(last_name)

            # ── Token access log (visible at INFO for demo clarity) ──
            logger.info("┌─── MCP Request Authenticated ───────────────────────")
            logger.info("│ Subject (sub) : %s", subject)
            logger.info("│ Name          : %s", full_name)
            logger.info("│ Scopes        : %s", ", ".join(scopes) if scopes else "(none)")
            if act:
                actor_sub = act.get("sub") if isinstance(act, dict) else str(act)
                logger.info("│ ⚡ OBO Flow — Agent acting on behalf of user")
                logger.info("│   User (sub)    : %s", subject)
                logger.info("│   Agent (act.sub): %s", actor_sub)
            else:
                logger.info("│ Token type    : Direct (agent or user token)")
            logger.info("└────────────────────────────────────────────────────")

            return AccessToken(
                token=token,
                client_id=audience if isinstance(audience, str) else self.jwt_validator.audience,
                scopes=scopes,
                expires_at=str(expires_at) if expires_at else None,
            )
        except TokenError as e:
            logger.warning(f"Token validation failed ({e.error_type}): {e.message}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return None


# ─── FastMCP Application ────────────────────────────────────────────────────

mcp = FastMCP(
    "HR & Leave Management",
    token_verifier=JWTTokenVerifier(config.JWKS_URL, config.AUTH_ISSUER, config.CLIENT_ID),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(config.AUTH_ISSUER),
        resource_server_url=AnyHttpUrl(f"http://localhost:{config.PORT}"),
    ),
    # DNS-rebinding protection off: this server is always behind a trusted
    # caller (the agent) and validates a JWT on every request, so the
    # browser-localhost threat the protection targets does not apply here.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ─── Tools: hr_basic_mcp scope (Pattern 2 — Agent token) ────────────────────

@mcp.tool()
async def get_company_holidays() -> dict:
    """Get the company holiday calendar for the year.
    Returns a list of holidays with dates and names."""
    scope_error = require_scope("hr_basic_mcp")
    if scope_error:
        return scope_error
    holidays = await hr_service.get_holidays()
    return {"holidays": holidays}


@mcp.tool()
async def get_leave_policy() -> dict:
    """Get the company leave policy — all leave types with their rules
    (max days per year, approval requirements, minimum notice period)."""
    scope_error = require_scope("hr_basic_mcp")
    if scope_error:
        return scope_error
    policy = await hr_service.get_leave_policy()
    return {"leave_types": policy}


# ─── Tools: hr_self_mcp scope (Pattern 3 — OBO token) ───────────────────────

@mcp.tool()
async def get_my_leave_balance() -> dict:
    """Get the authenticated user's own leave balance
    (annual, sick, and personal leave remaining days).
    New users automatically receive default balances."""
    scope_error = require_scope("hr_self_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    sub = current_user_sub.get()
    first_name = current_user_first_name.get() or "Unknown"
    last_name = current_user_last_name.get() or ""
    return await hr_service.get_my_leave_balance(sub, first_name, last_name)


@mcp.tool()
async def get_my_leave_requests() -> dict:
    """Get all leave requests submitted by the authenticated user."""
    scope_error = require_scope("hr_self_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    sub = current_user_sub.get()
    first_name = current_user_first_name.get() or "Unknown"
    last_name = current_user_last_name.get() or ""
    requests = await hr_service.get_my_leave_requests(sub, first_name, last_name)
    return {"leave_requests": requests}


@mcp.tool()
async def apply_leave(
    type: str, start_date: str, end_date: str, reason: str
) -> dict:
    """Submit a new leave request for the authenticated user.

    Args:
        type: Leave type — must be one of 'Annual Leave', 'Sick Leave', or 'Personal Leave'.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        reason: Reason for the leave request.
    """
    scope_error = require_scope("hr_self_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    sub = current_user_sub.get()
    first_name = current_user_first_name.get() or "Unknown"
    last_name = current_user_last_name.get() or ""
    return await hr_service.apply_leave(sub, first_name, last_name, type, start_date, end_date, reason)


# ─── Tools: hr_read_mcp scope (Pattern 3 — OBO token, HR Admin) ─────────────

@mcp.tool()
async def get_all_leave_requests(status: str = "", employee_name: str = "") -> dict:
    """List all leave requests across the organization.
    Use the optional status filter to show only Pending, Approved, or Rejected requests.
    Use the optional employee_name filter to search by employee name (case-insensitive partial match).
    Returns each request's reference ID, employee name, type, dates, days, and status.

    Args:
        status: Optional filter — 'Pending', 'Approved', or 'Rejected'.
        employee_name: Optional filter — search by employee name (e.g., 'Sarah' or 'Johnson').
    """
    scope_error = require_scope("hr_read_mcp")
    if scope_error:
        return scope_error

    requests = await hr_service.get_all_leave_requests(
        status=status or None,
        employee_name=employee_name or None,
    )
    return {"leave_requests": requests}


@mcp.tool()
async def get_leave_request_details(request_id: str) -> dict:
    """Get detailed information about a specific leave request, including
    the employee's name, leave type, dates, reason, status, and their
    current leave balance.

    Args:
        request_id: The leave request reference ID (e.g., 'LR001').
    """
    scope_error = require_scope("hr_read_mcp")
    if scope_error:
        return scope_error

    result = await hr_service.get_leave_request_details(request_id)
    if not result:
        return {"error": "not_found", "message": f"Leave request '{request_id}' not found."}
    return result


# ─── Tools: hr_approve_mcp scope (Pattern 3 — OBO token, HR Admin) ──────────

@mcp.tool()
async def approve_leave_request(request_id: str) -> dict:
    """Approve a pending leave request. The employee's leave balance will be
    deducted accordingly. Requires HR Admin authorization.

    To find the request_id, first use get_all_leave_requests to list pending requests.

    Args:
        request_id: The leave request reference ID to approve (e.g., 'LR001').
    """
    scope_error = require_scope("hr_approve_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    reviewer_sub = current_user_sub.get()
    reviewer_name = current_full_name()
    ensure_current_user()

    result = await hr_service.approve_leave_request(request_id, reviewer_sub, reviewer_name)

    if result.get("success"):
        actor = get_actor_description()
        logger.info(f"[AUDIT] Leave {request_id} approved by {actor}")
    return result


@mcp.tool()
async def reject_leave_request(request_id: str, reason: str) -> dict:
    """Reject a pending leave request with a reason. Requires HR Admin authorization.

    To find the request_id, first use get_all_leave_requests to list pending requests.

    Args:
        request_id: The leave request reference ID to reject (e.g., 'LR001').
        reason: The reason for rejecting the leave request.
    """
    scope_error = require_scope("hr_approve_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    reviewer_sub = current_user_sub.get()
    reviewer_name = current_full_name()
    ensure_current_user()

    result = await hr_service.reject_leave_request(request_id, reason, reviewer_sub, reviewer_name)

    if result.get("success"):
        # Audit log: identify the action and request, but do not echo free-form reason text.
        logger.info("[AUDIT] Leave %s rejected (reviewer_sub=%s)", request_id, reviewer_sub)
        if logger.isEnabledFor(logging.DEBUG):
            actor = get_actor_description()
            logger.debug("[AUDIT-DETAIL] Leave %s rejected by %s — reason: %s",
                         request_id, actor, reason)
    return result


def build_app():
    """Return the streamable HTTP ASGI app for the MCP server."""
    return mcp.streamable_http_app()
