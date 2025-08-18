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
from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, Field


class OAuthTokenType(str, Enum):
    """OAuth token types supported by the authentication system."""
    OBO_TOKEN = "authorization_code"
    AGENT_TOKEN = "agent_token"


class AuthConfig(BaseModel):
    """Configuration for authentication requests.
    
    Attributes:
        scopes: List of OAuth scopes required for the token
        token_type: Type of OAuth token to request
        resource: Target resource for the token
    """
    scopes: List[str] = Field(default_factory=list)
    token_type: OAuthTokenType = OAuthTokenType.AGENT_TOKEN
    resource: str

    class Config:
        frozen = True


class AuthRequestMessage(BaseModel):
    """Message sent to request user authorization.
    
    Attributes:
        type: Message type identifier
        auth_url: Authorization URL for user to visit
        state: OAuth state parameter for security
        scopes: Required OAuth scopes
    """
    type: Literal["auth_request"] = "auth_request"
    auth_url: str
    state: str
    scopes: List[str]
