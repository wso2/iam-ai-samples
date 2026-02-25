"""
JWT Validator for API endpoints.
Validates delegated tokens against Asgardeo JWKS.
"""

from dataclasses import dataclass
from typing import Optional

import httpx
import structlog
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError

from src.config import get_settings

logger = structlog.get_logger()
security = HTTPBearer()


@dataclass
class ActorClaim:
    """Actor claim from delegated token."""
    sub: str  # Actor subject (e.g., orchestrator-agent-id)


@dataclass
class TokenClaims:
    """Validated JWT claims."""
    sub: str  # User subject
    aud: str | list[str]  # Audience
    scope: str  # Scopes
    exp: int  # Expiration
    iss: str  # Issuer
    act: Optional[ActorClaim] = None  # Actor claim (proves delegation)
    azp: Optional[str] = None  # Authorized party
    jti: Optional[str] = None  # Token ID
    client_id: Optional[str] = None  # Client ID
    raw_token: Optional[str] = None  # Raw token string
    
    def has_scope(self, required_scope: str) -> bool:
        """Check if token has a specific scope."""
        scopes = self.scope.split() if self.scope else []
        return required_scope in scopes
    
    def has_audience(self, required_aud: str) -> bool:
        """Check if token has a specific audience."""
        if isinstance(self.aud, list):
            return required_aud in self.aud
        return self.aud == required_aud
    
    @property
    def is_delegated(self) -> bool:
        """Check if this is a delegated token (has actor claim)."""
        return self.act is not None
    
    @property
    def actor_sub(self) -> Optional[str]:
        """Get the actor subject if this is a delegated token."""
        return self.act.sub if self.act else None


class JWTValidator:
    """Validates JWTs against Asgardeo JWKS."""
    
    def __init__(self):
        self.settings = get_settings()
        self._jwks: Optional[dict] = None
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            # Disable SSL verification for local dev (localhost:9443)
            self._http_client = httpx.AsyncClient(timeout=30.0, verify=False)
        return self._http_client
    
    async def get_jwks(self) -> dict:
        """Fetch JWKS from Asgardeo (cached)."""
        if self._jwks is None:
            response = await self.http_client.get(self.settings.asgardeo_jwks_url)
            response.raise_for_status()
            self._jwks = response.json()
            logger.info("jwks_fetched", url=self.settings.asgardeo_jwks_url)
        return self._jwks
    
    async def validate(self, token: str) -> TokenClaims:
        """
        Validate a JWT and return its claims.
        
        Validates:
        - Signature (against JWKS)
        - Expiration
        - Issuer (must match Asgardeo tenant)
        
        Does NOT validate audience here - that's done per-API.
        """
        try:
            jwks = await self.get_jwks()
            
            # Decode without verification first to get header
            unverified = jwt.get_unverified_header(token)
            kid = unverified.get("kid")
            
            # Find matching key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break
            
            if not key:
                raise HTTPException(401, "Invalid token: signing key not found")
            
            # Verify and decode
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=None,  # Validate audience per-API instead
                options={"verify_aud": False}
            )
            
            # Parse actor claim if present
            act_claim = None
            if "act" in claims:
                act_data = claims["act"]
                act_claim = ActorClaim(sub=act_data.get("sub", ""))
            
            token_claims = TokenClaims(
                sub=claims.get("sub"),
                aud=claims.get("aud"),
                scope=claims.get("scope", ""),
                exp=claims.get("exp"),
                iss=claims.get("iss"),
                act=act_claim,
                azp=claims.get("azp"),
                jti=claims.get("jti"),
                client_id=claims.get("client_id"),
                raw_token=token
            )
            
            logger.info(
                "token_validated",
                sub=token_claims.sub,
                scope=token_claims.scope,
                aud=token_claims.aud,
                is_delegated=token_claims.is_delegated,
                actor=token_claims.actor_sub
            )
            
            return token_claims
            
        except JWTError as e:
            logger.error("token_validation_failed", error=str(e))
            raise HTTPException(401, f"Invalid token: {str(e)}")


# Singleton instance
_jwt_validator: Optional[JWTValidator] = None


def get_jwt_validator() -> JWTValidator:
    """Get or create the JWT validator singleton."""
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = JWTValidator()
    return _jwt_validator


async def validate_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> TokenClaims:
    """
    FastAPI dependency to validate bearer token.
    Use in route handlers: token: TokenClaims = Depends(validate_token)
    """
    validator = get_jwt_validator()
    return await validator.validate(credentials.credentials)


def require_scope(claims: TokenClaims, scope: str) -> None:
    """Verify token has required scope, raise 403 if not."""
    if not claims.has_scope(scope):
        logger.warning("scope_denied", required=scope, actual=claims.scope)
        raise HTTPException(403, f"Required scope: {scope}")


def require_audience(claims: TokenClaims, audience: str) -> None:
    """Verify token has required audience, raise 403 if not."""
    if not claims.has_audience(audience):
        logger.warning("audience_denied", required=audience, actual=claims.aud)
        raise HTTPException(403, f"Required audience: {audience}")
