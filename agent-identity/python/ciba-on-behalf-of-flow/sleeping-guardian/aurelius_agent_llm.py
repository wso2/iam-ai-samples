"""
Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

 This software is the property of WSO2 LLC. and its suppliers, if any.
 Dissemination of any information or reproduction of any material contained
 herein is strictly forbidden, unless permitted by WSO2 in accordance with
 the WSO2 Commercial License available at http://wso2.com/licenses.
 For specific language governing the permissions and limitations under
 this license, please see the license as well as any agreement you've
 entered into with WSO2 governing the purchase of this software and any
"""

import os
import asyncio
import threading
from datetime import datetime
from typing import Dict, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools.base import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

# LLM imports
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from market_engine import MarketEngine
from ciba_client import CIBAClient


INSUFFICIENT_SCOPE_SENTINEL = "insufficient_scope"


class AureliusAgentLLM:
    """
    The Aurelius AI Agent with LLM-powered reasoning.

    Uses LangChain + MCP tools to:
    1. Monitor stock market with AI analysis
    2. Decide when to trade based on market conditions
    3. Request CIBA authorization for high-value trades
    4. Execute trades using MCP stock server
    """

    def __init__(
        self,
        market_engine: MarketEngine,
        ciba_client: CIBAClient,
        user_email: str,
        mcp_server_url: str,
        model_name: str = "gemini-2.0-flash-exp",
        price_threshold: float = 140.00,
        trade_amount: float = 5000.00,
        initial_balance: float = 10000.00
    ):
        self.market_engine = market_engine
        self.ciba_client = ciba_client
        self.user_email = user_email
        self.mcp_server_url = mcp_server_url
        self.model_name = model_name
        self.price_threshold = price_threshold
        self.trade_amount = trade_amount

        # Agent state
        self.current_agent_token = None
        self.current_obo_token = None
        self.current_scopes = ["openid", "stock:read"]
        self.lock = threading.Lock()

        # History tracking (for UI display)
        self.history = []
        self.balance = initial_balance
        self.shares = 0
        self.initial_balance = initial_balance

        # LangChain components
        self.llm = None
        self.agent_executor = None
        self.mcp_client = None

        # Running state
        self.running = False
        self.monitoring = True
        self._event_loop = None

    def _initialize_llm(self):
        """Initialize the LLM using Google Gemini."""
        if not GOOGLE_AVAILABLE:
            raise ValueError(
                "langchain-google-genai package not installed. Please run: pip install langchain-google-genai"
            )

        if not os.getenv("GOOGLE_AI_API_KEY"):
            raise ValueError(
                "GOOGLE_AI_API_KEY not set in environment. Get your API key from https://aistudio.google.com/app/apikey"
            )

        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=0.7,
            google_api_key=os.getenv("GOOGLE_AI_API_KEY")
        )
        print(f"[Aurelius LLM] Using Google Gemini: {self.model_name}")

    def _build_mcp_config(self, access_token: str) -> dict:
        """Build MCP client configuration with access token."""
        return {
            "stock_server": {
                "transport": "streamable_http",
                "url": self.mcp_server_url,
                "headers": {
                    "Authorization": f"Bearer {access_token}",
                },
            }
        }

    async def _initialize_agent(self, access_token: str):
        """Initialize LangChain agent with MCP tools."""
        # DEBUG: Show token scopes being used
        import jwt as pyjwt
        token_payload = pyjwt.decode(access_token, options={"verify_signature": False})
        token_scopes = token_payload.get('scope', '').split() if token_payload.get('scope') else []

        print(f"\n[Aurelius LLM] 🔧 Initializing MCP Client")
        print(f"[Aurelius LLM] 🔍 Token Scopes: {token_scopes}")
        print(f"[Aurelius LLM] 🔍 Token Sub: {token_payload.get('sub', 'N/A')}")

        # Create MCP client with current token
        self.mcp_client = MultiServerMCPClient(self._build_mcp_config(access_token))

        # Get tools from MCP server
        tools = await self.mcp_client.get_tools()

        print(f"[Aurelius LLM] ✓ Loaded {len(tools)} tools from MCP server")

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Aurelius, an AI trading agent for {investor_name}.

