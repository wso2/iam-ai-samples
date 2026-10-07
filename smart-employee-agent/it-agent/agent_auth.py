"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT Agent Token Management

  The IT Agent is a first-class Asgardeo identity of its own — a *different*
  agent from the HR Agent, with its own credentials and its own role. It never
  borrows the HR Agent's token and never acts on a user's token; it calls the
  IT MCP server strictly as itself.

  Same caching contract as the HR Agent: one token per lifetime, refreshed on
  the first request that crosses the expiry buffer.
"""

import os
import time
import logging

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from token_debug import dump_encoded

logger = logging.getLogger(__name__)

REFRESH_BUFFER_SECONDS = 30

# Scopes the IT Agent needs on the IT MCP server. Asgardeo grants the subset
# its role actually permits, so requesting one the role lacks is safe.
IT_AGENT_SCOPES = ["openid", "it_basic_mcp", "it_ticket_mcp"]


def _required_env(key: str) -> str:
    """Read an environment variable or raise if missing/empty."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


class ITAgentAuth:
    """Manages the IT Agent's own token via Asgardeo App Native Auth."""

    def __init__(self):
        self._asgardeo_config = AsgardeoConfig(
            base_url=_required_env("ASGARDEO_BASE_URL"),
            client_id=_required_env("ASGARDEO_CLIENT_ID"),
            # App Native Auth never performs a browser redirect, but Asgardeo
            # still validates this against the callbacks registered on the
            # application — an unregistered value fails with
            # "invalid_callback - callback.not.match". Both agents authenticate
            # through the same MCP Client Application, so the HR agent's
            # registered callback is a valid value here.
            redirect_uri=_required_env("IT_REDIRECT_URI"),
        )
        self._agent_config = AgentConfig(
            agent_id=_required_env("IT_AGENT_ID"),
            agent_secret=_required_env("IT_AGENT_SECRET"),
        )
        self._token = None
        self._expires_at: float = 0.0

    @property
    def asgardeo_config(self) -> AsgardeoConfig:
        """Shared with the OBO flow, which authorizes users through this same
        application and needs the agent's own token as the actor token."""
        return self._asgardeo_config

    @property
    def agent_config(self) -> AgentConfig:
        return self._agent_config

    async def ensure_valid_token(self):
        """Return a valid IT agent token, refreshing if needed."""
        if self._token and time.time() < (self._expires_at - REFRESH_BUFFER_SECONDS):
            return self._token

        logger.info("Obtaining IT agent token via App Native Auth...")
        async with AgentAuthManager(self._asgardeo_config, self._agent_config) as auth_manager:
            self._token = await auth_manager.get_agent_token(IT_AGENT_SCOPES)

        if hasattr(self._token, "expires_in") and self._token.expires_in:
            self._expires_at = time.time() + self._token.expires_in
        else:
            self._expires_at = time.time() + 3600

        # A DIFFERENT agent identity from the HR agent, with its own scopes.
        # Dumping both makes that concrete: two subs, two scope sets.
        dump_encoded("[IT-AGENT] Agent Token (own identity)", self._token.access_token)
        logger.info(
            "IT agent token obtained (granted scopes: %s)",
            getattr(self._token, "scope", None) or "(none)",
        )
        return self._token
