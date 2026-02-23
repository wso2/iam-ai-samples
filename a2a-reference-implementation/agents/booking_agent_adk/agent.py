"""
ADK Booking Agent - Google Agent Development Kit implementation.

Uses ADK's built-in A2A protocol support — no executor.py needed.
Model: OpenAI gpt-4o-mini via LiteLLM (model="openai/gpt-4o-mini")
Token: Bearer token from incoming A2A request stored in ContextVar,
       read by tool functions when calling the Booking API.
"""

import os
import sys
import logging
from contextvars import ContextVar
from datetime import date, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)
load_dotenv(os.path.join(project_root, '.env'))

from google.adk.agents import LlmAgent

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Per-request token storage (set by TokenMiddleware in __main__.py)
# ─────────────────────────────────────────────────────────────────

_current_token: ContextVar[Optional[str]] = ContextVar("booking_token", default=None)

BOOKING_API_BASE = "http://localhost:8005/api/booking"


def _get_token() -> Optional[str]:
    return _current_token.get()


async def _call_api(method: str, path: str, json_data: dict = None) -> dict:
    """Make an authenticated call to the Booking API using the current request token."""
    token = _get_token()
    if not token:
        return {"success": False, "error": "No authentication token available"}

    url = f"{BOOKING_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            method=method,
            url=url,
            headers={"Authorization": f"Bearer {token}"},
            json=json_data
        )
        if response.status_code >= 400:
            return {"success": False, "error": f"API error {response.status_code}: {response.text}"}
        result = response.json()
        if isinstance(result, dict):
            result["success"] = True
        else:
            result = {"success": True, "data": result}
        return result


# ─────────────────────────────────────────────────────────────────
# Tool Functions — ADK calls these based on Gemini/OpenAI decisions
# ─────────────────────────────────────────────────────────────────

async def create_task(
    employee_id: str,
    task_type: str = "orientation",
    title: str = None,
    scheduled_date: str = None,
    duration_hours: float = 2.0,
    description: str = "Scheduled onboarding task"
) -> dict:
    """
    Schedule an onboarding task for an employee.

    Args:
        employee_id: Employee ID in format EMP-XXXX
        task_type: Type of task - orientation, security_training, hr_orientation, or general
        title: Title of the task (auto-generated from task_type if not provided)
        scheduled_date: ISO date string (YYYY-MM-DD). Defaults to 3 days from today.
        duration_hours: Duration in hours (default 2.0)
        description: Task description

    Returns:
        dict with task_id, employee_id, task_type, scheduled_date, status
    """
    if not scheduled_date:
        scheduled_date = (date.today() + timedelta(days=3)).isoformat()
    if not title:
        title = f"{task_type.replace('_', ' ').title()} Session"

    payload = {
        "employee_id": employee_id,
        "task_type": task_type,
        "title": title,
        "scheduled_date": scheduled_date,
        "duration_hours": duration_hours,
        "description": description
    }
    logger.info(f"[ADK_BOOKING] Creating task: {title} for {employee_id}")
    result = await _call_api("POST", "/tasks", payload)
    if result.get("success"):
        return {
            "success": True,
            "message": f"[OK] Task '{title}' scheduled for {employee_id} on {scheduled_date}",
            "task_id": result.get("task_id"),
            "scheduled_date": result.get("scheduled_date"),
            "status": result.get("status", "scheduled")
        }
    return result


