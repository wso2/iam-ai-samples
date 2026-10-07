"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT MCP Server

  Exposes IT service-desk tools over MCP, guarded by scope checks.

  Calls arrive on one of two tokens, and the tools treat them identically:

    Pattern 4  the IT Agent's own agent token, when the HR Agent delegates.
    Pattern 7  an OBO token, when an IT admin uses the service desk directly.
               `sub` is the human, `act.sub` is the IT Agent, and the granted
               scopes are the human's. A federated partner-org admin arrives
               this way, and their home organization is recorded for audit.

  The scope guard does not branch on which one it is. That is deliberate: the
  server authorizes the presented token, not the story around it.
"""

import logging

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

import config
from auth.context import (
    current_scopes,
    current_token_info,
    current_user_sub,
    current_user_first_name,
    current_user_last_name,
)
from auth.jwt_validator import JWTValidator, TokenError
from auth.token_debug import dump_claims
from auth.scopes import (
    require_scope,
    require_user,
    actor_description,
    current_full_name,
    current_home_org,
    is_user_delegated,
)
from service import it_service

logger = logging.getLogger(__name__)


# Claims that can carry "which identity domain did this human come from".
# Asgardeo names this differently depending on how the user was authenticated
# (federated connection vs local vs organization), so we check in order rather
# than pin one. Verify against a real token from your tenant before relying on
# a specific claim in production.
HOME_ORG_CLAIMS = ("idp", "identity_provider", "org_name", "org_handle", "user_org")


def _home_org(payload: dict) -> str:
    """Best-effort home organization / originating IdP for a delegated user."""
    for claim in HOME_ORG_CLAIMS:
        value = payload.get(claim)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "primary"


# ─── JWT Token Verifier ─────────────────────────────────────────────────────

class JWTTokenVerifier(TokenVerifier):
    """Verifies JWTs and propagates the caller's scopes into request context."""

    def __init__(self, jwks_url: str, issuer: str, client_id):
        # `client_id` may be a list: agent/OBO tokens are minted for the MCP
        # client app, exchanged tokens for the exchange app. PyJWT accepts any
        # match when given a list.
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

            home_org = _home_org(payload)
            current_scopes.set(scopes)
            current_token_info.set({
                "sub": subject,
                "aut": aut,
                "act": act,
                "scopes": scopes,
                "home_org": home_org,
            })

            # An OBO token carries the human; an agent token does not. Only set
            # the user context vars in the delegated case, so require_user()
            # cannot be satisfied by an agent acting alone.
            if act:
                current_user_sub.set(subject)
                current_user_first_name.set(payload.get("given_name") or "")
                current_user_last_name.set(
                    payload.get("family_name") or payload.get("last_name") or ""
                )
            else:
                current_user_sub.set(None)
                current_user_first_name.set("")
                current_user_last_name.set("")

            dump_claims(
                "[IT-MCP] OBO Token" if act else "[IT-MCP] Agent Token",
                payload, token,
            )

            scope_str = ", ".join(scopes) if scopes else "(none)"
            if act:
                actor_sub = act.get("sub") if isinstance(act, dict) else str(act)
                logger.info(
                    "[IT-MCP >> OBO Token] user(sub)=%s | home_org=%s | "
                    "agent(act.sub)=%s | scopes=%s",
                    subject, home_org, actor_sub, scope_str,
                )
            else:
                logger.info(
                    "[IT-MCP >> Agent Token] sub=%s | aut=%s | scopes=%s",
                    subject, aut or "(none)", scope_str,
                )

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
    "IT Service Desk",
    token_verifier=JWTTokenVerifier(
        config.JWKS_URL, config.AUTH_ISSUER, config.ACCEPTED_AUDIENCES
    ),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(config.AUTH_ISSUER),
        resource_server_url=AnyHttpUrl(f"http://localhost:{config.PORT}"),
    ),
    # Same rationale as the HR server: always behind a trusted caller that
    # presents a JWT validated on every request.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ─── Tools: it_basic_mcp scope (read-only IT information) ───────────────────

@mcp.tool()
async def get_it_policies(topic: str = "") -> dict:
    """Get IT policies — VPN access, password rules, software requests, device
    replacement. Pass a topic substring to filter, or omit it for all policies."""
    scope_error = require_scope("it_basic_mcp")
    if scope_error:
        return scope_error
    policies = await it_service.get_policies(topic)
    return {"policies": policies}


