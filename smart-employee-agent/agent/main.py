"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Employee Portal — Agent Server (Resource Server)

  A FastAPI server that:
  - Validates user JWTs (requires agent_access scope)
  - Hosts a LangChain AI agent connected to an HR MCP server
  - Manages its own credentials for basic MCP access (Pattern 2)
  - Handles OBO flow for elevated user-specific actions (Pattern 3)
  - Maintains per-user sessions with chat history

  No internal employee IDs — user identity comes from JWT tokens.
"""

import asyncio
import hmac
import json
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
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

import uvicorn

from session import SessionStore, UserSession
from agent_auth import AgentAuth
import obo_flow
import ciba_flow
import google_calendar
from token_debug import dump_claims, dump_encoded

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

# IT Agent (Pattern 4). The HR Agent calls it with its OWN agent token; the IT
# Agent requires the 'it_agent_invoke' scope on that token before doing any work.
IT_AGENT_URL = os.getenv("IT_AGENT_URL", "http://127.0.0.1:5002")
IT_AGENT_TIMEOUT = float(os.getenv("IT_AGENT_TIMEOUT", "60"))
# Off by default so the existing three-pattern demo runs unchanged.
IT_AGENT_ENABLED = os.getenv("IT_AGENT_ENABLED", "false").lower() == "true"
# When the IT hop carries the USER's authority (RFC 8693 exchange on the far
# side), the agent must hold the user's delegation BEFORE it delegates onward.
# Must match A2A_DELEGATION in it-agent/.env.
A2A_DELEGATION = os.getenv("A2A_DELEGATION", "").lower() == "true"

# Patterns 5-6: employee consent after leave approval and Google Calendar access.
CIBA_ENABLED = os.getenv("CIBA_ENABLED", "false").lower() == "true"
CIBA_CLIENT_ID = os.getenv("CIBA_CLIENT_ID", "")
CIBA_CLIENT_SECRET = os.getenv("CIBA_CLIENT_SECRET", "")
CIBA_NOTIFY_SCOPES = os.getenv("CIBA_NOTIFY_SCOPES", "openid profile email hr_self_mcp").split()
CIBA_NOTIFY_TIMEOUT = float(os.getenv("CIBA_NOTIFY_TIMEOUT_SECONDS", "300"))
CIBA_HINT_FALLBACK_SUB = os.getenv("CIBA_HINT_FALLBACK_SUB", "true").lower() == "true"
LEAVE_EVENT_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")

GOOGLE_CALENDAR_ENABLED = os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() == "true"
google_cal = google_calendar.GoogleCalendarClient()
if GOOGLE_CALENDAR_ENABLED and not obo_flow.FEDERATED_IDP_NAME:
    raise ValueError("GOOGLE_CALENDAR_ENABLED requires FEDERATED_IDP_NAME")
if CIBA_ENABLED and not all([CIBA_CLIENT_ID, CIBA_CLIENT_SECRET, LEAVE_EVENT_SECRET]):
    raise ValueError("CIBA_ENABLED requires CIBA_CLIENT_ID, CIBA_CLIENT_SECRET and AGENT_WEBHOOK_SECRET")

logger.info("HR MCP server URL: %s", HR_MCP_SERVER_URL)
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

    # Pattern 4: only advertise the IT Service Desk when the delegation hop is on.
    it_tools = (
        "\nIT Service Desk (handled by a separate IT Agent):\n"
        "- ask_it_agent: Ask the IT Service Desk about VPN, passwords, software and\n"
        "  licensing, devices, IT outages, or to raise and check IT support tickets.\n"
        if IT_AGENT_ENABLED else ""
    )
    calendar_sync_tool = (
        "- add_leave_to_my_calendar: Add an APPROVED leave to your own Google Calendar"
        if GOOGLE_CALENDAR_ENABLED else ""
    )
    calendar_sync_guidance = (
        "- Only call add_leave_to_my_calendar when the employee explicitly asks or agrees.\n"
        "- Google access comes from the user's federated token returned by Asgardeo.\n"
        "  If it is missing or expired, ask them to authorize again through Google.\n"
        "- After an HR Admin approves leave, the employee's Calendar consent is\n"
        "  requested separately through CIBA when enabled. Never claim that an\n"
        "  approval alone added an event to anyone's calendar.\n"
        if GOOGLE_CALENDAR_ENABLED else ""
    )

    it_guidance = (
        "- Route IT questions (VPN, passwords, software, laptops, outages, IT\n"
        "  tickets) to ask_it_agent, and HR questions to the HR tools. Never answer\n"
        "  IT questions from your own knowledge when ask_it_agent is available.\n"
        "- Always call ask_it_agent for IT requests, even with basic access only.\n"
        "  Never decide on your own that you lack permission; the tool requests\n"
        "  the user's authorization itself when it is needed.\n"
        "- If ask_it_agent reports that you are not authorized to contact the IT\n"
        "  Service Desk, that is an agent permission problem — relay it and do NOT\n"
        "  ask the user to authorize anything.\n"
        if IT_AGENT_ENABLED else ""
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
{calendar_sync_tool}
{it_tools}
**Important guidelines:**
{it_guidance}{calendar_sync_guidance}- Always use the user's name when addressing them, never mention internal IDs.
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


def _build_it_agent_tool(agent_access_token: str, session: UserSession):
    """Build the `ask_it_agent` tool for one chat turn.

    The user's identity is captured in the closure rather than exposed as a
    tool argument, so the LLM cannot invent or alter who the request is for.

    Two things travel to the IT Agent, and they are not interchangeable:

      Authorization  this agent's OWN token. It is what the IT Agent
                     authorizes the call on, exactly as before.
      user_token     the user's delegated token, forwarded as the subject of
                     an RFC 8693 exchange on the far side. It is data here,
                     not a credential for this hop.

    Forwarding the user token is what lets the second hop carry the user's
    authority instead of only their name. Without it the IT Agent falls back
    to acting as itself, which is the original Pattern 4 behaviour.
    """
    requester = {"sub": session.user_sub, "name": session.user_name or "an employee"}

    @tool
    async def ask_it_agent(query: str) -> str:
        """Ask the IT Service Desk agent an IT question and return its answer.

        Use this for anything IT-related: VPN, passwords, software requests and
        licensing, laptop or device issues, IT service outages, and raising or
        checking IT support tickets. Pass the user's question through as-is.
        Do NOT use this for HR topics such as leave, holidays, or payroll."""
        # Acting at the IT desk with this person's authority requires their
        # consent first. Pattern 4 alone needed none — the agent acted as
        # itself — so nothing here ever prompted for it. Returning an
        # insufficient_scope marker routes this through the same "Authorize"
        # path the HR tools use, rather than quietly proceeding with the
        # agent's own, broader permissions.
        if A2A_DELEGATION and not session.has_valid_obo:
            logger.info(
                "[A2A >> IT Agent] delegation is on but this user has not "
                "authorized yet — prompting for consent instead of delegating"
            )
            return (
                "insufficient_scope: I need your authorization before I can act "
                "on your behalf at the IT Service Desk."
            )

        logger.info(
            "[A2A >> IT Agent] requester=%s | query=%r",
            requester["name"], query[:120],
        )
        payload = {"query": query, "requester": requester}
        # Only when the user has actually delegated to THIS agent. Absent that,
        # there is no user authority to pass on and the IT Agent acts as itself.
        if session.has_valid_obo:
            payload["user_token"] = session.obo_token.access_token
            logger.info("[A2A >> IT Agent] forwarding the user's delegated token for exchange")
        else:
            # Without consent there is no user authority to pass on, so the IT
            # Agent will act as itself. Said out loud because it is otherwise
            # indistinguishable from delegation being broken.
            logger.info(
                "[A2A >> IT Agent] no OBO token for this user — nothing to forward; "
                "the IT Agent will act on its own authority"
            )

        try:
            async with httpx.AsyncClient(timeout=IT_AGENT_TIMEOUT) as client:
                resp = await client.post(
                    f"{IT_AGENT_URL}/api/ask",
                    headers={"Authorization": f"Bearer {agent_access_token}"},
                    json=payload,
                )
        except httpx.RequestError as e:
            logger.error("IT agent unreachable: %s", e)
            return "The IT Service Desk is unreachable right now. Please try again later."

        if resp.status_code == 403:
            # The HR Agent's own token lacks 'it_agent_invoke'. This is an agent
            # authorization problem — user consent cannot fix it, so say so
            # plainly rather than triggering an OBO prompt.
            detail = _safe_json(resp).get("message", "not permitted")
            logger.warning("[A2A DENIED by IT Agent] %s", detail)
            return (
                "I am not authorized to contact the IT Service Desk. "
                f"({detail}) This is an agent permission issue, not something "
                "you can approve — please ask an administrator."
            )
        if resp.status_code == 502 and _safe_json(resp).get("error") == "delegation_failed":
            detail = _safe_json(resp).get("message", "delegation failed")
            logger.warning("[A2A DENIED] %s", detail)
            if "subject token" in detail.lower():
                # Asgardeo rejected the forwarded OBO token itself — typically
                # revoked after a role change or sign-out, though it has not
                # reached its exp yet. It is useless for delegation, so drop it
                # and route through the same re-authorize path as an expiry.
                session.obo_token = None
                session.obo_scopes = []
                session.obo_expires_at = 0.0
                logger.info(
                    "[A2A >> IT Agent] forwarded OBO token is no longer active — "
                    "cleared it; prompting the user to authorize again"
                )
                return (
                    "token_expired: your authorization is no longer valid. "
                    "Please authorize again so I can act on your behalf at the "
                    "IT Service Desk."
                )
            return (
                "The IT Service Desk could not act with your permissions, and is "
                f"configured not to fall back to its own. ({detail})"
            )
        if resp.status_code != 200:
            detail = _safe_json(resp).get("message", f"HTTP {resp.status_code}")
            logger.warning("IT agent returned %s: %s", resp.status_code, detail)
            return f"The IT Service Desk could not answer that: {detail}"

        data = _safe_json(resp)
        logger.info("[A2A << IT Agent] tools_used=%s", data.get("tools_used") or "(none)")
        return data.get("answer") or "The IT Service Desk returned no answer."

    return ask_it_agent


def _build_calendar_sync_tool(session: UserSession, access_token: str):
    """Tool: add an already-approved leave to the user's Google Calendar.

    Separate from the approval itself, and deliberately user-invoked. Writing
    to Google uses a consent Asgardeo has no part in, so the user confirms it
    explicitly rather than it happening as a side effect.
    """

    @tool
    async def add_leave_to_my_calendar(request_id: str) -> str:
        """Add an approved leave request to the user's Google Calendar.

        Only use this after the user has agreed to it. If they have not
        connected Google Calendar, this reports that and the client will offer
        them the connect button.

        Args:
            request_id: The approved leave request reference (e.g. 'LR001').
        """
        ref = request_id.strip().upper()
        if not (GOOGLE_CALENDAR_ENABLED):
            return "Google Calendar sync is not configured on this server."
        if not session.google_connected:
            return (
                "google_not_connected: Please authorize again through the Google "
                "connection in Asgardeo so I can access your Calendar."
            )

        logger.info(
            "[GOOGLE] syncing %s for user(sub)=%s using their Google grant",
            ref, session.user_sub,
        )

        leave = await _find_own_leave(access_token, ref)
        if leave is None:
            return f"I could not find leave request {ref} among your requests."
        if leave.get("status") != "Approved":
            return f"{ref} is {leave.get('status', 'not approved')}, so there is nothing to add yet."

        outcome = {
            "request_id": ref,
            "employee_sub": session.user_sub,
            "employee": session.user_name,
            "leave_type": leave.get("type") or leave.get("leave_type") or "Leave",
            "start_date": leave.get("start_date"),
            "end_date": leave.get("end_date"),
        }
        note = await _sync_leave_to_calendar(outcome, session)
        return note.strip() or f"Calendar sync for {ref} did not complete."

    return add_leave_to_my_calendar


async def _list_own_leaves(access_token: str) -> list[dict]:
    """All of the caller's own leave requests, via the MCP tools.

    Raises on a refusal rather than returning nothing: "the server said no"
    and "you have no leave" are different facts, and conflating them turns a
    missing scope into a phantom missing record.
    """
    tools = await _create_mcp_client(access_token).get_tools()
    lister = next((t for t in tools if t.name == "get_my_leave_requests"), None)
    if lister is None:
        raise RuntimeError("get_my_leave_requests is unavailable on the HR server")

    payload = _safe_load(await lister.ainvoke({}))
    if payload.get("error"):
        raise PermissionError(
            f"{payload.get('error')}: {payload.get('message', '')} "
            f"(required: {payload.get('required_scope', '?')}, "
            f"present: {payload.get('available_scopes', '?')})"
        )
    return payload.get("leave_requests") or payload.get("requests") or []


async def _find_own_leave(access_token: str, request_id: str) -> dict | None:
    """Look up one of the caller's own leave requests by reference."""
    for item in await _list_own_leaves(access_token):
        if str(item.get("request_id", "")).upper() == request_id:
            return item
    return None


