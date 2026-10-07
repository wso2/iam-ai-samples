"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Outbound Approval Events

  When a leave request is approved, the employee may not be anywhere near a
  browser — so nothing on their side can poll for the outcome. The HR server
  is the only party that knows the moment it happens, so it tells the agent,
  and the agent takes it from there (reaching the person out-of-band).

  Deliberately fire-and-forget: a notification problem must never turn a
  successful approval into a failed one. Failures are logged and dropped.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

AGENT_WEBHOOK_URL = os.getenv("AGENT_WEBHOOK_URL", "")
# Shared secret so the agent can tell a real event from anyone who found the
# endpoint. Not authorization in any real sense — it authenticates the caller,
# nothing more — but the alternative is an open endpoint that triggers
# messages to employees.
AGENT_WEBHOOK_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")
TIMEOUT_SECONDS = float(os.getenv("AGENT_WEBHOOK_TIMEOUT", "10"))


def enabled() -> bool:
    return bool(AGENT_WEBHOOK_URL and AGENT_WEBHOOK_SECRET)


async def _post(payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                AGENT_WEBHOOK_URL,
                json=payload,
                headers={"X-Webhook-Secret": AGENT_WEBHOOK_SECRET},
            )
        if resp.status_code >= 300:
            logger.warning(
                "[EVENT] agent rejected leave-approved for %s: HTTP %s %s",
                payload.get("request_id"), resp.status_code, resp.text[:200],
            )
        else:
            logger.info(
                "[EVENT >> Agent] leave-approved sent for %s", payload.get("request_id")
            )
    except Exception as e:
        logger.warning("[EVENT] could not notify the agent about %s: %s",
                       payload.get("request_id"), e)


def leave_approved(request: dict, user: dict) -> None:
    """Tell the agent a leave request was approved. Never raises, never blocks.

    Scheduled on the running loop rather than awaited, so the HTTP response to
    whoever approved is not held up by an outbound call to another service.
    """
    if not enabled():
        return

    payload = {
        "event": "leave_approved",
        "request_id": request.get("request_id"),
        "employee_sub": request.get("user_sub"),
        "employee_name": request.get("user_name"),
        # How to reach them when they are not in a browser. Either may be
        # empty if no token has yet carried the claim.
        "employee_email": user.get("email", ""),
        "employee_username": user.get("username", ""),
        "leave_type": request.get("leave_type"),
        "start_date": request.get("start_date"),
        "end_date": request.get("end_date"),
        "days_requested": request.get("days_requested"),
        "reviewed_by": request.get("reviewed_by_name"),
    }
    try:
        asyncio.get_running_loop().create_task(_post(payload))
    except RuntimeError:
        logger.warning("[EVENT] no running loop; dropped leave-approved event")