Your responsibilities:
1. Monitor stock market prices continuously
2. Analyze market conditions using available tools
3. Identify golden buy opportunities during market crashes
4. Make informed trading decisions based on data

Current context:
- Stock Symbol: {symbol}
- Price Threshold: ${threshold:.2f} (buy when price drops below this)
- Trade Budget: ${budget:.2f}
- Current Scopes: {scopes}

Important rules:
- Always check current market price before making decisions
- Only recommend trades when price is significantly below threshold
- Explain your reasoning clearly
- If you get "insufficient_scope" error, report it clearly so CIBA authorization can be requested

Be concise and actionable in your responses."""),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        # Create agent
        agent = create_tool_calling_agent(self.llm, tools, prompt)

        # Custom error handler: re-raise scope errors so they trigger CIBA.
        # Other tool errors (e.g. "unknown symbol") are shown to the LLM as text.
        def _scope_aware_error_handler(error: Exception) -> str:
            err_str = str(error)
            if INSUFFICIENT_SCOPE_SENTINEL in err_str:
                # Re-raise so our outer except ToolException block catches it
                raise ToolException(err_str)
            return f"Tool error: {err_str}"

        # Create executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=5,
            early_stopping_method="generate",
            handle_tool_errors=_scope_aware_error_handler,
        )

    async def start(self):
        """Start the Aurelius agent."""
        self.running = True

        # Store reference to the event loop for cleanup
        self._event_loop = asyncio.get_event_loop()

        # Initialize CIBA client and get initial token
        await self.ciba_client.initialize()
        self.current_agent_token = self.ciba_client.current_agent_token

        # Initialize LLM
        self._initialize_llm()

        # Initialize agent with initial token
        await self._initialize_agent(self.current_agent_token.access_token)

        print(f"[Aurelius] 🤖 AI Agent started with LLM")
        print(f"[Aurelius] 👤 Monitoring portfolio for: {self.user_email}")
        print(f"[Aurelius] 📊 Price threshold: ${self.price_threshold:.2f}")
        print(f"[Aurelius] 💰 Trade amount: ${self.trade_amount:.2f}")

        self._add_history("AI Agent initialized and monitoring market")

        # Main monitoring loop
        while self.running:
            await self._ai_monitoring_cycle()
            await asyncio.sleep(2)  # Check every 1 second for faster response

    async def _ai_monitoring_cycle(self):
        """AI-powered monitoring cycle."""
        if not self.monitoring:
            return

        # --- Local trigger check ---
        # We use the local MarketEngine ONLY as a cheap signal to decide whether
        # to wake up the LLM. The actual price/portfolio data is NOT passed to the
        # LLM here; the LLM must call get_market_price via MCP (requires stock:read).
        local_state = self.market_engine.get_current_state()
        if local_state['price'] > self.price_threshold or local_state['status'] != "CRASHING":
            return  # Market is stable - no need to invoke LLM

        print(f"\n[Aurelius AI] 🚨 Market alert detected - invoking AI analysis via MCP tools")
        print(f"[Aurelius AI] 🔍 Triggering LLM with stock:read scope required for price fetch")

        # Ask AI to use MCP tools to gather data and decide.
        # IMPORTANT: Tools must be called one at a time due to a bug in
        # langchain-google-genai (<=2.0.8) where parallel tool calls produce
        # an empty function_response.name, which the Gemini API rejects.
        analysis_prompt = f"""Market alert for {local_state['symbol']}!

Please use your available tools ONE AT A TIME (do NOT call multiple tools in parallel):
1. First, call get_market_price for {local_state['symbol']} to get the current verified price
2. Then, call get_my_portfolio to check your available balance
3. Analyse whether the price is below the threshold of ${self.price_threshold:.2f}
4. If yes, recommend exactly how many shares to buy with the ${self.trade_amount:.2f} budget

