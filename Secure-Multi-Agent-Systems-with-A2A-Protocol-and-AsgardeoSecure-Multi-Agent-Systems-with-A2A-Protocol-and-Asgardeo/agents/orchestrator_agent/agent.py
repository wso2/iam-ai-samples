"""
Orchestrator Agent - A2A Client + Server with OpenAI-based Tool Routing.
Uses official A2A SDK patterns for agent discovery and communication.
"""

import os
import json
import logging
from uuid import uuid4
from typing import Optional, Dict, Any, AsyncIterable, List, Callable

from dotenv import load_dotenv
import httpx

# Official A2A SDK imports
from a2a.client import A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    AgentCard,
    TextPart,
)

from auth import OAuthFlowHandler
from auth.agent_auth import AgentAuthService

load_dotenv()
logger = logging.getLogger(__name__)


# Tool Registry for OpenAI Function Calling
class ToolRegistry:
    """Registry for tools that can be called by the LLM."""
    
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable] = {}
    
    def register(self, name: str, description: str, parameters: Dict[str, Any] = None):
        """Decorator to register a tool."""
        def decorator(func: Callable):
            self.tools[name] = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters or {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
            self.handlers[name] = func
            return func
        return decorator
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get all registered tool schemas for OpenAI."""
        return list(self.tools.values())
    
    async def execute(self, name: str, *args, **kwargs) -> Any:
        """Execute a registered tool."""
        if name not in self.handlers:
            raise ValueError(f"Tool '{name}' not found")
        return await self.handlers[name](*args, **kwargs)


class OrchestratorAgent:
    """
    Orchestrator Agent using official A2A SDK patterns.
    - Discovers agents via A2ACardResolver
    - Communicates via A2AClient.send_message()
    - Uses OpenAI for intelligent routing
    - Handles OAuth with Asgardeo delegation
    """
    
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
    
    def __init__(self, config: dict):
        self.config = config
        
        # Asgardeo configuration
        self.client_id = os.getenv('ORCHESTRATOR_CLIENT_ID', '')
        self.client_secret = os.getenv('ORCHESTRATOR_CLIENT_SECRET', '')
        self.agent_id = os.getenv('ORCHESTRATOR_AGENT_ID', '')
        self.agent_secret = os.getenv('ORCHESTRATOR_AGENT_SECRET', '')
        self.redirect_uri = config.get('oauth', {}).get(
            'redirect_uri', 'http://localhost:8000/callback'
        )
        self.org_name = os.getenv('ASGARDEO_ORG', 'a2abasic')
        
        # Agent registry URLs
        self.agent_urls = config.get('agent_urls', ['http://localhost:8001'])
        
        # OAuth handler
        self.oauth = OAuthFlowHandler(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            org_name=self.org_name
        )
        
        # Agent auth handler
        self.agent_auth = AgentAuthService(
            client_id=self.client_id,
            client_secret=self.client_secret,
            agent_id=self.agent_id,
            agent_secret=self.agent_secret,
            org_name=self.org_name,
            redirect_uri=self.redirect_uri
        )
        
        # Session storage
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._actor_token: Optional[str] = None
        
        # Agent discovery cache: url -> (AgentCard, A2AClient)
        self._discovered_agents: Dict[str, Dict[str, Any]] = {}
        
        # OpenAI configuration
        self.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        self.openai_model = config.get('llm', {}).get('model', 'gpt-4o-mini')
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry()
        self._register_tools()
        
        logger.info("Orchestrator Agent initialized")
        logger.info(f"  Agent URLs for discovery: {self.agent_urls}")
        logger.info(f"  LLM: {'OpenAI' if self.openai_api_key else 'Fallback (keyword-based)'}")
        logger.info(f"  Registered tools: {list(self.tool_registry.tools.keys())}")
    
    def _register_tools(self):
        """Register all available tools for the LLM."""
        
        @self.tool_registry.register(
            name="discover_agents",
            description="Fetch a list of available AI agents and their capabilities (Agent Cards). Use this to find an agent that can handle the user's request.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        async def discover_agents_tool():
            """Tool wrapper for agent discovery."""
            agents = await self.discover_agents()
            # Return simplified format for LLM
            return [
                {
                    "name": agent["name"],
                    "url": agent["url"],
                    "skills": agent["skills"]
                }
                for agent in agents
            ]
        
        # Store reference for internal use
        self._discover_agents_tool = discover_agents_tool
    
    # ==================== A2A AGENT DISCOVERY ====================
    
    async def discover_agents(self) -> List[Dict[str, Any]]:
        """
        Discover available agents using A2ACardResolver (official SDK pattern).
        Fetches AgentCard from /.well-known/agent-card.json
        """
        agents = []
        
        async with httpx.AsyncClient() as httpx_client:
            for base_url in self.agent_urls:
                try:
                    # Use official A2ACardResolver
                    resolver = A2ACardResolver(
                        httpx_client=httpx_client,
                        base_url=base_url
                    )
                    
                    # Resolve agent card
                    agent_card: AgentCard = await resolver.get_agent_card()
                    
                    agent_info = {
                        "url": base_url,
                        "name": agent_card.name,
                        "description": agent_card.description or "",
                        "skills": [s.name for s in agent_card.skills] if agent_card.skills else [],
                        "agent_card": agent_card
                    }
                    agents.append(agent_info)
                    self._discovered_agents[base_url] = agent_info
                    
                    logger.info(f"✅ Discovered agent: {agent_card.name} at {base_url}")
                    logger.info(f"   Skills: {agent_info['skills']}")
                    
                except Exception as e:
                    logger.warning(f"Failed to discover agent at {base_url}: {e}")
        
        return agents
    
    async def call_agent(
        self,
        agent_url: str,
        query: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Call an agent using A2AClient.send_message() (official SDK pattern).
        """
        agent_info = self._discovered_agents.get(agent_url)
        if not agent_info:
            return {"error": f"Agent not discovered: {agent_url}"}
        
        agent_card = agent_info.get("agent_card")
        
        try:
            async with httpx.AsyncClient() as httpx_client:
                # Create A2AClient with agent card
                # Add authorization header for authenticated requests
                headers = {"Authorization": f"Bearer {access_token}"}
                
                # Note: A2AClient may not support custom headers directly,
                # so we'll use low-level httpx for auth until SDK supports it
                client = A2AClient(
                    httpx_client=httpx_client,
                    agent_card=agent_card
                )
                
                # Build message using SDK types
                send_message_payload = {
                    'message': {
                        'role': 'user',
                        'parts': [{'kind': 'text', 'text': query}],
                        'messageId': uuid4().hex,
                    }
                }
                
                # Create request using SDK types
                request = SendMessageRequest(
                    id=str(uuid4()),
                    params=MessageSendParams(**send_message_payload)
                )
                
                # Note: Since we need auth headers and SDK may not support them,
                # we'll do a direct HTTP call with the same payload structure
                payload = {
                    "jsonrpc": "2.0",
                    "id": str(uuid4()),
                    "method": "message/send",
                    "params": send_message_payload
                }
                
                response = await httpx_client.post(
                    agent_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"Agent error: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"Error calling agent: {e}")
            return {"error": str(e)}
    
    def _parse_agent_response(self, result: Dict[str, Any]) -> str:
        """Parse A2A response to extract text."""
        if "result" in result:
            message_result = result.get("result", {})
            
            # Handle message response
            if message_result.get("kind") == "message":
                parts = message_result.get("parts", [])
                for part in parts:
                    if part.get("kind") == "text" or part.get("type") == "text":
                        return part.get("text", "")
            
            # Handle task response with artifacts
            artifacts = message_result.get("artifacts", [])
            if artifacts:
                parts = artifacts[0].get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        
        if "error" in result:
            return f"Error: {result.get('error')}"
        
        return str(result)
    
    # ==================== OAUTH ====================
    
    async def ensure_actor_token(self) -> Optional[str]:
        """Get actor_token via 3-step agent auth flow."""
        if self._actor_token:
            return self._actor_token
        
        logger.info("Getting actor_token via 3-step agent auth...")
        self._actor_token = await self.agent_auth.get_actor_token()
        return self._actor_token
    
    def generate_auth_url(self, context_id: str) -> str:
        """Generate OAuth authorization URL for user login."""
        scopes = ['openid', 'profile', 'booking:read', 'booking:write']
        
        auth_url, state, code_verifier = self.oauth.generate_auth_url(
            scopes=scopes,
            requested_actor=self.agent_id if self.agent_id else None
        )
        
        self._sessions[context_id] = {
            'state': state,
            'code_verifier': code_verifier,
            'auth_url': auth_url
        }
        
        logger.info(f"Auth URL generated for context: {context_id}")
        return auth_url
    
    async def handle_callback(
        self,
        context_id: str,
        code: str,
        state: str
    ) -> Optional[str]:
        """Handle OAuth callback - exchange code for delegated token."""
        session = self._sessions.get(context_id)
        if not session:
            for ctx_id, sess in self._sessions.items():
                if sess.get('state') == state:
                    context_id = ctx_id
                    session = sess
                    break
        
        if not session:
            logger.error(f"No session found for state: {state[:20]}...")
            return None
        
        # Get actor_token for delegation
        actor_token = await self.ensure_actor_token()
        if not actor_token:
            logger.error("Failed to get actor_token")
            logger.info("Attempting token exchange without actor_token...")
        
        # Exchange code for delegated toke
        token_response = await self.oauth.exchange_code_for_token(
            code, state, actor_token=actor_token
        )
        
        if not token_response:
            return None
        
        access_token = token_response.get('access_token')
        session['access_token'] = access_token
        session['token_response'] = token_response
        
        logger.info(f"✅ Delegated token obtained for context: {context_id}")
        return access_token
    
    # ==================== LLM ROUTING ====================
    
    async def _call_openai(self, query: str) -> Dict[str, Any]:
        """
        Use OpenAI with registered tools to dynamically discover agents and route requests.
        """
        if not self.openai_api_key:
            return self._fallback_routing(query, [])

        # Get tool schemas from registry
        tools = self.tool_registry.get_tool_schemas()

        # Initial System Prompt
        # Prepare agent context string
        known_agents_str = ""
        if self._discovered_agents:
            agents_list = []
            for url, info in self._discovered_agents.items():
                skills = ", ".join(info.get("skills", []))
                agents_list.append(f"- {info['name']} ({url}): [{skills}]")
            known_agents_str = "\n".join(agents_list)
        
        # Initial System Prompt
        system_prompt = f"""You are an intelligent orchestrator.

Known Agents:
{known_agents_str}

1. If you see a suitable agent in the list above, route the request directly to it.
2. If the list is empty or you need to find new agents, use the `discover_agents` tool.
3. If an agent matches, respond with JSON:
   {{"action": "call_agent", "agent_url": "<url>", "query": "<user query>"}}
4. If no agent matches or for general chat, respond with JSON:
   {{"action": "respond", "response": "<your response>"}}
   
Respond ONLY with valid JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        try:
            async with httpx.AsyncClient() as client:
                # First call: OpenAI decides to use the tool
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openai_model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": 0.1
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenAI error (1): {response.status_code} - {response.text}")
                    return self._fallback_routing(query, [])

                result = response.json()
                msg = result["choices"][0]["message"]
                tool_calls = msg.get("tool_calls")

                # If OpenAI wants to use a tool
                if tool_calls:
                    # Append OpenAI's tool call message
                    messages.append(msg)

                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        logger.info(f"🤖 OpenAI invoked tool: {tool_name}")
                        
                        # Execute tool via registry
                        tool_result = await self.tool_registry.execute(tool_name)
                        
                        # Add tool output to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(tool_result)
                        })

                    # Second call: OpenAI makes the final routing decision
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openai_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.openai_model,
                            "messages": messages,
                            # No tools needed for final response, just JSON
                            "response_format": {"type": "json_object"}, 
                            "temperature": 0.1
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"OpenAI error (2): {response.status_code}")
                        return self._fallback_routing(query, [])
                    
                    result = response.json()
                    text = result["choices"][0]["message"]["content"]
                
                else:
                    # Model didn't call tool (maybe direct greeting)
                    text = msg["content"]

                # Parse final JSON decision
                try:
                    text = text.strip()
                    if text.startswith("```"):
                        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
                    decision = json.loads(text)
                    logger.info(f"🤖 LLM Decision: {decision}")
                    return decision
                except json.JSONDecodeError:
                    # Handle cases where model chats without JSON
                    return {"action": "respond", "response": text}

        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._fallback_routing(query, [])
    
    def _fallback_routing(
        self,
        query: str,
        agents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fallback keyword-based routing when LLM unavailable."""
        # Try to use cached agents if not provided
        if not agents and self._discovered_agents:
            agents = list(self._discovered_agents.values())
            
        travel_keywords = ['flight', 'hotel', 'book', 'travel', 'trip', 'fly', 'reservation']
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in travel_keywords) and agents:
            return {
                "action": "call_agent",
                "agent_url": agents[0]["url"],
                "query": query
            }
        
        return {
            "action": "respond",
            "response": "👋 Hello! I can help you with travel bookings. Ask about flights or hotels!"
        }
    
    # ==================== MAIN STREAM ====================
    
    async def stream(
        self,
        query: str,
        context_id: str
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Process user query using official A2A SDK patterns.
        1. Check authentication
        2. Route via LLM (OpenAI) with Tool-based Discovery
        3. Call agent via A2AClient pattern
        """
        session = self._sessions.get(context_id, {})
        access_token = session.get('access_token')
        
        # Check authentication
        if not access_token:
            auth_url = self.generate_auth_url(context_id)
            yield {
                "content": f"Please authenticate to continue: {auth_url}",
                "requires_auth": True,
                "auth_url": auth_url
            }
            return
        
        # Route request using LLM (which handles discovery via tools)
        logger.info(f"Processing: {query[:50]}...")
        decision = await self._call_openai(query)
        
        action = decision.get("action")
        
        if action == "call_agent":
            agent_url = decision.get("agent_url")
            agent_query = decision.get("query", query)
            
            # Ensure we have agent details (in case LLM routed but we need name)
            if not self._discovered_agents:
                 await self.discover_agents()
            
            agent_name = self._discovered_agents.get(agent_url, {}).get("name", "Agent")
            logger.info(f"🔧 Routing to {agent_name}")
            
            result = await self.call_agent(agent_url, agent_query, access_token)
            response_text = self._parse_agent_response(result)
            
            yield {"content": response_text}
        else:
            # Respond directly
            response = decision.get("response", "How can I help you?")
            yield {"content": response}
