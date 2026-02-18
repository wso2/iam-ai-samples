"""
IT MCP Server - Model Context Protocol server for IT provisioning.

Architecture:
  IT Agent → MCP Server (LLM routes request → picks tool) → Token Exchange → IT API

The MCP server:
1. Exposes a smart tool: handle_it_request
   - Uses OpenAI LLM to classify the incoming request
   - Routes to the correct internal function (vpn/github/aws/list)
2. Performs RFC 8693 token exchange (WITH actor token) to narrow scope:
   - Write operations → exchanges to it:write only
   - Read operations → exchanges to it:read only
   - Maintains delegation chain via actor_token parameter
3. Calls the IT API with the narrowed token

Token Exchange (with actor token):
  Uses Token Exchanger app credentials + subject_token + actor_token → narrowed token
  WSO2 IS maintains the delegation chain through scope narrowing exchanges.
"""

import os
import sys
import json
import logging
import base64
from typing import Optional

# CRITICAL: Configure logging to stderr BEFORE any imports that might log/print.
# MCP STDIO protocol reserves stdout exclusively for JSON-RPC messages.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

import httpx

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from mcp.server.fastmcp import FastMCP
from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Visualizer Broadcast (MCP-safe: prints to stderr, not stdout)
# ─────────────────────────────────────────────────────────────────

VISUALIZER_URL = "http://localhost:8200/log"

async def vlog(message: str):
    """Log to stderr + broadcast to visualizer. Never touches stdout."""
    print(message, file=sys.stderr)
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(VISUALIZER_URL, json={"message": message})
    except Exception:
        pass  # Visualizer may not be running


# ─────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────

settings = get_settings()
IT_API_BASE = "http://localhost:8002/api/it"

# Token Exchanger — performs the actual token exchange
# (no actor token needed, just client credentials + subject token)
TOKEN_EXCHANGER_CLIENT_ID = settings.token_exchanger_client_id
TOKEN_EXCHANGER_CLIENT_SECRET = settings.token_exchanger_client_secret
TOKEN_URL = settings.asgardeo_token_url

# OpenAI for LLM routing
OPENAI_API_KEY = settings.openai_api_key


# ─────────────────────────────────────────────────────────────────
# Token Exchange (simplified — no actor token)
# ─────────────────────────────────────────────────────────────────


