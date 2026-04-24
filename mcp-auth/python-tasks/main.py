"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pydantic import AnyHttpUrl

load_dotenv()

import jwt as pyjwt
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from jwt_validator import JWTValidator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TASK_TEMPLATES = [
    {"id": "1", "title": "Weekly Report", "description": "Prepare and submit the weekly status report"},
    {"id": "2", "title": "Code Review", "description": "Review pending pull requests and provide feedback"},
    {"id": "3", "title": "Team Standup Notes", "description": "Document key points from the daily standup"},
    {"id": "4", "title": "Bug Triage", "description": "Triage and prioritize incoming bug reports"},
    {"id": "5", "title": "Sprint Retrospective", "description": "Prepare notes for the sprint retrospective meeting"},
]


# Sub extraction approach: Option (A) from spec §5.5.
# The token has already been validated by JWTTokenVerifier upstream.
# We re-decode with verify_signature=False to extract the `sub` claim.
def get_user_id(token: AccessToken) -> str:
    """Extract the user's subject identifier from a validated access token."""
    payload = pyjwt.decode(token.token, options={"verify_signature": False})
    sub = payload.get("sub")
    if not sub:
        raise PermissionError("Token does not contain a 'sub' claim. An OBO token is required.")
    return sub


def require_scopes(*needed: str) -> AccessToken:
    """Enforce per-tool scopes. Returns the access token if all scopes are present."""
    token = get_access_token()
    if token is None:
        raise PermissionError("No access token in request context.")
    have = set(token.scopes or [])
    missing = [s for s in needed if s not in have]
    if missing:
        raise PermissionError(
            f"insufficient_scope: missing {missing}. "
            "Step up via CIBA with these scopes."
        )
    return token


# In-memory task store keyed by user id (sub claim)
_task_store: dict[str, list[dict]] = {}


class JWTTokenVerifier(TokenVerifier):
    """JWT token verifier using Asgardeo JWKS."""

    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=True
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

            logger.info("[JWT VALID] " + ", ".join(
                [f"sub={subject}", f"aut={aut}", f"scopes={scopes}"] +
                ([f"act={act}"] if act else [])
            ))

            return AccessToken(
                token=token,
                client_id=audience if isinstance(audience, str) else self.jwt_validator.audience,
                scopes=scopes,
                expires_at=str(expires_at) if expires_at else None
            )
        except ValueError as e:
            logger.warning(f"Token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return None


AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")
JWKS_URL = os.getenv("JWKS_URL")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8100"))

if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError("Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL")

mcp = FastMCP(
    "Tasks Tool",
    port=MCP_SERVER_PORT,
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH_ISSUER),
        resource_server_url=AnyHttpUrl(f"http://localhost:{MCP_SERVER_PORT}"),
    ),
)


@mcp.tool()
async def list_task_templates() -> list[dict]:
    """List available task templates. Returns a static list of suggested task templates."""
    require_scopes("tasks:templates_read")
    return TASK_TEMPLATES


@mcp.tool()
async def list_my_tasks() -> list[dict]:
    """List the caller's personal tasks."""
    token = require_scopes("tasks:read")
    user_id = get_user_id(token)
    return _task_store.get(user_id, [])


@mcp.tool()
async def create_my_task(title: str, due: str | None = None) -> dict:
    """Create a new task for the caller."""
    token = require_scopes("tasks:write")
    user_id = get_user_id(token)

    if user_id not in _task_store:
        _task_store[user_id] = []

    task = {
        "id": str(len(_task_store[user_id]) + 1),
        "title": title,
        "due": due,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    _task_store[user_id].append(task)
    return task


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
