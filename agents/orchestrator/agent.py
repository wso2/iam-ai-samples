"""
Orchestrator Agent - A2A Server with OpenAI-based routing.
Uses official A2A SDK patterns for agent discovery and communication.
Integrates with existing TokenBroker for token exchange.
"""

import os
import sys
import json
import logging
from uuid import uuid4
from typing import Optional, Dict, Any, AsyncIterable, List, Callable

from dotenv import load_dotenv
import httpx

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Official A2A SDK imports
from a2a.client import A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    AgentCard,
    TextPart,
)

# Local imports
from src.auth.token_broker import get_token_broker
from src.config import get_settings
from src.config_loader import load_yaml_config
from src.log_broadcaster import log_and_broadcast

load_dotenv()
logger = logging.getLogger(__name__)

# Visualizer log function
def vlog(message: str):
    """Log message and broadcast to visualizer."""
    log_and_broadcast(message)


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
    - Integrates with TokenBroker for delegation
    """

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()
        
        # Load configuration
        app_config = load_yaml_config()
        orch_config = app_config.get("orchestrator", {})
        self.agents_config = app_config.get("agents", {})
        
        # Agent URLs from config
        discovery_urls = orch_config.get("discovery", {}).get("agent_urls", [])
        self.agent_urls = discovery_urls or [
            "http://localhost:8001",  # HR
            "http://localhost:8002",  # IT
            "http://localhost:8003",  # Approval
            "http://localhost:8004",  # Booking
        ]
        
        # Token broker (uses existing implementation)
        self._token_broker = None
        
        # Session storage
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # Agent discovery cache: url -> (AgentCard, info)
        self._discovered_agents: Dict[str, Dict[str, Any]] = {}
        
        # OpenAI configuration
        self.openai_api_key = self.settings.openai_api_key
        self.openai_model = orch_config.get("llm", {}).get("model", "gpt-4o")
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry()
        self._register_tools()
        
        logger.info("Orchestrator Agent initialized")
        logger.info(f"  Agent URLs for discovery: {self.agent_urls}")
        logger.info(f"  LLM: {'OpenAI' if self.openai_api_key else 'Fallback (keyword-based)'}")

    @property
    def token_broker(self):
        """Lazy load token broker."""
        if self._token_broker is None:
            self._token_broker = get_token_broker()
        return self._token_broker

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
            return [
                {
                    "name": agent["name"],
                    "url": agent["url"],
                    "skills": agent["skills"]
                }
                for agent in agents
            ]

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
        access_token: str,
        pre_exchanged_token: str = None
    ) -> Dict[str, Any]:
        """
        Call an agent using A2AClient.send_message() pattern.
        Includes visualizer logging for token flow animations.
        
        Args:
            agent_url: URL of the target agent
            query: User query/task to send to the agent
            access_token: Source token (user delegated token)
            pre_exchanged_token: Optional pre-exchanged token to skip token exchange
        """
        agent_info = self._discovered_agents.get(agent_url)
        if not agent_info:
            # Try to discover if not cached
            await self.discover_agents()
            agent_info = self._discovered_agents.get(agent_url)
            if not agent_info:
                return {"error": f"Agent not discovered: {agent_url}"}

        # Determine agent type for logging
        agent_name = agent_info.get("name", "Agent")
        agent_type = "AGENT"
        agent_key = None
        target_scopes = []
        
        if "hr" in agent_name.lower():
            agent_type = "HR_AGENT"
            agent_key = "hr_agent"
            target_scopes = ["hr:read", "hr:write"]
        elif "it" in agent_name.lower():
            agent_type = "IT_AGENT"
            agent_key = "it_agent"
            target_scopes = ["it:read", "it:write"]
        elif "approval" in agent_name.lower():
            agent_type = "APPROVAL_AGENT"
            agent_key = "approval_agent"
            target_scopes = ["approval:read", "approval:write"]
        elif "booking" in agent_name.lower():
            agent_type = "BOOKING_AGENT"
            agent_key = "booking_agent"
            target_scopes = ["booking:read", "booking:write"]

        try:
            # Use pre-exchanged token if provided, otherwise perform token exchange
            if pre_exchanged_token:
                vlog(f"\n[USING PRE-EXCHANGED TOKEN FOR {agent_type}]")
                vlog(f"  Agent: {agent_name}")
                vlog(f"  URL: {agent_url}")
                vlog(f"  Token already exchanged by LangGraph")
                exchanged_token = pre_exchanged_token
            else:
                # Log token exchange for visualizer
                vlog(f"\n[TOKEN EXCHANGE FOR {agent_type}]")
                vlog(f"  Agent: {agent_name}")
                vlog(f"  URL: {agent_url}")
                
                # Log the source token (user delegated token)
                vlog(f"\n[SOURCE_TOKEN - User Delegated]:")
                vlog(f"  {access_token}")
                
                # Perform actual token exchange if agent_key is valid
                exchanged_token = access_token  # fallback to original
                
                if agent_key:
                    try:
                        broker = get_token_broker()
                        # Extract target audience from agent URL
                        # For now use a standard audience based on agent type
                        target_audience = agent_key.replace("_", "-")  # e.g., "hr-agent"
                        
                        vlog(f"\n[PERFORMING TOKEN EXCHANGE]")
                        vlog(f"  Subject Token: User Delegated Token")
                        vlog(f"  Target Audience: {target_audience}")
                        vlog(f"  Target Scopes: {target_scopes}")
                        
                        exchanged_token = await broker.exchange_token_for_agent(
                            source_token=access_token,
                            agent_key=agent_key,
                            target_audience=target_audience,
                            target_scopes=target_scopes
                        )
                        
                        vlog(f"\n[{agent_type}_EXCHANGED_TOKEN]:")
                        vlog(f"  {exchanged_token}")
                        
                    except Exception as exc:
                        vlog(f"\n[TOKEN EXCHANGE ERROR] {exc}")
                        # Propagate error - don't silently fallback
                        return {"error": f"Token exchange failed for {agent_type}: {exc}"}
                else:
                    # Unknown agent type - still need token exchange
                    vlog(f"\n[WARNING] Unknown agent type: {agent_type} - cannot exchange token")
                    return {"error": f"Unknown agent type: {agent_type}"}

            async with httpx.AsyncClient() as httpx_client:
                # Build message using SDK types
                send_message_payload = {
                    'message': {
                        'role': 'user',
                        'parts': [{'kind': 'text', 'text': query}],
                        'messageId': uuid4().hex,
                    }
                }

                # A2A JSON-RPC request with auth
                payload = {
                    "jsonrpc": "2.0",
                    "id": str(uuid4()),
                    "method": "message/send",
                    "params": send_message_payload
                }

                vlog(f"\n[{agent_type}] Sending A2A request...")

                response = await httpx_client.post(
                    agent_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {exchanged_token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    vlog(f"\n[{agent_type}] Response received successfully")
                    return result
                else:
                    vlog(f"\n[{agent_type}] Error: {response.status_code}")
                    return {"error": f"Agent error: {response.status_code}"}

        except Exception as e:
            logger.error(f"Error calling agent: {e}")
            vlog(f"\n[{agent_type}] Error: {str(e)}")
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

    # ==================== SESSION MANAGEMENT ====================

    def get_or_create_session(self, context_id: str) -> Dict[str, Any]:
        """Get or create a session for the context."""
        if context_id not in self._sessions:
            self._sessions[context_id] = {
                'context_id': context_id,
                'access_token': None,
                'user_sub': None
            }
        return self._sessions[context_id]

    def set_session_token(self, context_id: str, access_token: str, user_sub: str = None):
        """Set the access token for a session."""
        session = self.get_or_create_session(context_id)
        session['access_token'] = access_token
        session['user_sub'] = user_sub

    # ==================== LLM TASK DECOMPOSITION ====================

    async def decompose_to_tasks(self, user_input: str) -> List[Dict[str, Any]]:
        """
        Use LLM to break a user request into ordered tasks for available agents.
        Returns a list of tasks: [{agent_url, agent_name, task, step}]
        Falls back to keyword-based decomposition if LLM is unavailable.
        """
        # Ensure agents are discovered
        if not self._discovered_agents:
            await self.discover_agents()

        if not self._discovered_agents:
            return [{"error": "No agents discovered"}]

        # Build agent descriptions for LLM
        agents_desc = []
        for url, info in self._discovered_agents.items():
            skills = ", ".join(info.get("skills", []))
            agents_desc.append(
                f'  - name: "{info["name"]}", url: "{url}", skills: [{skills}]'
            )
        agents_block = "\n".join(agents_desc)

        system_prompt = f"""You are a task planner for an AI agent orchestrator. Given a user request, decompose it into concrete tasks for the available agents. Return ONLY valid JSON.

