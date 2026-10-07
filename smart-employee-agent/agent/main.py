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
import secrets
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
import action_links
import google_calendar
import grant_store
import mailer
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

# ─── Pattern 5: CIBA out-of-band approval ───────────────────────────────────
# The approver is a human who is NOT in this session and has no browser here.
CIBA_ENABLED = os.getenv("CIBA_ENABLED", "false").lower() == "true"
CIBA_APPROVER = os.getenv("CIBA_APPROVER", "")          # login_hint: the HR Admin
CIBA_TIMEOUT_SECONDS = float(os.getenv("CIBA_TIMEOUT_SECONDS", "90"))
CIBA_SCOPES = os.getenv("CIBA_SCOPES", "openid hr_approve_mcp").split()

# ─── Offline approval notice ────────────────────────────────────────────────
# When a leave is approved the employee may be nowhere near a browser. The HR
# server tells us, and we reach them on their own device with CIBA: the
# binding message IS the notification, and approving it IS the consent to act.
LEAVE_EVENT_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")
# Scopes asked for on the employee's out-of-band approval. Only what is needed
# to confirm it is them and to read their own leave.
CIBA_NOTIFY_SCOPES = os.getenv("CIBA_NOTIFY_SCOPES", "openid hr_self_mcp").split()
CIBA_NOTIFY_TIMEOUT = float(os.getenv("CIBA_NOTIFY_TIMEOUT_SECONDS", "300"))
# When no username/email claim ever reached us, try the user's subject as the
# CIBA login_hint rather than abandoning the notification outright.
CIBA_HINT_FALLBACK_SUB = os.getenv("CIBA_HINT_FALLBACK_SUB", "true").lower() == "true"
# Where the emailed link points. Must be reachable from the recipient's device.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5001").rstrip("/")
# Send a receipt when the sync already succeeded? Off by default: the CIBA
# prompt already told them, and the entry is in their calendar. A second mail
# that asks nothing of them is noise. Real deployments may want it on.
SEND_SYNC_RECEIPT = os.getenv("SEND_SYNC_RECEIPT", "").lower() == "true"

# Google consent journeys started from an emailed link rather than a session,
# keyed by the OAuth state. The recipient has no session yet, so there is
# nowhere else to hang the in-flight request.
_link_flows: dict[str, dict] = {}
# CIBA needs a confidential client. The App Native Auth app is public (no
# secret), so this is normally a SEPARATE application; falls back to the main
# one if you did add a secret there instead.
CIBA_CLIENT_ID = os.getenv("CIBA_CLIENT_ID") or os.getenv("ASGARDEO_CLIENT_ID", "")
ASGARDEO_CLIENT_SECRET = os.getenv("CIBA_CLIENT_SECRET") or os.getenv("ASGARDEO_CLIENT_SECRET", "")