async def _sync_leave_to_calendar(outcome: dict, viewer: UserSession) -> str:
    """Write an approved leave with the employee's Google federated token.

    Called after employee CIBA consent or an explicit employee chat request.
    The calendar belongs to the employee named in outcome, using their own
    federated Google delegation. HR approval alone never calls this function.

    That split is the whole point of Pattern 6. Approving is Asgardeo
    authority; writing to Google is not. An admin with every HR scope in the
    tenant still cannot put an entry on someone's calendar — only the employee
    can grant that, and only to Google, and they can revoke it at Google
    without touching Asgardeo at all.

    Returns a sentence to append to the assistant's reply — never raises. A
    calendar problem must not make a successful approval look like a failure.
    """
    if not GOOGLE_CALENDAR_ENABLED:
        return "Google Calendar sync is disabled."

    start, end = outcome.get("start_date"), outcome.get("end_date")
    if not start or not end:
        logger.warning("[GOOGLE] approval result had no dates; skipping calendar sync")
        return "I could not add the leave to Calendar because its dates are missing."

    # Whose calendar. The HR server returns the requester's sub precisely so an
    # approver acting on someone else's leave lands on the right one.
    employee_sub = outcome.get("employee_sub") or viewer.user_sub
    employee_name = outcome.get("employee") or "the employee"
    is_self = employee_sub == viewer.user_sub

    target = viewer if is_self else sessions.get(employee_sub)
    whose = "your" if is_self else f"{employee_name}'s"
    they = "you have" if is_self else f"{employee_name} has"

    if target is None:
        # The employee has never talked to this agent, so there is no grant of
        # theirs to use. Nothing to fall back on: the admin's own Google
        # authorization would be the wrong authority, not a substitute.
        logger.info(
            "[GOOGLE] no active session for employee(sub)=%s — nothing to sync",
            employee_sub,
        )
        return (f" I could not add it to {whose} calendar because {they} not "
                f"connected Google Calendar with me.")

    if not target.google_connected:
        return (f" I could not add it to {whose} calendar because {they} not "
                f"connected Google Calendar yet"
                + (" — authorize again through Google in Asgardeo." if is_self else "."))

    leave_type = outcome.get("leave_type", "Leave")
    try:
        await google_cal.create_leave_event(
            target.google_grant,
            summary=f"{leave_type} — {target.user_name or employee_name}",
            start_date=start,
            end_date=end,
            description=(
                f"{outcome.get('request_id', '')} approved via the Corporate "
                f"Concierge. Added by the agent using your Google authorization."
            ).strip(),
        )
    except google_calendar.GoogleCalendarError as e:
        logger.warning("[GOOGLE] calendar sync failed: %s", e)
        return f" The approval went through, but I could not add it to {whose} calendar: {e}"
    except Exception as e:
        logger.exception("[GOOGLE] unexpected calendar failure")
        return f" The approval went through, but the calendar sync failed: {e}"

    logger.info(
        "[GOOGLE >> Calendar] synced %s to employee(sub)=%s | approved in-session by %s",
        outcome.get("request_id"), employee_sub, viewer.user_sub,
    )
    return f" I have also added {start} to {end} to {whose} Google Calendar."