@mcp.tool()
async def get_service_status() -> dict:
    """Get the current operational status of internal IT services
    (email, VPN, wiki, CI pipelines)."""
    scope_error = require_scope("it_basic_mcp")
    if scope_error:
        return scope_error
    return {"services": await it_service.get_service_status()}


@mcp.tool()
async def get_software_catalog() -> dict:
    """List licensed software available to employees, and whether each item is
    auto-approved or needs manager plus IT security approval."""
    scope_error = require_scope("it_basic_mcp")
    if scope_error:
        return scope_error
    return {"software": await it_service.get_software_catalog()}


# ─── Tools: it_ticket_mcp scope (service-desk actions) ──────────────────────

@mcp.tool()
async def create_support_ticket(
    subject: str,
    category: str = "General",
    requested_for: str = "",
) -> dict:
    """File an IT support ticket.

    `requested_for` is the name of the employee the ticket is for. It is
    recorded for audit and confers no authority — the caller is authorized by
    its own agent token, not by the named employee."""
    scope_error = require_scope("it_ticket_mcp")
    if scope_error:
        return scope_error
    if not subject.strip():
        return {"error": "invalid_request", "message": "A ticket subject is required."}

    # When a human is on the token, the ticket belongs to them and the name
    # they typed is irrelevant to ownership. When only an agent is on the token
    # (Pattern 4), there is no verified owner — just the forwarded name.
    delegated = is_user_delegated()
    ticket = await it_service.create_ticket(
        subject=subject.strip(),
        category=category,
        requested_for=(current_full_name() if delegated else requested_for),
        actor=actor_description(requested_for),
        owner_sub=(current_user_sub.get() if delegated else None),
        home_org=current_home_org(),
    )
    return {"ticket": ticket, "message": f"Ticket {ticket['ticket_id']} created."}


@mcp.tool()
async def get_ticket_status(ticket_id: str) -> dict:
    """Get the status and details of a support ticket by its reference
    (for example IT001)."""
    scope_error = require_scope("it_ticket_mcp")
    if scope_error:
        return scope_error
    ticket = await it_service.get_ticket(ticket_id)
    if not ticket:
        return {"error": "not_found", "message": f"No ticket found with id '{ticket_id}'."}
    return {"ticket": ticket}


@mcp.tool()
async def list_support_tickets(requested_for: str = "") -> dict:
    """List IT support tickets, optionally filtered to those raised for a
    given employee name. Service-desk admins see the whole queue; everyone
    else sees only the tickets raised for them."""
    scope_error = require_scope("it_ticket_mcp")
    if scope_error:
        return scope_error

    # Whole-queue visibility rides on the same scope that permits closing a
    # ticket: if you are trusted to resolve other people's requests, you are
    # trusted to read them. An ordinary user is pinned to their own subject,
    # so no name they pass can widen what comes back.
    if is_user_delegated() and require_scope("it_resolve_mcp") is not None:
        own = await it_service.list_tickets(owner_sub=current_user_sub.get())
        logger.info(
            "[IT-MCP] queue scoped to own tickets for user(sub)=%s | %d ticket(s)",
            current_user_sub.get(), len(own),
        )
        return {"tickets": own, "scope_note": "Showing only tickets raised for you."}

    return {"tickets": await it_service.list_tickets(requested_for)}


# ─── Tools: it_resolve_mcp scope (service-desk administration) ──────────────

@mcp.tool()
async def resolve_support_ticket(ticket_id: str, resolution: str) -> dict:
    """Close an IT support ticket with a resolution note. Requires IT service
    desk administrator permission.

    Args:
        ticket_id: The ticket reference to close (for example 'IT001').
        resolution: What was done to fix it.
    """
    # Two independent gates. The scope says this permission was granted; the
    # user check says a person is actually behind the call. An agent acting
    # alone fails the second even if it somehow held the first — closing
    # someone's request is not something an unattended agent should do.
    scope_error = require_scope("it_resolve_mcp")
    if scope_error:
        return scope_error

    user_error = require_user()
    if user_error:
        return user_error

    result = await it_service.resolve_ticket(
        ticket_id, resolution, actor=actor_description()
    )
    if result.get("success"):
        logger.info(
            "[AUDIT] %s resolved by user(sub)=%s from home_org=%s",
            ticket_id, current_user_sub.get(), current_home_org(),
        )
    return result


def build_app():
    """Return the streamable HTTP ASGI app for the MCP server."""
    return mcp.streamable_http_app()
