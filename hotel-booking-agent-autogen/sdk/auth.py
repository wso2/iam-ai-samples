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

import requests
import pyotp
from typing import Optional

import base64
import hashlib
import secrets

import os

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_STORE_MAX_SIZE = 1000
DEFAULT_TOKEN_STORE_TTL = 3600
DEFAULT_AUTHORIZATION_TIMEOUT = 300  # 5 minute timeout

class OAuthTokenType(str, Enum):
    """OAuth token types supported by the tools"""
    CLIENT_TOKEN = "client_credentials"
    OBO_TOKEN = "authorization_code"
    AGENT_TOKEN = "agent_token"


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
    resource: str

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

class AgentConfig(BaseModel):
    agent_name: str
    agent_id: str
    agent_secret: str
    
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
            authorization_timeout: int = DEFAULT_AUTHORIZATION_TIMEOUT,
            agent_config: AgentConfig
    ):
        # Basic OAuth config
        if not idp_base_url.endswith("/"):
            idp_base_url = idp_base_url.rstrip("/")
        self.token_endpoint = f"{idp_base_url}/oauth2/token"
        self.authorize_endpoint = f"{idp_base_url}/oauth2/authorize"
        self.authn_url = f"{idp_base_url}/oauth2/authn"
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []
        self.authorization_timeout = authorization_timeout
        # Step 01
        self.agent_config = agent_config
        # Obtain the agent token when the auth manager is initialized
        self.agent_token = self.authenticate_agent_with_totp()

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
            verify=False,
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
            verify=False,
        )

        try:
            # Choose appropriate method to fetch the token
            if config.token_type == OAuthTokenType.OBO_TOKEN:  # Fetch OBO tokens
                if not code:
                    raise ValueError("'code' is required for OBO token")
                
                print("\n\n***********Agent Token In Memory***************:", self.agent_token, "\n\n")
                     
                # Step 03           
                token = await client.fetch_token(
                    url=self.token_endpoint,
                    code=code,
                    grant_type=OAuthTokenType.OBO_TOKEN,
                    actor_token=self.agent_token["access_token"] if self.agent_token else None,
                )
            elif config.token_type == OAuthTokenType.CLIENT_TOKEN:  # Fetch Client token
                token = await client.fetch_token(url=self.token_endpoint)
            elif config.token_type == OAuthTokenType.AGENT_TOKEN:
                token = self.authenticate_agent_with_totp(                    
                    config
                )
            else:
                raise ValueError(f"Unsupported token type: {config.token_type}")
        except Exception as e:
            logger.error(f"Error fetching token: {e}")
            raise

        return OAuthToken(**token)

    async def _fetch_obo_token(self, auth_config: AuthConfig) -> Optional["OAuthToken"]:
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
        self._pending_auths[state] = auth_config.scopes, auth_config.resource, future

        # TODO Support for PKCE
        # Construct authorization URL
        scope = " ".join(auth_config.scopes)
        params = [
            f"client_id={self.client_id}",
            "response_type=code",
            f"scope={scope}",
            f"redirect_uri={self.redirect_uri}",
            f"state={state}",
            f"requested_actor={self.agent_config.agent_id}"
        ]
        if auth_config.resource:
            params.append(f"resource={auth_config.resource}")
        auth_url = f"{self.authorize_endpoint}?" + "&".join(params)
        # log auth_url
        ##print("\n\n***********Auth URL***************:", auth_url, "\n\n")

        # Notify client via handler
        await self._message_handler(
            AuthRequestMessage(
                auth_url=auth_url,
                state=state,
                scopes=auth_config.scopes)
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

        # If a token exits, check if it is expired and if it is OBO token
        if token and token.is_expired() and config.token_type == OAuthTokenType.OBO_TOKEN:
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
        elif config.token_type == OAuthTokenType.AGENT_TOKEN:
            token = await self._fetch_oauth_token(config)
        else:
            raise ValueError(f"Unsupported token type: {config.token_type}")

        # Cache the token in token manager
        if token:
            self._token_manager.add_token(config, token)
        return token

    async def process_callback(self, state: str, code: str) -> OAuthToken:

        scopes, resource, future = self._pending_auths.pop(state, None)

        if not future and future.done():
            logger.error(f"No pending authorization for state: {state}")
            raise ValueError(f"Invalid state or no pending authorization.")

        try:
            token = await self._fetch_oauth_token(
                AuthConfig(scopes=scopes, token_type=OAuthTokenType.OBO_TOKEN, resource=resource), code=code
            )
            future.set_result(token)
            print("\n\n*****OBO Token Response*********:", token, "\n\n")
            return token
        except Exception as e:
            future.set_exception(e)
            logger.error(f"Error fetching token: {e}")
            raise
    
    # Step 02
    def authenticate_agent_with_totp(
        self,
        auth_config: Optional[AuthConfig] = None
    ):
        """
        Perform the full OAuth2 authentication flow for an agent using TOTP.

        Args:
            base_url (str): The base URL of the identity server.
            client_id (str): The OAuth2 client ID.
            redirect_uri (str): Redirect URI registered for the OAuth2 client.
            agent_name (str): The agent identifier (username).

        Returns:
            Optional[str]: The access token if successful, otherwise None.
        """
        # print("\n\n***********Agent Authentication Started***************\n\n")
        
        # print("\n\nAgent Config:", self.agent_config, "\n\n")
        # print("\n\nAuth Config:", auth_config, "\n\n")
        
        scopes = "openid"      
        if auth_config is not None:
             scopes = " ".join(auth_config.scopes)

        code_verifier = self.generate_code_verifier()
        code_challenge = self.generate_code_challenge(code_verifier)
        
        # TODO: Allow this to be overriden
        AGENT_DEFAULT_APP_CLIENT_ID = "vMH8K3zdIhlSiIDmmvnebNOI_bIa"

        # Step 1: Init Authorize
        authorize_data = {
            "client_id": AGENT_DEFAULT_APP_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": "1234",
            "scope": scopes,
            "response_mode": "direct",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "resource": "booking_api"
        }
        
        # print("\n\nAuthorize Data:", authorize_data, "\n\n")
        resp = requests.post(self.authorize_endpoint, data=authorize_data, verify=False)
        # resp.raise_for_status()
        resp_json = resp.json()
        # print("\n\nAuthorize Response:", resp_json, "\n\n")
        
        flow_id = resp_json.get("flowId")
        idf_authenticator_id = resp_json.get("nextStep", {}).get("authenticators", [{}])[0].get("authenticatorId")

        # Step 2: Authenticate with IDF
        idf_body = {
            "flowId": flow_id,
            "selectedAuthenticator": {
                "authenticatorId": idf_authenticator_id,
                "params": {
                    "username": self.agent_config.agent_name if self.agent_config else ""
                }
            }
        }
        
        resp = requests.post(self.authn_url, json=idf_body, verify=False)
        resp.raise_for_status()
        resp_json = resp.json()

        totp_authenticator_id = resp_json.get("nextStep", {}).get("authenticators", [{}])[0].get("authenticatorId")

        # Step 3: Authenticate with TOTP
        totp_token = pyotp.TOTP(self.agent_config.agent_secret).now()
        
        # print("\n\nTOTP Token:", totp_token, "\n\n")

        totp_body = {
            "flowId": flow_id,
            "selectedAuthenticator": {
                "authenticatorId": totp_authenticator_id,
                "params": {
                    "token": totp_token
                }
            }
        }
        resp = requests.post(self.authn_url, json=totp_body, verify=False)
        resp.raise_for_status()
        resp_json = resp.json()
        
        # print("\n\totp Auth Response:", resp_json, "\n\n")

        code = resp_json.get("authData", {}).get("code")
        if not code:
            return None

        # Step 4: Get token
        token_data = {
            "grant_type": "authorization_code",
            "client_id": AGENT_DEFAULT_APP_CLIENT_ID,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": self.redirect_uri,
            "scope": scopes,
            "resource": "booking_api"
        }
        
        # print("\n\nToken Data:", token_data, "\n\n")
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(self.token_endpoint, data=token_data, headers=headers, verify=False)
    
        resp.raise_for_status()
        resp_json = resp.json()
        
        # print(resp_json)
        
        # print("\n\nToken Response:", resp_json, "\n\n")
        #print("\n\n***********Agent Token***************:", resp_json.get("access_token"), "\n\n")

        return resp_json

    def generate_code_verifier(self, length: int = 64) -> str:
        return secrets.token_urlsafe(length)[:length]

    def generate_code_challenge(self, code_verifier: str) -> str:
        sha256_digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(sha256_digest).rstrip(b'=').decode('utf-8')
        return code_challenge


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