Available Agents:
{agents_block}

Rules:
- CAREFULLY identify ALL distinct actions in the user request. A single sentence can require MULTIPLE agents.
- For example: "Create employee profile and provision VPN for John" needs BOTH the HR agent (create profile) AND the IT agent (provision VPN).
- Each task must have a clear, specific instruction for that agent.
- Order tasks logically (e.g., create profile before provisioning access).
- If only one agent is genuinely needed, return a single task.
- Never skip an action that the user explicitly asked for.

Privilege / Access Workflow:
- When the request involves granting privileges, elevated access, or role-based permissions (e.g. "HR privileges", "admin access", "manager role"), the Approval Agent MUST be invoked FIRST to approve the privilege request.
- AFTER approval, route to the appropriate agent to actually grant/apply the privileges:
  * HR privileges / roles / access  →  HR Agent (after Approval Agent approves)
  * IT privileges / system access   →  IT Agent (after Approval Agent approves)
- Example: "give HR privileges to Bob" should produce:
  Step 1: Approval Agent → "Request approval for granting HR privileges to Bob"
  Step 2: HR Agent → "Grant HR privileges to Bob (approved by Approval Agent)"

Respond with JSON in this exact format:
{{
  "tasks": [
    {{"step": 1, "agent_url": "<url>", "agent_name": "<name>", "task": "<specific instruction for this agent>"}},
    ...
  ],
  "summary": "<one-line summary of the plan>"
}}"""

        if not self.openai_api_key:
            return self._fallback_decompose(user_input)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_input}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    logger.error(f"OpenAI error: {response.status_code}")
                    return self._fallback_decompose(user_input)

                result = response.json()
                text = result["choices"][0]["message"]["content"].strip()

                plan = json.loads(text)
                tasks = plan.get("tasks", [])
                summary = plan.get("summary", "")

                vlog(f"\n[LLM PLAN] {summary}")
                for t in tasks:
                    vlog(f"  Step {t['step']}: [{t['agent_name']}] {t['task']}")

                return tasks

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            return self._fallback_decompose(user_input)

    def _fallback_decompose(self, query: str) -> List[Dict[str, Any]]:
        """Keyword-based fallback for task decomposition."""
        query_lower = query.lower()
        tasks = []
        step = 1

        keyword_map = {
            "hr": (["employee", "profile", "hr", "hire", "onboard", "new hire", "create"], "http://localhost:8001"),
            "it": (["vpn", "github", "aws", "provision", "access", "account", "laptop", "email"], "http://localhost:8002"),
            "approval": (["approve", "approval", "permission", "request", "manager"], "http://localhost:8003"),
            "booking": (["schedule", "task", "booking", "book", "orientation", "equipment", "pickup"], "http://localhost:8004"),
        }

        for agent_key, (keywords, url) in keyword_map.items():
            if any(kw in query_lower for kw in keywords):
                agent_info = self._discovered_agents.get(url, {})
                tasks.append({
                    "step": step,
                    "agent_url": url,
                    "agent_name": agent_info.get("name", f"{agent_key} Agent"),
                    "task": query
                })
                step += 1

        # If no match, try all agents
        if not tasks:
            for url, info in self._discovered_agents.items():
                tasks.append({
                    "step": step,
                    "agent_url": url,
                    "agent_name": info.get("name", "Agent"),
                    "task": query
                })
                step += 1

        return tasks

    async def process_workflow(
        self,
        user_input: str,
        access_token: str,
        context_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Full workflow: decompose user input into tasks via LLM, then execute each.
        Returns structured results for all steps.
        """
        vlog(f"\n{'='*60}")
        vlog(f"[WORKFLOW] Processing: {user_input}")
        vlog(f"{'='*60}")

        # Step 1: LLM decomposes the request
        tasks = await self.decompose_to_tasks(user_input)

        if not tasks:
            return {"status": "error", "error": "Could not determine any tasks for the request."}

        if len(tasks) == 1 and "error" in tasks[0]:
            return {"status": "error", "error": tasks[0]["error"]}

        total = len(tasks)
        results = []

        # Step 2: Execute each task sequentially
        for task in tasks:
            step_num = task["step"]
            agent_url = task["agent_url"]
            agent_name = task["agent_name"]
            task_query = task["task"]

            vlog(f"\n{'='*60}")
            vlog(f"[STEP {step_num}/{total}] {agent_name}")
            vlog(f"  Task: {task_query}")
            vlog(f"{'='*60}")

            try:
                result = await self.call_agent(
                    agent_url=agent_url,
                    query=task_query,
                    access_token=access_token
                )
                response_text = self._parse_agent_response(result)

                results.append({
                    "step": step_num,
                    "agent": agent_name,
                    "task": task_query,
                    "status": "success",
                    "response": response_text
                })

                vlog(f"\n[STEP {step_num} COMPLETE] {agent_name}")

            except Exception as e:
                logger.error(f"Step {step_num} failed: {e}")
                results.append({
                    "step": step_num,
                    "agent": agent_name,
                    "task": task_query,
                    "status": "error",
                    "response": str(e)
                })
                vlog(f"\n[STEP {step_num} FAILED] {agent_name}: {e}")

        vlog(f"\n{'='*60}")
        vlog(f"[WORKFLOW COMPLETE] {sum(1 for r in results if r['status'] == 'success')}/{total} steps succeeded")
        vlog(f"{'='*60}")

        return {
            "status": "success",
            "input": user_input,
            "plan": [{"step": t["step"], "agent": t["agent_name"], "task": t["task"]} for t in tasks],
            "results": results
        }

    # ==================== LLM ROUTING ====================

    async def _call_openai(self, query: str) -> Dict[str, Any]:
        """Use OpenAI with registered tools to route requests."""
        if not self.openai_api_key:
            return self._fallback_routing(query, [])

        tools = self.tool_registry.get_tool_schemas()

        # Prepare agent context
        known_agents_str = ""
        if self._discovered_agents:
            agents_list = []
            for url, info in self._discovered_agents.items():
                skills = ", ".join(info.get("skills", []))
                agents_list.append(f"- {info['name']} ({url}): [{skills}]")
            known_agents_str = "\n".join(agents_list)

        system_prompt = f"""You are an intelligent onboarding orchestrator.

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
                    logger.error(f"OpenAI error: {response.status_code} - {response.text}")
                    return self._fallback_routing(query, [])

                result = response.json()
                msg = result["choices"][0]["message"]
                tool_calls = msg.get("tool_calls")

                if tool_calls:
                    messages.append(msg)

                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        logger.info(f"🤖 OpenAI invoked tool: {tool_name}")

                        tool_result = await self.tool_registry.execute(tool_name)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(tool_result)
                        })

                    # Second call for final decision
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openai_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.openai_model,
                            "messages": messages,
                            "response_format": {"type": "json_object"},
                            "temperature": 0.1
                        },
                        timeout=30.0
                    )

                    if response.status_code != 200:
                        return self._fallback_routing(query, [])

                    result = response.json()
                    text = result["choices"][0]["message"]["content"]
                else:
                    text = msg["content"]

                try:
                    text = text.strip()
                    if text.startswith("```"):
                        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
                    decision = json.loads(text)
                    logger.info(f"🤖 LLM Decision: {decision}")
                    return decision
                except json.JSONDecodeError:
                    return {"action": "respond", "response": text}

        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._fallback_routing(query, [])

    def _fallback_routing(self, query: str, agents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fallback keyword-based routing when LLM unavailable."""
        if not agents and self._discovered_agents:
            agents = list(self._discovered_agents.values())

        query_lower = query.lower()

        # Keyword mapping for onboarding
        keywords_map = {
            "hr": ["employee", "profile", "hr", "hire", "onboard"],
            "it": ["vpn", "github", "aws", "provision", "access", "account"],
            "approval": ["approve", "approval", "permission", "request"],
            "booking": ["schedule", "task", "booking", "book", "orientation"]
        }

        for agent in agents:
            agent_name = agent.get("name", "").lower()
            for key, keywords in keywords_map.items():
                if key in agent_name and any(kw in query_lower for kw in keywords):
                    return {
                        "action": "call_agent",
                        "agent_url": agent["url"],
                        "query": query
                    }

        return {
            "action": "respond",
            "response": "👋 Hello! I'm the Onboarding Orchestrator. I can help with employee onboarding, IT provisioning, approvals, and scheduling."
        }

    # ==================== MAIN STREAM ====================

    async def stream(
        self,
        query: str,
        context_id: str = "default",
        access_token: str = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Process user query using LangGraph workflow.
        Yields results incrementally for streaming responses.
        """
        session = self.get_or_create_session(context_id)
        token = access_token or session.get('access_token')

        # Check authentication
        if not token:
            yield {
                "content": "Please authenticate first. Use /auth/login to get started.",
                "requires_auth": True
            }
            return

        # Run LangGraph workflow
        logger.info(f"Processing with LangGraph: {query[:50]}...")
        
        try:
            result = await self.run_with_langgraph(query, context_id, token)
            
            if result.get("error"):
                yield {"content": f"Error: {result['error']}"}
                return
            
            # Yield the final response
            yield {"content": result.get("final_response", "Workflow completed")}
            
        except Exception as e:
            logger.exception("Error in stream")
            yield {"content": f"Error: {str(e)}"}

    async def run_with_langgraph(
        self,
        query: str,
        context_id: str = "default",
        access_token: str = None
    ) -> Dict[str, Any]:
        """
        Process user query using LangGraph workflow.
        This is an alternative to the stream() method that uses a stateful graph approach.
        
        Args:
            query: User's request
            context_id: Session context identifier
            access_token: OAuth2 access token
            
        Returns:
            Final state with aggregated results
        """
        try:
            # Authentication check
            session = self.get_or_create_session(context_id)
            token = access_token or session.get('access_token')

            if not token:
                return {
                    "error": "Not authenticated. Please login first.",
                    "redirect": "/auth/login"
                }

            # Import LangGraph workflow
            from agents.orchestrator.graph import run_orchestrator_workflow

            # Execute LangGraph workflow
            vlog(f"\n🚀 [LangGraph] Running orchestrator workflow for: {query[:100]}...")
            
            final_state = await run_orchestrator_workflow(
                user_query=query,
                access_token=token,
                context_id=context_id
            )

            # Return structured result
            return {
                "success": final_state.get("error") is None,
                "final_response": final_state.get("final_response"),
                "task_results": final_state.get("task_results", []),
                "task_plan": final_state.get("task_plan", []),
                "error": final_state.get("error")
            }

        except Exception as e:
            logger.exception("Error in run_with_langgraph")
            return {
                "success": False,
                "error": str(e),
                "final_response": f"Failed to execute workflow: {e}"
            }

