"""
Simplified OAuth 2.0 Flow Handler for Asgardeo.
Standard Authorization Code + PKCE flow.
"""

import os
import secrets
import hashlib
import base64
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import httpx

logger = logging.getLogger(__name__)


class OAuthFlowHandler:
    """Standard OAuth 2.0 Authorization Code + PKCE flow."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        org_name: str = "a2abasic"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.org_name = org_name
        
        # Asgardeo endpoints
        base_url = f"https://api.asgardeo.io/t/{org_name}"
        self.authorize_endpoint = f"{base_url}/oauth2/authorize"
        self.token_endpoint = f"{base_url}/oauth2/token"
        
        # PKCE storage (state -> code_verifier)
        self._pkce_verifiers: Dict[str, str] = {}
        
        logger.info(f"OAuth handler initialized for client: {client_id}")
    
    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge."""
        code_verifier = secrets.token_urlsafe(64)[:64]
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
        return code_verifier, code_challenge
    
    def generate_auth_url(
        self,
        scopes: List[str],
        state: Optional[str] = None,
        requested_actor: Optional[str] = None
    ) -> tuple[str, str, str]:
        """
        Generate OAuth authorization URL with PKCE.
        
        Args:
            scopes: OAuth scopes (e.g., ['booking:read', 'booking:write'])
            state: Optional state parameter
            requested_actor: Optional actor ID for delegation
            
        Returns:
            Tuple of (auth_url, state, code_verifier)
        """
        if not state:
            state = secrets.token_urlsafe(32)
        
        code_verifier, code_challenge = self._generate_pkce_pair()
        self._pkce_verifiers[state] = code_verifier
        
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        # Add requested_actor for Asgardeo A2A delegation
        if requested_actor:
            params['requested_actor'] = requested_actor
            logger.info(f"Including requested_actor: {requested_actor}")
        
        auth_url = f"{self.authorize_endpoint}?{urlencode(params)}"
        
        logger.info(f"Generated auth URL with scopes: {scopes}")
        
        return auth_url, state, code_verifier
    
    async def exchange_code_for_token(
        self,
        code: str,
        state: str,
        actor_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            state: State parameter to retrieve code_verifier
            actor_token: Optional actor token for delegation flow
            
        Returns:
            Token response dict or None if failed
        """
        code_verifier = self._pkce_verifiers.get(state)
        if not code_verifier:
            logger.error(f"No PKCE verifier found for state: {state[:20]}...")
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                token_data = {
                    'grant_type': 'authorization_code',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'redirect_uri': self.redirect_uri,
                    'code_verifier': code_verifier
                }
                
                # Build headers
                headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                
                # Add actor_token for delegation flow
                if actor_token:
                    # Try as form parameter (per some OAuth implementations)
                    token_data['actor_token'] = actor_token
                    token_data['actor_token_type'] = 'urn:ietf:params:oauth:token-type:access_token'
                    # Also in Authorization header
                    headers['Authorization'] = f'Bearer {actor_token}'
                    logger.info(f"Including actor_token in request (header + form)")
                
                response = await client.post(
                    self.token_endpoint,
                    headers=headers,
                    data=token_data
                )
                
                if response.status_code != 200:
                    logger.error(f"Token exchange failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return None
                
                # Clean up PKCE verifier
                del self._pkce_verifiers[state]
                
                token_response = response.json()
                logger.info(f"Token obtained successfully")
                return token_response
                
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return None
