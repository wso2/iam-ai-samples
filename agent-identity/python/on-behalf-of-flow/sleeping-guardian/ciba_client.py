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

import asyncio
import time
import jwt as pyjwt
from datetime import datetime
from typing import Optional, Dict
from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager


class CIBAClient:
    """
    Client for interacting with WSO2 Identity Server's CIBA (Client Initiated Backchannel Authentication).
    Handles the complete CIBA flow for agent authorization.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        agent_id: str,
        agent_secret: str,
        redirect_uri: str = "http://localhost:5001/callback",
        notification_channel: str = "email"
    ):
        # Configure Asgardeo settings
        self.asgardeo_config = AsgardeoConfig(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri  # Required by SDK even though CIBA doesn't use it
        )

        # Configure Agent identity
        self.agent_config = AgentConfig(
            agent_id=agent_id,
            agent_secret=agent_secret,
        )

        self.notification_channel = notification_channel
        self.auth_manager = None
        self.current_agent_token = None
        self.obo_token = None
        self.obo_expires_at = 0

    async def initialize(self):
        """Initialize the auth manager and get agent token."""
        if self.auth_manager is None:
            self.auth_manager = AgentAuthManager(
                self.asgardeo_config,
                self.agent_config
            )
            await self.auth_manager.__aenter__()

        # Get agent token with minimal permissions
        try:
            self.current_agent_token = await self.auth_manager.get_agent_token([
                "openid",
                "stock:read"
            ])
            print(f"[CIBA Client] ✓ Agent token obtained successfully")
            return self.current_agent_token
        except Exception as e:
            print(f"[CIBA Client] ✗ Failed to get agent token: {e}")
            raise

    async def request_trade_authorization(
        self,
        user_email: str,
        stock_symbol: str,
        current_price: float,
        trade_amount: float,
        shares: int,
        required_scopes: list = None
    ) -> Optional[Dict]:
        """
        Request authorization from user via CIBA to execute a trade.

        Args:
            user_email: Email of the user to request authorization from
            stock_symbol: Stock symbol (e.g., "NVDA")
            current_price: Current stock price
            trade_amount: Total trade amount in dollars
            shares: Number of shares to buy
            required_scopes: List of required scopes (default: ["openid", "stock:read", "stock:trade"])

        Returns:
            Dictionary with auth_req_id and token, or None if failed
        """
        if required_scopes is None:
            required_scopes = ["openid", "stock:read", "stock:trade"]

        # Ensure we have an agent token
        if not self.current_agent_token:
            await self.initialize()

        # Create a sanitized binding message (avoid emojis and special chars that trigger WAF)
        binding_message = (
            f"AI agent requests permission to buy {shares} shares of {stock_symbol} "
            f"at {current_price:.2f} for {trade_amount:.2f}"
        )

        print(f"\n{'='*80}")
        print(f"[CIBA] Initiating authorization request")
        print(f"[CIBA] User: {user_email}")
        print(f"[CIBA] Channel: {self.notification_channel}")
        print(f"[CIBA] 🔍 REQUESTED SCOPES: {required_scopes}")
        print(f"{'='*80}\n")

        auth_req_id = None
        expires_in = None

        def on_initiated(response):
            """Callback when CIBA request is initiated."""
            nonlocal auth_req_id, expires_in
            auth_req_id = response.auth_req_id
            expires_in = response.expires_in

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📩 Authorization request sent via {self.notification_channel}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Waiting up to {expires_in}s for user approval...")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Request ID: {auth_req_id}")

        try:
            # Request OBO token via CIBA
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Starting CIBA polling...")

            _, obo_token = await self.auth_manager.get_obo_token_with_ciba(
                login_hint=user_email,
                agent_token=self.current_agent_token,
                scopes=required_scopes,
                binding_message=binding_message,
                notification_channel=self.notification_channel,
                on_initiated=on_initiated
            )

            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] CIBA polling completed!")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Authorization approved!")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ On-behalf-of token obtained")

            # DEBUG: Decode token to verify scopes
            token_payload = pyjwt.decode(obo_token.access_token, options={"verify_signature": False})
            actual_scope = token_payload.get('scope', '')
            actual_scopes_list = actual_scope.split() if actual_scope else []

            print(f"\n{'='*80}")
            print(f"[CIBA] 🔍 SCOPE VALIDATION")
            print(f"[CIBA] REQUESTED: {required_scopes}")
            print(f"[CIBA] RECEIVED : {actual_scopes_list}")
            print(f"[CIBA] TOKEN SUB: {token_payload.get('sub', 'N/A')}")
            print(f"[CIBA] TOKEN AUT: {token_payload.get('aut', 'N/A')}")

            # Check for missing scopes
            missing_scopes = [s for s in required_scopes if s not in actual_scopes_list]
            if missing_scopes:
                print(f"[CIBA] ⚠️  WARNING: MISSING SCOPES: {missing_scopes}")
                print(f"[CIBA] ⚠️  This may cause MCP tool calls to fail!")
            else:
                print(f"[CIBA] ✅ All requested scopes granted")
            print(f"{'='*80}\n")

            return {
                'auth_req_id': auth_req_id,
                'token': obo_token,
                'approved': True,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            error_msg = str(e)
            print(f"\n{'='*80}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Authorization failed")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Exception type: {type(e).__name__}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Error message: {error_msg}")
            print(f"{'='*80}\n")

            if "access_denied" in error_msg:
                print(f"[{datetime.now().strftime('%H:%M:%S')}]   Reason: User denied the request")
                return {
                    'auth_req_id': auth_req_id,
                    'approved': False,
                    'denied': True,
                    'error': 'access_denied',
                    'timestamp': datetime.now().isoformat()
                }
            elif "expired_token" in error_msg or "timed out" in error_msg:
                print(f"[{datetime.now().strftime('%H:%M:%S')}]   Reason: Request timed out")
                return {
                    'auth_req_id': auth_req_id,
                    'approved': False,
                    'timeout': True,
                    'error': 'timeout',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}]   Reason: {error_msg}")
                return {
                    'auth_req_id': auth_req_id,
                    'approved': False,
                    'error': error_msg,
                    'timestamp': datetime.now().isoformat()
                }

    async def get_agent_token(self, scopes: list = None):
        """Get or refresh agent token."""
        if scopes is None:
            scopes = ["openid", "stock:read"]

        if not self.auth_manager:
            await self.initialize()

        self.current_agent_token = await self.auth_manager.get_agent_token(scopes)
        return self.current_agent_token

    async def cleanup(self):
        """Cleanup resources."""
        if self.auth_manager:
            await self.auth_manager.__aexit__(None, None, None)
            self.auth_manager = None