async def exchange_token_for_scope(
    subject_token: str,
    target_scope: str,
    target_audience: str = None
) -> str:
    """
    Exchange the incoming IT token for a narrowed-scope token with optional audience binding.
    
    Uses RFC 8693 Token Exchange WITH actor token:
      - subject_token: The IT Agent's token (it:read + it:write)
      - actor_token: Same as subject for scope narrowing
      - client credentials: Token Exchanger app (TOKEN_EXCHANGER_CLIENT_ID)
      - requested scope: narrowed (e.g., just "it:write")
      - audience: API-specific audience (e.g., "vpn-api", "github-api")
    
    This ensures each API gets a token specifically bound to it.
    
    Args:
        subject_token: IT Agent's broad token
        target_scope: Narrowed scope (e.g., "it:write")
        target_audience: Optional API-specific audience for token binding
    
    Returns: A new access token with narrowed scope and optional audience binding.
    """
    if not TOKEN_EXCHANGER_CLIENT_ID or not TOKEN_EXCHANGER_CLIENT_SECRET:
        raise ValueError("Token Exchanger credentials not configured")

    await vlog(f"\n{'#'*80}")
    await vlog(f"# TOKEN EXCHANGE FOR: MCP_IT_SERVER")
    await vlog(f"{'#'*80}")
    await vlog(f"Token Exchanger App: {TOKEN_EXCHANGER_CLIENT_ID}")
    await vlog(f"Target Scope: {target_scope}")
    if target_audience:
        await vlog(f"Target Audience: {target_audience}")
    
    await vlog(f"\n[SOURCE_TOKEN (from IT Agent)]:")
    await vlog(f"{subject_token}")
    
    # Decode source token for debug
    try:
        payload = subject_token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        await vlog(f"  [DEBUG] Source Token Sub: {claims.get('sub')}")
        await vlog(f"  [DEBUG] Source Token Iss: {claims.get('iss')}")
        await vlog(f"  [DEBUG] Source Token Scope: {claims.get('scope')}")
    except Exception as e:
        await vlog(f"  [DEBUG] Failed to decode source token: {e}")

    await vlog(f"\n[STEP 1: SCOPE-NARROWING TOKEN EXCHANGE (With Actor Token)]")
    await vlog(f"  Subject: IT Agent Token")
    await vlog(f"  Token Exchanger App: {TOKEN_EXCHANGER_CLIENT_ID}")
    await vlog(f"  Target Scope: {target_scope}")
    if target_audience:
        await vlog(f"  Target Audience: {target_audience}")
    await vlog(f"  Token URL: {TOKEN_URL}")
    
    basic_auth = base64.b64encode(
        f"{TOKEN_EXCHANGER_CLIENT_ID}:{TOKEN_EXCHANGER_CLIENT_SECRET}".encode()
    ).decode()

    # RFC 8693 Token Exchange WITH actor token to maintain delegation chain
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": subject_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "actor_token": subject_token,  # Same token acts as actor for scope narrowing
        "actor_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": target_scope,
    }
    
    # Add audience if specified for API-specific token binding
    if target_audience:
        data["audience"] = target_audience

    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        response = await client.post(
            TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_auth}"
            }
        )

        if response.status_code >= 400:
            error_text = response.text
            await vlog(f"\n[MCP_TOKEN_EXCHANGE_FAILED]:")
            await vlog(f"  Status: {response.status_code}")
            await vlog(f"  Error: {error_text}")
            await vlog(f"{'#'*80}\n")
            raise Exception(f"Token exchange failed ({response.status_code}): {error_text}")

        result = response.json()
        narrowed_token = result["access_token"]
        
        await vlog(f"\n[MCP_IT_EXCHANGED_TOKEN]:")
        await vlog(f"{narrowed_token}")
        
        # Decode exchanged token for debug
        try:
            payload = narrowed_token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            await vlog(f"  [DEBUG] Exchanged Token Sub: {claims.get('sub')}")
            await vlog(f"  [DEBUG] Exchanged Token Iss: {claims.get('iss')}")
            await vlog(f"  [DEBUG] Exchanged Token Scope: {claims.get('scope')}")
            await vlog(f"  [DEBUG] Exchanged Token Aud: {claims.get('aud')}")
        except Exception as e:
            await vlog(f"  [DEBUG] Failed to decode exchanged token: {e}")
        
        await vlog(f"{'#'*80}\n")
        return narrowed_token


# ─────────────────────────────────────────────────────────────────
# IT API Caller
# ─────────────────────────────────────────────────────────────────

async def call_it_api(
    method: str,
    path: str,
    token: str,
    target_scope: str,
    target_audience: str = None,
    json_data: dict = None
) -> dict:
    """
    Exchange token for narrowed scope and API-specific audience, then call the IT API.
    
    1. Exchange broad token -> narrowed token with API-specific audience
    2. Call IT API with narrowed token
    
    Args:
        method: HTTP method
        path: API path
        token: IT Agent's token
        target_scope: Narrowed scope
        target_audience: API-specific audience (e.g., "vpn-api")
        json_data: Request payload
    """
    # Step 1: Exchange token to narrow scope and bind to API audience
    try:
        narrowed_token = await exchange_token_for_scope(token, target_scope, target_audience)
    except Exception as e:
        logger.error(f"[MCP_IT] Token exchange failed: {e}")
        return {"success": False, "error": f"Token exchange failed: {str(e)}"}

    # Step 2: Call IT API with narrowed token
    url = f"{IT_API_BASE}{path}"
    await vlog(f"\n[MCP SERVER] API CALL: {method} {url}")
    await vlog(f"  Scope: {target_scope}")
    if json_data:
        await vlog(f"  Payload: {json.dumps(json_data)}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            method=method,
            url=url,
            headers={"Authorization": f"Bearer {narrowed_token}"},
            json=json_data
        )

        if response.status_code >= 400:
            error_detail = response.text
            await vlog(f"  [MCP API ERROR] {response.status_code}: {error_detail}")
            return {"success": False, "error": f"API error {response.status_code}: {error_detail}"}

        result = response.json()
        await vlog(f"  [MCP API OK] {response.status_code}")
        if isinstance(result, dict):
            result["success"] = True
        else:
            result = {"success": True, "data": result}
        return result


# ─────────────────────────────────────────────────────────────────
# Internal IT Operations (called by LLM router)
# ─────────────────────────────────────────────────────────────────

