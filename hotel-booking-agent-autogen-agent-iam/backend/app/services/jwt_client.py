"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any
"""

import os
import httpx
import logging
from typing import Optional
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

class JWTTokenClient:
    """Generic JWT token client for OAuth2 client credentials flow"""
    
    def __init__(self):
        self.client_id = os.getenv('ASGARDEO_SCIM_CLIENT_ID')
        self.client_secret = os.getenv('ASGARDEO_SCIM_CLIENT_SECRET')
        self.token_endpoint = os.getenv('ASGARDEO_TOKEN_ENDPOINT', 'https://dev.api.asgardeo.io/t/myagents/oauth2/token')
        
        # Token caching
        self._tokens = {}  # scope -> token_data
        self._token_lock = asyncio.Lock()
        
        if not all([self.client_id, self.client_secret]):
            logger.warning("JWT client credentials not configured. Token requests will fail.")
    
    async def get_access_token(self, scope: str) -> Optional[str]:
        """Get access token for specific scope using client credentials grant"""
        async with self._token_lock:
            # Check if we have a valid cached token for this scope
            token_data = self._tokens.get(scope)
            if (token_data and 
                token_data.get('expires_at') and 
                datetime.now() < token_data['expires_at']):
                logger.debug(f"Using cached token for scope: {scope}")
                return token_data['access_token']
            
            if not all([self.client_id, self.client_secret]):
                logger.error("Missing JWT client credentials")
                return None
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.token_endpoint,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        data={
                            'grant_type': 'client_credentials',
                            'client_id': self.client_id,
                            'client_secret': self.client_secret,
                            'scope': scope
                        }
                    )
                    response.raise_for_status()
                    
                    token_response = response.json()
                    access_token = token_response.get('access_token')
                    expires_in = token_response.get('expires_in', 3600)  # Default 1 hour
                    
                    # Set expiration with 5-minute buffer
                    expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                    
                    # Cache the token for this scope
                    self._tokens[scope] = {
                        'access_token': access_token,
                        'expires_at': expires_at,
                        'scope': scope
                    }
                    
                    logger.info(f"Successfully obtained JWT access token for scope: {scope}")
                    return access_token
                    
            except Exception as e:
                logger.error(f"Failed to get JWT access token for scope {scope}: {str(e)}")
                return None
    
    def clear_token_cache(self, scope: Optional[str] = None) -> None:
        """Clear cached tokens (for specific scope or all)"""
        if scope:
            self._tokens.pop(scope, None)
            logger.info(f"Cleared cached token for scope: {scope}")
        else:
            self._tokens.clear()
            logger.info("Cleared all cached tokens")
    
    def get_token_stats(self) -> dict:
        """Get token cache statistics for monitoring"""
        valid_tokens = 0
        for token_data in self._tokens.values():
            if (token_data.get('expires_at') and 
                datetime.now() < token_data['expires_at']):
                valid_tokens += 1
        
        return {
            'total_cached_tokens': len(self._tokens),
            'valid_tokens': valid_tokens,
            'cached_scopes': list(self._tokens.keys())
        }

# Global instance
jwt_client = JWTTokenClient()
