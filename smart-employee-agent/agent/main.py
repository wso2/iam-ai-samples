"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Smart Employee Agent — Agent Server (Resource Server)

  A FastAPI server that:
  - Validates user JWTs (requires agent_access scope)
  - Hosts a LangChain AI agent connected to an HR MCP server
  - Manages its own credentials for basic MCP access (Pattern 2)
  - Handles OBO flow for elevated user-specific actions (Pattern 3)
  - Maintains per-user sessions with chat history

  No internal employee IDs — user identity comes from JWT tokens.
"""

import os
import logging
from datetime import date

from dotenv import load_dotenv
load_dotenv()

# Disable SSL verification for self-signed certificates (dev only)
if os.getenv("DISABLE_SSL_VERIFY", "").lower() == "true":
    import warnings
    import httpx
    warnings.warn("SSL verification disabled — for development/testing only!", stacklevel=1)
    _orig_httpx_init = httpx.AsyncClient.__init__
    def _patched_httpx_init(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        _orig_httpx_init(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = _patched_httpx_init

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm
import httpx

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

import uvicorn

from session import SessionStore, UserSession
from agent_auth import AgentAuth
import obo_flow

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

def _resolve_hr_mcp_url() -> str:
    """
    Prefer an explicit HR_MCP_SERVER_URL when it's a real http(s) URL.
    Otherwise fall back to the Choreo Connection-injected service URL.
    Choreo doesn't expand ${VAR} placeholders in config values, so a value
    like "${CHOREO_HR_SERVER_SERVICEURL}/mcp" reaches us literally — treat
    that as "not set" and use the actual env var instead.
    """
    explicit = os.getenv("HR_MCP_SERVER_URL", "")
    if explicit.startswith(("http://", "https://")):
        return explicit
    base = os.getenv("CHOREO_HR_SERVER_SERVICEURL", "").rstrip("/")
    if base:
        return f"{base}/mcp"
    return "http://127.0.0.1:8000/mcp"


HR_MCP_SERVER_URL = _resolve_hr_mcp_url()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
logger.info("HR MCP server URL: %s", HR_MCP_SERVER_URL)

# Base URL for HR MCP server reset endpoint
HR_MCP_BASE_URL = HR_MCP_SERVER_URL.replace("/mcp", "")

# Cap on chat-history turns replayed to the model per request (user+assistant = 1 turn).
MAX_CHAT_HISTORY_TURNS = int(os.getenv("MAX_CHAT_HISTORY_TURNS", "20"))

# JWT validation config
JWKS_URL = os.getenv("JWKS_URL")
AUTH_ISSUER = os.getenv("AUTH_ISSUER")
TOKEN_AUDIENCE = os.getenv("TOKEN_AUDIENCE")

# ─── JWT Validation ──────────────────────────────────────────────────────────

_jwks_cache = None


async def _fetch_jwks():
    """Fetch and cache JWKS keys from Asgardeo."""
    global _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


async def validate_user_token(token: str) -> dict:
    """Validate a user JWT and return the payload.

    Checks signature, expiry, issuer, audience, and agent_access scope.
    """
    global _jwks_cache

    try:
        header = pyjwt.get_unverified_header(token)
        jwks = _jwks_cache or await _fetch_jwks()

        kid = header.get("kid")
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                signing_key = RSAAlgorithm.from_jwk(key)
                break

        if not signing_key:
            jwks = await _fetch_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    signing_key = RSAAlgorithm.from_jwk(key)
                    break
            if not signing_key:
                raise HTTPException(status_code=401, detail="Invalid token: unknown signing key")

        payload = pyjwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=AUTH_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )

        scopes = payload.get("scope", "").split()
        if "agent_access" not in scopes:
            raise HTTPException(status_code=403, detail="Token missing required scope: agent_access")

        return payload

    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(status_code=401, detail="Token validation failed")


# ─── Globals ─────────────────────────────────────────────────────────────────

agent_auth = AgentAuth()
sessions = SessionStore()

# ─── Helper Functions ────────────────────────────────────────────────────────


def determine_role(scopes: list[str]) -> str:
    """Derive the user's role from their token scopes."""
    if "hr_approve_rest" in scopes:
        return "HR Admin"
    return "Employee"


