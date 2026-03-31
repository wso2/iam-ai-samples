"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR & Leave Management MCP Server (v2)

  A secured MCP server with 9 HR tools, scope-based access control,
  and dynamic user registration from JWT claims.

  No internal employee IDs — all user data is keyed by JWT `sub` claim.
  Any Asgardeo user with the right permissions can use this immediately.

  MCP Scopes (for agent/OBO access):
    hr_basic_mcp   - Company holidays, leave policy
    hr_self_mcp    - Own leave balance, own leave requests, apply for leave
    hr_read_mcp    - All leave requests, leave request details
    hr_approve_mcp - Approve/reject leave requests

  REST Scopes (for browser dashboard):
    hr_self_rest   - Own leave requests
    hr_read_rest   - All leave requests
"""

import os
import contextvars
from dotenv import load_dotenv
from pydantic import AnyHttpUrl

load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from jwt_validator import JWTValidator, TokenError
import hr_data
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Context variables for current request ──────────────────────────────────

current_scopes: contextvars.ContextVar[list] = contextvars.ContextVar(
    "current_scopes", default=[]
)
current_token_info: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "current_token_info", default={}
)
# User identity from JWT — sub (Asgardeo UUID) and name (display name)
current_user_sub: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_sub", default=None
)
current_user_first_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_first_name", default=""
)
current_user_last_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_last_name", default=""
)


def require_scope(scope: str) -> dict | None:
    """Check if the current request has the required scope.
    Returns an error dict if missing, None if OK."""
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
    """Check that we have a resolved user sub from the JWT.
    Returns an error dict if not available, None if OK."""
    sub = current_user_sub.get()
    if not sub:
        return {
            "error": "unknown_user",
            "message": "Your identity could not be determined from the token.",
        }
    return None


def _ensure_current_user():
    """Auto-register the current user from JWT claims."""
    sub = current_user_sub.get()
    first_name = current_user_first_name.get() or "Unknown"
    last_name = current_user_last_name.get() or ""
    if sub:
        hr_data.ensure_user(sub, first_name, last_name)


def _current_full_name() -> str:
    """Get the current user's full name from context variables."""
    first = current_user_first_name.get() or ""
    last = current_user_last_name.get() or ""
    return f"{first} {last}".strip() or "Unknown"


def get_actor_description() -> str:
    """Build an actor description for audit logging."""
    info = current_token_info.get()
    act = info.get("act")
    name = _current_full_name()
    if act:
        return f"AI Agent (on behalf of {name})"
    return f"AI Agent ({name})"


# ─── JWT Token Verifier ─────────────────────────────────────────────────────

class JWTTokenVerifier(TokenVerifier):
    """JWT token verifier that extracts scopes and user identity
    from token claims. No SCIM2 — identity comes directly from JWT."""

    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=SSL_VERIFY,
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
                # Fallback: try full name claim and split
                full = payload.get("name") or payload.get("preferred_username") or payload.get("username") or ""
                if full:
                    parts = full.split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""

            if not first_name:
                # Look up from previously registered data
                existing = hr_data.users.get(subject)
                if existing:
                    first_name = existing.get("first_name", "")
                    last_name = existing.get("last_name", "")
                else:
                    first_name = subject  # UUID as last resort

            full_name = f"{first_name} {last_name}".strip()

            # Set context variables
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

            # Log token claims for debugging
            logger.info("=" * 60)
            logger.info("[JWT TOKEN CLAIMS]")
            logger.info(f"  sub (subject)   : {subject}")
            logger.info(f"  name            : {full_name}")
            logger.info(f"  aud (audience)  : {audience}")
            logger.info(f"  aut (auth type) : {aut}")
            if act:
                logger.info(f"  act (actor)     : {act}")
            logger.info(f"  scope           : {payload.get('scope', 'N/A')}")
            logger.info(f"  scopes (parsed) : {scopes}")
            logger.info(f"  exp (expires)   : {expires_at}")
            logger.info("=" * 60)

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


# ─── Server Configuration ────────────────────────────────────────────────────

AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")          # MCP Client app client_id
SPA_CLIENT_ID = os.getenv("SPA_CLIENT_ID")  # SPA app client_id
JWKS_URL = os.getenv("JWKS_URL")
SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true"

if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError("Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL")

mcp = FastMCP(
    "HR & Leave Management",
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH_ISSUER),
        resource_server_url=AnyHttpUrl("http://localhost:8000"),
    ),
)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


# ─── Tools: hr_basic_mcp scope (Pattern 2 — Agent token) ────────────────────

@mcp.tool()
async def get_company_holidays() -> dict:
    """Get the company holiday calendar for the year.
    Returns a list of holidays with dates and names."""
    scope_error = require_scope("hr_basic_mcp")
    if scope_error:
        return scope_error
    holidays = await hr_data.get_holidays()
    return {"holidays": holidays}


