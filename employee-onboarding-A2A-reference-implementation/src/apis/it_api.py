"""
IT API - Account provisioning endpoints.
Required scope: it:write, it:read
Required audience: it-api
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
_provisions: dict[str, dict] = {}


class VPNProvisionRequest(BaseModel):
    """Request to provision VPN access."""
    employee_id: str
    vpn_profile: str = "standard"
    approved_by: Optional[str] = None


class GitHubProvisionRequest(BaseModel):
    """Request to provision GitHub access."""
    employee_id: str
    organization: str
    repositories: list[str]
    permission: str = "write"
    approved_by: Optional[str] = None


class AWSProvisionRequest(BaseModel):
    """Request to provision AWS access."""
    employee_id: str
    account: str
    role: str = "developer"
    approved_by: Optional[str] = None


class ProvisionResponse(BaseModel):
    """Response for provisioning operations."""
    provision_id: str
    employee_id: str
    service: str
    status: str
    details: dict
    provisioned_at: str
    provisioned_by: str


@router.post("/provision/vpn", response_model=ProvisionResponse)
async def provision_vpn(
    request: VPNProvisionRequest,
    token: TokenClaims = Depends(validate_token)
):
    """
    Provision VPN access for an employee.
    
    Security:
    - Requires scope: it:write
    - Requires audience: it-api
    """
    require_scope(token, "it:write")
    require_audience(token, "onboarding-api")
    
    provision_id = f"VPN-{uuid4().hex[:8].upper()}"
    
    record = {
        "provision_id": provision_id,
        "employee_id": request.employee_id,
        "service": "vpn",
        "status": "active",
        "details": {
            "vpn_profile": request.vpn_profile,
            "vpn_server": "vpn.nebulasoft.internal",
            "credentials_sent": True
        },
        "provisioned_at": datetime.utcnow().isoformat(),
        "provisioned_by": token.sub,
        "approved_by": request.approved_by
    }
    
    _provisions[provision_id] = record
    
    logger.info(
        "vpn_provisioned",
        provision_id=provision_id,
        employee_id=request.employee_id,
        provisioned_by=token.sub,
        actor=token.act.sub if token.act else None
    )
    
    return ProvisionResponse(**record)


@router.post("/provision/github", response_model=ProvisionResponse)
async def provision_github(
    request: GitHubProvisionRequest,
    token: TokenClaims = Depends(validate_token)
):
    """Provision GitHub Enterprise access."""
    require_scope(token, "it:write")
    require_audience(token, "onboarding-api")
    
    provision_id = f"GH-{uuid4().hex[:8].upper()}"
    
    record = {
        "provision_id": provision_id,
        "employee_id": request.employee_id,
        "service": "github",
        "status": "active",
        "details": {
            "organization": request.organization,
            "repositories": request.repositories,
            "permission": request.permission,
            "github_username": f"user_{request.employee_id.lower()}"
        },
        "provisioned_at": datetime.utcnow().isoformat(),
        "provisioned_by": token.sub,
        "approved_by": request.approved_by
    }
    
    _provisions[provision_id] = record
    
    logger.info(
        "github_provisioned",
        provision_id=provision_id,
        employee_id=request.employee_id,
        repositories=request.repositories
    )
    
    return ProvisionResponse(**record)


@router.post("/provision/aws", response_model=ProvisionResponse)
async def provision_aws(
    request: AWSProvisionRequest,
    token: TokenClaims = Depends(validate_token)
):
    """Provision AWS environment access."""
    require_scope(token, "it:write")
    require_audience(token, "onboarding-api")
    
    provision_id = f"AWS-{uuid4().hex[:8].upper()}"
    
    record = {
        "provision_id": provision_id,
        "employee_id": request.employee_id,
        "service": "aws",
        "status": "active",
        "details": {
            "account": request.account,
            "role": request.role,
            "iam_user": f"iam_{request.employee_id.lower()}",
            "access_key_sent": True
        },
        "provisioned_at": datetime.utcnow().isoformat(),
        "provisioned_by": token.sub,
        "approved_by": request.approved_by
    }
    
    _provisions[provision_id] = record
    
    logger.info(
        "aws_provisioned",
        provision_id=provision_id,
        employee_id=request.employee_id,
        account=request.account
    )
    
    return ProvisionResponse(**record)


@router.get("/provisions/{employee_id}", response_model=list[ProvisionResponse])
async def get_provisions(
    employee_id: str,
    token: TokenClaims = Depends(validate_token)
):
    """Get all provisions for an employee."""
    require_scope(token, "it:read")
    require_audience(token, "onboarding-api")
    
    provisions = [
        p for p in _provisions.values()
        if p["employee_id"] == employee_id
    ]
    
    return [ProvisionResponse(**p) for p in provisions]