def build_system_prompt(session: UserSession) -> str:
    """Build a dynamic system prompt based on the user's identity and role."""
    name = session.user_name or "User"
    role = session.user_role or "Employee"
    has_obo = session.has_valid_obo

    role_capabilities = {
        "Employee": (
            "- View company holidays and leave policy\n"
            "- View your own leave balance\n"
            "- View your own leave requests\n"
            "- Apply for leave (Annual, Sick, or Personal)"
        ),
        "HR Admin": (
            "- Everything an Employee can do, plus:\n"
            "- View all leave requests across the organization\n"
            "- View detailed information about any leave request\n"
            "- Approve or reject pending leave requests"
        ),
    }

    capabilities = role_capabilities.get(role, role_capabilities["Employee"])

    if not has_obo:
        auth_guidance = (
            "**Authorization Status**: You currently have basic access only "
            "(company holidays and leave policy).\n"
            '- If a tool returns an "insufficient_scope" error, tell the user: '
            '"I need your authorization to perform this action. '
            'Please click the Authorize button to grant me access."\n'
            "- Do NOT retry the tool — the client will handle the authorization popup.\n"
        )
    else:
        auth_guidance = (
            "**Authorization Status**: You have been authorized by the user "
            "and can perform actions on their behalf.\n"
            '- If a tool returns an "insufficient_scope" error, this means the user\'s role '
            "does NOT have permission for this action. Explain politely what their role can "
            "do instead. Do NOT ask for re-authorization.\n"
            '- If a tool returns a "token_expired" error, tell the user their authorization '
            "has expired and ask them to re-authorize.\n"
        )

    today = date.today()

    return f"""You are the Corporate Concierge, a smart AI assistant for {name} ({role}).
You help employees with leave management — checking balances, applying for leave, \
and (for HR Admins) reviewing and approving leave requests.

**Today's date is {today.isoformat()}. The current year is {today.year}.**
Always use the current year for any date-related operations.

**Your Capabilities for {name} ({role}):**
{capabilities}

{auth_guidance}
**Available Tools:**

HR & Leave Management:
- get_company_holidays: View company holiday calendar
- get_leave_policy: View leave type rules and limits
- get_my_leave_balance: View your remaining leave days
- get_my_leave_requests: View your leave request history
- apply_leave: Submit a new leave request
- get_all_leave_requests: View all leave requests (HR Admin)
- get_leave_request_details: Get details of a specific leave request (HR Admin)
- approve_leave_request: Approve a pending leave request (HR Admin)
- reject_leave_request: Reject a leave request with a reason (HR Admin)

**Important guidelines:**
- Always use the user's name when addressing them, never mention internal IDs.
- When reporting leave requests, include the reference ID (e.g., LR001) so users can refer to specific requests.
- For approvals/rejections, first list pending requests using get_all_leave_requests, \
then use the reference ID from the results.
- Be clear and concise. Include relevant details like names, dates, and status."""


def _create_mcp_client(access_token: str) -> MultiServerMCPClient:
    """Create an MCP client with the given access token."""
    return MultiServerMCPClient(
        {
            "hr_server": {
                "transport": "streamable_http",
                "url": HR_MCP_SERVER_URL,
                "headers": {"Authorization": f"Bearer {access_token}"},
            },
        }
    )


def _extract_text(content) -> str:
    """Extract plain text from a LangChain message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _check_tool_errors(response) -> tuple:
    """Check tool responses for auth-related errors.

    Returns (error_type, error_message) or (None, None).
    """
    for message in response.get("messages", []):
        if hasattr(message, "type") and message.type == "tool":
            content = str(message.content)
            if "token_expired" in content:
                return "token_expired", content
            if "insufficient_scope" in content:
                return "insufficient_scope", content
    return None, None


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Smart Employee Agent")

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session(request: Request) -> UserSession:
    """FastAPI dependency: validate JWT and return the user's session."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]
    payload = await validate_user_token(token)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    session = sessions.get_or_create(sub)

    # Update session with latest token info
    scopes = payload.get("scope", "").split()
    session.user_scopes = scopes

    # Extract name — prefer given_name + last_name, fallback to name claim
    first_name = payload.get("given_name") or ""
    last_name = payload.get("last_name") or ""
    if first_name or last_name:
        session.user_name = f"{first_name} {last_name}".strip()
    else:
        session.user_name = (
            payload.get("name")
            or payload.get("preferred_username")
        )
    session.user_role = determine_role(scopes)

    return session


