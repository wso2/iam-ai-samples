"""
JWT Token Validation Module

This module handles JWT token validation using JWKS (JSON Web Key Set).
It provides a clean interface for validating JWT tokens with proper error handling.

### JWT Validation Settings

The JWTTokenVerifier supports the following features:
- **Algorithm**: RS256 (configurable in JWTValidator)
- **Expiration**: Verified automatically
- **Audience**: Verified against CLIENT_ID
- **Issuer**: Verified against AUTH_ISSUER
- **Scopes**: Extracted and included in AccessToken
"""

import jwt
from jwt.algorithms import RSAAlgorithm
import httpx
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class JWTValidator:
    """
    A class to handle JWT token validation using JWKS.
    Fetches and caches JWKS keys for performance.
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str, ssl_verify: bool = True):
        """
        Initialize the JWT validator.
        
        Args:
            jwks_url: The URL to fetch JWKS from
            issuer: Expected token issuer
            audience: Expected token audience
            ssl_verify: Whether to verify SSL certificates (False for dev/testing)
        """
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.ssl_verify = ssl_verify
        self._jwks_cache: Optional[Dict[str, Any]] = None

    async def _fetch_jwks(self) -> Dict[str, Any]:
        """Fetch JWKS from the authorization server."""
        try:
            async with httpx.AsyncClient(verify=self.ssl_verify) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch JWKS from {self.jwks_url}: {e}")
            raise

    async def _get_jwks(self) -> Dict[str, Any]:
        """Get JWKS, using cache if available."""
        if self._jwks_cache is None:
            self._jwks_cache = await self._fetch_jwks()
        return self._jwks_cache

    def _get_signing_key(self, token_header: Dict[str, Any], jwks: Dict[str, Any]) -> str:
        """Extract the signing key from JWKS based on token header."""
        kid = token_header.get('kid')
        if not kid:
            raise ValueError("Token header missing 'kid' field")

        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                # Convert JWK to PEM format for PyJWT
                return RSAAlgorithm.from_jwk(key)

        raise ValueError(f"Unable to find matching key for kid: {kid}")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a JWT token and return the decoded payload.

        Args:
            token: The JWT token to validate
            
        Returns:
            Dict containing the decoded token payload with additional metadata

        Raises:
            ValueError: If token validation fails
        """
        try:
            # Decode header without verification to get the key ID
            unverified_header = jwt.get_unverified_header(token)

            # Get JWKS
            jwks = await self._get_jwks()

            # Get the signing key
            signing_key = self._get_signing_key(unverified_header, jwks)

            # Decode and verify the token
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=['RS256'],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True
                }
            )

            # Add metadata to the payload
            payload['_validated_by'] = 'JWTValidator'
            payload['_issuer'] = self.issuer
            payload['_audience'] = self.audience

            return payload

        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidAudienceError:
            raise ValueError("Invalid audience")
        except jwt.InvalidIssuerError:
            raise ValueError("Invalid issuer")
        except jwt.InvalidSignatureError:
            raise ValueError("Invalid token signature")
        except jwt.DecodeError:
            raise ValueError("Invalid token format")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")


def create_jwt_validator(jwks_url: str, issuer: str, audience: str, ssl_verify: bool = True) -> JWTValidator:
    """
    Factory function to create a JWT validator instance.
    
    Args:
        jwks_url: The URL to fetch JWKS from
        issuer: Expected token issuer
        audience: Expected token audience
        ssl_verify: Whether to verify SSL certificates
        
    Returns:
        JWTValidator: Configured validator instance
    """
    return JWTValidator(jwks_url, issuer, audience, ssl_verify)