IMPORTANT: Call each tool separately, one after another. Do not batch tool calls."""

        try:
            response = await self.agent_executor.ainvoke({
                "input": analysis_prompt,
                "investor_name": self.user_email,
                "symbol": local_state['symbol'],
                "threshold": self.price_threshold,
                "budget": self.trade_amount,
                "scopes": ", ".join(self.current_scopes)
            })

            output = response.get("output", "")
            print(f"[Aurelius AI] 💡 Analysis: {output}")

            # Check if AI recommended buying
            if "buy" in output.lower() or "purchase" in output.lower():
                import re
                shares_match = re.search(r'(\d+)\s*shares?', output, re.IGNORECASE)
                shares = int(shares_match.group(1)) if shares_match else int(self.trade_amount / local_state['price'])

                self._add_history(f"AI recommended: Buy {shares} shares")

                # Try to execute trade (will trigger CIBA if stock:trade scope missing)
                await self._execute_ai_trade(local_state['symbol'], shares)

        except ToolException as e:
            if INSUFFICIENT_SCOPE_SENTINEL in str(e):
                print(f"\n{'='*80}")
                print(f"[Aurelius AI] 🔐 INSUFFICIENT SCOPE ERROR DETECTED")
                print(f"[Aurelius AI] Error: {str(e)}")
                print(f"[Aurelius AI] Current Scopes: {self.current_scopes}")
                print(f"[Aurelius AI] Triggering CIBA authorization...")
                print(f"{'='*80}\n")
                await self._handle_insufficient_scope(local_state, str(e))
            else:
                print(f"[Aurelius AI] ⚠️  Tool error: {e}")
        except Exception as e:
            print(f"[Aurelius AI] ⚠️  Error during AI analysis: {e}")
            print(f"[Aurelius AI] Will retry on next monitoring cycle")

    async def _execute_ai_trade(self, symbol: str, shares: int):
        """Execute trade recommended by AI."""
        trade_prompt = f"""Execute a buy order:
- Stock: {symbol}
- Shares: {shares}

