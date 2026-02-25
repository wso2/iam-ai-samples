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
    start_time: str = None,
    duration_hours: float = 2.0,
    description: str = "Scheduled onboarding task"
) -> dict:
    """
    Schedule an onboarding task (e.g. orientation session) for an employee.

    Args:
        employee_id: Employee ID in format EMP-XXXX
        task_type: Type of task - orientation, security_training, hr_orientation, or general
        title: Title of the task (auto-generated from task_type if not provided)
        scheduled_date: ISO date string (YYYY-MM-DD). Defaults to 3 days from today.
        start_time: Time in HH:MM 24h format, e.g. "15:00" for 3 PM. Defaults to "09:00".
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
    if start_time:
        payload["start_time"] = start_time

    logger.info(f"[ADK_BOOKING] Creating task: {title} for {employee_id} on {scheduled_date} at {start_time or '09:00'}")
    result = await _call_api("POST", "/tasks", payload)
    if result.get("success"):
        return {
            "success": True,
            "message": f"[OK] Task '{title}' scheduled for {employee_id} on {scheduled_date} at {start_time or '09:00'}",
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
    delivery_date: str = None,
    start_time: str = None
) -> dict:
    """
    Schedule an equipment delivery (e.g. laptop) for an employee.

    Args:
        employee_id: Employee ID in format EMP-XXXX
        item_type: Type of item - laptop, equipment, phone, or monitor
        item_description: Description of the item (auto-generated if not provided)
        delivery_address: Delivery address
        delivery_date: ISO date string (YYYY-MM-DD). Defaults to 5 days from today.
        start_time: Delivery time in HH:MM 24h format, e.g. "08:00". Defaults to "10:00".

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
    if start_time:
        payload["start_time"] = start_time

    logger.info(f"[ADK_BOOKING] Scheduling delivery: {item_type} for {employee_id} on {delivery_date} at {start_time or '10:00'}")
    result = await _call_api("POST", "/deliveries", payload)
    if result.get("success"):
        return {
            "success": True,
            "message": f"[OK] {item_type.title()} delivery scheduled for {employee_id} on {delivery_date} at {start_time or '10:00'}",
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

from datetime import datetime as _dt

def _build_instruction() -> str:
    today = _dt.utcnow().strftime("%B %d, %Y")
    return f"""You are a Booking Agent for an employee onboarding system.

TODAY'S DATE: {today}
CURRENT YEAR: {_dt.utcnow().year}

IMPORTANT: When the user says a date like "March 1st" or "next Friday", always use the CURRENT YEAR ({_dt.utcnow().year}) unless they explicitly specify a different year.

You help schedule onboarding tasks and equipment deliveries for new employees.

Available operations:
- **create_task**: Schedule an onboarding task (orientation, training, etc.)
- **schedule_delivery**: Schedule equipment delivery (laptop, phone, monitor, etc.)
- **list_tasks**: List scheduled tasks (optionally for a specific employee)
- **list_deliveries**: List scheduled deliveries (optionally for a specific employee)

Rules:
- Always extract the employee ID (format: EMP-XXXX) from the request or context.
- `create_task` is ONLY for scheduling sessions/orientations/trainings. Use the ORIENTATION date + time.
- `schedule_delivery` is ONLY for physical equipment delivery. Use the DELIVERY date + time.
- NEVER call `create_task` with the delivery date.
- NEVER call `schedule_delivery` with the orientation date.
- Each tool must be called exactly ONCE per item requested.
- Always extract the time from the request and pass it as `start_time` in "HH:MM" 24h format.
  * "3 PM" or "3:00 pm" → "15:00"
  * "8 AM" or "8:00 am" → "08:00"
  * "2:30 PM" → "14:30"
  * If no time given → omit start_time (API will use default)

Date+time mapping — follow this exactly:
  "orientation on March 5th at 3 PM"    → call `create_task` with scheduled_date="2026-03-05", start_time="15:00"  (ONE call)
  "laptop delivery on March 6th at 8 AM" → call `schedule_delivery` with delivery_date="2026-03-06", start_time="08:00" (ONE call)

- Each requested action = exactly ONE tool call on exactly ONE date. Do not repeat calls.
- Always confirm ALL scheduled items in your response, each on its own line with date and time.
- CRITICAL: Do NOT ask for confirmation. Execute all tool calls immediately.
- If no token is available, inform the user authentication is required.
"""

root_agent = LlmAgent(
    # Uses OpenAI via LiteLLM — ADK supports any LiteLLM-compatible model
    model="openai/gpt-4o-mini",
    name="booking_agent",
    description=(
        "Schedules onboarding tasks (orientation, training sessions) and "
        "equipment deliveries (laptops, phones, monitors) for new employees."
    ),
    instruction=_build_instruction(),
    tools=[create_task, schedule_delivery, list_tasks, list_deliveries],
)
