"""
Asgardeo 3-Step Agent Authentication.
Used by Orchestrator to get its own actor_token for delegation.
"""

import logging
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AgentAuthService:
    """
    3-step agent authentication per Asgardeo docs:
    1. POST /oauth2/authorize with response_mode=direct
    2. POST /oauth2/authn with agent credentials
    3. POST /oauth2/token to get actor_token
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        agent_id: str,
        agent_secret: str,
        org_name: str = "a2abasic",
        redirect_uri: str = "http://localhost:8000/callback"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.agent_id = agent_id
        self.agent_secret = agent_secret
        self.org_name = org_name
        self.redirect_uri = redirect_uri
        
        # Asgardeo endpoints
        base_url = f"https://api.asgardeo.io/t/{org_name}"
        self.authorize_endpoint = f"{base_url}/oauth2/authorize"
        self.authn_endpoint = f"{base_url}/oauth2/authn"
        self.token_endpoint = f"{base_url}/oauth2/token"
        
        # Cached actor token
        self._actor_token: Optional[str] = None
        
        logger.info(f"AgentAuthService initialized for client: {client_id}")
    
    async def _exchange_code_for_token(self, client: httpx.AsyncClient, code: str, code_verifier: str = None) -> Optional[str]:
        """Exchange code for token (step 3 of the flow)."""
        logger.info("Exchanging code for actor_token...")
        
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        # Add code_verifier for PKCE if provided
        if code_verifier:
            token_data['code_verifier'] = code_verifier
        
        token_response = await client.post(
            self.token_endpoint,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=token_data
        )
        
        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.status_code}")
            logger.error(f"Response: {token_response.text}")
            return None
        
        token_data = token_response.json()
        self._actor_token = token_data.get('access_token')
        
        if self._actor_token:
            logger.info(f"✅ Actor token obtained: {self._actor_token[:30]}...")
            return self._actor_token
        else:
            logger.error("No access_token in response")
            return None
    
    async def get_actor_token(self, scopes: list = None) -> Optional[str]:
        """
        Get actor_token via 3-step flow.
        Caches the token for reuse.
        """
        if self._actor_token:
            return self._actor_token
        
        if not scopes:
            scopes = ['openid', 'profile']
        
        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Authorize (get flowId)
                logger.info("Step 1: Initiating agent authorization...")
                
                # Create Basic auth header
                import base64
                import secrets
                import hashlib
                
                credentials = f"{self.client_id}:{self.client_secret}"
                basic_auth = base64.b64encode(credentials.encode()).decode()
                
                # Generate PKCE
                code_verifier = secrets.token_urlsafe(64)[:64]
                digest = hashlib.sha256(code_verifier.encode()).digest()
                code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                
                auth_request_data = {
                    'response_type': 'code',
                    'redirect_uri': self.redirect_uri,
                    'scope': ' '.join(scopes),
                    'response_mode': 'direct',
                    'client_id': self.client_id,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'S256'
                }
                
                logger.info(f"Authorize request to: {self.authorize_endpoint}")
                logger.info(f"With client_id: {self.client_id}")
                
                auth_response = await client.post(
                    self.authorize_endpoint,
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Authorization': f'Basic {basic_auth}'
                    },
                    data=auth_request_data
                )
                
                if auth_response.status_code != 200:
                    logger.error(f"Step 1 failed: {auth_response.status_code}")
                    logger.error(f"Response: {auth_response.text}")
                    return None
                
                # Debug: log the full response
                response_text = auth_response.text
                logger.info(f"Step 1 response: {response_text[:500]}...")
                
                auth_result = auth_response.json()
                flow_id = auth_result.get('flowId')
                
                # Check if we got a code directly (app-native auth might skip interactive flow)
                if not flow_id:
                    code = auth_result.get('code')
                    if code:
                        logger.info(f"Got code directly (no interactive flow): {code[:20]}...")
                        # Skip step 2, go directly to step 3
                        return await self._exchange_code_for_token(client, code, code_verifier)
                    
                    logger.error(f"No flowId in response. Keys: {list(auth_result.keys())}")
                    return None
                
                # Get authenticator ID - FIX: use auth_result not auth_data
                authenticators = auth_result.get('nextStep', {}).get('authenticators', [])
                if not authenticators:
                    logger.error("No authenticators found")
                    return None
                
                authenticator_id = authenticators[0].get('authenticatorId')
                logger.info(f"Step 1 complete. FlowId: {flow_id[:20]}...")
                
                # Step 2: Authenticate with agent credentials
                logger.info("Step 2: Authenticating agent...")
                
                authn_response = await client.post(
                    self.authn_endpoint,
                    headers={'Content-Type': 'application/json'},
                    json={
                        'flowId': flow_id,
                        'selectedAuthenticator': {
                            'authenticatorId': authenticator_id,
                            'params': {
                                'username': self.agent_id,
                                'password': self.agent_secret
                            }
                        }
                    }
                )
                
                if authn_response.status_code != 200:
                    logger.error(f"Step 2 failed: {authn_response.status_code}")
                    logger.error(f"Response: {authn_response.text}")
                    return None
                
                # Debug: log full response
                authn_text = authn_response.text
                logger.info(f"Step 2 response: {authn_text[:500]}...")
                
                authn_data = authn_response.json()
                
                # Check if auth is complete
                flow_status = authn_data.get('flowStatus')
                if flow_status == 'SUCCESS_COMPLETED':
                    # Check for authData containing code
                    auth_data = authn_data.get('authData', {})
                    code = auth_data.get('code') or authn_data.get('code')
                    if code:
                        logger.info(f"Step 2 complete. Code: {code[:20]}...")
                    else:
                        logger.error(f"flowStatus=SUCCESS_COMPLETED but no code. authData keys: {list(auth_data.keys())}")
                        return None
                else:
                    code = authn_data.get('code')
                    if not code:
                        logger.error(f"No code in authn response. flowStatus={flow_status}, keys: {list(authn_data.keys())}")
                        return None
                    logger.info(f"Step 2 complete. Code: {code[:20]}...")
                
                # Step 3: Exchange code for token
                logger.info("Step 3: Exchanging code for actor_token...")
                
                token_response = await client.post(
                    self.token_endpoint,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    data={
                        'grant_type': 'authorization_code',
                        'client_id': self.client_id,
                        'client_secret': self.client_secret,
                        'code': code,
                        'redirect_uri': self.redirect_uri,
                        'code_verifier': code_verifier
                    }
                )
                
                if token_response.status_code != 200:
                    logger.error(f"Step 3 failed: {token_response.status_code}")
                    logger.error(f"Response: {token_response.text}")
                    return None
                
                token_data = token_response.json()
                self._actor_token = token_data.get('access_token')
                
                if self._actor_token:
                    logger.info(f"✅ Actor token obtained: {self._actor_token[:30]}...")
                    return self._actor_token
                else:
                    logger.error("No access_token in response")
                    return None
                    
        except Exception as e:
            logger.error(f"Agent auth error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
