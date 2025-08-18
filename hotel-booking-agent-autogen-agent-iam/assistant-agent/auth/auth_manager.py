"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you’ve
  entered into with WSO2 governing the purchase of this software and any
"""
import asyncio
import inspect
import logging
import secrets
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, get_type_hints


from .models import AuthConfig, AuthRequestMessage, OAuthTokenType
from .token_manager import DEFAULT_TOKEN_STORE_MAX_SIZE, DEFAULT_TOKEN_STORE_TTL, TokenManager

from asgardeo.models import AsgardeoConfig, OAuthToken
from asgardeo_ai.agent_auth_manager import AgentAuthManager
from asgardeo_ai import AgentConfig

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_AUTHORIZATION_TIMEOUT = 300  # 5 minutes in seconds

class AutogenAuthManager:
    """Main authentication manager for handling OAuth flows and token management.
    
    This class manages both agent-based authentication and On-Behalf-Of (OBO) token flows,
    with support for token caching, refresh, and authorization callback handling.
    """
    
    def __init__(
        self,
        config: AsgardeoConfig,
        agent_config: AgentConfig,
        message_handler: Optional[Callable[[AuthRequestMessage], Awaitable[None]]] = None,
        token_store_maxsize: int = DEFAULT_TOKEN_STORE_MAX_SIZE,
        token_store_ttl: int = DEFAULT_TOKEN_STORE_TTL,
        authorization_timeout: int = DEFAULT_AUTHORIZATION_TIMEOUT,
    ):
        """Initialize the authentication manager.
        
        Args:
            server_config: OAuth server configuration
            client_config: OAuth client configuration
            agent_config: Agent-specific configuration
            message_handler: Optional handler for authorization request messages
            token_store_maxsize: Maximum size of token cache
            token_store_ttl: Token cache TTL in seconds
            authorization_timeout: Timeout for authorization flows in seconds
        """
        self.authorization_timeout = authorization_timeout
        self._pending_auths: Dict[str, Tuple[List[str], str, asyncio.Future, str]] = {}
        self._message_handler = message_handler
        self._token_manager = TokenManager(
            maxsize=token_store_maxsize,
            ttl=token_store_ttl
        )
        
        self.agent_auth_manager = AgentAuthManager(
            config=config,
            agent_config=agent_config,
        )
        
        self.agent_token: Optional[OAuthToken] = None
        self._validate()

    # Public API methods
    async def get_oauth_token(self, config: AuthConfig) -> Optional[OAuthToken]:
        """Get an OAuth token based on the provided configuration.
        
        Args:
            config: Authentication configuration specifying token type and scopes
            
        Returns:
            OAuth token if successful, None otherwise
            
        Raises:
            ValueError: For unsupported token types
        """
        # Check cache first
        token = self._token_manager.get_token(config)

        if token:
            return token

        # Fetch new token
        logger.debug("Fetching new %s for scopes %s", config.token_type.name, config.scopes)
        
        if config.token_type == OAuthTokenType.OBO_TOKEN:
            token = await self._fetch_obo_token(config)
        elif config.token_type == OAuthTokenType.AGENT_TOKEN:
            token = await self._fetch_agent_token(config)
        else:
            raise ValueError(f"Unsupported token type: {config.token_type}")

        # Cache the token
        if token:
            self._token_manager.add_token(config, token)
            
        return token

    async def process_callback(self, state: str, code: str) -> OAuthToken:
        """Process OAuth authorization callback.
        
        Args:
            state: OAuth state parameter
            code: Authorization code from OAuth provider
            
        Returns:
            OAuth token obtained from the authorization code
            
        Raises:
            ValueError: If state is invalid or authorization failed
        """
        auth_data = self._pending_auths.pop(state, None)
        if not auth_data:
            logger.error(f"No pending authorization for state: {state}")
            raise ValueError("Invalid state or no pending authorization")

        scopes, resource, future, code_verifier = auth_data

        if future.done():
            logger.error(f"Authorization already completed for state: {state}")
            raise ValueError("Authorization already completed")

        try:
            config = AuthConfig(scopes=scopes, token_type=OAuthTokenType.OBO_TOKEN, resource=resource)
            token = await self._fetch_oauth_token(config, code=code, code_verifier=code_verifier)
            future.set_result(token)
            logger.info(f"Successfully obtained OBO token for scopes: {scopes}")
            return token
        except Exception as e:
            future.set_exception(e)
            logger.error(f"Error processing authorization callback: {e}")
            raise

    def get_message_handler(self) -> Optional[Callable[[AuthRequestMessage], Awaitable[None]]]:
        """Get the registered message handler.
        
        Returns:
            Message handler function if registered, None otherwise
        """
        return self._message_handler

    # Private helper methods
    def _validate(self) -> None:
        """Validate the configuration and components."""
        self._validate_message_handler()

    def _validate_message_handler(self) -> None:
        """Validate the message handler if provided."""
        if not self._message_handler:
            return
            
        if not callable(self._message_handler):
            raise TypeError("message_handler must be callable")
            
        if not inspect.iscoroutinefunction(self._message_handler):
            raise TypeError("message_handler must be an async function")

        signature = inspect.signature(self._message_handler)
        params = list(signature.parameters.values())

        if len(params) != 1:
            raise TypeError("message_handler must accept exactly one parameter")

        param_type = get_type_hints(self._message_handler).get(params[0].name)
        if param_type != AuthRequestMessage:
            raise TypeError(f"message_handler parameter must be of type AuthRequestMessage, not {param_type}")

    async def _ensure_agent_token(self) -> OAuthToken:
        """Ensure agent token is available, fetch if not present."""
        if self.agent_token is None:
            self.agent_token = await self._fetch_agent_token()
        return self.agent_token

    async def _fetch_agent_token(self, config: Optional[AuthConfig] = None) -> OAuthToken:
        """Fetch an agent token using agent credentials.
        
        Args:
            config: Optional authentication configuration for scopes
            
        Returns:
            Agent OAuth token
        """
        scopes = config.scopes if config else []
        return await self.agent_auth_manager.get_agent_token(scopes)

    async def _fetch_oauth_token(
        self, 
        config: AuthConfig, 
        code: Optional[str] = None, 
        code_verifier: Optional[str] = None
    ) -> OAuthToken:
        """Fetch OAuth token based on the token type.
        
        Args:
            config: Authentication configuration
            code: Authorization code (required for OBO tokens)
            
        Returns:
            OAuth token
            
        Raises:
            ValueError: If required parameters are missing or token type is unsupported
        """
        try:
            if config.token_type == OAuthTokenType.OBO_TOKEN:
                if not code:
                    raise ValueError("Authorization code is required for OBO token")
                
                await self._ensure_agent_token()
                return await self.agent_auth_manager.get_obo_token(
                    auth_code=code,
                    agent_token=self.agent_token,
                    code_verifier=code_verifier
                )
            elif config.token_type == OAuthTokenType.AGENT_TOKEN:
                return await self._fetch_agent_token(config)
            else:
                raise ValueError(f"Unsupported token type: {config.token_type}")
        except Exception as e:
            logger.error(f"Error fetching {config.token_type} token: {e}")
            raise

    async def _fetch_obo_token(self, config: AuthConfig) -> Optional[OAuthToken]:
        """Initiate OBO token flow by requesting user authorization.
        
        Args:
            config: Authentication configuration
            
        Returns:
            OAuth token if authorization succeeds, None otherwise
        """
        if not self._message_handler:
            logger.error("No message handler registered for OBO token flow")
            return None

        try:

            auth_url, state, code_verifier = self.agent_auth_manager.get_authorization_url_with_pkce(
                scopes=config.scopes
            )

            # Create future to await authorization completion
            future = asyncio.Future()
            self._pending_auths[state] = (config.scopes, config.resource, future, code_verifier)

            # Notify client via handler
            await self._message_handler(
                AuthRequestMessage(
                    auth_url=auth_url,
                    state=state,
                    scopes=config.scopes
                )
            )

            # Wait for authorization with timeout
            try:
                token = await asyncio.wait_for(future, timeout=self.authorization_timeout)
                return token
            except asyncio.TimeoutError:
                logger.warning(f"Authorization timed out for state: {state}")
                self._cleanup_pending_auth(state)
                return None
                
        except Exception as e:
            logger.error(f"Error initiating OBO token flow: {e}")
            return None

    def _cleanup_pending_auth(self, state: str) -> None:
        """Clean up a pending authorization request.
        
        Args:
            state: OAuth state parameter to clean up
        """
        if state in self._pending_auths:
            _, _, future, _ = self._pending_auths.pop(state)
            if not future.done():
                future.cancel()

    @staticmethod
    def _create_state() -> str:
        """Create a secure random state parameter for OAuth.
        
        Returns:
            URL-safe random string
        """
        return secrets.token_urlsafe(16)
