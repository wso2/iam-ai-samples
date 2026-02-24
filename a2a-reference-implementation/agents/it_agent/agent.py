"""
IT Agent - A2A Server for IT provisioning.
Routes through the IT MCP Server which uses LLM to classify requests
and performs token scope narrowing before calling the IT API.

Flow: IT Agent (LangGraph) → call_mcp_node → MCP handle_it_request
      → LLM classifies → Token Exchange (scope narrowing) → IT API
      → format_results_node → A2A response
"""

import os
import sys
import json
import logging
from typing import Dict, Any, AsyncIterable

from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, '.env'))

from mcp import ClientSession
from mcp.client.sse import sse_client
from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)

# MCP Server SSE endpoint (started separately on port 8020)
MCP_SSE_URL = "http://localhost:8020/sse"


class ITAgent:
    """
    IT Agent - Provisions IT accounts via MCP Server with LLM routing.
    
    Instead of deciding which tool to call, this agent sends the raw
    request to the MCP Server's handle_it_request tool, which uses
    an LLM to classify and route to the correct operation.
    
    The MCP Server handles:
    1. LLM classification (gpt-4o-mini) → picks vpn/github/aws/list
    2. Token exchange via Token Exchanger (no actor token) → scope narrowing
    3. Calls the IT API with the narrowed token
    
    Required scopes: it:read, it:write
    """

    REQUIRED_SCOPES = ["it:read", "it:write"]
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()
        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("it_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)

        logger.info("IT Agent initialized (LangGraph + MCP SSE mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  MCP SSE URL: {MCP_SSE_URL}")

    async def _call_mcp_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """
        Connect to the IT MCP Server via SSE and invoke a tool.
        Called by the LangGraph call_mcp_node.
        """
        logger.info(f"[IT_AGENT] MCP tool call (SSE): {tool_name}")

        try:
            async with sse_client(MCP_SSE_URL) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)

                    if result.content:
                        for content_item in result.content:
                            if hasattr(content_item, 'text'):
                                return json.loads(content_item.text)

                    return {"success": False, "error": "No response from MCP server"}

        except Exception as e:
            logger.error(f"[IT_AGENT] MCP tool call failed: {e}")
            return {"success": False, "error": f"MCP tool call failed: {str(e)}"}

    async def process_request(self, query: str, token: str = None) -> str:
        """
        Process IT request via the LangGraph workflow.

        The graph handles:
          1. call_mcp_node  — forward raw query to MCP Server via SSE
          2. format_results_node — format the MCP response for the Orchestrator
        """
        if not token:
            return "[X] No token provided. Authentication required."

        logger.info(f"[IT_AGENT] Starting LangGraph workflow for: {query[:80]}...")

        from agents.it_agent.graph import run_it_agent_workflow
        return await run_it_agent_workflow(query=query, token=token)

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response — A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
