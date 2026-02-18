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
from typing import Dict, Any, AsyncIterable

import httpx
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

APPROVAL_CLASSIFICATION_PROMPT = """You are an approval workflow request classifier.
Given a natural language request, classify it into exactly ONE action and extract parameters.

Available actions:
1. "create_request" - Create a new approval request (and auto-approve for demo)
2. "approve_request" - Approve an existing approval request by ID
3. "reject_request" - Reject an existing approval request by ID
4. "get_request" - Get details of a specific approval request by ID
5. "list_requests" - List approval requests, optionally filtered by status

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "action": "<one of: create_request, approve_request, reject_request, get_request, list_requests>",
  "params": {
    "request_id": "<approval request ID if mentioned, pattern APR-XXXX>",
    "target_user": "<target user/employee name or email>",
    "request_type": "<type of request: access_request, privilege_request, etc>",
    "reason": "<reason for the request>",
    "status_filter": "<pending, approved, or rejected if filtering>"
  }
}

CRITICAL CLASSIFICATION RULES:
1. **CREATE vs APPROVE**:
   - If request says "Approve/Review/Check request to GRANT/GIVE permissions" → create_request (NEW approval needed)
   - If request says "Approve request APR-1234" (with APR-ID) → approve_request (EXISTING approval)
   - If NO APR-ID is mentioned → create_request
   - If APR-ID IS mentioned → approve_request/reject_request

2. Other rules:
   - If request mentions create, submit, need approval, request access → create_request
   - If request mentions list, show, pending, status, check (without specific ID) → list_requests
   - Extract request IDs matching pattern APR-XXXX
   - Extract target user names and emails from context
   - For list_requests, detect status filter (pending/approved/rejected)
   - Only include params that are actually mentioned

Examples:
- "Approve request to grant IT permissions to Alice" → create_request (no APR-ID)
- "Approve APR-1234" → approve_request (has APR-ID)
- "Check if we can give Bob admin access" → create_request (no APR-ID)
- "Reject request APR-5678" → reject_request (has APR-ID)
"""


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
        logger.info(f"Approval Agent initialized (LLM classification mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  Approval API: {APPROVAL_API_BASE}")

    async def _classify_request(self, query: str) -> dict:
        """Use OpenAI gpt-4o-mini to classify the approval request."""
        logger.info(f"[APPROVAL_AGENT] LLM classifying: {query[:100]}...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": APPROVAL_CLASSIFICATION_PROMPT},
                        {"role": "user", "content": query}
                    ]
                }
            )

            if response.status_code != 200:
                logger.error(f"[APPROVAL_AGENT] OpenAI error: {response.status_code}")
                raise Exception(f"LLM classification failed: {response.status_code}")

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            classification = json.loads(content)
            logger.info(f"[APPROVAL_AGENT] LLM classified -> action={classification['action']}")
            return classification

    async def _llm_decide_approval(self, request_params: dict, original_query: str) -> dict:
        """
        Use LLM to intelligently decide whether to approve or deny an approval request.
        Returns: {"decision": "approved"|"denied", "reason": "explanation"}
        """
        logger.info(f"[APPROVAL_AGENT] LLM deciding approval for: {request_params}")

        decision_prompt = f"""You are an intelligent approval manager for an organization.
Analyze the following approval request and decide whether to APPROVE or DENY it.

Request Details:
- Type: {request_params.get('request_type', 'access_request')}
- Target User: {request_params.get('target_user', 'Unknown')}
- Target Resource: {request_params.get('target_resource', 'N/A')}
- Reason: {request_params.get('reason', 'No reason provided')}
- Priority: {request_params.get('priority', 'normal')}

Original Request: {original_query}

Decision Criteria:
1. APPROVE if:
   - Reason is clear and valid
   - Request seems reasonable for business operations
   - User role/position seems appropriate
   - No obvious security risks
   - Standard onboarding/offboarding requests

2. DENY if:
   - Reason is vague, missing, or suspicious
   - Request seems excessive or unusual
   - Contains words like "urgent", "emergency" without proper justification
   - Requests sensitive/privileged access without clear need
   - Any indication of policy violation

Respond with ONLY a JSON object (no markdown):
{{
  "decision": "approved" or "denied",
  "reason": "Brief explanation (1 sentence)"
}}
"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,  # Slight randomness for realistic decisions
                    "messages": [
                        {"role": "system", "content": "You are an approval decision engine. Always respond with valid JSON only."},
                        {"role": "user", "content": decision_prompt}
                    ]
                }
            )

            if response.status_code != 200:
                logger.error(f"[APPROVAL_AGENT] OpenAI error for decision: {response.status_code}")
                # Default to denial if LLM fails
                return {"decision": "denied", "reason": "Unable to verify approval criteria"}

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Clean up markdown if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            decision = json.loads(content)
            logger.info(f"[APPROVAL_AGENT] LLM decision -> {decision['decision']}: {decision['reason']}")
            return decision

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

    async def create_approval_request(self, request_data: Dict[str, Any], token: str) -> Dict[str, Any]:
        """Create approval request via Approval API (POST /api/approval/requests)."""
        payload = {
            "request_type": request_data.get("request_type", "access_request"),
            "target_user": request_data.get("target_user", "employee@company.com"),
            "target_resource": request_data.get("target_resource"),
            "approver_email": request_data.get("approver", "manager@company.com"),
            "reason": request_data.get("reason", "Standard approval request"),
            "priority": request_data.get("priority", "normal")
        }
        logger.info(f"[APPROVAL_AGENT] Creating approval request via API: {payload['request_type']}")
        return await self._call_api("POST", "/requests", token, payload)

    async def approve_request(self, request_id: str, token: str) -> Dict[str, Any]:
        """Approve a pending request via Approval API."""
        logger.info(f"[APPROVAL_AGENT] Approving request {request_id} via API")
        return await self._call_api("POST", f"/requests/{request_id}/approve", token)

    async def reject_request(self, request_id: str, token: str) -> Dict[str, Any]:
        """Reject a pending request via Approval API."""
        logger.info(f"[APPROVAL_AGENT] Rejecting request {request_id} via API")
        return await self._call_api("POST", f"/requests/{request_id}/reject", token)

    async def get_request(self, request_id: str, token: str) -> Dict[str, Any]:
        """Get approval request by ID via Approval API."""
        return await self._call_api("GET", f"/requests/{request_id}", token)

    async def list_requests(self, token: str, status: str = None) -> Dict[str, Any]:
        """List approval requests via Approval API."""
        path = "/requests"
        if status:
            path += f"?status={status}"
        url = f"{APPROVAL_API_BASE}{path}"
        logger.info(f"[APPROVAL_AGENT] Listing approval requests via API")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code >= 400:
                return {"success": False, "error": f"API error {response.status_code}: {response.text}"}
            return {"success": True, "requests": response.json()}

    async def process_request(self, query: str, token: str = None) -> str:
        """Process approval request using LLM classification to determine action."""
        if not token:
            return "❌ No token provided. Authentication required."

        # LLM classifies the request
        try:
            classification = await self._classify_request(query)
        except Exception as e:
            logger.error(f"[APPROVAL_AGENT] Classification failed: {e}")
            return f"❌ Failed to classify request: {str(e)}"

        action = classification.get("action", "unknown")
        params = classification.get("params", {})
        logger.info(f"[APPROVAL_AGENT] Action: {action}, Params: {params}")

        if action == "create_request":
            result = await self.create_approval_request(params, token)
            if result.get("success"):
                created_id = result.get("request_id")
                if created_id:
                    # Use LLM to decide whether to approve or deny
                    decision = await self._llm_decide_approval(params, query)
                    
                    if decision["decision"] == "approved":
                        approve_result = await self.approve_request(created_id, token)
                        if approve_result.get("success"):
                            return (
                                f"✅ Approval request created and approved!\n"
                                f"- ID: {approve_result.get('request_id', created_id)}\n"
                                f"- Status: {approve_result.get('status', 'approved')}\n"
                                f"- Reason: {decision['reason']}"
                            )
                    else:
                        # Deny the request
                        reject_result = await self.reject_request(created_id, token)
                        if reject_result.get("success"):
                            return (
                                f"❌ Approval request created but DENIED!\n"
                                f"- ID: {reject_result.get('request_id', created_id)}\n"
                                f"- Status: {reject_result.get('status', 'rejected')}\n"
                                f"- Reason: {decision['reason']}"
                            )
                
                return (
                    f"✅ Approval request created via API!\n"
                    f"- ID: {result.get('request_id')}\n"
                    f"- Status: {result.get('status', 'pending')}\n"
                    f"- Type: {result.get('request_type')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "approve_request":
            request_id = params.get("request_id", "APR-UNKNOWN")
            result = await self.approve_request(request_id, token)
            if result.get("success"):
                return (
                    f"✅ Approval request approved via API!\n"
                    f"- ID: {result.get('request_id', request_id)}\n"
                    f"- Status: {result.get('status', 'approved')}\n"
                    f"- Approved by: {result.get('approved_by', 'N/A')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "reject_request":
            request_id = params.get("request_id", "APR-UNKNOWN")
            result = await self.reject_request(request_id, token)
            if result.get("success"):
                return (
                    f"❌ Approval request rejected via API!\n"
                    f"- ID: {result.get('request_id', request_id)}\n"
                    f"- Status: {result.get('status', 'rejected')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "get_request":
            request_id = params.get("request_id", "APR-UNKNOWN")
            result = await self.get_request(request_id, token)
            if result.get("success"):
                return (
                    f"📋 Approval Request Details:\n"
                    f"- ID: {result.get('request_id')}\n"
                    f"- Type: {result.get('request_type')}\n"
                    f"- Target: {result.get('target_user')}\n"
                    f"- Status: {result.get('status')}\n"
                    f"- Approver: {result.get('approver_email')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "list_requests":
            status_filter = params.get("status_filter")
            result = await self.list_requests(token, status_filter)
            if result.get("success"):
                requests = result.get("requests", [])
                if not requests:
                    return f"📋 No {'(' + status_filter + ') ' if status_filter else ''}approval requests found."
                lines = [f"📋 Approval Requests ({len(requests)} total):"]
                for r in requests:
                    lines.append(f"  - {r.get('request_id')}: {r.get('request_type')} ({r.get('status')})")
                return "\n".join(lines)
            return f"❌ Failed: {result.get('error')}"

        return f"❌ Unknown action: {action}. Could not process the request."

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        response = await self.process_request(query, token)
        yield {"content": response}
