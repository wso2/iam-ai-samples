"""
HR Agent - A2A Server for employee profile management.
Calls the real HR API with token-based scope validation.
Uses LLM (gpt-4o-mini) to classify incoming requests.
"""

import os
import sys
import json
import re
import logging
from datetime import date
from typing import Optional, Dict, Any, AsyncIterable

import httpx
from dotenv import load_dotenv

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, '.env'))

from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)

# The HR API is mounted on the same server
HR_API_BASE = "http://localhost:8001/api/hr"

HR_CLASSIFICATION_PROMPT = """You are an HR request classifier for an employee management agent.
Given a natural language HR request, classify it into exactly ONE action and extract parameters.

Available actions:
1. "create_employee" - Create/onboard a new employee profile
2. "list_employees" - List or show all employees
3. "get_employee" - Get a specific employee by ID
4. "grant_privileges" - Grant HR privileges/access/role to a user (e.g. after approval)

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "action": "<one of: create_employee, list_employees, get_employee, grant_privileges>",
  "params": {
    "name": "<employee name if mentioned>",
    "email": "<email if mentioned>",
    "role": "<role/position if mentioned>",
    "team": "<team if mentioned>",
    "employee_id": "<employee ID if mentioned, pattern EMP-XXXX>",
    "user": "<target user for privilege grant>"
  }
}

Rules:
- If request mentions create, onboard, hire, add, new employee -> create_employee
- If request mentions list, show, all employees -> list_employees
- If request mentions get, find, lookup + specific employee ID -> get_employee
- If request mentions privilege, grant, permission, role, access, elevate, approved -> grant_privileges
- Extract names, emails, roles, teams from context
- For grant_privileges, extract the target user name
- Only include params that are actually mentioned in the request
"""


