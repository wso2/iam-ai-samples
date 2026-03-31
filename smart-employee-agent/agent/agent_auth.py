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

logger = logging.getLogger(__name__)

REFRESH_BUFFER_SECONDS = 30


class AgentAuth:
    """Manages the agent's own token via Asgardeo App Native Auth."""

    def __init__(self):
        self._asgardeo_config = AsgardeoConfig(
            base_url=os.getenv("ASGARDEO_BASE_URL"),
            client_id=os.getenv("ASGARDEO_CLIENT_ID"),
            redirect_uri=os.getenv("OBO_REDIRECT_URI"),
        )
        self._agent_config = AgentConfig(
            agent_id=os.getenv("AGENT_ID"),
            agent_secret=os.getenv("AGENT_SECRET"),
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
            self._token = await auth_manager.get_agent_token(["openid", "hr_basic_mcp"])

        if hasattr(self._token, "expires_in") and self._token.expires_in:
            self._expires_at = time.time() + self._token.expires_in
        else:
            self._expires_at = time.time() + 3600

        logger.info("Agent token obtained (scopes: hr_basic_mcp)")
        return self._token
