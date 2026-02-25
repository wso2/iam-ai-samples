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
        Process IT request — admin approval gate with immediate response.

        Flow:
          1. Extract employee info + requested resources from query
          2. Create pending approval record + notify admin (email or terminal)
          3. Return IMMEDIATELY to the orchestrator with approval URL
          4. Background task polls for admin decision then calls MCP to provision
        """
        if not token:
            return "[X] No token provided. Authentication required."

        import re, os
        from agents.it_agent import approval_store
        from agents.it_agent.email_sender import send_it_approval_email

        base_url = os.environ.get("IT_SERVICE_BASE_URL", "http://localhost:8002")

        # ── Extract employee ID and name from query ──────────────────────────
        emp_match     = re.search(r'EMP-\w+', query, re.IGNORECASE)
        employee_id   = emp_match.group(0).upper() if emp_match else "EMP-UNKNOWN"
        name_match    = re.search(r'(?:for|employee)\s+([A-Z][a-z]+)', query)
        employee_name = name_match.group(1) if name_match else employee_id

        # ── Extract requested resources ──────────────────────────────────────
        resources = []
        if re.search(r'github|git', query, re.IGNORECASE):              resources.append("GitHub")
        if re.search(r'aws|cloud|iam|s3|ec2', query, re.IGNORECASE):   resources.append("AWS")
        if re.search(r'vpn|network|remote', query, re.IGNORECASE):      resources.append("VPN")
        if not resources:
            resources = ["IT Resources"]

        # ── Create pending approval record + notify admin ────────────────────
        approval_token = await approval_store.create_pending(
            employee_id=employee_id,
            employee_name=employee_name,
            resources=resources,
        )
        approval_url = f"{base_url}/it/approve/{approval_token}"
        reject_url   = f"{base_url}/it/reject/{approval_token}"

        await send_it_approval_email(
            employee_id=employee_id,
            employee_name=employee_name,
            resources=resources,
            approval_url=approval_url,
            reject_url=reject_url,
        )

        logger.info(f"[IT_AGENT] Approval pending ({approval_token[:8]}…) — returning immediately, background task will provision.")

        # Broadcast approval URL to visualizer so it's visible in the UI log
        from src.log_broadcaster import broadcast_log
        await broadcast_log(f"[IT_AGENT] Approval pending — Admin approval URL: {approval_url}")

        # ── Background task: poll → MCP provision ───────────────────────────
        async def _wait_and_provision():
            from src.log_broadcaster import broadcast_log as _broadcast
            try:
                final_status = await approval_store.wait_for_approval(approval_token, poll_interval=5.0)
                if final_status == "approved":
                    logger.info(f"[IT_AGENT] ✅ Approved! Proceeding with MCP provisioning.")
                    await _broadcast(f"[IT_AGENT] ✅ Approved! Proceeding with MCP provisioning for {employee_name} ({employee_id}).")
                    from agents.it_agent.graph import run_it_agent_workflow
                    result = await run_it_agent_workflow(query=query, token=token)
                    logger.info(f"[IT_AGENT] MCP provisioning complete: {result[:120]}")
                    await _broadcast(f"[IT_PROVISIONED] ✅ IT access provisioned for {employee_name} ({employee_id}): {result[:300]}")
                elif final_status == "rejected":
                    logger.warning(f"[IT_AGENT] ❌ Rejected by admin — no resources provisioned for {employee_id}.")
                    await _broadcast(f"[IT_PROVISIONED] ❌ IT access request rejected for {employee_name} ({employee_id}). No resources were provisioned.")
                else:
                    logger.warning(f"[IT_AGENT] ⏰ Approval timed out for {employee_id}.")
                    await _broadcast(f"[IT_PROVISIONED] ⏰ IT access approval timed out for {employee_name} ({employee_id}). Please retry.")
            except Exception as e:
                logger.error(f"[IT_AGENT] Background provisioning failed: {e}", exc_info=True)
                await _broadcast(f"[IT_PROVISIONED] ❌ IT provisioning error for {employee_name} ({employee_id}): {e}")
        import asyncio
        asyncio.create_task(_wait_and_provision())

        # ── Return immediately ───────────────────────────────────────────────
        resource_list = ", ".join(resources)
        return (
            f"⏳ **IT Access Approval Requested** for {employee_name} ({employee_id})\n\n"
            f"Resources: **{resource_list}**\n\n"
            f"An approval request has been sent to the IT admin.\n"
            f"Once approved, access will be provisioned automatically.\n\n"
            f"Admin approval link:\n`{approval_url}`"
        )

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response — A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
