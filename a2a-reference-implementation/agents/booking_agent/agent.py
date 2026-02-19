"""
Booking Agent - A2A Server for task scheduling.
Calls the real Booking API with token-based scope validation.
Uses LLM (gpt-4o-mini) to classify incoming requests.
"""

import os
import sys
import re
import json
import logging
from datetime import date, timedelta
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

# The Booking API is mounted on the same server
BOOKING_API_BASE = "http://localhost:8004/api/booking"

BOOKING_CLASSIFICATION_PROMPT = """You are a booking/scheduling request classifier for an onboarding system.
Given a natural language request, classify it into exactly ONE action and extract parameters.

Available actions:
1. "create_task" - Schedule an onboarding task (orientation, training, session)
2. "schedule_delivery" - Schedule equipment/item delivery (laptop, equipment)
3. "list_tasks" - List/show scheduled tasks
4. "list_deliveries" - List/show scheduled deliveries
5. "list_all" - List both tasks and deliveries

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "action": "<one of: create_task, schedule_delivery, list_tasks, list_deliveries, list_all>",
  "params": {
    "employee_id": "<employee ID if mentioned, pattern EMP-XXXX>",
    "task_type": "<orientation, security_training, hr_orientation, general>",
    "title": "<task title if mentioned>",
    "item_type": "<laptop, equipment, phone, monitor>",
    "item_description": "<description of item>",
    "description": "<task description>"
  }
}

Rules:
- If request mentions orientation, training, session, onboarding task -> create_task
- If request mentions delivery, laptop, equipment, ship, send, device -> schedule_delivery
- If request mentions list/show tasks, scheduled tasks -> list_tasks
- If request mentions list/show deliveries, shipments -> list_deliveries
- If request mentions list/show all, status, check, pending -> list_all
- If request says "schedule" with equipment context -> schedule_delivery, otherwise create_task
- Extract employee IDs matching pattern EMP-XXXX
- For create_task: determine task_type from context (security_training, hr_orientation, general)
- Only include params that are actually mentioned
"""