async def _provision_vpn(employee_id: str, token: str, vpn_profile: str = "standard") -> dict:
    """Provision VPN access — exchanges token to it:write scope with onboarding-api audience."""
    logger.info(f"[MCP_IT] Internal: provision_vpn for {employee_id}")
    return await call_it_api(
        method="POST",
        path="/provision/vpn",
        token=token,
        target_scope="it:write",
        target_audience="onboarding-api",
        json_data={"employee_id": employee_id, "vpn_profile": vpn_profile}
    )


async def _provision_github(
    employee_id: str, token: str,
    organization: str = "nebulasoft",
    repositories: list = None,
    permission: str = "write"
) -> dict:
    """Provision GitHub access — exchanges token to it:write scope with onboarding-api audience."""
    logger.info(f"[MCP_IT] Internal: provision_github for {employee_id}")
    return await call_it_api(
        method="POST",
        path="/provision/github",
        token=token,
        target_scope="it:write",
        target_audience="onboarding-api",
        json_data={
            "employee_id": employee_id,
            "organization": organization,
            "repositories": repositories or ["main-app", "docs"],
            "permission": permission
        }
    )


async def _provision_aws(
    employee_id: str, token: str,
    account: str = "nebulasoft-dev",
    role: str = "developer"
) -> dict:
    """Provision AWS access — exchanges token to it:write scope with onboarding-api audience."""
    logger.info(f"[MCP_IT] Internal: provision_aws for {employee_id}")
    return await call_it_api(
        method="POST",
        path="/provision/aws",
        token=token,
        target_scope="it:write",
        target_audience="onboarding-api",
        json_data={"employee_id": employee_id, "account": account, "role": role}
    )


async def _list_provisions(employee_id: str, token: str) -> dict:
    """List provisions — exchanges token to it:read scope with onboarding-api audience."""
    logger.info(f"[MCP_IT] Internal: list_provisions for {employee_id}")
    return await call_it_api(
        method="GET",
        path=f"/provisions/{employee_id}",
        token=token,
        target_scope="it:read",
        target_audience="onboarding-api"
    )


# ─────────────────────────────────────────────────────────────────
# LLM Router — classifies request and picks the right operation
# ─────────────────────────────────────────────────────────────────

ROUTING_SYSTEM_PROMPT = """You are an IT provisioning request classifier for an MCP server.
Given a natural language IT request, classify it into ONE OR MORE actions and extract parameters.

Available actions:
1. "provision_vpn" - Set up VPN access for an employee
2. "provision_github" - Set up GitHub Enterprise repository access
3. "provision_aws" - Set up AWS cloud environment access
4. "list_provisions" - List/check existing IT provisions for an employee

You must respond with ONLY a JSON object (no markdown, no explanation):
{
  "actions": [
    {
      "action": "<provision_vpn, provision_github, provision_aws, or list_provisions>",
      "employee_id": "<extracted employee ID or 'EMP-NEW-001' if not found>",
      "params": {<any additional parameters>}
    }
  ]
}

Rules:
- If the request mentions MULTIPLE operations (e.g., "VPN, GitHub, and AWS"), return MULTIPLE action objects
- If the request mentions VPN, network access, or remote access -> include provision_vpn
- If the request mentions GitHub, git, repository, code access -> include provision_github
- If the request mentions AWS, cloud, IAM, S3, EC2 -> include provision_aws
- If the request mentions list, show, check, status, existing -> include list_provisions
- Extract employee IDs that match pattern EMP-XXXX or similar
- For github params, extract: organization, repositories (as list), permission
- For aws params, extract: account, role
- For vpn params, extract: vpn_profile

Examples:
Request: "Provision VPN, GitHub, and AWS access for Alice"
Response: {
  "actions": [
    {"action": "provision_vpn", "employee_id": "EMP-NEW-001", "params": {}},
    {"action": "provision_github", "employee_id": "EMP-NEW-001", "params": {}},
    {"action": "provision_aws", "employee_id": "EMP-NEW-001", "params": {}}
  ]
}

Request: "Set up VPN for Bob"
Response: {
  "actions": [
    {"action": "provision_vpn", "employee_id": "EMP-NEW-001", "params": {}}
  ]
}
"""


