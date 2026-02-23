"""
HR Agent - A2A Server for employee profile management.
Calls the real HR API with token-based scope validation.
Uses Vercel AI SDK (vercel-ai-sdk) for LLM tool-calling.
"""

import os
import sys
import re
import logging
from contextvars import ContextVar
from datetime import date
from typing import Dict, Any, AsyncIterable

import vercel_ai_sdk as ai
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

# ContextVar so module-level tools can read the current auth token
# without needing `self` — same pattern as booking_agent_adk
_current_token: ContextVar[str] = ContextVar("hr_current_token", default="")


# ---------------------------------------------------------------------------
# Module-level tools — the ONLY pattern supported by @ai.tool
# (class methods cause a Pydantic schema error on the `self` parameter)
# ---------------------------------------------------------------------------

@ai.tool
async def create_employee(
    name: str,
    email: str = None,
    role: str = "Software Engineer",
    team: str = "Engineering",
    manager_email: str = "manager@company.com",
    start_date: str = None,
) -> str:
    """Create or onboard a new employee profile via HR API."""
    token = _current_token.get()
    if not start_date:
        start_date = date.today().isoformat()

    safe_email = re.sub(r"[^a-z0-9.]", "", name.lower().replace(" ", ".")) if name else "new.employee"
    payload = {
        "name": name,
        "email": email or f"{safe_email}@company.com",
        "role": role,
        "team": team,
        "manager_email": manager_email,
        "start_date": start_date,
    }
    logger.info(f"[HR_AGENT] Creating employee via API (Vercel): {payload['name']}")

    url = f"{HR_API_BASE}/employees"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)

    if response.status_code >= 400:
        return f"❌ Failed: API error {response.status_code}: {response.text}"

    data = response.json()
    return (
        f"✅ Employee created via HR API!\n"
        f"- ID: {data.get('employee_id')}\n"
        f"- Name: {data.get('name')}\n"
        f"- Email: {data.get('email')}\n"
        f"- Status: {data.get('status')}"
    )


@ai.tool
async def get_employee(employee_id: str) -> str:
    """Get a specific employee's details by their ID via HR API."""
    token = _current_token.get()
    url = f"{HR_API_BASE}/employees/{employee_id}"
    logger.info(f"[HR_AGENT] Getting employee {employee_id} via API (Vercel)")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code >= 400:
        return f"❌ Failed: API error {response.status_code}: {response.text}"

    data = response.json()
    return (
        f"📋 Employee Details:\n"
        f"- ID: {data.get('employee_id')}\n"
        f"- Name: {data.get('name')}\n"
        f"- Email: {data.get('email')}\n"
        f"- Role: {data.get('role')}\n"
        f"- Team: {data.get('team')}\n"
        f"- Status: {data.get('status')}"
    )


@ai.tool
async def list_employees() -> str:
    """List or show all employee profiles in the system via HR API."""
    token = _current_token.get()
    url = f"{HR_API_BASE}/employees"
    logger.info("[HR_AGENT] Listing employees via API (Vercel)")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code >= 400:
        return f"❌ Failed: API error {response.status_code}: {response.text}"

    employees = response.json()
    if not employees:
        return "📋 No employees found in the system."

    lines = [f"📋 Employees ({len(employees)} total):"]
    for emp in employees:
        lines.append(f"  - {emp.get('employee_id')}: {emp.get('name')} ({emp.get('role')})")
    return "\n".join(lines)


@ai.tool
async def grant_privileges(user: str, privilege_details: str) -> str:
    """Grant HR privileges, access, or specific roles to a user via HR API."""
    token = _current_token.get()
    safe_email = re.sub(r"[^a-z0-9.]", "", user.lower().replace(" ", ".")) if user else "privilege.user"
    payload = {
        "name": user,
        "email": f"{safe_email}@company.com",
        "role": "HR Admin (Privilege Grant)",
        "team": "HR",
        "manager_email": "admin@company.com",
        "start_date": date.today().isoformat(),
    }
    logger.info(f"[HR_AGENT] Granting HR privileges to {user} via API (Vercel)")

    url = f"{HR_API_BASE}/employees"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)

    if response.status_code >= 400:
        return f"❌ Failed: API error {response.status_code}: {response.text}"

    data = response.json()
    return (
        f"✅ HR privileges granted via API!\n"
        f"- Employee ID: {data.get('employee_id', 'N/A')}\n"
        f"- User: {data.get('name', user)}\n"
        f"- Role: {data.get('role', 'HR Admin')}\n"
        f"- Status: granted\n"
        f"- Effective: immediately\n"
        f"- Privileges: {privilege_details}"
    )


# ---------------------------------------------------------------------------
# Agent function — passed directly to ai.run()
# ---------------------------------------------------------------------------

async def _hr_agent_fn(llm, query: str) -> None:
    """Top-level agent coroutine executed by ai.run()."""
    messages = ai.make_messages(
        system=(
            "You are an HR request manager. Use your provided tools to handle the user's request. "
            "Only output the results returned by your tools. Do not add conversational filler."
        ),
        user=query,
    )
    await ai.stream_loop(
        llm,
        messages=messages,
        tools=[create_employee, get_employee, list_employees, grant_privileges],
    )


# ---------------------------------------------------------------------------
# HRAgent class — thin wrapper that sets the ContextVar and drives ai.run()
# ---------------------------------------------------------------------------

class HRAgent:
    """
    HR Agent — Creates employee profiles via HR API.
    Uses Vercel AI SDK for LLM tool-calling.
    Required scopes: hr:read, hr:write
    """

    REQUIRED_SCOPES = ["hr:read", "hr:write"]
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()

        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("hr_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)
        self.openai_api_key = self.settings.openai_api_key

        self.llm = ai.openai.OpenAIModel(
            model="gpt-4o-mini",
            api_key=self.openai_api_key,
        )

        logger.info("HR Agent initialized (Vercel AI SDK mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  HR API: {HR_API_BASE}")

    async def process_request(self, query: str, token: str = None) -> str:
        """Process HR request using Vercel AI SDK."""
        if not token:
            return "❌ No token provided. Authentication required."

        # Set the ContextVar so module-level tools can read the token
        token_var = _current_token.set(token)

        logger.info("[HR_AGENT] Forwarding query to Vercel AI SDK...")
        result_text = ""
        try:
            # ai.run() provides the Runtime context that @ai.tool and ai.stream_loop need
            run_result = ai.run(_hr_agent_fn, self.llm, query)
            async for msg in run_result:
                if hasattr(msg, "text_delta") and msg.text_delta:
                    result_text += msg.text_delta

            if not result_text:
                result_text = "✅ Task completed."

        except Exception as e:
            logger.error(f"[HR_AGENT] Vercel execution failed: {e}", exc_info=True)
            result_text = f"❌ Request execution failed: {str(e)}"
        finally:
            _current_token.reset(token_var)

        return result_text

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response — A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
