"""
 Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any


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
- **JWKS Caching**: TTL-based cache (default: 10 minutes) with automatic refresh
- **Key Rotation**: Automatic retry with JWKS refresh on signature validation failures
"""

import jwt
from jwt.algorithms import RSAAlgorithm
import httpx
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class JWTValidator:
    """
    A class to handle JWT token validation using JWKS.
    Fetches and caches JWKS keys for performance with TTL-based refresh.
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str, ssl_verify: bool = True, cache_ttl_minutes: int = 10):
        """
        Initialize the JWT validator.

        Args:
            jwks_url: The URL to fetch JWKS from
            issuer: Expected token issuer
            audience: Expected token audience
            ssl_verify: Whether to verify SSL certificates (False for dev/testing)
            cache_ttl_minutes: How long to cache JWKS before refreshing (default: 10 minutes)
        """
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.ssl_verify = ssl_verify
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None

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

    async def _get_jwks(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get JWKS, using cache if available and not expired.

        Args:
            force_refresh: Force a refresh of the JWKS cache

        Returns:
            The JWKS dictionary
        """
        now = datetime.now()
        cache_expired = (
            self._cache_timestamp is None or
            (now - self._cache_timestamp) > self.cache_ttl
        )

        if force_refresh or self._jwks_cache is None or cache_expired:
            logger.info(f"{'Force refreshing' if force_refresh else 'Refreshing'} JWKS cache (last fetch: {self._cache_timestamp})")
            self._jwks_cache = await self._fetch_jwks()
            self._cache_timestamp = now

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
        Implements retry logic to handle JWKS key rotation.

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
        except (jwt.InvalidSignatureError, ValueError) as e:
            # If signature validation fails or key not found, try refreshing JWKS once
            # This handles key rotation scenarios
            if "signature" in str(e).lower() or "unable to find matching key" in str(e).lower():
                logger.warning(f"Token validation failed ({e}), attempting JWKS refresh")
                try:
                    # Force refresh JWKS and retry
                    jwks = await self._get_jwks(force_refresh=True)
                    signing_key = self._get_signing_key(unverified_header, jwks)

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

                    payload['_validated_by'] = 'JWTValidator'
                    payload['_issuer'] = self.issuer
                    payload['_audience'] = self.audience

                    logger.info("Token validation succeeded after JWKS refresh")
                    return payload

                except Exception as retry_error:
                    logger.error(f"Token validation failed even after JWKS refresh: {retry_error}")
                    raise ValueError(f"Invalid token signature (retry failed): {retry_error}")
            raise ValueError(f"Invalid token signature: {e}")
        except jwt.DecodeError:
            raise ValueError("Invalid token format")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")


def create_jwt_validator(
    jwks_url: str,
    issuer: str,
    audience: str,
    ssl_verify: bool = True,
    cache_ttl_minutes: int = 10
) -> JWTValidator:
    """
    Factory function to create a JWT validator instance.

    Args:
        jwks_url: The URL to fetch JWKS from
        issuer: Expected token issuer
        audience: Expected token audience
        ssl_verify: Whether to verify SSL certificates
        cache_ttl_minutes: How long to cache JWKS before refreshing (default: 10 minutes)

    Returns:
        JWTValidator: Configured validator instance
    """
    return JWTValidator(jwks_url, issuer, audience, ssl_verify, cache_ttl_minutes)