async def classify_request(request_text: str) -> dict:
    """
    Use OpenAI LLM to classify an IT request into an action + parameters.
    
    Returns: {"action": "...", "employee_id": "...", "params": {...}}
    """
    logger.info(f"[MCP_IT] LLM classifying request: {request_text[:100]}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                    {"role": "user", "content": request_text}
                ]
            }
        )

        if response.status_code != 200:
            logger.error(f"[MCP_IT] OpenAI API error: {response.status_code} - {response.text}")
            raise Exception(f"LLM classification failed: {response.status_code}")

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        classification = json.loads(content)
        logger.info(f"[MCP_IT] LLM classified -> action={classification['action']}, "
                     f"employee={classification.get('employee_id', 'N/A')}")
        return classification


# ─────────────────────────────────────────────────────────────────
# MCP Server Definition
# ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "IT MCP Server",
    instructions=(
        "IT provisioning server with LLM-powered request routing and "
        "least-privilege token exchange. Send natural language IT requests "
        "to handle_it_request - the LLM will classify and route to the "
        "correct provisioning operation with scope-narrowed tokens."
    )
)


@mcp.tool()
async def handle_it_request(
    request: str,
    token: str = ""
) -> str:
    """
    Smart IT provisioning tool with LLM routing.
    
    Accepts a natural language IT request, uses an LLM to classify it,
    then routes to the correct provisioning operation with scope-narrowed
    token exchange.
    
    Examples:
      - "Set up VPN access for EMP-ABC123"
      - "Provision GitHub repos for employee John"
      - "Create AWS dev environment for EMP-NEW-001"
      - "List all IT provisions for EMP-ABC123"
      - "Set up all IT accounts for the new employee EMP-XYZ"
    
    Args:
        request: Natural language IT provisioning request
        token: The IT-scoped bearer token from the IT Agent
    
    Returns:
        JSON string with provisioning results including routing metadata
    """
    if not token:
        return json.dumps({"success": False, "error": "No token provided"})

    await vlog(f"\n{'#'*80}")
    await vlog(f"# MCP SERVER: handle_it_request (LLM-routed)")
    await vlog(f"{'#'*80}")
    await vlog(f"  Request: {request}")

    # Step 1: LLM classifies the request into one or more actions
    await vlog(f"\n[MCP LLM ROUTING] Classifying request via gpt-4o-mini...")
    try:
        classification = await classify_request(request)
    except Exception as e:
        await vlog(f"  [MCP LLM ERROR] Classification failed: {e}")
        return json.dumps({"success": False, "error": f"Request classification failed: {str(e)}"})

    # Handle both old (single action) and new (actions array) formats
    actions = classification.get("actions", [])
    if not actions:
        # Backward compatibility: check if old single-action format
        if "action" in classification:
            await vlog(f"  [MCP LLM] Detected old format, converting to new format")
            actions = [{
                "action": classification["action"],
                "employee_id": classification.get("employee_id", "EMP-NEW-001"),
                "params": classification.get("params", {})
            }]
        else:
            return json.dumps({"success": False, "error": "No actions classified from request"})

    await vlog(f"  [MCP LLM RESULT] Found {len(actions)} action(s)")

    # Step 2: Execute all identified actions (each gets its own token exchange)
    results = []
    for idx, action_obj in enumerate(actions):
        action = action_obj.get("action", "")
        employee_id = action_obj.get("employee_id", "EMP-NEW-001")
        params = action_obj.get("params", {})

        await vlog(f"\n  [MCP ACTION {idx+1}/{len(actions)}]")
        await vlog(f"    Action: {action}")
        await vlog(f"    Employee: {employee_id}")
        await vlog(f"    Params: {json.dumps(params)}")

        # Route to the correct internal operation
        if action == "provision_vpn":
            result = await _provision_vpn(
                employee_id=employee_id,
                token=token,
                vpn_profile=params.get("vpn_profile", "standard")
            )
            scope_info = "it:read+it:write -> it:write"

        elif action == "provision_github":
            repos = params.get("repositories", ["main-app", "docs"])
            if isinstance(repos, str):
                repos = [r.strip() for r in repos.split(",")]
            result = await _provision_github(
                employee_id=employee_id,
                token=token,
                organization=params.get("organization", "nebulasoft"),
                repositories=repos,
                permission=params.get("permission", "write")
            )
            scope_info = "it:read+it:write -> it:write"

        elif action == "provision_aws":
            result = await _provision_aws(
                employee_id=employee_id,
                token=token,
                account=params.get("account", "nebulasoft-dev"),
                role=params.get("role", "developer")
            )
            scope_info = "it:read+it:write -> it:write"

        elif action == "list_provisions":
            result = await _list_provisions(
                employee_id=employee_id,
                token=token
            )
            scope_info = "it:read+it:write -> it:read"

        else:
            result = {
                "success": False,
                "error": f"Unknown action '{action}' classified by LLM"
            }
            scope_info = "none"

        # Add routing metadata to each result
        if isinstance(result, dict):
            result["_routing"] = {
                "action": action,
                "employee_id": employee_id,
                "scope_narrowing": scope_info,
                "routed_by": "LLM (gpt-4o-mini)"
            }

        results.append(result)

    # Return combined results
    return json.dumps({
        "success": all(r.get("success", False) for r in results),
        "actions_executed": len(results),
        "results": results
    }, indent=2)