You MUST call the buy_stock tool now. Do NOT check scopes or permissions yourself — just call the tool and let the server decide. Call tools one at a time."""

        try:
            response = await self.agent_executor.ainvoke({
                "input": trade_prompt,
                "investor_name": self.user_email,
                "symbol": symbol,
                "threshold": self.price_threshold,
                "budget": self.trade_amount,
                "scopes": ", ".join(self.current_scopes)
            })

            output = response.get("output", "")
            print(f"[Aurelius AI] ✓ Trade result: {output}")

            # Check if the LLM refused to call the tool or reported a scope error
            scope_refusal_keywords = ["insufficient_scope", "stock:trade", "scope", "authorization", "permission"]
            if any(kw in output.lower() for kw in scope_refusal_keywords) and "success" not in output.lower():
                print(f"[Aurelius AI] 🔐 Trade blocked due to insufficient scope — triggering CIBA")
                await self._handle_insufficient_scope(
                    self.market_engine.get_current_state(),
                    output
                )
                return

            # NOTE: MCP server maintains the authoritative portfolio state
            # We update local state for UI display purposes only
            current_price = self.market_engine.get_price()
            self.shares += shares
            self.balance -= shares * current_price

            self._add_history(f"✓ Trade executed: Bought {shares} shares")

            # Market recovers after successful trade
            self.market_engine.trigger_recovery()
            self.monitoring = False  # Stop monitoring after successful trade

        except ToolException as e:
            if INSUFFICIENT_SCOPE_SENTINEL in str(e):
                await self._handle_insufficient_scope(
                    self.market_engine.get_current_state(),
                    str(e)
                )
            else:
                raise

    async def _handle_insufficient_scope(self, market_data: dict, error_msg: str):
        """Handle insufficient scope by requesting CIBA authorization."""
        # Extract required scopes (simplified - in production, parse from error)
        required_scopes = ["openid", "stock:read", "stock:trade"]
        new_permissions = ["stock:trade"]  # The new scope we need

        print(f"[Aurelius AI] 🔐 Requesting user authorization via CIBA...")

        self._add_history("Requesting user authorization for trading...")

        # Calculate trade details
        shares = int(self.trade_amount / market_data['price'])

        # Request authorization via CIBA
        result = await self.ciba_client.request_trade_authorization(
            user_email=self.user_email,
            stock_symbol=market_data['symbol'],
            current_price=market_data['price'],
            trade_amount=self.trade_amount,
            shares=shares,
            required_scopes=required_scopes
        )

        if result and result.get('approved'):
            # We got the token!
            self.current_obo_token = result['token']

            # Verify the token actually contains the required scopes
            import jwt as pyjwt
            token_payload = pyjwt.decode(self.current_obo_token.access_token, options={"verify_signature": False})
            actual_scopes = token_payload.get('scope', '').split() if token_payload.get('scope') else []
            missing_scopes = [s for s in required_scopes if s not in actual_scopes]

            print(f"\n{'='*80}")
            print(f"[Aurelius AI] ✓ AUTHORIZATION APPROVED!")
            print(f"[Aurelius AI] 🔄 Verifying token scopes...")
            print(f"[Aurelius AI] 🔍 Required: {required_scopes}")
            print(f"[Aurelius AI] 🔍 Actual:   {actual_scopes}")

            if missing_scopes:
                print(f"[Aurelius AI] ❌ CRITICAL: OBO token missing scopes: {missing_scopes}")
                print(f"[Aurelius AI] ❌ Asgardeo is NOT granting these scopes!")
                print(f"[Aurelius AI] 🔧 FIX REQUIRED:")
                print(f"[Aurelius AI]    1. Go to Asgardeo Console → Applications")
                print(f"[Aurelius AI]    2. Open your application → API Authorization tab")
                print(f"[Aurelius AI]    3. Authorize Stock Trading API with scopes: {missing_scopes}")
                print(f"[Aurelius AI]    4. Update and restart the demo")
                print(f"[Aurelius AI] ⚠️  NOT retrying trade to prevent infinite loop")
                print(f"{'='*80}\n")
                self._add_history(f"✗ Asgardeo config error: missing scopes {missing_scopes}")
                return

            self.current_scopes = required_scopes
            print(f"[Aurelius AI] ✅ All required scopes present!")
            print(f"[Aurelius AI] 🔄 Reinitializing agent with OBO token...")
            print(f"{'='*80}\n")

            # Reinitialize agent with new token
            await self._initialize_agent(self.current_obo_token.access_token)

            print(f"[Aurelius AI] ✓ Agent reinitialized! Retrying trade...")
            self._add_history("✓ User approved authorization")

            # Retry the trade
            await self._execute_ai_trade(market_data['symbol'], shares)

        else:
            print(f"[Aurelius AI] ✗ Authorization denied or failed")
            self._add_history("✗ User denied authorization or request timed out")

    def _add_history(self, message: str):
        """Add event to history log."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.history.append({
            'timestamp': timestamp,
            'message': message
        })

        if len(self.history) > 50:
            self.history.pop(0)

    def get_portfolio(self) -> Dict:
        """
        Get current portfolio state for UI display.

        NOTE: This is cached local data for UI rendering only.
        The agent's actual decision-making uses MCP tools (get_market_price, buy_stock, etc.)
        which properly enforce authentication and scopes.
        """
        with self.lock:
            # Use approximate market price for UI display
            # The MCP server maintains the authoritative portfolio state
            current_price = self.market_engine.get_price()
            total_value = self.balance + (self.shares * current_price)
            profit_loss = total_value - self.initial_balance
            profit_loss_percent = (profit_loss / self.initial_balance) * 100 if self.initial_balance > 0 else 0.0

            return {
                'balance': round(self.balance, 2),
                'shares': self.shares,
                'total_value': round(total_value, 2),
                'profit_loss': round(profit_loss, 2),
                'profit_loss_percent': round(profit_loss_percent, 2),
                'history': self.history[-10:]
            }

    def get_ciba_status(self) -> Dict:
        """Get CIBA status (stub for compatibility)."""
        return {
            'active': False,
            'approved': False,
            'pending_trade': None,
            'details': None
        }

    def reset(self):
        """Reset agent state."""
        with self.lock:
            self.balance = self.initial_balance
            self.shares = 0
            self.history = []
            self.monitoring = True
            self._add_history("Agent reset to initial state")

    def stop(self):
        """Stop the agent."""
        self.running = False

        # Schedule cleanup in the agent's event loop if it exists
        if self._event_loop and not self._event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self.ciba_client.cleanup(),
                self._event_loop
            )
