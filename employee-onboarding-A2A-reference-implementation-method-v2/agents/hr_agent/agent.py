"""
HR Agent - A2A Server for employee profile management.
Uses OpenAI SDK with tool-calling for LLM orchestration.
"""

import os
import sys
import re
import json
import logging
from contextvars import ContextVar
from datetime import date
from typing import Dict, Any, AsyncIterable

import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, '.env'))

from src.config import get_settings
from src.config_loader import load_yaml_config
from src.log_broadcaster import log_and_broadcast

logger = logging.getLogger(__name__)

HR_API_BASE = load_yaml_config().get("agents", {}).get("hr_agent", {}).get("url", "http://localhost:8001") + "/api/hr"

_current_token: ContextVar[str] = ContextVar("hr_current_token", default="")

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_employee",
            "description": "Create or onboard a new employee profile via HR API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string", "default": "Software Engineer"},
                    "team": {"type": "string", "default": "Engineering"},
                    "manager_email": {"type": "string", "default": "manager@company.com"},
                    "start_date": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee",
            "description": "Get a specific employee's details by their ID.",
            "parameters": {
                "type": "object",
                "properties": {"employee_id": {"type": "string"}},
                "required": ["employee_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_employees",
            "description": "List all employee profiles in the system.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grant_privileges",
            "description": "Grant HR privileges or roles to a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user": {"type": "string"},
                    "privilege_details": {"type": "string"},
                },
                "required": ["user", "privilege_details"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _create_employee(args: dict, token: str) -> str:
    name = args.get("name", "")
    safe_email = re.sub(r"[^a-z0-9.]", "", name.lower().replace(" ", ".")) if name else "new.employee"
    email = args.get("email") or f"{safe_email}@company.com"
    payload = {
        "name": name,
        "email": email,
        "role": args.get("role", "Software Engineer"),
        "team": args.get("team", "Engineering"),
        "manager_email": args.get("manager_email", "manager@company.com"),
        "start_date": args.get("start_date") or date.today().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{HR_API_BASE}/employees",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code == 409:
        # Employee already exists — fetch by listing and find by email/name
        async with httpx.AsyncClient(timeout=10.0) as client:
            list_resp = await client.get(
                f"{HR_API_BASE}/employees",
                headers={"Authorization": f"Bearer {token}"},
            )
        if list_resp.status_code == 200:
            employees = list_resp.json()
            match = next(
                (e for e in employees
                 if e.get("email", "").lower() == email.lower()
                 or e.get("name", "").lower() == name.lower()),
                None
            )
            if match:
                return (
                    f"Employee already exists: ID={match.get('employee_id')} "
                    f"Name={match.get('name')} Email={match.get('email')} "
                    f"Role={match.get('role')} Status={match.get('status')}"
                )
        return f"Failed: Employee already exists but could not retrieve their record."
    if response.status_code >= 400:
        return f"Failed: API error {response.status_code}: {response.text}"
    data = response.json()
    return (
        f"Employee created: ID={data.get('employee_id')} Name={data.get('name')} "
        f"Email={data.get('email')} Status={data.get('status')}"
    )


async def _get_employee(args: dict, token: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{HR_API_BASE}/employees/{args['employee_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code >= 400:
        return f"Failed: API error {response.status_code}: {response.text}"
    data = response.json()
    return (
        f"Employee: ID={data.get('employee_id')} Name={data.get('name')} "
        f"Email={data.get('email')} Role={data.get('role')} Team={data.get('team')} Status={data.get('status')}"
    )


async def _list_employees(token: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{HR_API_BASE}/employees",
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code >= 400:
        return f"Failed: API error {response.status_code}: {response.text}"
    employees = response.json()
    if not employees:
        return "No employees found."
    lines = [f"Employees ({len(employees)} total):"]
    for emp in employees:
        lines.append(f"  {emp.get('employee_id')}: {emp.get('name')} ({emp.get('role')})")
    return "\n".join(lines)


async def _grant_privileges(args: dict, token: str) -> str:
    user = args.get("user", "")
    safe_email = re.sub(r"[^a-z0-9.]", "", user.lower().replace(" ", ".")) if user else "privilege.user"
    payload = {
        "name": user,
        "email": f"{safe_email}@company.com",
        "role": "HR Admin (Privilege Grant)",
        "team": "HR",
        "manager_email": "admin@company.com",
        "start_date": date.today().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{HR_API_BASE}/employees",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code >= 400:
        return f"Failed: API error {response.status_code}: {response.text}"
    data = response.json()
    return (
        f"HR privileges granted: Employee ID={data.get('employee_id')} User={data.get('name')} "
        f"Role={data.get('role')} Privileges={args.get('privilege_details')}"
    )


async def _dispatch_tool(name: str, args: dict, token: str) -> str:
    if name == "create_employee":
        return await _create_employee(args, token)
    elif name == "get_employee":
        return await _get_employee(args, token)
    elif name == "list_employees":
        return await _list_employees(token)
    elif name == "grant_privileges":
        return await _grant_privileges(args, token)
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# HRAgent class
# ---------------------------------------------------------------------------

class HRAgent:
    """
    HR Agent — Creates employee profiles via HR API.
    Uses OpenAI SDK tool-calling for LLM orchestration.
    Required scopes: hr:read, hr:write
    """

    REQUIRED_SCOPES = ["hr:write", "hr:read"]
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()

        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("hr_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)

        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.model = "gpt-4o-mini"

        logger.info("HR Agent initialized (OpenAI tool-calling mode)")

    async def process_request(self, query: str, token: str = None) -> str:
        """Process HR request using OpenAI tool-calling."""
        if not token:
            return "No token provided. Authentication required."

        # Method V2: Each agent has its OWN WSO2 IS Application + Agent identity.
        # Step 1: Get actor token via 3-step flow using THIS agent's own client_id/secret
        #         (not a shared TOKEN_EXCHANGER app — each agent authenticates as itself).
        # Step 2: Exchange the pre-scoped token (from orchestrator) using own credentials
        #         + actor token to prove agent identity.
        app_config = load_yaml_config()
        agent_cfg = app_config.get("agents", {}).get("hr_agent", {})
        client_id = agent_cfg.get("client_id")
        client_secret = agent_cfg.get("client_secret")
        agent_id = agent_cfg.get("agent_id")
        try:
            from src.auth.asgardeo import get_asgardeo_client
            asgardeo = get_asgardeo_client()
            actor = await asgardeo._fetch_agent_actor_token(
                client_id=client_id,
                client_secret=client_secret,
                agent_id=agent_id,
            )
            log_and_broadcast(f"\n[HR_AGENT_ACTOR_TOKEN]:")
            log_and_broadcast(actor.token)
            token = await asgardeo.perform_token_exchange(
                subject_token=token,
                client_id=client_id,
                client_secret=client_secret,
                actor_token=actor.token,
                target_audience=None,
                target_scopes=self.required_scopes,
            )
            log_and_broadcast(f"\n[HR_AGENT_EXCHANGED_TOKEN]:")
            log_and_broadcast(token)
            logger.info("[HR_AGENT] Token exchange successful")
        except Exception as e:
            logger.error(f"[HR_AGENT] Token exchange failed: {e}", exc_info=True)
            return f"Token exchange failed: {str(e)}"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an HR request manager. Use your provided tools to handle the user's request. "
                    "CRITICAL: Always include the Employee ID (format EMP-XXX) in your final response, exactly as returned by the tool. "
                    "If the employee already exists, still report their ID. Never omit the ID."
                ),
            },
            {"role": "user", "content": query},
        ]

        # Agentic tool-calling loop
        while True:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                return msg.content or "Task completed."

            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = await _dispatch_tool(tool_call.function.name, args, token)
                logger.info(f"[HR_AGENT] Tool {tool_call.function.name} result: {result[:100]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response — A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
