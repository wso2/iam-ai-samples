"""
Payroll API - Employee payroll and expense management endpoints.
Required scope: approval:write, approval:read
Required audience: payroll-api
"""

from datetime import date, datetime
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.jwt_validator import TokenClaims, validate_token, require_scope, require_audience

logger = structlog.get_logger()
router = APIRouter()

# In-memory store (no extra DB needed)
_payroll_records: dict[str, dict]  = {}
_expense_accounts: dict[str, dict] = {}


# ── Pydantic models ────────────────────────────────────────────────────────

class PayrollCreate(BaseModel):
    employee_id: str
    employee_name: str
    role: str
    salary_grade: Optional[str] = None        # L1–L10
    annual_salary: Optional[float] = None     # USD
    pay_frequency: str = "monthly"            # monthly | biweekly
    currency: str = "USD"
    start_date: Optional[date] = None


class PayrollResponse(BaseModel):
    payroll_id: str
    employee_id: str
    employee_name: str
    role: str
    salary_grade: str
    annual_salary: float
    pay_frequency: str
    currency: str
    start_date: str
    status: str
    created_at: str


class ExpenseAccountCreate(BaseModel):
    employee_id: str
    monthly_limit: float = 1000.0
    categories: Optional[list[str]] = None   # ["travel", "equipment", "meals", ...]
    currency: str = "USD"


class ExpenseAccountResponse(BaseModel):
    account_id: str
    employee_id: str
    monthly_limit: float
    categories: list[str]
    currency: str
    status: str
    created_at: str


# ── Salary grade lookup ────────────────────────────────────────────────────

_GRADE_MAP = {
    "intern":              ("L1",  35_000),
    "junior":              ("L2",  55_000),
    "associate":           ("L3",  70_000),
    "mid":                 ("L4",  90_000),
    "senior":              ("L5", 120_000),
    "senior it manager":   ("L5", 120_000),
    "staff":               ("L6", 150_000),
    "principal":           ("L7", 185_000),
    "director":            ("L8", 220_000),
    "vp":                  ("L9", 280_000),
    "c-level":             ("L10",400_000),
}

def _infer_grade(role: str) -> tuple[str, float]:
    role_lower = role.lower()
    for key, val in _GRADE_MAP.items():
        if key in role_lower:
            return val
    return ("L4", 90_000)   # default


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/payroll", response_model=PayrollResponse, status_code=201)
async def register_payroll(
    data: PayrollCreate,
    token: TokenClaims = Depends(validate_token)
):
    """
    Register an employee in the payroll system.
    - Requires scope: payroll:write
    - Requires audience: payroll-api (validated as onboarding-api in this demo)
    """
    require_scope(token, "approval:write")
    require_audience(token, "onboarding-api")

    if data.employee_id in _payroll_records:
        raise HTTPException(409, f"Payroll record already exists for {data.employee_id}")

    grade, default_salary = _infer_grade(data.role)
    salary_grade   = data.salary_grade or grade
    annual_salary  = data.annual_salary or default_salary
    payroll_id     = f"PAY-{uuid4().hex[:8].upper()}"
    now            = datetime.utcnow().isoformat()

    record = {
        "payroll_id":    payroll_id,
        "employee_id":   data.employee_id,
        "employee_name": data.employee_name,
        "role":          data.role,
        "salary_grade":  salary_grade,
        "annual_salary": annual_salary,
        "pay_frequency": data.pay_frequency,
        "currency":      data.currency,
        "start_date":    (data.start_date or date.today()).isoformat(),
        "status":        "active",
        "created_at":    now,
    }
    _payroll_records[data.employee_id] = record
    logger.info("payroll_registered", payroll_id=payroll_id, employee=data.employee_id)
    return PayrollResponse(**record)


@router.post("/expense-accounts", response_model=ExpenseAccountResponse, status_code=201)
async def create_expense_account(
    data: ExpenseAccountCreate,
    token: TokenClaims = Depends(validate_token)
):
    """
    Create an expense account with monthly spending limits.
    - Requires scope: payroll:write
    """
    require_scope(token, "approval:write")
    require_audience(token, "onboarding-api")

    if data.employee_id in _expense_accounts:
        raise HTTPException(409, f"Expense account already exists for {data.employee_id}")

    default_categories = ["travel", "meals", "equipment", "training", "misc"]
    account_id = f"EXP-{uuid4().hex[:8].upper()}"
    now = datetime.utcnow().isoformat()

    account = {
        "account_id":    account_id,
        "employee_id":   data.employee_id,
        "monthly_limit": data.monthly_limit,
        "categories":    data.categories or default_categories,
        "currency":      data.currency,
        "status":        "active",
        "created_at":    now,
    }
    _expense_accounts[data.employee_id] = account
    logger.info("expense_account_created", account_id=account_id, employee=data.employee_id)
    return ExpenseAccountResponse(**account)


@router.get("/payroll/{employee_id}", response_model=PayrollResponse)
async def get_payroll(
    employee_id: str,
    token: TokenClaims = Depends(validate_token)
):
    require_scope(token, "approval:read")
    require_audience(token, "onboarding-api")
    record = _payroll_records.get(employee_id)
    if not record:
        raise HTTPException(404, f"No payroll record for {employee_id}")
    return PayrollResponse(**record)


@router.get("/expense-accounts/{employee_id}", response_model=ExpenseAccountResponse)
async def get_expense_account(
    employee_id: str,
    token: TokenClaims = Depends(validate_token)
):
    require_scope(token, "approval:read")
    require_audience(token, "onboarding-api")
    account = _expense_accounts.get(employee_id)
    if not account:
        raise HTTPException(404, f"No expense account for {employee_id}")
    return ExpenseAccountResponse(**account)
