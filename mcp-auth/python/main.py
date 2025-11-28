"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you’ve
  entered into with WSO2 governing the purchase of this software and any
"""

import os
from dotenv import load_dotenv
from pydantic import AnyHttpUrl

# Load environment variables from .env file
load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from jwt_validator import JWTValidator
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JWTTokenVerifier(TokenVerifier):
    """JWT token verifier using Asgardeo JWKS."""

    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=True  # Set to False for development if needed
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # Validate the JWT token
            payload = await self.jwt_validator.validate_token(token)

            # Extract information from the validated token
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

# Validate that required environment variables are set
if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError("Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL")

# Create FastMCP instance as a Resource Server
mcp = FastMCP(
    "Addition Tool",
    # Token verifier for authentication
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    # Auth settings for RFC 9728 Protected Resource Metadata
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH_ISSUER),
        resource_server_url=AnyHttpUrl("http://localhost:8000"),  # Authorization Server URL # This server's URL
        # required_scopes=["user"]
    ),
)


@mcp.tool()
async def add(a: float, b: float) -> dict[str, float]:
    """Add two numbers and return the result."""
    return {
        "a": a,
        "b": b,
        "result": a + b,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