# ─── Pattern 6: Google Calendar (external API, third-party delegation) ──────
GOOGLE_CALENDAR_ENABLED = os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() == "true"
google_cal = google_calendar.GoogleCalendarClient(
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    redirect_uri=os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:5001/api/google/callback"
    ),
)
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
            + (
                "- EXCEPTION — approving a leave request: the Authorize button can "
                "NEVER grant this, because approval belongs to the HR Admin's role, "
                "not the user's. Use request_admin_approval instead. Never tell the "
                "user to click Authorize for an approval.\n"
                if CIBA_ENABLED else ""
            )
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
    ciba_tools = (
        "\nApprovals (handled out-of-band by the HR Admin):\n"
        "- request_admin_approval: Ask the HR Admin to approve a pending leave\n"
        "  request on their own device. They are not in this chat.\n"
        if CIBA_ENABLED else ""
    )
    ciba_guidance = (
        "- Approvals are ALWAYS handled by request_admin_approval when you are not\n"
        "  talking to an HR Admin. This is the only way to get a leave request\n"
        "  approved — never ask the user to authorize it themselves.\n"
        "- If the user does not give a request reference (like LR001), ASK them for\n"
        "  it — it is shown in the Ref column on their dashboard. Do NOT call\n"
        "  get_my_leave_requests to look it up: that needs the user's own\n"
        "  authorization, which has nothing to do with getting approval, and it\n"
        "  would pop an unrelated consent prompt at them.\n"
        "- You MUST actually call request_admin_approval. Never merely promise to\n"
        "  send it, and never say you will report back later: you cannot send a\n"
        "  message after this reply, so a promise to follow up is always false.\n"
        "- The tool WAITS for the approver and returns the final outcome. Call it,\n"
        "  then report what it returned — approved or not — in this same reply.\n"
        if CIBA_ENABLED else ""
    )
    # Pattern 6: the sync is automatic on approval, but the model must relay
    # what happened — including the case where the employee never connected.
    calendar_tool = (
        "\n  (this also adds the leave to the EMPLOYEE's own Google Calendar)"
        if GOOGLE_CALENDAR_ENABLED and google_cal.configured else ""
    )
    calendar_sync_tool = (
        "- add_leave_to_my_calendar: Add an APPROVED leave to the user's Google Calendar"
        if GOOGLE_CALENDAR_ENABLED and google_cal.configured else ""
    )

    calendar_sync_guidance = (
        "- After an approval is announced you may offer to add the leave to the\n"
        "  user's Google Calendar. Only call add_leave_to_my_calendar once they\n"
        "  have agreed — a reply like 'yes' or 'please do' following that offer.\n"
        "- Writing to Google uses a permission the user grants at Google, separate\n"
        "  from anything they approved here. If the tool says it is not connected,\n"
        "  tell them plainly and stop; the client will offer the connect button.\n"
        if GOOGLE_CALENDAR_ENABLED and google_cal.configured else ""
    )

    calendar_guidance = (
        "- approve_leave_request may return a 'calendar_sync' field. Relay it to the\n"
        "  user verbatim in your reply. If it says the employee has not connected\n"
        "  Google Calendar, say so plainly — the approval still succeeded, and it is\n"
        "  the employee's own choice to make, not something you or an HR Admin can\n"
        "  authorize on their behalf.\n"
        "- Never claim you added anything to a calendar unless 'calendar_sync' says\n"
        "  you did.\n"
        if GOOGLE_CALENDAR_ENABLED and google_cal.configured else ""
    )

    it_guidance = (
        "- Route IT questions (VPN, passwords, software, laptops, outages, IT\n"
        "  tickets) to ask_it_agent, and HR questions to the HR tools. Never answer\n"
        "  IT questions from your own knowledge when ask_it_agent is available.\n"
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
- approve_leave_request: Approve a pending leave request (HR Admin){calendar_tool}
- reject_leave_request: Reject a leave request with a reason (HR Admin)
{calendar_sync_tool}
{it_tools}{ciba_tools}
**Important guidelines:**
{it_guidance}{ciba_guidance}{calendar_sync_guidance}{calendar_guidance}- Always use the user's name when addressing them, never mention internal IDs.
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
        if not (GOOGLE_CALENDAR_ENABLED and google_cal.configured):
            return "Google Calendar sync is not configured on this server."
        if not session.google_connected:
            # Grants live in memory on the session, so the usual cause of this
            # after a successful connect is that the agent restarted in
            # between — which also drops the OBO token. Say so, rather than
            # just repeating "please connect" at someone who already did.
            logger.warning(
                "[GOOGLE] %s asked to sync %s but this session holds no Google "
                "grant (user(sub)=%s). If they connected earlier, the agent has "
                "restarted since — grants are in memory and do not survive it.",
                session.user_name or "the user", ref, session.user_sub,
            )
            # Marker the chat endpoint turns into a "Connect Google Calendar"
            # prompt, mirroring how insufficient_scope becomes "Authorize".
            return (
                "google_not_connected: I need access to your Google Calendar "
                "before I can add anything to it."
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
        return note.strip() or f"I added {ref} to your Google Calendar."

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


def _build_ciba_tool(agent_access_token: str, session: UserSession):
    """Build the `request_admin_approval` tool for one chat turn (Pattern 5).

    The approver named by CIBA_APPROVER is not in this session — they get a
    notification on their own device. The agent's token rides along as
    `actor_token`, so what comes back is a delegated token (sub=approver,
    act=agent) that the HR MCP server already knows how to validate.
    """
    client = ciba_flow.CibaClient(
        base_url=os.getenv("ASGARDEO_BASE_URL", ""),
        client_id=CIBA_CLIENT_ID,
        client_secret=ASGARDEO_CLIENT_SECRET,
        ssl_verify=os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true",
    )

    @tool
    async def request_admin_approval(request_id: str, summary: str = "") -> str:
        """Ask the HR Admin to approve a pending leave request out-of-band.

        Use this when a leave request needs HR Admin approval and the admin is
        not the person you are talking to. The admin is notified on their own
        device and approves there; this call waits for their answer.

        Args:
            request_id: The leave request reference, e.g. 'LR004'.
            summary: One line describing the request (employee, dates, type),
                shown to the approver on their device."""
        if not CIBA_APPROVER:
            return "Out-of-band approval is not configured (no approver set)."
        if not ASGARDEO_CLIENT_SECRET:
            return ("Out-of-band approval is not configured: CIBA requires a "
                    "client secret on the application.")

        detail = summary.strip() or f"leave request {request_id}"
        binding_message = f"Approve {request_id}: {detail}"[:200]

        logger.info(
            "[CIBA >> %s] requested by user(sub)=%s | %r",
            CIBA_APPROVER, session.user_sub, binding_message,
        )
        try:
            started = await client.initiate(
                login_hint=CIBA_APPROVER,
                scopes=CIBA_SCOPES,
                binding_message=binding_message,
                actor_token=agent_access_token,
            )
        except ciba_flow.CibaError as e:
            return f"Could not reach the HR Admin for approval: {e}"
        except Exception as e:
            logger.exception("CIBA initiation failed")
            return f"Could not start the approval request: {e}"

        result = await client.await_approval(
            started["auth_req_id"],
            timeout_seconds=CIBA_TIMEOUT_SECONDS,
            interval_seconds=float(started.get("interval", 2)),
        )

        if not result.approved:
            logger.info("[CIBA] not approved: %s", result.status)
            return (
                f"The HR Admin has not approved {request_id}: {result.detail} "
                "The request is still pending."
            )

        # Approve using the DELEGATED token, not the agent's own token — the
        # agent has no hr_approve_mcp of its own, and must not.
        obo_access_token = result.token.get("access_token")
        granted = (result.token.get("scope") or "").split()
        logger.info(
            "[CIBA >> Delegated Token] granted scopes=%s",
            ", ".join(granted) if granted else "(none)",
        )
        missing = [s for s in CIBA_SCOPES if s != "openid" and s not in granted]
        if missing:
            # Asgardeo grants the intersection of requested / app-authorized /
            # role-permitted. A missing scope here is console config, not consent.
            logger.warning(
                "[CIBA] approved but token lacks %s (granted: %s) — check that the "
                "scope is authorized on the CIBA application and that the "
                "approver's role is associated with it",
                ", ".join(missing), ", ".join(granted) or "(none)",
            )
            return (
                f"The HR Admin approved, but the token they granted is missing "
                f"{', '.join(missing)} (it has: {', '.join(granted) or 'nothing'}). "
                "That is an Asgardeo configuration issue on the approval "
                "application, not something the approver can fix."
            )
        try:
            tools = await _create_mcp_client(obo_access_token).get_tools()
            approver = next((t for t in tools if t.name == "approve_leave_request"), None)
            if approver is None:
                return "The approval tool is unavailable on the HR server."
            outcome = _safe_load(await approver.ainvoke({"request_id": request_id}))
        except Exception as e:
            logger.exception("Approval call failed after CIBA")
            return f"The HR Admin approved, but applying it failed: {e}"

        if outcome.get("error"):
            logger.warning("[CIBA] approval rejected downstream: %s", outcome.get("message"))
            return f"The HR Admin approved, but the request could not be applied: {outcome.get('message')}"

        logger.info("[CIBA] %s approved out-of-band and applied", request_id)
        message = (
            f"The HR Admin approved {request_id} on their device. "
            f"{outcome.get('notification', 'The request is now Approved.')}"
        )
        # Pattern 6: the approval is a business event; syncing it to the
        # employee's own Google Calendar uses THEIR separate Google consent,
        # not the approving admin's authority and not the agent's.
        return message + await _sync_leave_to_calendar(outcome, session)

    return request_admin_approval


def _wrap_approve_with_calendar_sync(tools: list, session: UserSession) -> list:
    """Replace the MCP `approve_leave_request` tool with one that also writes
    the approved leave to the employee's Google Calendar (Pattern 6).

    Wrapping rather than instructing keeps the external call deterministic: the
    calendar write happens because an approval actually succeeded, not because
    the model remembered to make a second tool call. The model still narrates
    the outcome, but it cannot skip, duplicate, or invent it.

    Failures and scope errors from the inner tool pass through untouched, so
    the OBO prompt in `_check_tool_errors` still sees exactly what it expects.
    """
    inner = next((t for t in tools if t.name == "approve_leave_request"), None)
    if inner is None:
        return tools

    @tool
    async def approve_leave_request(request_id: str) -> dict:
        """Approve a pending leave request. The employee's leave balance will be
        deducted accordingly, and the leave is added to the employee's Google
        Calendar. Requires HR Admin authorization.

        To find the request_id, first use get_all_leave_requests to list pending
        requests.

        Args:
            request_id: The leave request reference ID to approve (e.g., 'LR001').
        """
        raw = await inner.ainvoke({"request_id": request_id})
        outcome = _safe_load(raw)
        if not outcome.get("success"):
            return raw

        note = await _sync_leave_to_calendar(outcome, session)
        if note:
            outcome["calendar_sync"] = note.strip()
        return outcome

    return [approve_leave_request if t is inner else t for t in tools]


async def _sync_leave_to_calendar(outcome: dict, viewer: UserSession) -> str:
    """Write an approved leave to the EMPLOYEE's own Google Calendar.

    `viewer` is whoever is in the chat — the employee themselves on the CIBA
    path, an HR Admin on the direct-approval path. Either way the calendar
    written to belongs to the employee named in `outcome`, using the Google
    delegation that employee granted personally.

    That split is the whole point of Pattern 6. Approving is Asgardeo
    authority; writing to Google is not. An admin with every HR scope in the
    tenant still cannot put an entry on someone's calendar — only the employee
    can grant that, and only to Google, and they can revoke it at Google
    without touching Asgardeo at all.

    Returns a sentence to append to the assistant's reply — never raises. A
    calendar problem must not make a successful approval look like a failure.
    """
    if not GOOGLE_CALENDAR_ENABLED or not google_cal.configured:
        return ""

    start, end = outcome.get("start_date"), outcome.get("end_date")
    if not start or not end:
        logger.warning("[GOOGLE] approval result had no dates; skipping calendar sync")
        return ""

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
                + (" — use Connect Google Calendar in the user menu." if is_self else "."))

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


# Tools that resolve their own authorization out-of-band. A scope failure they
# report is about the APPROVER's token, not the user's, so it must never be
# turned into an "authorize me" prompt aimed at the person in the chat.
_SELF_AUTHORIZING_TOOLS = {"request_admin_approval"}


def _check_tool_errors(response) -> tuple:
    """Check tool responses for auth-related errors.

    Returns (error_type, error_message) or (None, None).
    """
    for message in response.get("messages", []):
        if not (hasattr(message, "type") and message.type == "tool"):
            continue
        if getattr(message, "name", None) in _SELF_AUTHORIZING_TOOLS:
            # Its outcome is already prose for the user; prompting for consent
            # here would hide a completed (or refused) out-of-band approval.
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

    # Google grants outlive this process; the sessions holding them did not.
    # Restoring them is what makes "the second approval needs no link" true
    # across a restart.
    for sub, grant in grant_store.restore_all(google_calendar).items():
        sessions.get_or_create(sub).google_grant = grant
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

        # Pattern 5: out-of-band approval by a human who is not in this session.
        if CIBA_ENABLED:
            agent_token = await agent_auth.ensure_valid_token()
            tools = [*tools, _build_ciba_tool(agent_token.access_token, session)]

        # Pattern 6: approving is an Asgardeo decision; the calendar entry that
        # follows is written with the EMPLOYEE's own Google delegation, which
        # no HR scope in the tenant can substitute for.
        if GOOGLE_CALENDAR_ENABLED and google_cal.configured:
            tools = _wrap_approve_with_calendar_sync(tools, session)
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

    # The calendar tool reports a missing Google grant with this marker; turn
    # it into a connect prompt rather than letting the model explain it away.
    for message in response.get("messages", []):
        if getattr(message, "type", None) == "tool" and \
                "google_not_connected" in str(message.content):
            session.chat_history.append({"role": "user", "content": user_message})
            session.chat_history.append({"role": "assistant", "content": agent_reply})
            return JSONResponse({
                "type": "google_required",
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

async def _sync_for_offline_user(sub: str, leave: dict) -> bool:
    """Write the leave to the user's calendar using a grant they gave earlier.

    Grants hang off the session, which survives the user closing the browser
    (they are keyed by subject and live for the session TTL). If there is no
    grant we cannot proceed here: Google has no out-of-band consent, so it
    needs a browser and therefore a link.
    """
    target = sessions.get(sub)
    if target is None or not target.google_connected:
        return False
    note = await _sync_leave_to_calendar({**leave, "employee_sub": sub}, target)
    return "could not" not in note.lower()


def _approval_email(name: str, leave: dict, link: str | None) -> tuple:
    """Subject and body of the approval notice."""
    ref = leave.get("request_id")
    when = f"{leave.get('start_date')} to {leave.get('end_date')}"
    subject = f"Your leave request {ref} was approved"
    if link:
        body = (
            f"Hi {name},\n\n"
            f"Your {leave.get('leave_type', 'leave')} request {ref} ({when}) "
            f"has been approved.\n\n"
            f"To add it to your Google Calendar, open this link and sign in to "
            f"Google:\n\n  {link}\n\n"
            f"The link works once and expires. Adding the entry needs your "
            f"permission at Google, which is separate from anything approved "
            f"here — we cannot do it on your behalf without it.\n\n"
            f"— Corporate Concierge\n"
        )
    else:
        body = (
            f"Hi {name},\n\n"
            f"Your {leave.get('leave_type', 'leave')} request {ref} ({when}) "
            f"has been approved, and I have added it to your Google Calendar "
            f"using the access you granted earlier.\n\n"
            f"— Corporate Concierge\n"
        )
    return subject, body


async def _handle_leave_approved(event: dict) -> None:
    """Reach an employee who is not in a browser, and offer the calendar sync.

    CIBA first: its binding message is the notification AND the request for
    consent, in one out-of-band interaction on their own device. Only once
    they approve do we touch anything on their behalf.

    Google is the part CIBA cannot cover — it has no out-of-band consent — so
    if they have not connected it, the follow-up has to be a link they open in
    a browser.
    """
    sub = event.get("employee_sub")
    name = event.get("employee_name") or "there"
    leave = {
        "request_id": event.get("request_id"),
        "leave_type": event.get("leave_type", "Leave"),
        "start_date": event.get("start_date"),
        "end_date": event.get("end_date"),
        "employee": name,
    }
    login_hint = event.get("employee_username") or event.get("employee_email") or ""
    email = event.get("employee_email") or ""

    # Nothing the HR server saw carried a username or email. Before giving up,
    # try what we DO have: the subject. Asgardeo accepts a user id as a
    # login_hint in many configurations, so this often just works — and when
    # it does not, the CIBA error says so plainly.
    if not login_hint and sub and CIBA_HINT_FALLBACK_SUB:
        login_hint = sub
        logger.warning(
            "[OFFLINE] no username/email known for %s — falling back to their "
            "subject as the CIBA login_hint. Add 'email' to the application's "
            "requested attributes and access token to fix this properly.", name,
        )

    if not CIBA_ENABLED or not ASGARDEO_CLIENT_SECRET:
        logger.warning(
            "[OFFLINE] %s approved but CIBA is not configured — cannot ask %s "
            "out-of-band", leave["request_id"], name,
        )
        return
    if not login_hint:
        logger.warning(
            "[OFFLINE] %s approved but there is no way to reach %s. No token "
            "the HR server saw carried 'email' or 'username'. Add them to the "
            "application's User Attributes AND its Access Token Attributes, "
            "then have the user sign in again.", leave["request_id"], name,
        )
        return

    client = ciba_flow.CibaClient(
        base_url=os.getenv("ASGARDEO_BASE_URL", ""),
        client_id=CIBA_CLIENT_ID,
        client_secret=ASGARDEO_CLIENT_SECRET,
        ssl_verify=os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true",
    )
    binding = (
        f"Leave {leave['request_id']} ({leave['start_date']} to "
        f"{leave['end_date']}) approved. Add it to your calendar?"
    )[:100]

    try:
        agent_token = await agent_auth.ensure_valid_token()
        # Ask for the upstream provider's token as well. On a code grant these
        # ride as query parameters on /authorize; CIBA has no such call, so
        # they go on the initiation request instead. Undocumented — Asgardeo
        # may forward them into the authentication flow or ignore them — but
        # the full token response is logged either way, so we will see.
        fed_extra = {}
        if obo_flow.FEDERATED_IDP_NAME:
            fed_extra = {
                "share_federated_token": "true",
                "federated_token_scope": (
                    f"{obo_flow.FEDERATED_IDP_NAME};{obo_flow.FEDERATED_TOKEN_SCOPE}"
                ),
            }

        started = await client.initiate(
            login_hint=login_hint,
            scopes=CIBA_NOTIFY_SCOPES,
            binding_message=binding,
            actor_token=agent_token.access_token,
            extra=fed_extra,
        )
        if fed_extra:
            logger.info(
                "[OFFLINE >> CIBA] also requested a federated token from '%s' "
                "(scope: %s)",
                obo_flow.FEDERATED_IDP_NAME, obo_flow.FEDERATED_TOKEN_SCOPE,
            )
        logger.info(
            "[OFFLINE >> CIBA] asked %s to confirm the calendar sync for %s",
            login_hint, leave["request_id"],
        )
        result = await client.await_approval(
            started["auth_req_id"],
            timeout_seconds=CIBA_NOTIFY_TIMEOUT,
            interval_seconds=float(started.get("interval", 2)),
        )
    except ciba_flow.CibaError as e:
        logger.error("[OFFLINE] could not reach %s out-of-band: %s", login_hint, e)
        return

    if not result.approved:
        logger.info(
            "[OFFLINE] %s did not approve the calendar sync for %s (%s)",
            login_hint, leave["request_id"], result.status,
        )
        return

    ciba_access_token = (result.token or {}).get("access_token", "")
    dump_encoded("[AGENT] CIBA Token (employee approved offline)", ciba_access_token)

    # If Asgardeo did pass the upstream token through, use it — the user has
    # then already consented to Google as part of approving, and no emailed
    # link is needed at all.
    fed_grant = obo_flow.google_grant_from((result.token or {}).get("federated_tokens"))
    if fed_grant is not None:
        sessions.get_or_create(sub).google_grant = fed_grant
        logger.info(
            "[OFFLINE >> Google] calendar access arrived with the CIBA token — "
            "no link needed for user(sub)=%s", sub,
        )

    granted = (result.token or {}).get("scope", "").split()
    missing = [s for s in CIBA_NOTIFY_SCOPES if s != "openid" and s not in granted]
    if missing:
        logger.warning(
            "[OFFLINE] the CIBA token is missing %s (granted: %s). That is "
            "application/role configuration on the CIBA app, not something the "
            "approver can fix.", ", ".join(missing), " ".join(granted) or "(none)",
        )

    # Use the token they just granted, rather than trusting the webhook.
    #
    # Everything so far arrived as a JSON payload from another service. The
    # delegated token (sub=employee, act=agent) lets the agent read the leave
    # from the HR server *as the employee* and confirm it really is theirs and
    # really is approved. Without this the CIBA approval would be decoration:
    # a consent obtained and then never exercised.
    if ciba_access_token:
        try:
            verified = await _find_own_leave(ciba_access_token, leave["request_id"])
        except PermissionError as e:
            # The token was issued but carries too little to read their leave.
            # Almost always the CIBA application is not authorized for the HR
            # MCP resource, so Asgardeo silently trims the scope to openid.
            logger.error(
                "[OFFLINE] the token %s granted cannot read their leave — %s\n"
                "    Authorize the CIBA application for the HR MCP API resource "
                "(hr_self_mcp) and confirm their role grants it, then retry. "
                "Asgardeo grants the intersection of requested / app-authorized "
                "/ role-permitted, so an unauthorized app yields 'openid' alone.",
                name, e,
            )
            return
        except Exception as e:
            logger.warning(
                "[OFFLINE] could not verify %s with the delegated token: %s",
                leave["request_id"], e,
            )
            verified = None

        if verified is None:
            logger.warning(
                "[OFFLINE] %s is not among %s's own leave requests when read "
                "with their delegated token — refusing to act on the webhook "
                "payload alone.", leave["request_id"], name,
            )
            return
        if verified.get("status") != "Approved":
            logger.warning(
                "[OFFLINE] %s reads as %s with the employee's own token, not "
                "Approved — not syncing.", leave["request_id"], verified.get("status"),
            )
            return

        # Authoritative values, straight from the resource server.
        leave.update({
            "leave_type": verified.get("type") or verified.get("leave_type") or leave["leave_type"],
            "start_date": verified.get("start_date") or leave["start_date"],
            "end_date": verified.get("end_date") or leave["end_date"],
        })
        logger.info(
            "[OFFLINE >> Verified] %s confirmed as Approved by reading it with "
            "%s's own delegated authority", leave["request_id"], name,
        )

    # They said yes. If Google is already connected we are done; otherwise the
    # only way to get that consent is a browser, so send a link.
    if await _sync_for_offline_user(sub, leave):
        logger.info(
            "[OFFLINE] synced %s to the calendar with an existing grant — "
            "nothing further is needed from %s", leave["request_id"], name,
        )
        # Mail only when there is still something for them to do. Here there
        # is not: they approved, and the entry exists.
        if SEND_SYNC_RECEIPT:
            subject, body = _approval_email(name, leave, None)
            mailer.send(email, subject, body)
        return

    token = action_links.create(
        "sync_calendar", sub,
        request_id=leave["request_id"], leave=leave, name=name,
    )
    link = f"{PUBLIC_BASE_URL}/api/calendar-link?token={token}"
    logger.info(
        "[OFFLINE] %s has no Google grant — emailing a one-time link for %s",
        name, leave["request_id"],
    )
    subject, body = _approval_email(name, leave, link)
    mailer.send(email, subject, body)


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


def _link_page(title: str, heading: str, body_html: str, tone: str = "ok") -> HTMLResponse:
    """Standalone page for someone arriving from an email, with no session."""
    colour = {"ok": "#166534", "err": "#991b1b"}.get(tone, "#1f2937")
    background = {"ok": "#f0fdf4", "err": "#fef2f2"}.get(tone, "#f8fafc")
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         display:flex; align-items:center; justify-content:center;
         min-height:100vh; margin:0; background:{background}; }}
  .card {{ max-width:34rem; padding:2.5rem; text-align:center; }}
  h2 {{ color:{colour}; margin-bottom:.75rem; }}
  p {{ color:#4b5563; line-height:1.6; }}
  a.btn {{ display:inline-block; margin-top:1.25rem; padding:.7rem 1.4rem;
          background:#2563eb; color:#fff; border-radius:8px;
          text-decoration:none; font-weight:600; }}
</style></head>
<body><div class="card"><h2>{heading}</h2>{body_html}</div></body></html>""")


@app.get("/api/calendar-link")
async def calendar_link(token: str = ""):
    """Landing page for the emailed link.

    Deliberately does not act on arrival. The link proves only that someone
    received the mail, so the page explains what is about to happen and waits
    for a click — and the click leads to Google, where the real authorization
    happens.
    """
    body = action_links.peek(token, "sync_calendar")
    if body is None:
        return _link_page(
            "Link no longer valid", "This link is no longer valid",
            "<p>It may have expired, or already been used. Sign in to the "
            "portal and ask the assistant to add the leave instead.</p>", "err")

    leave = body.get("leave", {})
    return _link_page(
        "Add leave to your calendar",
        f"Add {leave.get('request_id')} to your calendar",
        f"<p>Your {leave.get('leave_type', 'leave')} from "
        f"<strong>{leave.get('start_date')}</strong> to "
        f"<strong>{leave.get('end_date')}</strong> was approved.</p>"
        f"<p>Adding it needs your permission at Google, which is separate from "
        f"anything approved at work. You will sign in to Google next.</p>"
        f'<a class="btn" href="/api/calendar-link/start?token={token}">'
        f"Continue to Google</a>")


@app.get("/api/calendar-link/start")
async def calendar_link_start(token: str = ""):
    """Spend the link and hand the visitor to Google."""
    body = action_links.verify(token, "sync_calendar")
    if body is None:
        return _link_page(
            "Link no longer valid", "This link is no longer valid",
            "<p>It may have expired, or already been used.</p>", "err")
    if not (GOOGLE_CALENDAR_ENABLED and google_cal.configured):
        return _link_page("Unavailable", "Calendar sync is not configured",
                          "<p>Ask an administrator to enable it.</p>", "err")

    state = secrets.token_urlsafe(24)
    _link_flows[state] = {"sub": body["sub"], "leave": body.get("leave", {}),
                          "name": body.get("name", "there")}
    logger.info("[OFFLINE >> Google] consent started from an emailed link for "
                "user(sub)=%s", body["sub"])
    return HTMLResponse(
        f'<meta http-equiv="refresh" content="0;url={google_cal.authorization_url(state)}">'
    )


async def _complete_link_flow(state: str, code: str) -> HTMLResponse:
    """Finish an emailed-link journey: store the grant, write the entry."""
    flow = _link_flows.pop(state)
    sub, leave = flow["sub"], flow["leave"]
    try:
        grant = await google_cal.exchange_code(code)
    except Exception as e:
        logger.error("[OFFLINE] Google token exchange failed: %s", e)
        return _link_page("Could not connect", "Could not connect to Google",
                          f"<p>{e}</p>", "err")

    # Keep the grant so a later approval needs no link at all.
    target = sessions.get_or_create(sub)
    target.google_grant = grant
    grant_store.save(sub, grant.refresh_token)
    if not target.user_name:
        target.user_name = flow.get("name")

    note = await _sync_leave_to_calendar({**leave, "employee_sub": sub}, target)
    if "could not" in note.lower():
        logger.warning("[OFFLINE] calendar write failed for %s: %s",
                       leave.get("request_id"), note)
        return _link_page("Not added", "Connected, but the entry was not added",
                          f"<p>{note.strip()}</p>", "err")

    logger.info("[OFFLINE] %s added to the calendar via the emailed link",
                leave.get("request_id"))
    return _link_page(
        "Added to your calendar", "Added to your calendar",
        f"<p>{leave.get('leave_type', 'Leave')} "
        f"{leave.get('start_date')} to {leave.get('end_date')} is now in your "
        f"Google Calendar.</p><p>You can close this window.</p>")


# ─── Pattern 6: Google Calendar connection ──────────────────────────────────

@app.get("/api/google/status")
async def google_status(session: UserSession = Depends(get_session)):
    """Whether this user has connected their Google Calendar."""
    return JSONResponse({
        "enabled": GOOGLE_CALENDAR_ENABLED and google_cal.configured,
        "connected": session.google_connected,
    })


@app.get("/api/google/url")
async def google_url(session: UserSession = Depends(get_session)):
    """Consent URL for the Google popup.

    Deliberately a separate consent from the Asgardeo one: Asgardeo has no
    authority over Google, so nothing the user approved there grants calendar
    access here.
    """
    if not (GOOGLE_CALENDAR_ENABLED and google_cal.configured):
        return JSONResponse(
            {"error": "disabled", "message": "Google Calendar is not configured."},
            status_code=404,
        )
    state = secrets.token_urlsafe(24)
    session.google_oauth_state = state
    logger.info("[GOOGLE] consent started for user(sub)=%s", session.user_sub)
    return JSONResponse({"auth_url": google_cal.authorization_url(state)})


@app.get("/api/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    """Google redirects the popup here. Browser redirect, so no JWT — the
    session is identified by the state we generated."""
    if error:
        logger.warning("[GOOGLE] consent refused: %s", error)
        return HTMLResponse(content=obo_flow.callback_html(success=False, error=error))
    if not code or not state:
        return HTMLResponse(
            content=obo_flow.callback_html(success=False, error="Missing code or state")
        )

    # A visitor arriving from an emailed link has no session, so the state
    # points at a pending flow instead. Checked first: these are one-shot.
    if state in _link_flows:
        return await _complete_link_flow(state, code)

    session = sessions.find_by_google_state(state)
    if not session:
        return HTMLResponse(
            content=obo_flow.callback_html(success=False, error="Invalid state parameter")
        )

    try:
        session.google_grant = await google_cal.exchange_code(code)
        session.google_oauth_state = None
        grant_store.save(session.user_sub, session.google_grant.refresh_token)
        logger.info("[GOOGLE] calendar connected for user(sub)=%s", session.user_sub)
        return HTMLResponse(content=obo_flow.callback_html(success=True))
    except Exception as e:
        logger.error("[GOOGLE] token exchange failed: %s", e)
        return HTMLResponse(content=obo_flow.callback_html(success=False, error=str(e)))


@app.post("/api/google/disconnect")
async def google_disconnect(session: UserSession = Depends(get_session)):
    """Drop the stored Google grant. Revoking at Google is separate and is
    done by the user at myaccount.google.com/permissions."""
    session.google_grant = None
    grant_store.forget(session.user_sub)
    logger.info("[GOOGLE] calendar disconnected for user(sub)=%s", session.user_sub)
    return JSONResponse({"success": True})


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