class BookingAgent:
    """
    Booking Agent - Schedules tasks and deliveries via Booking API.
    Uses LLM to classify requests instead of keyword matching.
    Required scopes: booking:read, booking:write
    """

    REQUIRED_SCOPES = ["booking:read", "booking:write"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.settings = get_settings()
        app_config = load_yaml_config()
        agent_config = app_config.get("agents", {}).get("booking_agent", {})
        self.required_scopes = agent_config.get("required_scopes", self.REQUIRED_SCOPES)
        self.openai_api_key = self.settings.openai_api_key
        logger.info(f"Booking Agent initialized (LLM classification mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  Booking API: {BOOKING_API_BASE}")

    async def _classify_request(self, query: str) -> dict:
        """Use OpenAI gpt-4o-mini to classify the booking request."""
        logger.info(f"[BOOKING_AGENT] LLM classifying: {query[:100]}...")

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
                        {"role": "system", "content": BOOKING_CLASSIFICATION_PROMPT},
                        {"role": "user", "content": query}
                    ]
                }
            )

            if response.status_code != 200:
                logger.error(f"[BOOKING_AGENT] OpenAI error: {response.status_code}")
                raise Exception(f"LLM classification failed: {response.status_code}")

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            classification = json.loads(content)
            logger.info(f"[BOOKING_AGENT] LLM classified -> action={classification['action']}")
            return classification

    async def _call_api(self, method: str, path: str, token: str, json_data: dict = None) -> Dict[str, Any]:
        """Make an authenticated call to the Booking API."""
        url = f"{BOOKING_API_BASE}{path}"
        logger.info(f"[BOOKING_AGENT] API call: {method} {url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_data
            )
            if response.status_code >= 400:
                error_detail = response.text
                logger.error(f"[BOOKING_AGENT] API error {response.status_code}: {error_detail}")
                return {"success": False, "error": f"API error {response.status_code}: {error_detail}"}
            result = response.json()
            if isinstance(result, dict):
                result["success"] = True
            else:
                result = {"success": True, "data": result}
            return result

    async def create_task(self, task_data: Dict[str, Any], token: str) -> Dict[str, Any]:
        """Create an onboarding task via Booking API (POST /api/booking/tasks)."""
        scheduled_date = task_data.get("scheduled_date", (date.today() + timedelta(days=3)).isoformat())
        task_type = task_data.get("task_type", "orientation")
        payload = {
            "employee_id": task_data.get("employee_id", "EMP-NEW-001"),
            "task_type": task_type,
            "title": task_data.get("title", f"{task_type.replace('_', ' ').title()} Session"),
            "scheduled_date": scheduled_date,
            "duration_hours": task_data.get("duration_hours", 2.0),
            "description": task_data.get("description", "Scheduled onboarding task")
        }
        logger.info(f"[BOOKING_AGENT] Creating task via API: {payload['title']}")
        return await self._call_api("POST", "/tasks", token, payload)

    async def schedule_delivery(self, delivery_data: Dict[str, Any], token: str) -> Dict[str, Any]:
        """Schedule a delivery via Booking API (POST /api/booking/deliveries)."""
        delivery_date = delivery_data.get("delivery_date", (date.today() + timedelta(days=5)).isoformat())
        item_type = delivery_data.get("item_type", "laptop")
        payload = {
            "employee_id": delivery_data.get("employee_id", "EMP-NEW-001"),
            "item_type": item_type,
            "item_description": delivery_data.get("item_description", f"Company {item_type}"),
            "delivery_address": delivery_data.get("delivery_address", "Office HQ, Floor 5"),
            "delivery_date": delivery_date
        }
        logger.info(f"[BOOKING_AGENT] Scheduling delivery via API: {payload['item_type']}")
        return await self._call_api("POST", "/deliveries", token, payload)

    async def list_tasks(self, token: str, employee_id: str = None) -> Dict[str, Any]:
        """List tasks via Booking API (GET /api/booking/tasks)."""
        path = "/tasks"
        if employee_id:
            path += f"?employee_id={employee_id}"
        url = f"{BOOKING_API_BASE}{path}"
        logger.info(f"[BOOKING_AGENT] Listing tasks via API")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code >= 400:
                return {"success": False, "error": f"API error {response.status_code}: {response.text}"}
            return {"success": True, "tasks": response.json()}

    async def list_deliveries(self, token: str, employee_id: str = None) -> Dict[str, Any]:
        """List deliveries via Booking API (GET /api/booking/deliveries)."""
        path = "/deliveries"
        if employee_id:
            path += f"?employee_id={employee_id}"
        url = f"{BOOKING_API_BASE}{path}"
        logger.info(f"[BOOKING_AGENT] Listing deliveries via API")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code >= 400:
                return {"success": False, "error": f"API error {response.status_code}: {response.text}"}
            return {"success": True, "deliveries": response.json()}

    async def process_request(self, query: str, token: str = None) -> str:
        """Process booking request using LLM classification to determine action."""
        if not token:
            return "❌ No token provided. Authentication required."

        # LLM classifies the request
        try:
            classification = await self._classify_request(query)
        except Exception as e:
            logger.error(f"[BOOKING_AGENT] Classification failed: {e}")
            return f"❌ Failed to classify request: {str(e)}"

        action = classification.get("action", "unknown")
        params = classification.get("params", {})
        employee_id = params.get("employee_id")
        logger.info(f"[BOOKING_AGENT] Action: {action}, Params: {params}")

        if action == "create_task":
            result = await self.create_task(params, token)
            if result.get("success"):
                return (
                    f"✅ Task scheduled via Booking API!\n"
                    f"- Task ID: {result.get('task_id', 'N/A')}\n"
                    f"- Employee: {result.get('employee_id', 'N/A')}\n"
                    f"- Type: {result.get('task_type', 'N/A')}\n"
                    f"- Date: {result.get('scheduled_date', 'TBD')}\n"
                    f"- Duration: {result.get('duration_hours', 2.0)}h\n"
                    f"- Status: {result.get('status', 'scheduled')}"
                )
            return f"❌ Task scheduling failed: {result.get('error')}"

        if action == "schedule_delivery":
            result = await self.schedule_delivery(params, token)
            if result.get("success"):
                return (
                    f"✅ Delivery scheduled via Booking API!\n"
                    f"- Delivery ID: {result.get('delivery_id', 'N/A')}\n"
                    f"- Employee: {result.get('employee_id', 'N/A')}\n"
                    f"- Item: {result.get('item_description', 'N/A')}\n"
                    f"- Delivery Date: {result.get('delivery_date', 'TBD')}\n"
                    f"- Tracking: {result.get('tracking_number', 'N/A')}\n"
                    f"- Status: {result.get('status', 'scheduled')}"
                )
            return f"❌ Delivery scheduling failed: {result.get('error')}"

        if action == "list_tasks":
            result = await self.list_tasks(token, employee_id)
            if result.get("success"):
                tasks = result.get("tasks", [])
                if not tasks:
                    return "📋 No tasks found."
                lines = [f"📋 Tasks ({len(tasks)} total):"]
                for t in tasks:
                    lines.append(f"  - {t.get('task_id')}: {t.get('title')} ({t.get('status')}) on {t.get('scheduled_date')}")
                return "\n".join(lines)
            return f"❌ Failed: {result.get('error')}"

        if action == "list_deliveries":
            result = await self.list_deliveries(token, employee_id)
            if result.get("success"):
                deliveries = result.get("deliveries", [])
                if not deliveries:
                    return "📦 No deliveries found."
                lines = [f"📦 Deliveries ({len(deliveries)} total):"]
                for d in deliveries:
                    lines.append(f"  - {d.get('delivery_id')}: {d.get('item_type')} ({d.get('status')}) - {d.get('tracking_number')}")
                return "\n".join(lines)
            return f"❌ Failed: {result.get('error')}"

        if action == "list_all":
            tasks_result = await self.list_tasks(token, employee_id)
            deliveries_result = await self.list_deliveries(token, employee_id)
            lines = []
            if tasks_result.get("success"):
                tasks = tasks_result.get("tasks", [])
                lines.append(f"📋 Tasks ({len(tasks)} total):")
                for t in tasks:
                    lines.append(f"  - {t.get('task_id')}: {t.get('title')} ({t.get('status')}) on {t.get('scheduled_date')}")
                if not tasks:
                    lines.append("  (none)")
            if deliveries_result.get("success"):
                deliveries = deliveries_result.get("deliveries", [])
                lines.append(f"📦 Deliveries ({len(deliveries)} total):")
                for d in deliveries:
                    lines.append(f"  - {d.get('delivery_id')}: {d.get('item_type')} ({d.get('status')}) - {d.get('tracking_number')}")
                if not deliveries:
                    lines.append("  (none)")
            if lines:
                return "\n".join(lines)
            return "❌ Failed to retrieve tasks/deliveries."

        return f"❌ Unknown action: {action}. Could not process the request."

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response - A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
