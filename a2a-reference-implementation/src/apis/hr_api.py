"""
HR API - Employee management endpoints.
Required scope: hr:write, hr:read
Required audience: hr-api
"""

from datetime import date
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from src.auth.jwt_validator import (
    TokenClaims,
    validate_token,
    require_scope,
    require_audience
)

logger = structlog.get_logger()
router = APIRouter()

# In-memory storage (replace with database in production)
_employees: dict[str, dict] = {}


class EmployeeCreate(BaseModel):
    """Request model for creating an employee."""
    name: str
    email: EmailStr
    role: str
    team: str
    manager_email: EmailStr
    start_date: date


class EmployeeResponse(BaseModel):
    """Response model for employee data."""
    employee_id: str
    name: str
    email: str
    role: str
    team: str
    manager_email: str
    start_date: date
    status: str
    created_at: str
    created_by: str


@router.post("/employees", response_model=EmployeeResponse)
async def create_employee(
    employee: EmployeeCreate,
    token: TokenClaims = Depends(validate_token)
):
    """
    Create a new employee.
    
    Security:
    - Requires scope: hr:write
    - Requires audience: hr-api
    - Logs actor context for audit
    """
    # Validate token requirements
    require_scope(token, "hr:write")
    require_audience(token, "onboarding-api")
    
    # Generate employee ID
    employee_id = f"EMP-{uuid4().hex[:8].upper()}"
    
    # Create employee record
    record = {
        "employee_id": employee_id,
        "name": employee.name,
        "email": employee.email,
        "role": employee.role,
        "team": employee.team,
        "manager_email": employee.manager_email,
        "start_date": employee.start_date.isoformat(),
        "status": "pending_onboarding",
        "created_at": date.today().isoformat(),
        "created_by": token.sub,
    }
    
    _employees[employee_id] = record
    
    # Log with actor context
    logger.info(
        "employee_created",
        employee_id=employee_id,
        created_by=token.sub,
        actor=token.act.sub if token.act else None,
        team=employee.team
    )
    
    return EmployeeResponse(**record)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get employee by ID."""
    require_scope(token, "hr:read")
    require_audience(token, "onboarding-api")
    
    if employee_id not in _employees:
        raise HTTPException(404, f"Employee not found: {employee_id}")
    
    return EmployeeResponse(**_employees[employee_id])


@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    team: Optional[str] = None,
    token: TokenClaims = Depends(validate_token)
):
    """List all employees, optionally filtered by team."""
    require_scope(token, "hr:read")
    require_audience(token, "onboarding-api")
    
    employees = list(_employees.values())
    
    if team:
        employees = [e for e in employees if e["team"] == team]
    
    return [EmployeeResponse(**e) for e in employees]


@router.patch("/employees/{employee_id}/status")
async def update_employee_status(
    employee_id: str,
    status: str,
    token: TokenClaims = Depends(validate_token)
):
    """Update employee status."""
    require_scope(token, "hr:write")
    require_audience(token, "onboarding-api")
    
    if employee_id not in _employees:
        raise HTTPException(404, f"Employee not found: {employee_id}")
    
    _employees[employee_id]["status"] = status
    
    logger.info(
        "employee_status_updated",
        employee_id=employee_id,
        new_status=status,
        updated_by=token.sub
    )
    
    return {"employee_id": employee_id, "status": status}
