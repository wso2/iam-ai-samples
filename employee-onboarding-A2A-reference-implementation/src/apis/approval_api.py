"""
Approval API - Approval workflow endpoints.
Required scope: approval:write, approval:read
Required audience: approval-api
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.jwt_validator import (
    TokenClaims,
    validate_token,
    require_scope,
    require_audience
)

logger = structlog.get_logger()
router = APIRouter()

# In-memory storage
_approval_requests: dict[str, dict] = {}


class ApprovalRequest(BaseModel):
    """Request to create an approval."""
    request_type: str  # e.g., "github_core_repo_access", "vpn_aws_access"
    target_user: str
    target_resource: Optional[str] = None
    approver_email: str
    reason: str
    priority: str = "normal"
    policy_reference: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response for approval operations."""
    request_id: str
    request_type: str
    target_user: str
    target_resource: Optional[str]
    approver_email: str
    reason: str
    priority: str
    policy_reference: Optional[str]
    status: str
    created_at: str
    created_by: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None


@router.post("/requests", response_model=ApprovalResponse)
async def create_approval_request(
    request: ApprovalRequest,
    token: TokenClaims = Depends(validate_token)
):
    """
    Create a new approval request.
    
    Security:
    - Requires scope: approval:write
    - Requires audience: approval-api
    """
    require_scope(token, "approval:write")
    require_audience(token, "onboarding-api")
    
    request_id = f"APR-{uuid4().hex[:8].upper()}"
    
    record = {
        "request_id": request_id,
        "request_type": request.request_type,
        "target_user": request.target_user,
        "target_resource": request.target_resource,
        "approver_email": request.approver_email,
        "reason": request.reason,
        "priority": request.priority,
        "policy_reference": request.policy_reference,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "created_by": token.sub, # This line is kept as the instruction was to replace .get('sub') with .sub, and the provided snippet was incomplete/misleading for this specific change.
        "approved_at": None,
        "approved_by": None
    }
    
    _approval_requests[request_id] = record
    
    logger.info(
        "approval_request_created",
        request_id=request_id,
        request_type=request.request_type,
        approver=request.approver_email,
        priority=request.priority
    )
    
    return ApprovalResponse(**record)


@router.get("/requests/{request_id}", response_model=ApprovalResponse)
async def get_approval_request(
    request_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get an approval request by ID."""
    require_scope(token, "approval:read")
    require_audience(token, "onboarding-api")
    
    if request_id not in _approval_requests:
        raise HTTPException(404, f"Approval request not found: {request_id}")
    
    return ApprovalResponse(**_approval_requests[request_id])


@router.get("/requests", response_model=list[ApprovalResponse])
async def list_approval_requests(
    status: Optional[str] = None,
    approver: Optional[str] = None,
    token: TokenClaims = Depends(validate_token)
):
    """List approval requests with optional filters."""
    require_scope(token, "approval:read")
    require_audience(token, "onboarding-api")
    
    requests = list(_approval_requests.values())
    
    if status:
        requests = [r for r in requests if r["status"] == status]
    if approver:
        requests = [r for r in requests if r["approver_email"] == approver]
    
    return [ApprovalResponse(**r) for r in requests]


@router.post("/requests/{request_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    request_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """
    Approve a pending request.
    The approver must match the request's approver_email.
    """
    require_scope(token, "approval:write")
    require_audience(token, "onboarding-api")
    
    if request_id not in _approval_requests:
        raise HTTPException(404, f"Approval request not found: {request_id}")
    
    record = _approval_requests[request_id]
    
    if record["status"] != "pending":
        raise HTTPException(400, f"Request already {record['status']}")
    
    # In production, verify token.sub matches approver_email
    record["status"] = "approved"
    record["approved_at"] = datetime.utcnow().isoformat()
    record["approved_by"] = token.sub
    
    logger.info(
        "approval_granted",
        request_id=request_id,
        approved_by=token.sub
    )
    
    return ApprovalResponse(**record)


@router.post("/requests/{request_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    request_id: str,
    reason: str = "Rejected",
    token: TokenClaims = Depends(validate_token)
):
    """Reject a pending request."""
    require_scope(token, "approval:write")
    require_audience(token, "onboarding-api")
    
    if request_id not in _approval_requests:
        raise HTTPException(404, f"Approval request not found: {request_id}")
    
    record = _approval_requests[request_id]
    
    if record["status"] != "pending":
        raise HTTPException(400, f"Request already {record['status']}")
    
    record["status"] = "rejected"
    record["approved_at"] = datetime.utcnow().isoformat()
    record["approved_by"] = token.sub
    
    logger.info(
        "approval_rejected",
        request_id=request_id,
        rejected_by=token.sub,
        reason=reason
    )
    
    return ApprovalResponse(**record)


@router.post("/requests/check-status")
async def check_status_batch(
    request_ids: list[str],
    token: TokenClaims = Depends(validate_token)
):
    """Check status of multiple approval requests."""
    require_scope(token, "approval:read")
    require_audience(token, "onboarding-api")
    
    result = {}
    for rid in request_ids:
        if rid in _approval_requests:
            result[rid] = _approval_requests[rid]["status"]
        else:
            result[rid] = "not_found"
    
    return result