@mcp.tool()
async def get_leave_policy() -> dict:
    """Get the company leave policy — all leave types with their rules
    (max days per year, approval requirements, minimum notice period)."""
    scope_error = require_scope("hr_basic_mcp")
    if scope_error:
        return scope_error
    policy = await hr_data.get_leave_policy()
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
    return await hr_data.get_my_leave_balance(sub, first_name, last_name)


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
    requests = await hr_data.get_my_leave_requests(sub, first_name, last_name)
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
    return await hr_data.apply_leave(sub, first_name, last_name, type, start_date, end_date, reason)


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

    requests = await hr_data.get_all_leave_requests(
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

    result = await hr_data.get_leave_request_details(request_id)
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
    reviewer_name = _current_full_name()
    _ensure_current_user()  # ensure reviewer is registered

    result = await hr_data.approve_leave_request(request_id, reviewer_sub, reviewer_name)

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
    reviewer_name = _current_full_name()
    _ensure_current_user()  # ensure reviewer is registered

    result = await hr_data.reject_leave_request(request_id, reason, reviewer_sub, reviewer_name)

    if result.get("success"):
        actor = get_actor_description()
        logger.info(f"[AUDIT] Leave {request_id} rejected by {actor} — Reason: {reason}")
    return result


# ─── REST API for Dashboard (ASGI middleware) ────────────────────────────────

from starlette.responses import JSONResponse as StarletteJSONResponse, Response as StarletteResponse
import uvicorn


class DashboardMiddleware:
    """ASGI middleware that intercepts /api/leaves for the dashboard.

    Scope-based response:
      - hr_self_rest: returns own leaves (matched by JWT sub)
      - hr_read_rest: returns all leaves with optional filters

    No internal IDs in responses — uses employee names only.
    """

    def __init__(self, app):
        self.app = app
        audiences = [CLIENT_ID]
        if SPA_CLIENT_ID:
            audiences.append(SPA_CLIENT_ID)
        self.jwt_validator = JWTValidator(
            jwks_url=JWKS_URL,
            issuer=AUTH_ISSUER,
            audience=audiences,
            ssl_verify=SSL_VERIFY,
        )

    def _get_origin(self, headers):
        for h_name, h_value in headers:
            if h_name == b"origin":
                return h_value.decode("utf-8")
        return ""

    def _cors_headers(self, origin: str) -> dict:
        if origin in ALLOWED_ORIGINS:
            return {
                "access-control-allow-origin": origin,
                "access-control-allow-headers": "authorization, content-type",
                "access-control-allow-methods": "GET, POST, OPTIONS",
            }
        return {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        headers = scope.get("headers", [])
        origin = self._get_origin(headers)

        # Handle CORS preflight
        if path in ("/api/leaves", "/reset") and scope["method"].upper() == "OPTIONS":
            cors = self._cors_headers(origin)
            response = StarletteResponse(status_code=204, headers=cors)
            await response(scope, receive, send)
            return

        if path == "/api/leaves":
            await self._handle_leaves(scope, receive, send, headers, origin)
            return

        await self.app(scope, receive, send)

    async def _handle_leaves(self, scope, receive, send, headers, origin):
        cors = self._cors_headers(origin)

        # Extract Authorization header
        auth_header = ""
        for h_name, h_value in headers:
            if h_name == b"authorization":
                auth_header = h_value.decode("utf-8")
                break

        if not auth_header.startswith("Bearer "):
            response = StarletteJSONResponse(
                {"error": "missing_token", "message": "Missing or invalid Authorization header"},
                status_code=401, headers=cors,
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        try:
            payload = await self.jwt_validator.validate_token(token)
        except TokenError as e:
            response = StarletteJSONResponse(
                {"error": e.error_type, "message": e.message},
                status_code=401, headers=cors,
            )
            await response(scope, receive, send)
            return

        scopes = payload.get("scope", "").split() if payload.get("scope") else []
        sub = payload.get("sub")

        # Extract first/last name from SPA token
        first_name = payload.get("given_name") or ""
        last_name = payload.get("last_name") or ""
        if not first_name and not last_name:
            full = payload.get("name") or payload.get("preferred_username") or ""
            if full:
                parts = full.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

        # Register/update user on any authenticated request
        if sub and first_name:
            hr_data.ensure_user(sub, first_name, last_name)

        if "hr_read_rest" in scopes:
            # HR Admin: all leave requests with optional filters
            query_string = scope.get("query_string", b"").decode("utf-8")
            params = dict(p.split("=", 1) for p in query_string.split("&") if "=" in p) if query_string else {}
            leaves = await hr_data.get_leaves_for_dashboard(
                status=params.get("status"),
                employee_name=params.get("employee_name"),
            )
            response = StarletteJSONResponse({"leaves": leaves}, headers=cors)
            await response(scope, receive, send)

        elif "hr_self_rest" in scopes and sub:
            # Employee: own leave requests only
            leaves = await hr_data.get_leaves_for_dashboard(user_sub=sub)
            response = StarletteJSONResponse({"leaves": leaves}, headers=cors)
            await response(scope, receive, send)

        else:
            response = StarletteJSONResponse(
                {"error": "insufficient_scope", "message": "Requires hr_self_rest or hr_read_rest scope."},
                status_code=403, headers=cors,
            )
            await response(scope, receive, send)


# ─── Reset Endpoint ──────────────────────────────────────────────────────────

from starlette.routing import Route
from starlette.requests import Request as StarletteRequest


async def reset_handler(request: StarletteRequest):
    """Reset all HR in-memory data. Global data re-seeded, user data cleared."""
    hr_data.reset_data()
    return StarletteJSONResponse({"success": True, "message": "HR data reset to default state."})


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from contextlib import asynccontextmanager

    mcp_starlette = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_starlette.router.lifespan_context(app):
            yield

    reset_route = Route("/reset", reset_handler, methods=["POST"])
    app = DashboardMiddleware(
        Starlette(routes=[reset_route, Mount("/", app=mcp_starlette)], lifespan=lifespan)
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)
