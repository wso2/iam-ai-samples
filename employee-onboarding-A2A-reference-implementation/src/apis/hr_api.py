"""
HR API - Employee management endpoints (SQLite-backed).
Required scope: hr:write, hr:read
Required audience: hr-api
"""

import os
import aiosqlite
from datetime import date, datetime
from typing import Optional

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

# ── SQLite DB path ─────────────────────────────────────────────────────────
_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "data", "hr.db"
)
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


async def _get_db() -> aiosqlite.Connection:
    """Open a connection; create tables on first use."""
    db = await aiosqlite.connect(_DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            role          TEXT NOT NULL,
            team          TEXT NOT NULL,
            manager_email TEXT NOT NULL,
            start_date    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending_onboarding',
            created_at    TEXT NOT NULL,
            created_by    TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


# ── Pydantic models ────────────────────────────────────────────────────────

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
    start_date: str
    status: str
    created_at: str
    created_by: str


class StatusUpdate(BaseModel):
    status: str


# ── Helpers ────────────────────────────────────────────────────────────────

_VALID_STATUSES = {
    "pending_onboarding", "active", "offboarded", "suspended", "on_leave"
}


def _row_to_response(row) -> EmployeeResponse:
    return EmployeeResponse(**dict(row))


async def _next_employee_id(db: aiosqlite.Connection) -> str:
    """Return the next sequential employee ID, e.g. EMP-001, EMP-002 ..."""
    async with db.execute("SELECT COUNT(*) FROM employees") as cur:
        row = await cur.fetchone()
        count = row[0] if row else 0
    return f"EMP-{count + 1:03d}"

# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    token: TokenClaims = Depends(validate_token)
):
    """
    Create a new employee record (persisted to SQLite).

    Security:
    - Requires scope: hr:write
    - Requires audience: hr-api
    """
    require_scope(token, "hr:write")
    require_audience(token, "onboarding-api")

    now = datetime.utcnow().isoformat()
    db = await _get_db()
    employee_id = await _next_employee_id(db)
    try:
        await db.execute("""
            INSERT INTO employees
                (employee_id, name, email, role, team, manager_email,
                 start_date, status, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_onboarding', ?, ?)
        """, (
            employee_id,
            employee.name,
            str(employee.email),
            employee.role,
            employee.team,
            str(employee.manager_email),
            employee.start_date.isoformat(),
            now,
            token.sub
        ))
        await db.commit()
    except aiosqlite.IntegrityError:
        await db.close()
        raise HTTPException(409, f"Employee with email {employee.email} already exists.")
    finally:
        await db.close()

    logger.info(
        "employee_created",
        employee_id=employee_id,
        name=employee.name,
        email=str(employee.email),
        role=employee.role,
        created_by=token.sub,
        actor=token.act.sub if token.act else None,
    )

    return EmployeeResponse(
        employee_id=employee_id,
        name=employee.name,
        email=str(employee.email),
        role=employee.role,
        team=employee.team,
        manager_email=str(employee.manager_email),
        start_date=employee.start_date.isoformat(),
        status="pending_onboarding",
        created_at=now,
        created_by=token.sub,
    )


@router.get("/employees/search/by-email", response_model=EmployeeResponse)
async def get_employee_by_email(
    email: str,
    token: TokenClaims = Depends(validate_token)
):
    """Look up an employee by email address."""
    require_scope(token, "hr:read")
    require_audience(token, "onboarding-api")

    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM employees WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"No employee found with email: {email}")

    return _row_to_response(row)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get a single employee by ID."""
    require_scope(token, "hr:read")
    require_audience(token, "onboarding-api")

    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"Employee not found: {employee_id}")

    return _row_to_response(row)
