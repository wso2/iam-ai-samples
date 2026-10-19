"""
Token Broker for centralized token management.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

from src.auth.asgardeo import (
    AsgardeoClient,
    TokenResponse,
    ActorToken,
    PKCEChallenge,
    generate_pkce,
    get_asgardeo_client
)
from src.config_loader import load_yaml_config
from src.config import get_settings
from src.log_broadcaster import log_and_broadcast

logger = structlog.get_logger()

def vlog(message: str):
    """Log message and broadcast to visualizer."""
    log_and_broadcast(message)

@dataclass
class UserSession:
    """User session with OAuth state."""
    session_id: str
    user_sub: Optional[str] = None
    pkce: Optional[PKCEChallenge] = None
    delegated_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class AuditEntry:
    timestamp: datetime
    operation: str
    user_sub: Optional[str]
    actor_sub: str
    target_service: str
    scopes: list[str]
    success: bool = True
    error: Optional[str] = None

class TokenBroker:
    """
    Centralized token broker.
    """
    
    def __init__(self, asgardeo: AsgardeoClient = None):
        self.settings = get_settings()
        self.asgardeo = asgardeo or get_asgardeo_client()
        self._actor_token: Optional[ActorToken] = None
        self._sessions: dict[str, UserSession] = {}
        self._audit_log: list[AuditEntry] = []
        
        # Load agent configs for identity lookup
        self.app_config = load_yaml_config()
        self.agents_config = self.app_config.get("agents", {})

    async def initialize(self):
        """Initialize the token broker by getting the orchestrator's actor token."""
        try:
            vlog(f"\n[TOKEN BROKER] Initializing orchestrator actor token...")
            self._actor_token = await self.asgardeo.get_actor_token()
            vlog(f"[TOKEN BROKER] Actor token obtained: {self._actor_token.token[:50]}...")
            vlog(f"\n[ORCHESTRATOR_ACTOR_TOKEN]:")
            vlog(f"{self._actor_token.token}")
            logger.info("token_broker_initialized", actor_id=self._actor_token.actor_id)
        except Exception as e:
            logger.error("broker_init_error", error=str(e))
            vlog(f"[TOKEN BROKER ERROR] Failed to initialize: {e}")
            raise  # Re-raise so caller knows initialization failed

    def create_session(self) -> UserSession:
        session_id = str(uuid.uuid4())
        pkce = generate_pkce()
        session = UserSession(session_id=session_id, pkce=pkce)
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        return self._sessions.get(session_id)
        
    def get_authorization_url(self, session_id: str, scopes: list[str]) -> str:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        return self.asgardeo.build_user_authorize_url(scopes, session_id, session.pkce)

    async def handle_callback(self, code: str, state: str) -> UserSession:
        """
        Handle OAuth callback - exchange code for delegated token.
        Requires actor token to prove the orchestrator agent's identity.
        """
        session = self._sessions.get(state)
        if not session:
            raise ValueError(f"Session not found: {state}")
        
        vlog(f"\n[HANDLE CALLBACK]")
        vlog(f"  Code: {code[:30]}...")
        vlog(f"  State: {state}")

        # First, get the orchestrator's actor token (using 3-step flow)
        if not self._actor_token:
            vlog(f"\n[GETTING ORCHESTRATOR ACTOR TOKEN...]")
            await self.initialize()
        
        if not self._actor_token:
            raise ValueError("Failed to obtain orchestrator actor token")
        
        vlog(f"\n[ORCHESTRATOR_ACTOR_TOKEN]:")
        vlog(f"  {self._actor_token.token}")

        # Exchange code for delegated token (with actor token)
        token_response = await self.asgardeo.exchange_code_for_delegated_token(
            code, session.pkce.verifier, self._actor_token.token
        )
        
        vlog(f"\n[USER_DELEGATED_TOKEN]:")
        vlog(f"  {token_response.access_token}")
        vlog(f"  Scope: {token_response.scope}")

        
        session.delegated_token = token_response.access_token
        session.token_expires_at = token_response.expires_at
        
        self._log_audit(
            operation="delegated_token_obtained",
            user_sub="user",
            target_service="orchestrator",
            scopes=token_response.scope.split()
        )
        return session

    def get_delegated_token(self, session_id: str) -> Optional[str]:
        session = self._sessions.get(session_id)
        if not session or not session.delegated_token:
            return None
        return session.delegated_token
        
    # ─────────────────────────────────────────────────────────────────
    # Token Exchange (Method V2 — Per-Agent App, No Actor Token)
    # ─────────────────────────────────────────────────────────────────

    async def exchange_token_for_agent(
        self,
        source_token: str,
        agent_key: str,  # e.g. "hr_agent"
        target_audience: str,
        target_scopes: list[str]
    ) -> str:
        """
        Downscope the user delegated token for a specific agent.

        Method V2 flow:
        - Orchestrator uses its OWN WSO2 IS application credentials to downscope.
          WSO2 IS only allows the issuing application to exchange its own tokens —
          the subject_token was issued by the orchestrator app, so only the
          orchestrator's client_id/secret can exchange it (self-delegation).
        - No actor_token parameter is sent — WSO2 IS self-delegation does not
          require an actor token.
        - The resulting token is scoped to the agent's required scopes and
          forwarded to the agent, which then does a second exchange with its own
          application credentials + its own actor token.
        """
        agent_config = self.agents_config.get(agent_key)
        if not agent_config:
            raise ValueError(f"Unknown agent: {agent_key}")

        # Use orchestrator's own credentials — it is the token issuer
        client_id = self.settings.orchestrator_client_id
        client_secret = self.settings.orchestrator_client_secret

        vlog(f"\n{'#'*80}")
        vlog(f"# ORCHESTRATOR DOWNSCOPING TOKEN FOR: {agent_key.upper()}")
        vlog(f"{'#'*80}")
        vlog(f"Orchestrator App Client ID: {client_id}")
        vlog(f"Target Scopes: {target_scopes}")

        vlog(f"\n[SOURCE_TOKEN (User Delegated)]:")
        vlog(f"{source_token}")

        vlog(f"\n[ORCHESTRATOR DOWNSCOPE — RFC 8693, Self-Delegation, No Actor Token]")
        vlog(f"  Using orchestrator's own credentials (token issuer): {client_id}")
        vlog(f"  Scopes: {target_scopes}")

        new_token = await self.asgardeo.perform_token_exchange(
            subject_token=source_token,
            client_id=client_id,
            client_secret=client_secret,
            # No actor_token — WSO2 IS self-delegation does not require one
            target_audience=None,
            target_scopes=target_scopes
        )

        vlog(f"\n[{agent_key.upper()}_DOWNSCOPED_TOKEN (forwarded to agent)]:")
        vlog(f"{new_token}")
        vlog(f"{'#'*80}\n")

        self._log_audit(
            operation="orchestrator_downscope",
            user_sub="unknown",
            target_service=agent_key,
            scopes=target_scopes
        )

        return new_token


    def _log_audit(self, operation, user_sub, target_service, scopes, success=True, error=None):
        entry = AuditEntry(
            timestamp=datetime.utcnow(),
            operation=operation,
            user_sub=user_sub,
            actor_sub=self.settings.orchestrator_agent_id,
            target_service=target_service,
            scopes=scopes,
            success=success,
            error=error
        )
        self._audit_log.append(entry)

_token_broker: Optional[TokenBroker] = None

def get_token_broker() -> TokenBroker:
    global _token_broker
    if _token_broker is None:
        _token_broker = TokenBroker()
    return _token_broker
