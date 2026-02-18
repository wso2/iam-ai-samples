"""
IT Agent - A2A Server for IT provisioning.
Routes through the IT MCP Server which uses LLM to classify requests
and performs token scope narrowing before calling the IT API.

Flow: IT Agent → MCP handle_it_request tool → LLM classifies → 
      Token Exchange (scope narrowing, no actor token) → IT API
"""

import os
import sys
import json
import logging
import re
from typing import Dict, Any, AsyncIterable

from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, '.env'))

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)


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

        # MCP Server path
        self.mcp_server_path = os.path.join(project_root, "src", "mcp", "it_mcp_server.py")

        logger.info(f"IT Agent initialized (MCP + LLM routing mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  MCP Server: {self.mcp_server_path}")

    async def _call_mcp_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """
        Connect to the IT MCP Server via stdio and invoke a tool.
        
        The MCP server runs as a subprocess. Each tool call:
        1. Spawns the MCP server process
        2. Sends the tool invocation
        3. MCP server processes (LLM routing + token exchange + API call)
        4. Returns the result
        """
        logger.info(f"[IT_AGENT] MCP tool call: {tool_name}")

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.mcp_server_path],
            cwd=project_root
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)

                    if result.content:
                        for content_item in result.content:
                            if hasattr(content_item, 'text'):
                                parsed = json.loads(content_item.text)
                                return parsed

                    return {"success": False, "error": "No response from MCP server"}

        except Exception as e:
            logger.error(f"[IT_AGENT] MCP tool call failed: {e}")
            return {"success": False, "error": f"MCP tool call failed: {str(e)}"}

    async def process_request(self, query: str, token: str = None) -> str:
        """
        Process IT request by sending it to the MCP Server's LLM-routed tool.
        
        The IT Agent does NOT decide which operation to perform.
        It sends the raw natural language request to the MCP Server's
        handle_it_request tool, which uses an LLM to classify and route.
        """
        if not token:
            return "❌ No token provided. Authentication required."

        logger.info(f"[IT_AGENT] Sending request to MCP handle_it_request: {query[:80]}...")

        # Send the raw request to MCP Server — LLM inside will classify it
        result = await self._call_mcp_tool("handle_it_request", {
            "request": query,
            "token": token
        })

        # Format the response based on what happened
        if not result.get("success"):
            return f"❌ IT provisioning failed: {result.get('error', 'Unknown error')}"

        routing = result.get("_routing", {})
        action = routing.get("action", "unknown")
        scope_info = routing.get("scope_narrowed", "N/A")
        classified_by = routing.get("classified_by", "N/A")

        if action == "provision_vpn":
            return (
                f"✅ VPN access provisioned via MCP → IT API!\n"
                f"- Provision ID: {result.get('provision_id', 'N/A')}\n"
                f"- Employee: {result.get('employee_id', 'N/A')}\n"
                f"- VPN Server: {result.get('details', {}).get('vpn_server', 'vpn.nebulasoft.internal')}\n"
                f"- Status: {result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )

        if action == "provision_github":
            return (
                f"✅ GitHub Enterprise access provisioned via MCP → IT API!\n"
                f"- Provision ID: {result.get('provision_id', 'N/A')}\n"
                f"- Employee: {result.get('employee_id', 'N/A')}\n"
                f"- GitHub User: {result.get('details', {}).get('github_username', 'N/A')}\n"
                f"- Repos: {result.get('details', {}).get('repositories', [])}\n"
                f"- Status: {result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )

        if action == "provision_aws":
            return (
                f"✅ AWS environment provisioned via MCP → IT API!\n"
                f"- Provision ID: {result.get('provision_id', 'N/A')}\n"
                f"- Employee: {result.get('employee_id', 'N/A')}\n"
                f"- IAM User: {result.get('details', {}).get('iam_user', 'N/A')}\n"
                f"- Account: {result.get('details', {}).get('account', 'N/A')}\n"
                f"- Status: {result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )

        if action == "list_provisions":
            provisions = result.get("data", [])
            if not provisions:
                return f"📋 No provisions found for {routing.get('employee_id', 'N/A')}."
            lines = [f"📋 Provisions for {routing.get('employee_id', 'N/A')} ({len(provisions)} total):"]
            for p in provisions:
                lines.append(f"  - {p.get('provision_id')}: {p.get('service')} ({p.get('status')})")
            lines.append(f"  Routed by: {classified_by}")
            lines.append(f"  Token scope narrowed: {scope_info}")
            return "\n".join(lines)

        # Generic success
        return (
            f"✅ IT request processed via MCP → IT API!\n"
            f"- Action: {action}\n"
            f"- Routed by: {classified_by}\n"
            f"- Token scope narrowed: {scope_info}\n"
            f"- Result: {json.dumps(result, indent=2)}"
        )

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response - A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
