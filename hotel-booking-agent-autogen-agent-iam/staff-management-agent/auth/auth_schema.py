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
import logging


from .models import AuthConfig, OAuthTokenType
from .auth_manager import AutogenAuthManager


logger = logging.getLogger(__name__)

class AuthSchema:
    """Schema for validating authentication manager configuration.
    
    This class ensures that the authentication manager is properly configured
    for the requested token type and validates required components.
    """
    
    def __init__(self, manager: AutogenAuthManager, config: AuthConfig):
        """Initialize the authentication schema validator.
        
        Args:
            manager: Authentication manager instance to validate
            config: Authentication configuration to validate against
            
        Raises:
            ValueError: If manager configuration is invalid for the token type
        """
        self.manager = manager
        self.config = config
        self._validate_manager()

    def _validate_manager(self) -> None:
        """Validate the manager configuration based on the token type.
        
        Raises:
            ValueError: If required components are missing for the token type
        """
        if self.config.token_type == OAuthTokenType.OBO_TOKEN:
            if not self.manager.get_message_handler():
                raise ValueError(
                    "Message handler is required for OBO token authentication. "
                    "Please provide a message_handler when initializing AutogenAuthManager."
                )
