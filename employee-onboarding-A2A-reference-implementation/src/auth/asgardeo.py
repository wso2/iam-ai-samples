"""
WSO2 IS Client - Authentication & Token Exchange.
Implements 3-step actor token flow and RFC 8693 Token Exchange.
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs

import structlog

from src.config import get_settings
from src.auth.utils import generate_pkce, PKCEChallenge
from src.log_broadcaster import log_and_broadcast

logger = structlog.get_logger()


# Use log_and_broadcast instead of print for visualizer integration
def vlog(message: str):
    """Log message and broadcast to visualizer."""
    log_and_broadcast(message)


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: str = ""
    token_type: str = "Bearer"
    expires_in: int = 3600
    expires_at: datetime = None

    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(seconds=self.expires_in)


@dataclass
class ActorToken:
    token: str
    actor_id: str
    expires_at: datetime


class AsgardeoClient:
    """
    Client for interacting with WSO2 Identity Server.
    Handles:
    - User Authentication (Authorization Code Flow)
    - Actor Token Acquisition (3-Step Flow)
    - Token Exchange (RFC 8693) for delegation and downscoping
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._actor_token: Optional[ActorToken] = None
    
    def _create_fresh_client(self) -> httpx.AsyncClient:
        """Create a fresh HTTP client with no cookies (for each auth flow)."""
        return httpx.AsyncClient(
            timeout=30.0, 
            verify=False,
            follow_redirects=False
        )

    # ─────────────────────────────────────────────────────────────────
    # 1. User Authorization (Orchestrator App)
    # ─────────────────────────────────────────────────────────────────

    def build_user_authorize_url(
        self,
        scopes: list[str],
        state: str,
        pkce: PKCEChallenge
    ) -> str:
        """
        Build the authorization URL for user consent.
        Includes requested_actor to bind the orchestrator agent to the resulting token.
        """
        from urllib.parse import urlencode
        
        all_scopes = scopes + ["openid", "profile"]
        
        params = {
            "response_type": "code",
            "client_id": self.settings.orchestrator_client_id,
            "scope": " ".join(all_scopes),
            "redirect_uri": self.settings.app_callback_url,
            "state": state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "requested_actor": self.settings.orchestrator_agent_id
        }
        
        # Properly URL-encode all parameters
        query = urlencode(params)
        auth_url = f"{self.settings.asgardeo_authorize_url}?{query}"
        
        vlog(f"\n[BUILD AUTH URL]")
        vlog(f"  Requested Scopes: {all_scopes}")
        vlog(f"  URL: {auth_url}")
        
        return auth_url


    async def exchange_code_for_delegated_token(
        self,
        code: str,
        code_verifier: str,
        actor_token: str
    ) -> TokenResponse:
        """
        Exchange auth code for a delegated access token.
        Requires actor_token to prove the agent's identity.
        """
        async with self._create_fresh_client() as client:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.app_callback_url,
                "code_verifier": code_verifier,
                "actor_token": actor_token,
                "actor_token_type": "urn:ietf:params:oauth:token-type:access_token"
            }
            
            vlog(f"\n{'='*80}")
            vlog(f"[EXCHANGE CODE FOR DELEGATED TOKEN]")
            vlog(f"{'='*80}")
            vlog(f"  Token URL: {self.settings.asgardeo_token_url}")
            vlog(f"  Grant Type: authorization_code")
            vlog(f"  Code: {code}")
            vlog(f"  Redirect URI: {self.settings.app_callback_url}")
            vlog(f"  Client ID: {self.settings.orchestrator_client_id}")
            vlog(f"  Code Verifier: {code_verifier}")
            vlog(f"  Actor Token: {actor_token[:50]}...")
            vlog(f"{'='*80}")
            
            # Use HTTP Basic Auth only (WSO2 IS rejects body + header auth together)
            import base64
            basic_auth = base64.b64encode(
                f"{self.settings.orchestrator_client_id}:{self.settings.orchestrator_client_secret}".encode()
            ).decode()
            
            response = await client.post(
                self.settings.asgardeo_token_url,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {basic_auth}"
                }
            )
            
            vlog(f"\n[RESPONSE]")
            vlog(f"  Status: {response.status_code}")
            vlog(f"  Body: {response.text}")

            
            response.raise_for_status()
            
            result = response.json()
            
            vlog(f"  Access Token: {result.get('access_token', '')[:50]}...")
            vlog(f"  Scope: {result.get('scope', '')}")
            
            logger.info("delegated_token_received", scope=result.get("scope"))
            
            return TokenResponse(**result)


    # ─────────────────────────────────────────────────────────────────
    # 2. Agent Actor Token (3-Step Flow)
    # ─────────────────────────────────────────────────────────────────

    async def get_actor_token(self) -> ActorToken:
        """Get an actor token for the orchestrator agent."""
        if self._actor_token and self._actor_token.expires_at > datetime.utcnow():
            return self._actor_token
            
        token = await self._fetch_agent_actor_token(
            client_id=self.settings.orchestrator_client_id,
            client_secret=self.settings.orchestrator_client_secret,
            agent_id=self.settings.orchestrator_agent_id
        )
        
        self._actor_token = token
        logger.info("actor_token_obtained", agent_id=self.settings.orchestrator_agent_id)
        return token

    async def _fetch_agent_actor_token(self, client_id: str, client_secret: str, agent_id: str) -> ActorToken:
        """
        Get an actor token for an agent via 3-step authorization_code flow.
        Uses the passed client_id/client_secret for Steps 1 & 3.
        - Orchestrator agent: pass orchestrator app credentials
        - Worker agents: pass token exchanger app credentials
        """
        vlog(f"\n{'='*80}")
        vlog(f"[FETCHING AGENT ACTOR TOKEN]")
        vlog(f"  Agent ID: {agent_id}")
        vlog(f"{'='*80}")

        # Lookup Agent Secret from Config
        from src.config import get_settings
        from src.config_loader import load_yaml_config
        
        # Reload config to ensure we have latest secrets
        config = load_yaml_config()
        agents = config.get("agents", {})
        agent_secret = None
        
        for key, agent_config in agents.items():
            if agent_config.get("agent_id") == agent_id:
                agent_secret = agent_config.get("agent_secret")
                vlog(f"  Found secret for {key}")
                break
            # Also check nested mcp_server config
            mcp_cfg = agent_config.get("mcp_server", {})
            if mcp_cfg.get("agent_id") == agent_id:
                agent_secret = mcp_cfg.get("agent_secret")
                vlog(f"  Found secret for {key}.mcp_server")
                break
        
        # Fallback: Check if this is the Orchestrator Agent
        if not agent_secret:
            settings = get_settings()
            if agent_id == settings.orchestrator_agent_id:
                agent_secret = settings.orchestrator_agent_secret
                vlog(f"  Using Orchestrator Agent credentials")
            else:
                vlog(f"[ERROR] No secret found for Agent ID: {agent_id}")
        
        # ─────────────────────────────────────────────────────────────
        # Agent Authentication via 3-Step Authorization Code Flow
        # Uses passed client_id/client_secret for Steps 1 & 3
        # ─────────────────────────────────────────────────────────────
        vlog(f"\n[3-STEP AUTHORIZATION CODE FLOW]")
        vlog(f"  Application Client ID: {client_id}")
        
        try:
            pkce = generate_pkce()
            
            # Use fresh client for each flow (clears cookies)
            async with self._create_fresh_client() as fresh_client:
                # Step 1: Initiate Auth Flow - Get flowId
                flow_id = await self._initiate_auth_flow(
                    fresh_client, 
                    client_id,
                    client_secret, 
                    pkce
                )
                vlog(f"\n[STEP 1] Flow ID: {flow_id}")
                
                # Check if we got a code directly (session was active)
                if flow_id.startswith("CODE:"):
                    auth_code = flow_id[5:]  # Strip "CODE:" prefix
                    vlog(f"\n[STEP 1] Got code directly (session active): {auth_code}")
                else:
                    # Step 2: Authenticate Agent with agent_id and agent_secret
                    auth_code = await self._authenticate_agent(fresh_client, flow_id, agent_id)
                    vlog(f"\n[STEP 2] Auth Code: {auth_code}")
                
                # Step 3: Exchange for Actor Token
                actor_token = await self._exchange_code_for_actor_token(
                    fresh_client, 
                    client_id,
                    client_secret,
                    auth_code, 
                    pkce.verifier, 
                    agent_id
                )
                vlog(f"\n[STEP 3] ACTOR_TOKEN: {actor_token.token[:20]}...")
                
                return actor_token
        except Exception as e:
            vlog(f"\n[FATAL] Authorization code flow failed for agent {agent_id}")
            raise e

    async def _initiate_auth_flow(self, client: httpx.AsyncClient, client_id: str, client_secret: str, pkce: PKCEChallenge) -> str:
        """
        Step 1: Initiate authorization flow for AI Agent authentication.
        POST /oauth2/authorize with response_mode=direct -> Returns JSON with flowId
        """
        data = {
            "response_type": "code",
            "client_id": client_id,
            "scope": "openid",
            "redirect_uri": self.settings.app_callback_url,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "response_mode": "direct"
        }
        
        vlog(f"\n  [Step 1] Calling: POST {self.settings.asgardeo_authorize_url}")
        
        # Use HTTP Basic Auth (client_secret_basic) for WSO2 IS
        import base64
        basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        
        response = await client.post(
            self.settings.asgardeo_authorize_url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Authorization": f"Basic {basic_auth}"
            }
        )
        
        vlog(f"  [Step 1] Response status: {response.status_code}")
        
        # Handle 302 redirect - extract flowId/sessionDataKey from redirect URL
        if response.status_code == 302:
            location = response.headers.get("location", "")
            vlog(f"  [Step 1] Redirect to: {location[:100]}...")
            
            parsed = urlparse(location)
            query_params = parse_qs(parsed.query)
            
            # Try different parameter names
            flow_id = (
                query_params.get("flowId", [None])[0] or
                query_params.get("sessionDataKey", [None])[0]
            )
            if flow_id:
                return flow_id
            else:
                raise ValueError(f"flowId not found in redirect: {location}")
        elif response.status_code == 200:
            # JSON response with response_mode=direct
            result = response.json()
            flow_status = result.get("flowStatus")
            vlog(f"  [Step 1] JSON Response: flowStatus={flow_status}")
            
            # If session is active, authorize may return SUCCESS_COMPLETED with code directly
            if flow_status == "SUCCESS_COMPLETED":
                direct_code = result.get("code") or result.get("authData", {}).get("code")
                if direct_code:
                    vlog(f"  [Step 1] Session active - got code directly: {direct_code}")
                    # Return code as a special marker (caller should handle)
                    return f"CODE:{direct_code}"
            
            flow_id = result.get("flowId")
            if flow_id:
                return flow_id
            else:
                raise ValueError(f"flowId not found in response: {result}")
        else:
            vlog(f"  [Step 1] Error: {response.text}")
            raise ValueError(f"Failed to initiate auth flow: {response.status_code} {response.text}")

    async def _authenticate_agent(self, client: httpx.AsyncClient, flow_id: str, agent_id: str) -> str:
        """
        Step 2: Authenticate agent with flowId to get auth code.
        POST /oauth2/authn with proper payload structure
        """
        # Get agent secret from config
        from src.config_loader import load_yaml_config
        config = load_yaml_config()
        
        # Find agent secret
        agent_secret = None
        agents = config.get("agents", {})
        
        vlog(f"\n  [Step 2] Looking up agent secret for agent_id: {agent_id}")
        vlog(f"  [Step 2] Available agents in config: {list(agents.keys())}")
        
        for key, agent_config in agents.items():
            config_agent_id = agent_config.get("agent_id")
            vlog(f"  [Step 2] Checking {key}: config agent_id={config_agent_id}")
            if config_agent_id == agent_id:
                agent_secret = agent_config.get("agent_secret")
                vlog(f"  [Step 2] FOUND! agent_secret length: {len(agent_secret) if agent_secret else 0}")
                break
        
        # Fallback: check if this is the orchestrator agent
        if not agent_secret and agent_id == self.settings.orchestrator_agent_id:
            agent_secret = self.settings.orchestrator_agent_secret
            vlog(f"  [Step 2] Using orchestrator agent credentials")
        
        if not agent_secret:
            vlog(f"  [Step 2] ERROR: No agent_secret found for {agent_id}")
            raise ValueError(f"No agent_secret found for agent_id: {agent_id}")
        
        authn_url = f"{self.settings.asgardeo_base_url}/oauth2/authn"
        
        vlog(f"\n  [Step 2] Calling: POST {authn_url}")
        vlog(f"  [Step 2] Agent ID (username): {agent_id}")
        vlog(f"  [Step 2] Agent Secret (password) first 3 chars: {agent_secret[:3]}...")
        
        # Proper WSO2 IS authn payload structure
        payload = {
            "flowId": flow_id,
            "selectedAuthenticator": {
                "authenticatorId": "QmFzaWNBdXRoZW50aWNhdG9yOkxPQ0FM",  # Base64 of "BasicAuthenticator:LOCAL"
                "params": {
                    "username": agent_id,
                    "password": agent_secret
                }
            }
        }
        
        vlog(f"  [Step 2] Payload: flowId={flow_id}, username={agent_id}")
        
        response = await client.post(
            authn_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        vlog(f"  [Step 2] Response status: {response.status_code}")
        
        # Handle different response types
        if response.status_code == 302:
            # Redirect contains the auth code
            location = response.headers.get("location", "")
            vlog(f"  [Step 2] Redirect: {location[:100]}...")
            
            parsed = urlparse(location)
            query_params = parse_qs(parsed.query)
            
            auth_code = query_params.get("code", [None])[0]
            if auth_code:
                return auth_code
            else:
                raise ValueError(f"Auth code not found in redirect: {location}")
        elif response.status_code == 200:
            result = response.json()
            vlog(f"  [Step 2] Response: {result}")
            
            # Check if we got the code directly, in authData, or need to follow a redirect
            if "code" in result:
                return result["code"]
            elif "authData" in result and "code" in result["authData"]:
                return result["authData"]["code"]
            elif "authorizationCode" in result:
                return result["authorizationCode"]
            elif "redirectUrl" in result:
                # Parse code from redirectUrl
                parsed = urlparse(result["redirectUrl"])
                query_params = parse_qs(parsed.query)
                auth_code = query_params.get("code", [None])[0]
                if auth_code:
                    return auth_code
            
            raise ValueError(f"Auth code not found in response: {result}")
        else:
            error_text = response.text
            vlog(f"  [Step 2] Error: {error_text}")
            raise ValueError(f"Authentication failed: {response.status_code} - {error_text}")

    async def _exchange_code_for_actor_token(
        self, 
        client: httpx.AsyncClient,
        client_id: str, 
        client_secret: str, 
        code: str, 
        verifier: str,
        agent_id: str
    ) -> ActorToken:
        """
        Step 3: Exchange authorization code for actor token.
        Includes audience parameter pointing to Token Exchanger.
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": self.settings.app_callback_url,
            "code_verifier": verifier,
        }
        
        vlog(f"\n  [Step 3] Calling: POST {self.settings.asgardeo_token_url}")
        vlog(f"  [Step 3] Client ID: {client_id}")
        
        response = await client.post(
            self.settings.asgardeo_token_url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        
        vlog(f"  [Step 3] Response status: {response.status_code}")
        
        if response.status_code != 200:
            vlog(f"  [Step 3] Error: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        expires_in = result.get("expires_in", 3600)
        
        return ActorToken(
            token=result["access_token"],
            actor_id=agent_id,
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
        )
    # ─────────────────────────────────────────────────────────────────
    # 2b. Agent Actor Token via Client Credentials + Agent Binding
    # ─────────────────────────────────────────────────────────────────

    async def get_agent_actor_token_credentials(
        self,
        client_id: str,
        client_secret: str,
        agent_id: str,
        agent_secret: str
    ) -> ActorToken:
        """
        Get an agent's actor token using client credentials grant with agent binding.
        This is for worker agents that are registered as agents (not users) in WSO2 IS.
        
        Uses: POST /oauth2/token with grant_type=client_credentials and agent binding.
        """
        vlog(f"\n{'='*80}")
        vlog(f"[AGENT ACTOR TOKEN - CLIENT CREDENTIALS]")
        vlog(f"  Application Client ID: {client_id}")
        vlog(f"  Agent ID: {agent_id}")
        vlog(f"{'='*80}")
        
        async with self._create_fresh_client() as client:
            # Client credentials grant with agent binding
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "openid",
                "agent_id": agent_id,
                "agent_secret": agent_secret
            }
            
            vlog(f"\n[REQUEST]")
            vlog(f"  URL: POST {self.settings.asgardeo_token_url}")
            vlog(f"  grant_type: client_credentials")
            vlog(f"  agent_id: {agent_id}")
            
            response = await client.post(
                self.settings.asgardeo_token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            vlog(f"\n[RESPONSE]")
            vlog(f"  Status: {response.status_code}")
            
            if response.status_code != 200:
                vlog(f"  Error: {response.text}")
                raise ValueError(f"Failed to get agent actor token: {response.status_code} - {response.text}")
            
            result = response.json()
            expires_in = result.get("expires_in", 3600)
            
            vlog(f"  Access Token: {result.get('access_token', '')[:50]}...")
            vlog(f"{'='*80}\n")
            
            return ActorToken(
                token=result["access_token"],
                actor_id=agent_id,
                expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
            )

    # ─────────────────────────────────────────────────────────────────
    # 3. Token Exchange (RFC 8693)
    # ─────────────────────────────────────────────────────────────────

    async def perform_token_exchange(
        self,
        subject_token: str,
        client_id: str,
        client_secret: str,
        actor_token: Optional[str] = None,
        target_audience: Optional[str] = None,
        target_scopes: Optional[list[str]] = None
    ) -> str:
        """
        Exchange a token for a new one (RFC 8693).
        """
        async with self._create_fresh_client() as client:
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": subject_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            }
            
            if actor_token:
                data["actor_token"] = actor_token
                data["actor_token_type"] = "urn:ietf:params:oauth:token-type:access_token"
            
            if target_audience:
                data["audience"] = target_audience
                
            if target_scopes:
                data["scope"] = " ".join(target_scopes)
            
            vlog(f"\n{'='*80}")
            vlog(f"[TOKEN EXCHANGE]")
            vlog(f"  Client: {client_id}")
            vlog(f"  Audience: {target_audience}")
            vlog(f"  Scopes: {target_scopes}")
            vlog(f"{'='*80}")
            vlog(f"\n[SUBJECT_TOKEN]:")
            vlog(f"  {subject_token}")
            if actor_token:
                vlog(f"\n[ACTOR_TOKEN]:")
                vlog(f"  {actor_token}")

            # Use HTTP Basic Auth only (WSO2 IS rejects body + header auth together)
            import base64
            basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                
            response = await client.post(
                self.settings.asgardeo_token_url,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {basic_auth}"
                }
            )
            response.raise_for_status()
            
            result = response.json()
            exchanged_token = result["access_token"]
            
            vlog(f"\n[EXCHANGED_TOKEN]:")
            vlog(f"  {exchanged_token}")
            vlog(f"{'='*80}\n")
            
            return exchanged_token


# Singleton
_asgardeo_client: Optional[AsgardeoClient] = None

def get_asgardeo_client() -> AsgardeoClient:
    global _asgardeo_client
    if _asgardeo_client is None:
        _asgardeo_client = AsgardeoClient()
    return _asgardeo_client