# ─── Startup ─────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Authenticate the agent on startup."""
    logger.info("Authenticating agent with Asgardeo...")
    await agent_auth.ensure_valid_token()
    logger.info("Agent server ready on :5001")


# ─── Chat Endpoint ───────────────────────────────────────────────────────────


@app.post("/api/chat")
async def chat(request: Request, session: UserSession = Depends(get_session)):
    """Process a user message through the AI agent.

    Uses OBO token if available, otherwise falls back to agent token.
    Detects auth errors and returns appropriate response types.
    """
    body = await request.json()
    user_message = body.get("message", "").strip()
    if not user_message:
        return JSONResponse(
            {"type": "error", "message": "Message cannot be empty."},
            status_code=400,
        )

    # Determine which token to use for MCP calls
    if session.has_valid_obo:
        access_token = session.obo_token.access_token
    else:
        agent_token = await agent_auth.ensure_valid_token()
        access_token = agent_token.access_token

    mcp_client = _create_mcp_client(access_token)

    try:
        tools = await mcp_client.get_tools()

        llm = ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0.7)
        agent = create_agent(llm, tools)

        system_prompt = build_system_prompt(session)
        messages = [{"role": "system", "content": system_prompt}]
        # Replay only the most recent N turns to bound latency/cost and avoid
        # blowing past the model's context window.
        history_window = session.chat_history[-(MAX_CHAT_HISTORY_TURNS * 2):]
        messages.extend(history_window)
        messages.append({"role": "user", "content": user_message})

        response = await agent.ainvoke({"messages": messages})

    except Exception as e:
        logger.exception("Agent invocation failed")
        # ExceptionGroup (TaskGroup) hides the real cause — surface the inner exceptions too.
        detail = str(e)
        sub_excs = getattr(e, "exceptions", None)
        if sub_excs:
            for i, sub in enumerate(sub_excs):
                logger.error("  sub-exception %d: %r", i, sub, exc_info=sub)
            detail = "; ".join(repr(s) for s in sub_excs)
        return JSONResponse(
            {"type": "error", "message": f"Agent error: {detail}"},
            status_code=500,
        )

    # Check for auth-related errors in tool responses
    error_type, _ = _check_tool_errors(response)
    agent_reply = _extract_text(response["messages"][-1].content)

    if error_type == "token_expired":
        session.pending_message = user_message
        return JSONResponse({
            "type": "obo_required",
            "message": "Your authorization has expired. Please re-authorize to continue.",
        })

    if error_type == "insufficient_scope":
        if not session.has_valid_obo and not session.obo_expired:
            session.pending_message = user_message
            return JSONResponse({
                "type": "obo_required",
                "message": agent_reply,
            })
        elif session.obo_expired:
            session.pending_message = user_message
            return JSONResponse({
                "type": "obo_required",
                "message": "Your authorization has expired. Please re-authorize to continue.",
            })
        # OBO exists but scope is missing → role limitation, return normally

    # Successful response — append and trim to the configured window.
    session.chat_history.append({"role": "user", "content": user_message})
    session.chat_history.append({"role": "assistant", "content": agent_reply})
    max_msgs = MAX_CHAT_HISTORY_TURNS * 2
    if len(session.chat_history) > max_msgs:
        del session.chat_history[:-max_msgs]

    return JSONResponse({
        "type": "response",
        "message": agent_reply,
        "refresh_dashboard": True,
    })


# ─── OBO Flow Endpoints ─────────────────────────────────────────────────────