async def schedule_delivery(
    employee_id: str,
    item_type: str = "laptop",
    item_description: str = None,
    delivery_address: str = "Office HQ, Floor 5",
    delivery_date: str = None
) -> dict:
    """
    Schedule an equipment delivery for an employee.

    Args:
        employee_id: Employee ID in format EMP-XXXX
        item_type: Type of item - laptop, equipment, phone, or monitor
        item_description: Description of the item (auto-generated if not provided)
        delivery_address: Delivery address
        delivery_date: ISO date string (YYYY-MM-DD). Defaults to 5 days from today.

    Returns:
        dict with delivery_id, employee_id, item_type, delivery_date, tracking_number, status
    """
    if not delivery_date:
        delivery_date = (date.today() + timedelta(days=5)).isoformat()
    if not item_description:
        item_description = f"Company {item_type}"

    payload = {
        "employee_id": employee_id,
        "item_type": item_type,
        "item_description": item_description,
        "delivery_address": delivery_address,
        "delivery_date": delivery_date
    }
    logger.info(f"[ADK_BOOKING] Scheduling delivery: {item_type} for {employee_id}")
    result = await _call_api("POST", "/deliveries", payload)
    if result.get("success"):
        return {
            "success": True,
            "message": f"[OK] {item_type.title()} delivery scheduled for {employee_id} on {delivery_date}",
            "delivery_id": result.get("delivery_id"),
            "tracking_number": result.get("tracking_number"),
            "delivery_date": result.get("delivery_date"),
            "status": result.get("status", "scheduled")
        }
    return result


async def list_tasks(employee_id: str = None) -> dict:
    """
    List scheduled onboarding tasks.

    Args:
        employee_id: Optional employee ID to filter tasks (format EMP-XXXX)

    Returns:
        dict with list of tasks
    """
    path = "/tasks"
    if employee_id:
        path += f"?employee_id={employee_id}"
    logger.info(f"[ADK_BOOKING] Listing tasks (employee_id={employee_id})")
    async with httpx.AsyncClient(timeout=10.0) as client:
        token = _get_token()
        response = await client.get(
            f"{BOOKING_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code >= 400:
            return {"success": False, "error": f"API error {response.status_code}"}
        tasks = response.json()
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }


async def list_deliveries(employee_id: str = None) -> dict:
    """
    List scheduled equipment deliveries.

    Args:
        employee_id: Optional employee ID to filter deliveries (format EMP-XXXX)

    Returns:
        dict with list of deliveries
    """
    path = "/deliveries"
    if employee_id:
        path += f"?employee_id={employee_id}"
    logger.info(f"[ADK_BOOKING] Listing deliveries (employee_id={employee_id})")
    async with httpx.AsyncClient(timeout=10.0) as client:
        token = _get_token()
        response = await client.get(
            f"{BOOKING_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code >= 400:
            return {"success": False, "error": f"API error {response.status_code}"}
        deliveries = response.json()
        return {
            "success": True,
            "count": len(deliveries),
            "deliveries": deliveries
        }


# ─────────────────────────────────────────────────────────────────
# ADK Agent Definition
# ─────────────────────────────────────────────────────────────────

root_agent = LlmAgent(
    # Uses OpenAI via LiteLLM — ADK supports any LiteLLM-compatible model
    model="openai/gpt-4o-mini",
    name="booking_agent",
    description=(
        "Schedules onboarding tasks (orientation, training sessions) and "
        "equipment deliveries (laptops, phones, monitors) for new employees."
    ),
    instruction="""You are a Booking Agent for an employee onboarding system.

You help schedule onboarding tasks and equipment deliveries for new employees.

Available operations:
- **create_task**: Schedule an onboarding task (orientation, training, etc.)
- **schedule_delivery**: Schedule equipment delivery (laptop, phone, monitor, etc.)
- **list_tasks**: List scheduled tasks (optionally for a specific employee)
- **list_deliveries**: List scheduled deliveries (optionally for a specific employee)

Rules:
- Always extract the employee ID (format: EMP-XXXX) from the request
- For tasks: determine task_type from context (orientation, security_training, hr_orientation, general). If unspecified, default to 'orientation'.
- For deliveries: determine item_type from context (laptop, equipment, phone, monitor). If unspecified, default to 'laptop'.
- If listing is requested, call the appropriate list tool
- If both tasks and deliveries are asked for, call both list_tasks and list_deliveries
- Always provide clear, concise confirmation of what was scheduled
- CRITICAL: Do NOT ask the user for confirmation or clarification before scheduling. Automatically proceed with 'orientation' and 'laptop' as defaults and execute the underlying tool calls immediately.
- If no token is available, inform the user authentication is required
""",
    tools=[create_task, schedule_delivery, list_tasks, list_deliveries],
)