class HRAgent:
    """
    HR Agent - Creates employee profiles via HR API.
    Uses LLM to classify requests instead of keyword matching.
    Required scopes: hr:read, hr:write
    """

    REQUIRED_SCOPES = ["hr:read", "hr:write"]
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()

        # Load agent config
        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("hr_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)
        self.openai_api_key = self.settings.openai_api_key

        logger.info(f"HR Agent initialized (LLM classification mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  HR API: {HR_API_BASE}")

    async def _classify_request(self, query: str) -> dict:
        """Use OpenAI gpt-4o-mini to classify the HR request."""
        logger.info(f"[HR_AGENT] LLM classifying: {query[:100]}...")

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
                        {"role": "system", "content": HR_CLASSIFICATION_PROMPT},
                        {"role": "user", "content": query}
                    ]
                }
            )

            if response.status_code != 200:
                logger.error(f"[HR_AGENT] OpenAI error: {response.status_code}")
                raise Exception(f"LLM classification failed: {response.status_code}")

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            classification = json.loads(content)
            logger.info(f"[HR_AGENT] LLM classified -> action={classification['action']}")
            return classification

    async def _call_api(self, method: str, path: str, token: str, json_data: dict = None) -> Dict[str, Any]:
        """Make an authenticated call to the HR API."""
        url = f"{HR_API_BASE}{path}"
        logger.info(f"[HR_AGENT] API call: {method} {url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_data
            )
            if response.status_code >= 400:
                error_detail = response.text
                logger.error(f"[HR_AGENT] API error {response.status_code}: {error_detail}")
                return {"success": False, "error": f"API error {response.status_code}: {error_detail}"}
            result = response.json()
            result["success"] = True
            return result

    async def create_employee(self, employee_data: Dict[str, Any], token: str) -> Dict[str, Any]:
        """Create employee profile via HR API (POST /api/hr/employees)."""
        name = employee_data.get("name", "New Employee")
        safe_email = re.sub(r'[^a-z0-9.]', '', name.lower().replace(' ', '.'))
        if not safe_email:
            safe_email = "new.employee"
        payload = {
            "name": name,
            "email": employee_data.get("email", f"{safe_email}@company.com"),
            "role": employee_data.get("role", "Software Engineer"),
            "team": employee_data.get("team", "Engineering"),
            "manager_email": employee_data.get("manager_email", "manager@company.com"),
            "start_date": employee_data.get("start_date", date.today().isoformat())
        }
        logger.info(f"[HR_AGENT] Creating employee via API: {payload['name']}")
        return await self._call_api("POST", "/employees", token, payload)

    async def get_employee(self, employee_id: str, token: str) -> Dict[str, Any]:
        """Get employee by ID via HR API (GET /api/hr/employees/{id})."""
        return await self._call_api("GET", f"/employees/{employee_id}", token)

    async def list_employees(self, token: str) -> Dict[str, Any]:
        """List all employees via HR API (GET /api/hr/employees)."""
        url = f"{HR_API_BASE}/employees"
        logger.info(f"[HR_AGENT] Listing employees via API")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code >= 400:
                return {"success": False, "error": f"API error {response.status_code}: {response.text}"}
            return {"success": True, "employees": response.json()}

    async def grant_privileges(self, user: str, privilege_details: str, token: str) -> Dict[str, Any]:
        """Grant HR privileges to a user via HR API."""
        safe_email_user = re.sub(r'[^a-z0-9.]', '', user.lower().replace(' ', '.'))
        if not safe_email_user:
            safe_email_user = "privilege.user"
        payload = {
            "name": user,
            "email": f"{safe_email_user}@company.com",
            "role": "HR Admin (Privilege Grant)",
            "team": "HR",
            "manager_email": "admin@company.com",
            "start_date": date.today().isoformat()
        }
        logger.info(f"[HR_AGENT] Granting HR privileges to {user} via API")
        result = await self._call_api("POST", "/employees", token, payload)
        if result.get("success"):
            result["privilege"] = privilege_details
            result["status"] = "granted"
            result["effective_from"] = "immediately"
        return result

    async def process_request(self, query: str, token: str = None) -> str:
        """Process HR request using LLM classification to determine action."""
        if not token:
            return "❌ No token provided. Authentication required."

        # LLM classifies the request
        try:
            classification = await self._classify_request(query)
        except Exception as e:
            logger.error(f"[HR_AGENT] Classification failed: {e}")
            return f"❌ Failed to classify request: {str(e)}"

        action = classification.get("action", "unknown")
        params = classification.get("params", {})
        logger.info(f"[HR_AGENT] Action: {action}, Params: {params}")

        if action == "create_employee":
            result = await self.create_employee(params, token)
            if result.get("success"):
                return (
                    f"✅ Employee created via HR API!\n"
                    f"- ID: {result.get('employee_id')}\n"
                    f"- Name: {result.get('name')}\n"
                    f"- Email: {result.get('email')}\n"
                    f"- Status: {result.get('status')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "get_employee":
            employee_id = params.get("employee_id", "EMP-001")
            result = await self.get_employee(employee_id, token)
            if result.get("success"):
                return (
                    f"📋 Employee Details:\n"
                    f"- ID: {result.get('employee_id')}\n"
                    f"- Name: {result.get('name')}\n"
                    f"- Email: {result.get('email')}\n"
                    f"- Role: {result.get('role')}\n"
                    f"- Team: {result.get('team')}\n"
                    f"- Status: {result.get('status')}"
                )
            return f"❌ Failed: {result.get('error')}"

        if action == "list_employees":
            result = await self.list_employees(token)
            if result.get("success"):
                employees = result.get("employees", [])
                if not employees:
                    return "📋 No employees found in the system."
                lines = [f"📋 Employees ({len(employees)} total):"]
                for emp in employees:
                    lines.append(f"  - {emp.get('employee_id')}: {emp.get('name')} ({emp.get('role')})")
                return "\n".join(lines)
            return f"❌ Failed: {result.get('error')}"

        if action == "grant_privileges":
            user = params.get("user", params.get("name", "Unknown User"))
            result = await self.grant_privileges(user, query, token)
            if result.get("success"):
                return (
                    f"✅ HR privileges granted via API!\n"
                    f"- Employee ID: {result.get('employee_id', 'N/A')}\n"
                    f"- User: {result.get('name', user)}\n"
                    f"- Role: {result.get('role', 'HR Admin')}\n"
                    f"- Status: granted\n"
                    f"- Effective: immediately"
                )
            return f"❌ Failed: {result.get('error')}"

        return f"❌ Unknown action: {action}. Could not process the request."

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response - A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
