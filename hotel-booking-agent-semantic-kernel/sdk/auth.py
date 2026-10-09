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
import time
from enum import Enum
from typing import List, Dict, Callable, Awaitable, Literal, get_type_hints, Tuple
from typing import Optional

from authlib.integrations.httpx_client import AsyncOAuth2Client
from cachetools import TTLCache
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_STORE_MAX_SIZE = 1000
DEFAULT_TOKEN_STORE_TTL = 3600
DEFAULT_AUTHORIZATION_TIMEOUT = 300  # 5 minute timeout


class OAuthTokenType(str, Enum):
    """OAuth token types supported by the tools"""
    CLIENT_TOKEN = "client_credentials"
    OBO_TOKEN = "authorization_code"


class OAuthToken(BaseModel):
    """OAuth token information"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None
    expires_at: Optional[float] = None

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        return time.time() >= self.expires_at - 60  # Refresh slightly early


class AuthConfig(BaseModel):
    """Context information for tool authorization"""
    scopes: List[str] = Field(default_factory=list)
    token_type: OAuthTokenType = OAuthTokenType.CLIENT_TOKEN

    class Config:
        frozen = True


class AuthRequestMessage(BaseModel):
    type: Literal["auth_request"] = "auth_request"
    auth_url: str
    state: str
    scopes: List[str]


class TokenManager:
    def __init__(self, maxsize=1000, ttl=3600):
        self.token_store = TTLCache(maxsize=maxsize, ttl=ttl)  # TTL in seconds

    def add_token(self, config: AuthConfig, token: OAuthToken):
        key = (frozenset(config.scopes), config.token_type)
        self.token_store[key] = token

    def get_token(self, config: AuthConfig) -> Optional[OAuthToken]:
        key = (frozenset(config.scopes), config.token_type)
        token = self.token_store.get(key)

        # clean the expired tokens
        if token and token.is_expired():
            _ = self.token_store.pop(config)

        return token


class AuthManager:
    def __init__(
            self,
            idp_base_url: str,
            client_id: str,
            client_secret: str,
            redirect_uri: Optional[str] = None,
            message_handler: Optional[Callable[[AuthRequestMessage], Awaitable[None]]] = None,
            scopes: Optional[List[str]] = None,
            *,
            token_store_maxsize: int = DEFAULT_TOKEN_STORE_MAX_SIZE,
            token_store_ttl: int = DEFAULT_TOKEN_STORE_TTL,
            authorization_timeout: int = DEFAULT_AUTHORIZATION_TIMEOUT
    ):
        # Basic OAuth config
        if not idp_base_url.endswith("/"):
            idp_base_url = idp_base_url.rstrip("/")
        self.token_endpoint = f"{idp_base_url}/oauth2/token"
        self.authorize_endpoint = f"{idp_base_url}/oauth2/authorize"
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []
        self.authorization_timeout = authorization_timeout

        # Pending authorization requests
        self._pending_auths: Dict[str, Tuple[List[str], asyncio.Future]] = {}

        # Optional message handler
        self._message_handler = message_handler

        # Token manager with configurable eviction
        self._token_manager: TokenManager = TokenManager(
            maxsize=token_store_maxsize,
            ttl=token_store_ttl
        )

        self._validate()

    def _validate(self):
        self._validate_message_handler()

    def _validate_message_handler(self):
        message_handler = self._message_handler
        if not message_handler:
            return
        if not callable(message_handler):
            raise TypeError("message_handler must be callable")
        if not inspect.iscoroutinefunction(message_handler):
            raise TypeError("message_handler must be an async function")

        signature = inspect.signature(message_handler)
        params = list(signature.parameters.values())

        if len(params) != 1:
            raise TypeError("message_handler must accept exactly one parameter")

        param_type = get_type_hints(message_handler).get(params[0].name)
        if param_type != AuthRequestMessage:
            raise TypeError(f"message_handler parameter must be of type AuthRequestMessage, not {param_type}")

    @staticmethod
    def _create_state() -> str:
        state = secrets.token_urlsafe(16)
        # self.state_mapping[state] = thread_id
        return state

    def get_message_handler(self) -> Callable[[AuthRequestMessage], Awaitable[None]]:
        return self._message_handler

    async def _refresh_oauth_token(self, refresh_token: str, scopes: List[str]) -> Optional[OAuthToken]:
        """Refresh OAuth token"""

        # If refresh token is empty, then stop token refreshing
        if not refresh_token:
            return None

        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=scopes,
        )

        try:
            token = await client.refresh_token(self.token_endpoint, refresh_token)  # Passing as string
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise

        return OAuthToken(**token)

    async def _fetch_oauth_token(self, config: AuthConfig, code: Optional[str] = None) -> OAuthToken:
        """Fetch Oauth token based on the token type (Client or OBO)"""
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,  # Only applicable for OBO token, else should be None
            scope=config.scopes,
        )

        try:
            # Choose appropriate method to fetch the token
            if config.token_type == OAuthTokenType.OBO_TOKEN:  # Fetch OBO tokens
                if not code:
                    raise ValueError("'code' is required for OBO token")
                token = await client.fetch_token(
                    url=self.token_endpoint,
                    code=code,
                    grant_type=OAuthTokenType.OBO_TOKEN
                )
            elif config.token_type == OAuthTokenType.CLIENT_TOKEN:  # Fetch Client token
                token = await client.fetch_token(url=self.token_endpoint)
            else:
                raise ValueError(f"Unsupported token type: {config.token_type}")
        except Exception as e:
            logger.error(f"Error fetching token: {e}")
            raise

        return OAuthToken(**token)

    async def _fetch_obo_token(self, config: AuthConfig) -> Optional["OAuthToken"]:
        """
        Fetches the OBO token for the given scopes.
        Requests user authorization and waits for a token asynchronously.

        Args:
            config (AuthConfig): The auth configuration

        Returns:
            Optional[OAuthToken]: The token received upon user authorization, or None if it fails or times out.
        """
        if not self._message_handler:
            logger.error(f"[Authorization Error] No message handler registered.")
            return None

        state = self._create_state()

        # Create a future to await authorization completion
        future = asyncio.Future()
        self._pending_auths[state] = config.scopes, future

        # TODO Support for PKCE
        # Construct authorization URL
        scope = " ".join(config.scopes)
        auth_url = (
            f"{self.authorize_endpoint}?"
            f"client_id={self.client_id}&"
            f"response_type=code&"
            f"scope={scope}&"
            f"redirect_uri={self.redirect_uri}&"
            f"state={state}"
        )

        # Notify client via handler
        await self._message_handler(
            AuthRequestMessage(
                auth_url=auth_url,
                state=state,
                scopes=config.scopes)
        )

        # Wait for authorization to complete (with timeout)
        try:
            token = await asyncio.wait_for(future, timeout=self.authorization_timeout)
            return token
        except asyncio.TimeoutError:
            logger.warning(f"Authorization timed out for session {state}")
            # Clean up the pending auth
            if state in self._pending_auths:
                future = self._pending_auths.pop(state)
                if not future.done():
                    future.cancel()
            return None

    async def get_oauth_token(self, config: AuthConfig) -> OAuthToken:
        """
        Fetches the OAuth token based on the token type (Client or OBO) and the scope

        Args:
            config (AuthConfig): The auth configuration

        Returns:
            OAuthToken: The OAuth token
        """

        # Check if a valid token exists already
        token = self._token_manager.get_token(config)

        # If a token exits, check if it is expired
        if token and token.is_expired():
            # If the token is expired, try refreshing it
            logger.debug("Token expired. Attempting to refresh %s for the scopes %s", config.token_type.name,
                         config.scopes)
            token = await self._refresh_oauth_token(token.refresh_token, config.scopes)

        # If token is available then return
        if token:
            return token

        logger.debug("Attempting to fetch %s for the scopes %s", config.token_type.name, config.scopes)
        if config.token_type == OAuthTokenType.OBO_TOKEN:
            token = await self._fetch_obo_token(config)
        elif config.token_type == OAuthTokenType.CLIENT_TOKEN:
            token = await self._fetch_oauth_token(config)
        else:
            raise ValueError(f"Unsupported token type: {config.token_type}")

        # Cache the token in token manager
        if token:
            self._token_manager.add_token(config, token)
        return token

    async def process_callback(self, state: str, code: str) -> OAuthToken:

        scopes, future = self._pending_auths.pop(state, None)

        if not future and future.done():
            logger.error(f"No pending authorization for state: {state}")
            raise ValueError(f"Invalid state or no pending authorization.")

        try:
            token = await self._fetch_oauth_token(
                AuthConfig(scopes=scopes, token_type=OAuthTokenType.OBO_TOKEN), code=code
            )
            future.set_result(token)
            return token
        except Exception as e:
            future.set_exception(e)
            logger.error(f"Error fetching token: {e}")
            raise


class AuthSchema:
    def __init__(self, manager: AuthManager, config: AuthConfig):
        self.manager = manager
        self.config = config
        self._validate_manager()  # Validate the manager based on the grant type

    def _validate_manager(self):
        if self.config.token_type is OAuthTokenType.OBO_TOKEN:
            if not self.manager.redirect_uri:
                raise ValueError(
                    "Redirect URI is required for authorization code grant type."
                )
            if not self.manager.get_message_handler():
                raise ValueError(
                    "Message handler is required for authorization code grant type."
                )