# Also expose individual tools for direct invocation (bypasses LLM routing)

@mcp.tool()
async def provision_vpn(
    employee_id: str,
    vpn_profile: str = "standard",
    token: str = ""
) -> str:
    """
    Directly provision VPN access for an employee (bypasses LLM routing).
    Exchanges token to it:write scope via Token Exchanger.
    
    Args:
        employee_id: The employee ID to provision VPN for
        vpn_profile: VPN profile type (default: "standard")
        token: The IT-scoped bearer token
    """
    if not token:
        return json.dumps({"success": False, "error": "No token provided"})
    result = await _provision_vpn(employee_id, token, vpn_profile)
    return json.dumps(result)


@mcp.tool()
async def provision_github(
    employee_id: str,
    organization: str = "nebulasoft",
    repositories: str = "main-app,docs",
    permission: str = "write",
    token: str = ""
) -> str:
    """
    Directly provision GitHub Enterprise access (bypasses LLM routing).
    Exchanges token to it:write scope via Token Exchanger.
    
    Args:
        employee_id: The employee ID to provision GitHub for
        organization: GitHub organization name
        repositories: Comma-separated list of repositories
        permission: Permission level (read/write/admin)
        token: The IT-scoped bearer token
    """
    if not token:
        return json.dumps({"success": False, "error": "No token provided"})
    result = await _provision_github(
        employee_id, token, organization,
        [r.strip() for r in repositories.split(",")], permission
    )
    return json.dumps(result)


@mcp.tool()
async def provision_aws(
    employee_id: str,
    account: str = "nebulasoft-dev",
    role: str = "developer",
    token: str = ""
) -> str:
    """
    Directly provision AWS environment access (bypasses LLM routing).
    Exchanges token to it:write scope via Token Exchanger.
    
    Args:
        employee_id: The employee ID to provision AWS for
        account: AWS account name
        role: IAM role to assign
        token: The IT-scoped bearer token
    """
    if not token:
        return json.dumps({"success": False, "error": "No token provided"})
    result = await _provision_aws(employee_id, token, account, role)
    return json.dumps(result)


@mcp.tool()
async def list_provisions(
    employee_id: str,
    token: str = ""
) -> str:
    """
    Directly list all IT provisions for an employee (bypasses LLM routing).
    Exchanges token to it:read scope via Token Exchanger.
    
    Args:
        employee_id: The employee ID to look up provisions for
        token: The IT-scoped bearer token
    """
    if not token:
        return json.dumps({"success": False, "error": "No token provided"})
    result = await _list_provisions(employee_id, token)
    return json.dumps(result)


# ─────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()

    print(f"\n🔧 Starting IT MCP Server (LLM-routed)", file=sys.stderr)
    print(f"   Transport: {args.transport}", file=sys.stderr)
    print(f"   IT API Target: {IT_API_BASE}", file=sys.stderr)
    print(f"   Token Exchanger: {TOKEN_EXCHANGER_CLIENT_ID}", file=sys.stderr)
    print(f"   LLM Router: gpt-4o-mini", file=sys.stderr)
    print(f"   Tools: handle_it_request (smart), provision_vpn, provision_github, provision_aws, list_provisions", file=sys.stderr)

    if args.transport == "sse":
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware

        print(f"   SSE URL: http://localhost:{args.port}/sse", file=sys.stderr)
        print(f"   CORS: enabled for MCP Inspector", file=sys.stderr)

        # Get the underlying Starlette app from FastMCP and wrap with CORS
        sse_app = mcp.sse_app()
        sse_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(sse_app, host="127.0.0.1", port=args.port)
    else:
        mcp.run(transport="stdio")

