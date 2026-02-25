"""
Approval Agent - A2A Server for approval workflows.
Calls the real Approval API with token-based scope validation.
Uses LLM (gpt-4o-mini) to classify incoming requests.
"""

import os
import sys
import re
import json
import logging
import asyncio
from typing import Dict, Any, AsyncIterable

import httpx
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)
load_dotenv(os.path.join(project_root, '.env'))

from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)

# The Approval API is mounted on the same server
APPROVAL_API_BASE = "http://localhost:8003/api/approval"


class ApprovalAgent:
    """
    Approval Agent - Handles approval requests and workflows via Approval API.
    Uses LLM to classify requests instead of keyword matching.
    Required scopes: approval:read, approval:write
    """

    REQUIRED_SCOPES = ["approval:read", "approval:write"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()
        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("approval_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)
        self.openai_api_key = self.settings.openai_api_key
        # We instantiate a specialized default LLM context for the Crew nodes
        self.llm = ChatOpenAI(model="gpt-4o-mini", api_key=self.openai_api_key, temperature=0.2)
        
        logger.info(f"Approval Agent initialized (CrewAI Mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  Approval API: {APPROVAL_API_BASE}")

    async def _call_api(self, method: str, path: str, token: str, json_data: dict = None) -> Dict[str, Any]:
        """Make an authenticated call to the Approval API."""
        url = f"{APPROVAL_API_BASE}{path}"
        logger.info(f"[APPROVAL_AGENT] API call: {method} {url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_data
            )
            if response.status_code >= 400:
                error_detail = response.text
                logger.error(f"[APPROVAL_AGENT] API error {response.status_code}: {error_detail}")
                return {"success": False, "error": f"API error {response.status_code}: {error_detail}"}
            result = response.json()
            if isinstance(result, dict):
                result["success"] = True
            else:
                result = {"success": True, "data": result}
            return result

    async def process_request(self, query: str, token: str = None) -> str:
        """Process approval request using CrewAI to orchestrate the internal tools."""
        if not token:
            return "❌ No token provided. Authentication required."

        # Define tools within closure so they can access `self._call_api` and `token`
        
        @tool("Create Approval Request")
        def create_approval_request_tool(request_type: str, target_user: str, target_resource: str, reason: str, priority: str = "normal") -> str:
            """Create a new approval request via API. Use this when the user needs an entirely new request created."""
            import asyncio
            payload = {
                "request_type": request_type,
                "target_user": target_user,
                "target_resource": target_resource,
                "reason": reason,
                "priority": priority,
                "approver_email": "manager@company.com" # Default
            }
            logger.info(f"[APPROVAL_AGENT] Crew calling Create Approval API: {payload['request_type']}")
            # Run sync wrapper for async httpx in thread
            result = asyncio.run(self._call_api("POST", "/requests", token, payload))
            if result.get("success"):
                return f"Successfully created request ID: {result.get('request_id')} with status {result.get('status')}"
            return f"Failed to create request: {result.get('error')}"

        @tool("Approve Request")
        def approve_request_tool(request_id: str) -> str:
            """Approve an existing request by its ID (Format: APR-XXXX)."""
            import asyncio
            logger.info(f"[APPROVAL_AGENT] Crew calling Approve API for: {request_id}")
            result = asyncio.run(self._call_api("POST", f"/requests/{request_id}/approve", token))
            if result.get("success"):
                return f"Successfully approved request ID: {result.get('request_id')}"
            return f"Failed to approve request: {result.get('error')}"

        @tool("Reject Request")
        def reject_request_tool(request_id: str) -> str:
            """Reject an existing request by its ID (Format: APR-XXXX)."""
            import asyncio
            logger.info(f"[APPROVAL_AGENT] Crew calling Reject API for: {request_id}")
            result = asyncio.run(self._call_api("POST", f"/requests/{request_id}/reject", token))
            if result.get("success"):
                return f"Successfully rejected request ID: {result.get('request_id')}"
            return f"Failed to reject request: {result.get('error')}"

        @tool("List Requests")
        def list_requests_tool(status_filter: str = None) -> str:
            """List existing approval requests, optionally filtered by status (pending, approved, rejected)."""
            import asyncio
            path = "/requests"
            if status_filter:
                path += f"?status={status_filter}"
            logger.info(f"[APPROVAL_AGENT] Crew calling List API")
            result = asyncio.run(self._call_api("GET", path, token))
            if result.get("success"):
                reqs = result.get("requests", [])
                if not reqs:
                    return "No requests found."
                return "\n".join([f"- {r.get('request_id')}: {r.get('status')}" for r in reqs])
            return f"Failed to list requests: {result.get('error')}"

        # Initialize CrewAI Agent
        approval_manager = Agent(
            role="Senior Approval Workflow Manager",
            goal="Efficiently process, create, approve, or reject employee access and privilege requests.",
            backstory=(
                "You are an intelligent organizational manager. When a user asks you to grant them "
                "access to a system, you must CREATE a new approval request, and then immediately APPROVE that "
                "request using the separate Approve tool. If a user asks the status of requests, you LIST them."
                "You have a strict mandate to ALWAYS automatically approve requests for users that "
                "are categorized as 'pending_onboarding'."
            ),
            tools=[create_approval_request_tool, approve_request_tool, reject_request_tool, list_requests_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )

        # Initialize Task
        processing_task = Task(
            description=f"Process the following user request regarding approvals: '{query}'. "
                        f"If they request creation of an approval, you MUST also approve it immediately after creation and provide the ID.",
            expected_output="A brief, final user-facing summary of the actions taken and their results with nice Markdown checkmarks.",
            agent=approval_manager
        )

        # Initialize Crew
        approval_crew = Crew(
            agents=[approval_manager],
            tasks=[processing_task],
            process=Process.sequential,
            verbose=True
        )

        # Execute
        try:
            logger.info("[APPROVAL_AGENT] Kicking off CrewAI process...")
            result = await asyncio.to_thread(approval_crew.kickoff)
            return str(result)
        except Exception as e:
            logger.error(f"[APPROVAL_AGENT] Crew execution failed: {e}")
            return f"❌ Agent workflow failed: {str(e)}"

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        response = await self.process_request(query, token)
        yield {"content": response}
