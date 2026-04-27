"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR REST API

  Mirrors the MCP tool surface for direct browser/SPA use. The SPA receives
  *_rest scopes from PKCE login and calls these endpoints with its user
  token; the chat path uses *_mcp scopes via OBO. Both paths reuse the
  same business logic in `service.hr_service`.

  Endpoints:
    GET  /api/holidays               (hr_basic_rest)
    GET  /api/leave-policy           (hr_basic_rest)
    GET  /api/leave-balance          (hr_self_rest)
    GET  /api/leaves                 (hr_self_rest | hr_read_rest)
    GET  /api/leaves/{id}            (hr_self_rest for own | hr_read_rest)
    POST /api/leaves                 (hr_self_rest)
    POST /api/leaves/{id}/approve    (hr_approve_rest)
    POST /api/leaves/{id}/reject     (hr_approve_rest)
    POST /reset                      (hr_approve_rest | hr_approve_mcp)
"""

import json
import logging
from typing import Iterable

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

import config
from auth.jwt_validator import JWTValidator, TokenError
from service import hr_service, store

logger = logging.getLogger(__name__)


# ─── JWT validator instance (shared across handlers) ────────────────────────

_audiences = [config.CLIENT_ID]
if config.SPA_CLIENT_ID:
    _audiences.append(config.SPA_CLIENT_ID)

_jwt_validator = JWTValidator(
    jwks_url=config.JWKS_URL,
    issuer=config.AUTH_ISSUER,
    audience=_audiences,
    ssl_verify=config.SSL_VERIFY,
)


# ─── Authentication helpers ────────────────────────────────────────────────

class _AuthContext:
    """Resolved identity + scopes from a validated bearer token."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.sub: str = payload.get("sub") or ""
        self.scopes: list[str] = payload.get("scope", "").split() if payload.get("scope") else []

        first = payload.get("given_name") or ""
        last = payload.get("last_name") or ""
        if not first and not last:
            full = payload.get("name") or payload.get("preferred_username") or ""
            if full:
                parts = full.split(" ", 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""
        self.first_name = first
        self.last_name = last
        self.full_name = f"{first} {last}".strip() or "User"


async def _authenticate(request: Request) -> _AuthContext | JSONResponse:
    """Validate the Authorization header. Returns _AuthContext or an error JSONResponse."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"error": "missing_token", "message": "Missing or invalid Authorization header"},
            status_code=401,
        )
    token = auth_header[7:]
    try:
        payload = await _jwt_validator.validate_token(token)
    except TokenError as e:
        return JSONResponse({"error": e.error_type, "message": e.message}, status_code=401)

    ctx = _AuthContext(payload)
    if ctx.sub and ctx.first_name:
        store.ensure_user(ctx.sub, ctx.first_name, ctx.last_name)

    act = payload.get("act")
    endpoint = request.url.path
    logger.info("┌─── REST Request Authenticated (%s) ──────────────", endpoint)
    logger.info("│ Subject (sub) : %s", ctx.sub)
    logger.info("│ Name          : %s", ctx.full_name)
    logger.info("│ Scopes        : %s", ", ".join(ctx.scopes) if ctx.scopes else "(none)")
    if act:
        actor_sub = act.get("sub") if isinstance(act, dict) else str(act)
        logger.info("│ ⚡ OBO Flow — Agent acting on behalf of user")
        logger.info("│   User (sub)    : %s", ctx.sub)
        logger.info("│   Agent (act.sub): %s", actor_sub)
    else:
        logger.info("│ Token type    : Direct (user token via SPA)")
    logger.info("└────────────────────────────────────────────────────")

    return ctx


def _require_scope(ctx: _AuthContext, *any_of: str) -> JSONResponse | None:
    """Return a 403 response if the caller has none of the listed scopes."""
    if not any(s in ctx.scopes for s in any_of):
        return JSONResponse(
            {
                "error": "insufficient_scope",
                "message": f"This action requires one of: {', '.join(any_of)}",
                "required_scope": list(any_of),
                "available_scopes": ctx.scopes,
            },
            status_code=403,
        )
    return None


# ─── Route handlers ─────────────────────────────────────────────────────────

async def get_holidays(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_basic_rest")
    if err:
        return err
    return JSONResponse({"holidays": await hr_service.get_holidays()})


async def get_leave_policy(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_basic_rest")
    if err:
        return err
    return JSONResponse({"leave_types": await hr_service.get_leave_policy()})


async def get_leave_balance(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_self_rest")
    if err:
        return err
    return JSONResponse(await hr_service.get_my_leave_balance(ctx.sub, ctx.first_name, ctx.last_name))


async def get_leaves(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx

    if "hr_read_rest" in ctx.scopes:
        leaves = await hr_service.get_leaves_for_dashboard(
            status=request.query_params.get("status"),
            employee_name=request.query_params.get("employee_name"),
        )
        return JSONResponse({"leaves": leaves})

    if "hr_self_rest" in ctx.scopes and ctx.sub:
        leaves = await hr_service.get_leaves_for_dashboard(user_sub=ctx.sub)
        return JSONResponse({"leaves": leaves})

    return JSONResponse(
        {"error": "insufficient_scope", "message": "Requires hr_self_rest or hr_read_rest scope."},
        status_code=403,
    )


async def get_leave_details(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx

    request_id = request.path_params["request_id"]
    details = await hr_service.get_leave_request_details(request_id)
    if not details:
        return JSONResponse(
            {"error": "not_found", "message": f"Leave request '{request_id}' not found."},
            status_code=404,
        )

    # HR Admin can see any; employees can only see their own.
    if "hr_read_rest" in ctx.scopes:
        return JSONResponse(details)
    if "hr_self_rest" in ctx.scopes and ctx.sub:
        owner_sub = store.leave_requests.get(request_id, {}).get("user_sub")
        if owner_sub == ctx.sub:
            return JSONResponse(details)
        return JSONResponse(
            {"error": "forbidden", "message": "You can only view your own leave requests."},
            status_code=403,
        )
    return JSONResponse(
        {"error": "insufficient_scope", "message": "Requires hr_self_rest or hr_read_rest scope."},
        status_code=403,
    )


async def create_leave(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_self_rest")
    if err:
        return err

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "invalid_body", "message": "Body must be valid JSON."}, status_code=400,
        )

    leave_type = (body.get("leave_type") or body.get("type") or "").strip()
    start_date = (body.get("start_date") or "").strip()
    end_date = (body.get("end_date") or "").strip()
    reason = (body.get("reason") or "").strip()

    missing = [k for k, v in {
        "leave_type": leave_type, "start_date": start_date, "end_date": end_date, "reason": reason,
    }.items() if not v]
    if missing:
        return JSONResponse(
            {"error": "missing_fields", "message": f"Required fields missing: {', '.join(missing)}"},
            status_code=400,
        )

    result = await hr_service.apply_leave(
        ctx.sub, ctx.first_name, ctx.last_name, leave_type, start_date, end_date, reason,
    )
    status = 201 if result.get("success") else 400
    return JSONResponse(result, status_code=status)


async def approve_leave(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_approve_rest")
    if err:
        return err

    request_id = request.path_params["request_id"]
    result = await hr_service.approve_leave_request(request_id, ctx.sub, ctx.full_name)
    if result.get("success"):
        logger.info("[AUDIT] Leave %s approved (reviewer_sub=%s)", request_id, ctx.sub)
        return JSONResponse(result)
    status = 404 if result.get("error") == "not_found" else 400
    return JSONResponse(result, status_code=status)


async def reject_leave(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_approve_rest")
    if err:
        return err

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "invalid_body", "message": "Body must be valid JSON."}, status_code=400,
        )
    reason = (body.get("reason") or "").strip()
    if not reason:
        return JSONResponse(
            {"error": "missing_fields", "message": "A non-empty 'reason' is required."},
            status_code=400,
        )

    request_id = request.path_params["request_id"]
    result = await hr_service.reject_leave_request(request_id, reason, ctx.sub, ctx.full_name)
    if result.get("success"):
        logger.info("[AUDIT] Leave %s rejected (reviewer_sub=%s)", request_id, ctx.sub)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("[AUDIT-DETAIL] Leave %s rejection reason: %s", request_id, reason)
        return JSONResponse(result)
    status = 404 if result.get("error") == "not_found" else 400
    return JSONResponse(result, status_code=status)


async def reset(request: Request):
    ctx = await _authenticate(request)
    if isinstance(ctx, JSONResponse):
        return ctx
    err = _require_scope(ctx, "hr_approve_rest", "hr_approve_mcp")
    if err:
        return err
    store.reset_data()
    return JSONResponse({"success": True, "message": "HR data reset to default state."})


# ─── CORS middleware ────────────────────────────────────────────────────────

class CORSMiddleware(BaseHTTPMiddleware):
    """Origin-checked CORS for the configured ALLOWED_ORIGINS."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        cors = self._headers_for(origin)

        if request.method == "OPTIONS":
            return Response(status_code=204, headers=cors)

        response = await call_next(request)
        for k, v in cors.items():
            response.headers[k] = v
        return response

    @staticmethod
    def _headers_for(origin: str) -> dict:
        if origin in config.ALLOWED_ORIGINS:
            return {
                "access-control-allow-origin": origin,
                "access-control-allow-headers": "authorization, content-type",
                "access-control-allow-methods": "GET, POST, OPTIONS",
            }
        return {}


# ─── Route table ────────────────────────────────────────────────────────────

def routes() -> Iterable[Route]:
    """REST routes for the HR server. Mounted alongside the MCP app."""
    return [
        Route("/api/holidays",                       get_holidays,       methods=["GET"]),
        Route("/api/leave-policy",                   get_leave_policy,   methods=["GET"]),
        Route("/api/leave-balance",                  get_leave_balance,  methods=["GET"]),
        Route("/api/leaves",                         get_leaves,         methods=["GET"]),
        Route("/api/leaves",                         create_leave,       methods=["POST"]),
        Route("/api/leaves/{request_id}",            get_leave_details,  methods=["GET"]),
        Route("/api/leaves/{request_id}/approve",    approve_leave,      methods=["POST"]),
        Route("/api/leaves/{request_id}/reject",     reject_leave,       methods=["POST"]),
        Route("/reset",                              reset,              methods=["POST"]),
    ]