@app.get("/api/obo/url")
async def get_obo_url(session: UserSession = Depends(get_session)):
    """Generate OBO authorization URL for the consent popup."""
    auth_url, state, code_verifier = await obo_flow.get_authorization_url(agent_auth)

    session.obo_code_verifier = code_verifier
    session.obo_pkce_state = state

    return JSONResponse({"auth_url": auth_url})


@app.get("/api/obo/callback")
async def obo_callback(code: str = None, state: str = None, error: str = None):
    """Handle OBO redirect from Asgardeo.

    Browser redirect (not API call), so no JWT validation.
    Session identified by the state parameter from the PKCE flow.
    """
    if error:
        logger.warning(f"OBO OAuth error: {error}")
        return HTMLResponse(content=obo_flow.callback_html(success=False, error=error))

    if not code:
        return HTMLResponse(
            content=obo_flow.callback_html(success=False, error="Missing authorization code")
        )

    if not state:
        return HTMLResponse(
            content=obo_flow.callback_html(success=False, error="Missing state parameter")
        )

    session = sessions.find_by_obo_state(state)
    if not session:
        return HTMLResponse(
            content=obo_flow.callback_html(success=False, error="Invalid state parameter")
        )

    try:
        obo_token, scopes, expires_at = await obo_flow.exchange_code(
            agent_auth, code, session.obo_code_verifier
        )

        session.obo_token = obo_token
        session.obo_scopes = scopes
        session.obo_expires_at = expires_at
        session.obo_code_verifier = None
        session.obo_pkce_state = None

        logger.info(f"OBO token stored for user {session.user_sub} (scopes: {scopes})")
        return HTMLResponse(content=obo_flow.callback_html(success=True))

    except Exception as e:
        logger.error(f"OBO token exchange failed: {e}")
        return HTMLResponse(content=obo_flow.callback_html(success=False, error=str(e)))


@app.get("/api/obo/status")
async def obo_status(session: UserSession = Depends(get_session)):
    """Check OBO authorization status."""
    if session.has_valid_obo:
        return JSONResponse({"authorized": True, "scopes": session.obo_scopes})
    return JSONResponse({"authorized": False})


@app.get("/api/obo/pending")
async def get_pending(session: UserSession = Depends(get_session)):
    """Get the pending message that triggered the OBO flow."""
    return JSONResponse({"pending_message": session.pending_message})


# ─── Logout Endpoint ─────────────────────────────────────────────────────────


@app.post("/api/logout")
async def logout(session: UserSession = Depends(get_session)):
    """Clear the user's agent session (OBO tokens, chat history).

    The SPA should call this on sign-out so that a subsequent login
    starts with a fresh session instead of reusing a stale OBO token.
    """
    sub = session.user_sub
    sessions.remove(sub)
    logger.info("Session cleared for user %s", sub)
    return JSONResponse({"success": True, "message": "Session cleared."})


# ─── Reset Endpoint ──────────────────────────────────────────────────────────


@app.post("/api/reset")
async def reset_data(
    request: Request, session: UserSession = Depends(get_session)
):
    """Reset all in-memory data and clear all sessions. HR Admin only."""
    if session.user_role != "HR Admin":
        raise HTTPException(
            status_code=403, detail="Reset is restricted to HR Admins"
        )

    auth_header = request.headers.get("Authorization", "")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            reset_resp = await client.post(
                f"{HR_MCP_BASE_URL}/reset",
                headers={"Authorization": auth_header} if auth_header else {},
            )
            reset_resp.raise_for_status()

        sessions.clear_all()

        logger.info("Data reset to default state, all sessions cleared")
        return JSONResponse({
            "success": True,
            "message": "Data reset to default state. All sessions cleared.",
        })

    except Exception as e:
        logger.error(f"Reset failed (downstream HR reset did not succeed): {e}")
        return JSONResponse(
            {"error": f"Reset failed: {str(e)}"},
            status_code=500,
        )


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("AGENT_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_SERVER_PORT", os.getenv("PORT", "5001")))
    uvicorn.run(app, host=host, port=port)