def _safe_load(result) -> dict:
    """Normalize an MCP tool result (dict or JSON string) into a dict."""
    if isinstance(result, dict):
        return result
    try:
        parsed = json.loads(str(result))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _safe_json(resp) -> dict:
    """Parse a JSON body, returning {} rather than raising on a non-JSON reply."""
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


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
        if not (hasattr(message, "type") and message.type == "tool"):
            continue
        content = str(message.content)
        if "token_expired" in content:
            return "token_expired", content
        if "insufficient_scope" in content:
            return "insufficient_scope", content
    return None, None


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Employee Portal")

# Shared with the OBO callback popup, which posts its result to these origins.
ALLOWED_ORIGINS = obo_flow.ALLOWED_ORIGINS

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

    # Pattern 1: the agent as a resource server. This is the browser's own
    # token, validated here before anything else happens.
    dump_claims("[AGENT] User Token (received from browser)", payload, token)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    session = sessions.get_or_create(sub)

    # Update session with latest token info
    scopes = payload.get("scope", "").split()
    session.user_scopes = scopes

    # Extract name — prefer given_name + family_name, fallback to name claim
    first_name = payload.get("given_name") or ""
    last_name = payload.get("family_name") or payload.get("last_name") or ""
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

    # Determine which token to use for MCP calls. Logged with the same
    # "[X >> Y Token]" shape the HR server uses, so a request can be followed
    # across both processes.
    if session.has_valid_obo:
        access_token = session.obo_token.access_token
        logger.info(
            "[CHAT >> OBO Token] user(sub)=%s | name=%s | scopes=%s",
            session.user_sub,
            session.user_name or "?",
            ", ".join(session.obo_scopes) if session.obo_scopes else "(none)",
        )
    else:
        agent_token = await agent_auth.ensure_valid_token()
        access_token = agent_token.access_token
        logger.info(
            "[CHAT >> Agent Token] user(sub)=%s | name=%s | scopes=%s",
            session.user_sub,
            session.user_name or "?",
            getattr(agent_token, "scope", None) or "(none)",
        )

    mcp_client = _create_mcp_client(access_token)

    try:
        tools = await mcp_client.get_tools()

        # Pattern 4: expose the IT Agent as one more tool. The HR Agent always
        # presents its OWN agent token on this hop, never the user's OBO token —
        # the two agents authorize each other independently of the user.
        if IT_AGENT_ENABLED:
            agent_token = await agent_auth.ensure_valid_token()
            tools = [*tools, _build_it_agent_tool(agent_token.access_token, session)]

        # Explicit employee Calendar requests use the Asgardeo federated grant.
        # Approvals themselves trigger CIBA via the HR server's webhook.
        if GOOGLE_CALENDAR_ENABLED:
            tools = [*tools, _build_calendar_sync_tool(session, access_token)]

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

    # A missing or expired Google grant needs fresh Asgardeo OBO authorization.
    for message in response.get("messages", []):
        if getattr(message, "type", None) == "tool" and \
                "google_not_connected" in str(message.content):
            session.chat_history.append({"role": "user", "content": user_message})
            session.chat_history.append({"role": "assistant", "content": agent_reply})
            return JSONResponse({
                "type": "obo_required",
                "message": agent_reply,
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


@app.get("/api/it/tickets")
async def it_tickets(session: UserSession = Depends(get_session)):
    """List IT tickets for the browser UI.

    Pattern 1 on the way in (the user's JWT is validated by get_session) and
    Pattern 4 on the way out (this agent presents its OWN token to the IT
    Agent). The user's token is never forwarded — exactly the same authority
    chain the chat path uses, just without the LLM.
    """
    if not IT_AGENT_ENABLED:
        return JSONResponse(
            {"error": "disabled", "message": "IT Agent delegation is not enabled."},
            status_code=404,
        )

    agent_token = await agent_auth.ensure_valid_token()
    logger.info(
        "[A2A >> IT Agent] GET /api/tickets for user(sub)=%s", session.user_sub
    )
    try:
        async with httpx.AsyncClient(timeout=IT_AGENT_TIMEOUT) as client:
            resp = await client.get(
                f"{IT_AGENT_URL}/api/tickets",
                headers={"Authorization": f"Bearer {agent_token.access_token}"},
            )
    except httpx.RequestError as e:
        logger.error("IT agent unreachable: %s", e)
        return JSONResponse(
            {"error": "unreachable", "message": "The IT Service Desk is unreachable."},
            status_code=502,
        )

    data = _safe_json(resp)
    if resp.status_code != 200:
        logger.warning("IT agent ticket listing failed (%s): %s",
                       resp.status_code, data.get("message"))
        return JSONResponse(
            {
                "error": data.get("error", "it_agent_error"),
                "message": data.get("message", f"HTTP {resp.status_code}"),
            },
            status_code=resp.status_code if resp.status_code in (401, 403) else 502,
        )

    tickets = data.get("tickets", [])
    logger.info("[A2A << IT Agent] %d ticket(s)", len(tickets))
    return JSONResponse({"tickets": tickets})


# ─── Offline approval notice: HR event -> CIBA -> calendar ──────────────────

async def _handle_leave_approved(event: dict) -> None:
    """Ask the employee for Calendar consent, then verify and sync their leave."""
    if not CIBA_ENABLED or not GOOGLE_CALENDAR_ENABLED:
        logger.info("[OFFLINE] Calendar consent is disabled; skipping %s", event.get("request_id"))
        return

    sub = event.get("employee_sub")
    request_id = event.get("request_id")
    if not sub or not request_id:
        logger.warning("[OFFLINE] leave-approved event is missing employee_sub or request_id")
        return
    name = event.get("employee_name") or "the employee"
    login_hint = event.get("employee_username") or event.get("employee_email") or ""
    if not login_hint and CIBA_HINT_FALLBACK_SUB:
        login_hint = sub
    if not login_hint:
        logger.warning("[OFFLINE] No username/email for %s; include email in user access-token attributes", name)
        return

    client = ciba_flow.CibaClient(
        base_url=os.getenv("ASGARDEO_BASE_URL", ""),
        client_id=CIBA_CLIENT_ID,
        client_secret=CIBA_CLIENT_SECRET,
        ssl_verify=os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true",
    )
    binding = (
        f"Leave {request_id} ({event.get('start_date')} to "
        f"{event.get('end_date')}) approved. Add it to your calendar?"
    )[:100]
    extra = {
        "share_federated_token": "true",
        "federated_token_scope": (
            f"{obo_flow.FEDERATED_IDP_NAME};{obo_flow.FEDERATED_TOKEN_SCOPE}"
        ),
    }
    try:
        agent_token = await agent_auth.ensure_valid_token()
        started = await client.initiate(
            login_hint=login_hint,
            scopes=CIBA_NOTIFY_SCOPES,
            binding_message=binding,
            actor_token=agent_token.access_token,
            extra=extra,
        )
        logger.info("[OFFLINE >> CIBA] asked %s to confirm Calendar sync for %s", name, request_id)
        result = await client.await_approval(
            started["auth_req_id"],
            timeout_seconds=CIBA_NOTIFY_TIMEOUT,
            interval_seconds=float(started.get("interval", 2)),
        )
    except ciba_flow.CibaError as e:
        logger.error("[OFFLINE] Could not request Calendar consent for %s: %s", request_id, e)
        return
    if not result.approved:
        logger.info("[OFFLINE] %s did not approve Calendar sync for %s (%s)", name, request_id, result.status)
        return

    token_response = result.token or {}
    access_token = token_response.get("access_token")
    granted = (token_response.get("scope") or "").split()
    if not access_token or "hr_self_mcp" not in granted:
        logger.error("[OFFLINE] CIBA token cannot verify %s: authorize hr_self_mcp on the CIBA app and employee role", request_id)
        return
    dump_encoded("[AGENT] CIBA Token (employee approved offline)", access_token)
    try:
        verified = await _find_own_leave(access_token, request_id)
    except Exception:
        logger.exception("[OFFLINE] Could not verify %s with the employee's delegated token", request_id)
        return
    if verified is None or verified.get("status") != "Approved":
        logger.warning("[OFFLINE] %s is not an approved leave owned by the consenting employee", request_id)
        return
    logger.info("[OFFLINE >> Verified] %s confirmed as Approved with %s's delegated authority", request_id, name)

    grant = obo_flow.google_grant_from(token_response.get("federated_tokens"))
    if grant is None:
        logger.error("[OFFLINE] No Google federated token for %s; check token sharing, the Google-only login step and its adaptive script", request_id)
        return
    target = sessions.get_or_create(sub)
    target.google_grant = grant
    target.user_name = target.user_name or name
    outcome = {
        "request_id": request_id,
        "employee_sub": sub,
        "employee": name,
        "leave_type": verified.get("type") or verified.get("leave_type") or event.get("leave_type", "Leave"),
        "start_date": verified.get("start_date"),
        "end_date": verified.get("end_date"),
    }
    note = await _sync_leave_to_calendar(outcome, target)
    logger.info("[OFFLINE] %s Calendar sync: %s", request_id, note.strip())


@app.post("/api/events/leave-approved")
async def leave_approved_event(request: Request):
    """Told by the HR server that a leave was approved.

    Authenticated with a shared secret, not a user token: there is no user in
    this request. Returns immediately and does the work in the background, so
    a slow out-of-band prompt never delays whoever clicked Approve.
    """
    if not LEAVE_EVENT_SECRET:
        return JSONResponse({"error": "not_configured"}, status_code=404)
    if not hmac.compare_digest(
        request.headers.get("X-Webhook-Secret", ""), LEAVE_EVENT_SECRET
    ):
        logger.warning("[OFFLINE] rejected a leave-approved event: bad secret")
        return JSONResponse({"error": "forbidden"}, status_code=403)

    event = await request.json()
    logger.info("[OFFLINE << HR] leave-approved for %s (%s)",
                event.get("request_id"), event.get("employee_name"))
    async def _guarded() -> None:
        try:
            await _handle_leave_approved(event)
        except Exception:
            # Nothing awaits this task, so an unhandled error would otherwise
            # surface only as "Task exception was never retrieved" — or not at
            # all. The employee simply would not hear back.
            logger.exception(
                "[OFFLINE] handling leave-approved for %s failed",
                event.get("request_id"),
            )

    asyncio.create_task(_guarded())
    return JSONResponse({"accepted": True})


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
        obo_token, scopes, expires_at, federated = await obo_flow.exchange_code(
            agent_auth, code, session.obo_code_verifier
        )

        session.obo_token = obo_token
        session.obo_scopes = scopes
        session.obo_expires_at = expires_at
        session.obo_code_verifier = None
        session.obo_pkce_state = None

        dump_encoded("[AGENT] OBO Token just issued", obo_token.access_token)
        logger.info(f"OBO token stored for user {session.user_sub} (scopes: {scopes})")

        # Asgardeo may have passed through the token its upstream provider
        # issued. When it does, the user has already consented to Google as
        # part of signing in, and the agent needs no Google OAuth of its own —
        # one consent covers both.
        grant = obo_flow.google_grant_from(federated)
        if grant is not None:
            session.google_grant = grant
            logger.info(
                "[FEDERATED >> Google] calendar access obtained via Asgardeo for "
                "user(sub)=%s — no separate Google connect needed",
                session.user_sub,
            )

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
    # Per-request access lines bury the token lines these logs exist to show.
    uvicorn.run(
        app, host=host, port=port,
        access_log=os.getenv("ACCESS_LOG", "").lower() == "true",
    )
