"""
Booking API - Task scheduling and delivery endpoints.
Required scope: booking:write, booking:read
Required audience: booking-api
"""

from datetime import datetime, date, timedelta
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.apis.google_calendar import create_calendar_event

from src.auth.jwt_validator import (
    TokenClaims,
    validate_token,
    require_scope,
    require_audience
)

logger = structlog.get_logger()
router = APIRouter()

# In-memory storage
_tasks: dict[str, dict] = {}
_deliveries: dict[str, dict] = {}


class TaskCreate(BaseModel):
    """Request to create an onboarding task."""
    employee_id: str
    task_type: str  # e.g., "hr_orientation", "security_training"
    title: str
    scheduled_date: date
    duration_hours: float = 2.0
    description: Optional[str] = None


class TaskResponse(BaseModel):
    """Response for task operations."""
    task_id: str
    employee_id: str
    task_type: str
    title: str
    scheduled_date: str
    duration_hours: float
    description: Optional[str]
    status: str
    created_at: str
    created_by: str


class DeliverySchedule(BaseModel):
    """Request to schedule a delivery."""
    employee_id: str
    item_type: str  # e.g., "laptop"
    item_description: str
    delivery_address: str
    delivery_date: date
    approved_by: Optional[str] = None


class DeliveryResponse(BaseModel):
    """Response for delivery operations."""
    delivery_id: str
    employee_id: str
    item_type: str
    item_description: str
    delivery_address: str
    delivery_date: str
    tracking_number: str
    status: str
    scheduled_at: str
    scheduled_by: str


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    task: TaskCreate,
    token: TokenClaims = Depends(validate_token)
):
    """
    Create an onboarding task.
    
    Security:
    - Requires scope: booking:write
    - Requires audience: booking-api
    """
    require_scope(token, "booking:write")
    require_audience(token, "onboarding-api")
    
    task_id = f"TASK-{uuid4().hex[:8].upper()}"
    
    # ── Year fix: if LLM sends a past year, correct it to current year ──
    current_year = datetime.utcnow().year
    scheduled = task.scheduled_date
    if scheduled.year < current_year:
        try:
            scheduled = scheduled.replace(year=current_year)
        except ValueError:
            # Feb 29 edge case in non-leap year
            scheduled = scheduled.replace(year=current_year, day=28)
    
    # ── Build Google Calendar event times (default 09:00, duration from request) ──
    start_dt = datetime.combine(scheduled, datetime.min.time()).replace(hour=9, minute=0)
    end_dt = start_dt + timedelta(hours=task.duration_hours)
    start_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    end_iso   = end_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    cal_result = create_calendar_event(
        title=task.title,
        description=task.description or f"Onboarding task for {task.employee_id}",
        start_iso=start_iso,
        end_iso=end_iso
    )

    extended_description = task.description or ""
    if cal_result.get("success") and not cal_result.get("mocked", False):
        if cal_result.get("htmlLink"):
            extended_description += f"\n\nCalendar Event: {cal_result['htmlLink']}"
        if cal_result.get("meetLink"):
            extended_description += f"\nGoogle Meet: {cal_result['meetLink']}"
        logger.info("google_calendar_event_created", link=cal_result.get('htmlLink'))
    elif cal_result.get("mocked"):
        extended_description += "\n\n(Calendar event mocked — service account credentials not found)"
        logger.warning("google_calendar_mocked")
    else:
        logger.warning("google_calendar_failed", error=cal_result.get('error'))

    record = {
        "task_id": task_id,
        "employee_id": task.employee_id,
        "task_type": task.task_type,
        "title": task.title,
        "scheduled_date": scheduled.isoformat(),
        "duration_hours": task.duration_hours,
        "description": extended_description,
        "status": "scheduled",
        "created_at": datetime.utcnow().isoformat(),
        "created_by": token.sub
    }
    
    _tasks[task_id] = record
    
    logger.info(
        "task_created",
        task_id=task_id,
        employee_id=task.employee_id,
        task_type=task.task_type,
        scheduled_date=scheduled.isoformat()
    )
    
    return TaskResponse(**record)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get a task by ID."""
    require_scope(token, "booking:read")
    require_audience(token, "onboarding-api")
    
    if task_id not in _tasks:
        raise HTTPException(404, f"Task not found: {task_id}")
    
    return TaskResponse(**_tasks[task_id])


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    employee_id: Optional[str] = None,
    token: TokenClaims = Depends(validate_token)
):
    """List tasks, optionally filtered by employee."""
    require_scope(token, "booking:read")
    require_audience(token, "onboarding-api")
    
    tasks = list(_tasks.values())
    
    if employee_id:
        tasks = [t for t in tasks if t["employee_id"] == employee_id]
    
    return [TaskResponse(**t) for t in tasks]


@router.post("/deliveries", response_model=DeliveryResponse)
async def schedule_delivery(
    delivery: DeliverySchedule,
    token: TokenClaims = Depends(validate_token)
):
    """
    Schedule a delivery (e.g., laptop).
    
    Security:
    - Requires scope: booking:write
    - Requires audience: booking-api
    """
    require_scope(token, "booking:write")
    require_audience(token, "onboarding-api")

    delivery_id = f"DEL-{uuid4().hex[:8].upper()}"
    tracking_number = f"TRK-{uuid4().hex[:12].upper()}"

    # ── Year fix: correct past years to current year ──
    current_year = datetime.utcnow().year
    delivery_date = delivery.delivery_date
    if delivery_date.year < current_year:
        try:
            delivery_date = delivery_date.replace(year=current_year)
        except ValueError:
            delivery_date = delivery_date.replace(year=current_year, day=28)

    # ── Build Google Calendar event for the delivery ──
    start_dt = datetime.combine(delivery_date, datetime.min.time()).replace(hour=10, minute=0)
    end_dt = start_dt + timedelta(hours=1)
    start_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    end_iso   = end_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    item_label = delivery.item_description or delivery.item_type.title()
    cal_result = create_calendar_event(
        title=f"Equipment Delivery: {item_label} → {delivery.employee_id}",
        description=(
            f"Delivery of {item_label} for employee {delivery.employee_id}.\n"
            f"Address: {delivery.delivery_address}\n"
            f"Tracking: {tracking_number}"
        ),
        start_iso=start_iso,
        end_iso=end_iso
    )

    calendar_note = ""
    if cal_result.get("success") and not cal_result.get("mocked", False):
        calendar_note = cal_result.get("htmlLink", "")
        logger.info("delivery_calendar_event_created", link=calendar_note)
    elif cal_result.get("mocked"):
        logger.warning("delivery_calendar_mocked")
    else:
        logger.warning("delivery_calendar_failed", error=cal_result.get("error"))

    record = {
        "delivery_id": delivery_id,
        "employee_id": delivery.employee_id,
        "item_type": delivery.item_type,
        "item_description": delivery.item_description,
        "delivery_address": delivery.delivery_address,
        "delivery_date": delivery_date.isoformat(),
        "tracking_number": tracking_number,
        "status": "scheduled",
        "scheduled_at": datetime.utcnow().isoformat(),
        "scheduled_by": token.sub,
        "approved_by": delivery.approved_by
    }

    _deliveries[delivery_id] = record

    logger.info(
        "delivery_scheduled",
        delivery_id=delivery_id,
        employee_id=delivery.employee_id,
        item_type=delivery.item_type,
        tracking_number=tracking_number,
        calendar_link=calendar_note or "mocked"
    )

    return DeliveryResponse(**record)


@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(
    delivery_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get delivery by ID."""
    require_scope(token, "booking:read")
    require_audience(token, "onboarding-api")
    
    if delivery_id not in _deliveries:
        raise HTTPException(404, f"Delivery not found: {delivery_id}")
    
    return DeliveryResponse(**_deliveries[delivery_id])


@router.get("/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries(
    employee_id: Optional[str] = None,
    token: TokenClaims = Depends(validate_token)
):
    """List deliveries, optionally filtered by employee."""
    require_scope(token, "booking:read")
    require_audience(token, "onboarding-api")
    
    deliveries = list(_deliveries.values())
    
    if employee_id:
        deliveries = [d for d in deliveries if d["employee_id"] == employee_id]
    
    return [DeliveryResponse(**d) for d in deliveries]
