from pydantic import AnyHttpUrl

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

            logger.info(f"Token validated successfully for subject: {subject}")

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

AUTH_ISSUER = "https://api.asgardeo.io/t/<tenant>/oauth2/token"
CLIENT_ID = "<CLIENT_ID>"  # Replace with your Asgardeo OAuth2 client ID
JWKS_URL = "https://api.asgardeo.io/t/<tenant>/oauth2/jwks"



# Create FastMCP instance as a Resource Server
mcp = FastMCP(
    "Weather Service",
    # Token verifier for authentication
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    # Auth settings for RFC 9728 Protected Resource Metadata
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://api.asgardeo.io/t/<tenant>/oauth2/token"),
        resource_server_url=AnyHttpUrl("http://localhost:8000"),  # Resource Server URL (this server)
        # required_scopes=["user"]
    ),
)


@mcp.tool()
async def get_weather(city: str = "London") -> dict[str, str]:
    """Get weather data for a city"""
    return {
        "city": city,
        "temperature": "22",
        "condition": "Partly cloudy",
        "humidity": "65%",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
