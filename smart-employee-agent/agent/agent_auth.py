"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Agent Token Management

  Manages the agent's own identity token using Asgardeo's App Native
  Authentication flow. The agent authenticates as a first-class identity
  (registered under Console > Agents) — not via client credentials.
  Auto-refreshes the token when it approaches expiry (30-second buffer).
"""

import os
import time
import logging

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from token_debug import dump_encoded

logger = logging.getLogger(__name__)

REFRESH_BUFFER_SECONDS = 30

# Scopes the HR Agent requests for itself. 'it_agent_invoke' is what authorizes
# it to call the IT Agent (Pattern 4) — the IT Agent checks for it before doing
# any work. Asgardeo grants only the subset this agent's role permits, so
# requesting a scope the role lacks is safe: it is silently dropped.
AGENT_SCOPES = ["openid", "hr_basic_mcp", "it_agent_invoke"]


def _required_env(key: str) -> str:
    """Read an environment variable or raise if missing/empty."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


class AgentAuth:
    """Manages the agent's own token via Asgardeo App Native Auth."""

    def __init__(self):
        self._asgardeo_config = AsgardeoConfig(
            base_url=_required_env("ASGARDEO_BASE_URL"),
            client_id=_required_env("ASGARDEO_CLIENT_ID"),
            redirect_uri=_required_env("OBO_REDIRECT_URI"),
        )
        self._agent_config = AgentConfig(
            agent_id=_required_env("AGENT_ID"),
            agent_secret=_required_env("AGENT_SECRET"),
        )
        self._token = None
        self._expires_at: float = 0.0

    @property
    def asgardeo_config(self) -> AsgardeoConfig:
        """Asgardeo configuration for SDK calls."""
        return self._asgardeo_config

    @property
    def agent_config(self) -> AgentConfig:
        """Agent configuration for SDK calls."""
        return self._agent_config

    async def ensure_valid_token(self):
        """Return a valid agent token, refreshing if needed."""
        if self._token and time.time() < (self._expires_at - REFRESH_BUFFER_SECONDS):
            return self._token

        logger.info("Obtaining agent token via App Native Auth...")
        async with AgentAuthManager(self._asgardeo_config, self._agent_config) as auth_manager:
            self._token = await auth_manager.get_agent_token(AGENT_SCOPES)

        if hasattr(self._token, "expires_in") and self._token.expires_in:
            self._expires_at = time.time() + self._token.expires_in
        else:
            self._expires_at = time.time() + 3600

        # Fires once per refresh (roughly hourly), not per request — the token
        # is cached for its lifetime. This is the agent acting as ITSELF, so
        # the dump shows no `act` claim: there is no user behind it.
        dump_encoded("[AGENT] Agent Token (own identity)", self._token.access_token)
        logger.info(
            "Agent token obtained (granted scopes: %s)",
            getattr(self._token, "scope", None) or "(none)",
        )
        return self._token
