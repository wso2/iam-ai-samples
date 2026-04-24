"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  JWT Token Validation Module

  Validates JWT tokens using JWKS (JSON Web Key Set) fetched from the
  authorization server. Supports RS256 algorithm with key caching.

  Error types:
    token_expired  - JWT has passed its expiration time
    invalid_token  - JWT signature verification failed or token is malformed
"""

import jwt
from jwt.algorithms import RSAAlgorithm
import httpx
from typing import Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Structured token validation error with an error type identifier."""

    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)


class JWTValidator:
    """
    JWT token validator using JWKS.
    Fetches and caches JWKS keys for performance.
    """

    def __init__(self, jwks_url: str, issuer: str, audience: Union[str, list[str]], ssl_verify: bool = True):
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.ssl_verify = ssl_verify
        self._jwks_cache: Optional[Dict[str, Any]] = None

    async def _fetch_jwks(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(verify=self.ssl_verify) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                self._jwks_cache = response.json()
                return self._jwks_cache
        except Exception as e:
            logger.error(f"Failed to fetch JWKS from {self.jwks_url}: {e}")
            raise

    async def _get_jwks(self) -> Dict[str, Any]:
        if self._jwks_cache is None:
            await self._fetch_jwks()
        return self._jwks_cache

    def _find_key_for_kid(self, kid: str, jwks: Dict[str, Any]):
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return RSAAlgorithm.from_jwk(key)
        return None

    async def _get_signing_key(self, token_header: Dict[str, Any]):
        """Resolve the signing key for the token, refreshing JWKS once on a kid miss
        so we tolerate IdP key rotation without requiring a service restart."""
        kid = token_header.get('kid')
        if not kid:
            raise TokenError("invalid_token", "Token header missing 'kid' field")

        jwks = await self._get_jwks()
        key = self._find_key_for_kid(kid, jwks)
        if key is not None:
            return key

        # kid not in cached JWKS — IdP may have rotated keys. Refetch once.
        logger.info(f"Unknown kid '{kid}' in cached JWKS; refetching from IdP")
        jwks = await self._fetch_jwks()
        key = self._find_key_for_kid(kid, jwks)
        if key is not None:
            return key

        raise TokenError("invalid_token", f"Unable to find matching key for kid: {kid}")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate a JWT token and return the payload.

        Checks signature (RS256), expiry, issuer, and audience.
        Raises TokenError on any validation failure.
        """
        try:
            unverified_header = jwt.get_unverified_header(token)
            signing_key = await self._get_signing_key(unverified_header)

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
                    "verify_aud": True,
                }
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise TokenError("token_expired", "Token has expired")
        except jwt.InvalidAudienceError:
            raise TokenError("invalid_token", "Invalid audience")
        except jwt.InvalidIssuerError:
            raise TokenError("invalid_token", "Invalid issuer")
        except jwt.InvalidSignatureError:
            raise TokenError("invalid_token", "Invalid token signature")
        except jwt.DecodeError:
            raise TokenError("invalid_token", "Invalid token format")
        except TokenError:
            raise
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise TokenError("invalid_token", f"Token validation failed: {e}")
