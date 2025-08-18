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
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
from .jwt_client import jwt_client

logger = logging.getLogger(__name__)

class AsgardeoSCIMService:
    """Service for interacting with Asgardeo SCIM APIs to fetch user and agent information"""
    
    def __init__(self):
        self.base_url = os.getenv('ASGARDEO_SCIM_BASE_URL', 'https://dev.api.asgardeo.io/t/myagents')
        self.scim_scope = 'internal_user_mgt_view'
        
        # Data caching - configurable TTL in seconds (default 30 minutes)
        self._cache_ttl = int(os.getenv('SCIM_CACHE_TTL', '1800'))  # 30 minutes
        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._agent_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
    
    async def _get_access_token(self) -> Optional[str]:
        """Get access token using shared JWT client"""
        return await jwt_client.get_access_token(self.scim_scope)
    
    def _is_cache_valid(self, cached_item: Dict[str, Any]) -> bool:
        """Check if cached item is still valid"""
        if not cached_item:
            return False
        
        cached_at = cached_item.get('cached_at')
        if not cached_at:
            return False
        
        return (datetime.now() - cached_at).total_seconds() < self._cache_ttl
    
    async def _get_from_cache(self, cache: Dict[str, Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
        """Get item from cache if valid"""
        async with self._cache_lock:
            cached_item = cache.get(key)
            if self._is_cache_valid(cached_item):
                logger.debug(f"Cache hit for {key}")
                return cached_item.get('data')
            elif cached_item:
                # Remove expired cache entry
                logger.debug(f"Cache expired for {key}, removing")
                cache.pop(key, None)
            return None
    
    async def _set_cache(self, cache: Dict[str, Dict[str, Any]], key: str, data: Dict[str, Any]) -> None:
        """Set item in cache with timestamp"""
        async with self._cache_lock:
            cache[key] = {
                'data': data,
                'cached_at': datetime.now()
            }
            logger.debug(f"Cached data for {key}")
    
    async def clear_cache(self) -> None:
        """Clear all cached data (useful for testing or manual refresh)"""
        async with self._cache_lock:
            self._user_cache.clear()
            self._agent_cache.clear()
            logger.info("Cleared all SCIM cache data")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            'user_cache_size': len(self._user_cache),
            'agent_cache_size': len(self._agent_cache),
            'cache_ttl_seconds': self._cache_ttl,
            'valid_user_entries': sum(1 for item in self._user_cache.values() if self._is_cache_valid(item)),
            'valid_agent_entries': sum(1 for item in self._agent_cache.values() if self._is_cache_valid(item))
        }
    
    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user information from Asgardeo SCIM Users API with caching"""
        # Check cache first
        cached_user = await self._get_from_cache(self._user_cache, user_id)
        if cached_user:
            return cached_user
        
        access_token = await self._get_access_token()
        if not access_token:
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/scim2/Users/{user_id}",
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Accept': 'application/scim+json'
                    }
                )
                response.raise_for_status()
                
                user_data = response.json()
                
                # Extract relevant user information
                name = user_data.get('name', {})
                emails = user_data.get('emails', [])
                
                user_info = {
                    'id': user_data.get('id'),
                    'userName': user_data.get('userName'),
                    'email': emails[0] if emails else None,
                    'first_name': name.get('givenName'),
                    'last_name': name.get('familyName'),
                    'display_name': f"{name.get('givenName', '')} {name.get('familyName', '')}".strip(),
                    'source': 'asgardeo_scim'
                }
                
                # Cache the result
                await self._set_cache(self._user_cache, user_id, user_info)
                logger.info(f"Fetched and cached user info for {user_id}")
                
                return user_info
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"User {user_id} not found in SCIM API")
                # Cache the negative result for a shorter time to avoid repeated calls
                await self._set_cache(self._user_cache, user_id, None)
            else:
                logger.error(f"SCIM API error for user {user_id}: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch user info for {user_id}: {str(e)}")
            return None
    
    async def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Fetch agent information from Asgardeo SCIM Agents API with caching"""
        # Check cache first
        cached_agent = await self._get_from_cache(self._agent_cache, agent_id)
        if cached_agent:
            return cached_agent
        
        access_token = await self._get_access_token()
        if not access_token:
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/scim2/Agents/{agent_id}",
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Accept': 'application/scim+json'
                    }
                )
                response.raise_for_status()
                
                agent_data = response.json()
                
                # Extract relevant agent information
                agent_schema = agent_data.get('urn:scim:wso2:agent:schema', {})
                
                agent_info = {
                    'id': agent_data.get('id'),
                    'userName': agent_data.get('userName'),
                    'display_name': agent_schema.get('DisplayName'),
                    'description': agent_schema.get('Description'),
                    'ai_model': agent_schema.get('AIModel'),
                    'owner': agent_schema.get('Owner'),
                    'source': 'asgardeo_scim'
                }
                
                # Cache the result
                await self._set_cache(self._agent_cache, agent_id, agent_info)
                logger.info(f"Fetched and cached agent info for {agent_id}")
                
                return agent_info
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Agent {agent_id} not found in SCIM API")
                # Cache the negative result for a shorter time to avoid repeated calls
                await self._set_cache(self._agent_cache, agent_id, None)
            else:
                logger.error(f"SCIM API error for agent {agent_id}: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch agent info for {agent_id}: {str(e)}")
            return None

# Global instance
scim_service = AsgardeoSCIMService()
