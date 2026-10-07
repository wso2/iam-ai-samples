"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT Agent — Two Inbound Paths, Two Kinds of Authority

  A second, independent agent, reachable two ways:

  Pattern 4  /api/ask, /api/tickets — another AGENT calls, holding
             'it_agent_invoke'. The IT Agent then acts purely as itself. The
             human it is acting for arrives as unverified context, used for
             wording and audit only. Authority belongs to the two agents.

  Pattern 7  /api/desk/* — a PERSON calls, holding the desk access scope. The
             IT Agent obtains that person's delegated (OBO) token and calls the
             IT MCP server with it, so the resource server enforces THEIR
             scopes. This is the path a service-desk admin uses, including one
             whose identity lives in a federated partner organization.

  The two guards are mirror images: the agent path rejects humans, the human
  path rejects agents. Neither can be reached with the other's token, so the
  authority that applies is never ambiguous.
"""

import json
import os
import logging

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

import secrets

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

import uvicorn

import obo_flow
import token_exchange
from agent_auth import ITAgentAuth
from token_debug import dump_claims, dump_encoded
from jwt_validator import JWTValidator, TokenError
from session import DeskSession, DeskSessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IT_MCP_SERVER_URL = os.getenv("IT_MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

# The scope a *calling agent* must hold to invoke this agent at all.
INVOKE_SCOPE = os.getenv("IT_INVOKE_SCOPE", "it_agent_invoke")

# The scope a *person* must hold to use the service desk directly.
DESK_SCOPE = os.getenv("IT_DESK_SCOPE", "it_desk_access")

# Pattern 4+: carry the USER's authority across the second agent hop, instead
# of the IT Agent acting purely as itself. When on, the HR Agent forwards the
# user's delegated token and this agent exchanges it (RFC 8693) for one whose
# actor chain names both agents. Off by default: it needs token exchange
# enabled on the application, which not every tenant has.
A2A_DELEGATION = os.getenv("A2A_DELEGATION", "").lower() == "true"
# Fail closed rather than quietly acting with the agent's own (broader)
# authority when the exchange does not work.
A2A_REQUIRE_DELEGATION = os.getenv("A2A_REQUIRE_DELEGATION", "").lower() == "true"
# Scopes to request on the exchanged token. The subject token carries HR
# scopes, which are meaningless at the IT MCP server, so ask explicitly for the
# IT ones. Asgardeo still grants only what the USER's role permits — which is
# the point: an employee will not receive it_resolve_mcp here.
EXCHANGE_SCOPES = os.getenv(
    "EXCHANGE_SCOPES", "openid it_basic_mcp it_ticket_mcp it_resolve_mcp"
).split()

JWKS_URL = os.getenv("JWKS_URL")
AUTH_ISSUER = os.getenv("AUTH_ISSUER")
TOKEN_AUDIENCE = os.getenv("TOKEN_AUDIENCE")
# Browser tokens are issued to the SPA, agent tokens to the MCP client app, so
# the two paths carry different audiences. Both are accepted here and then told
# apart by `aut`, rather than being validated by two separate validators.
SPA_CLIENT_ID = os.getenv("SPA_CLIENT_ID", "")

if not all([JWKS_URL, AUTH_ISSUER, TOKEN_AUDIENCE]):
    raise ValueError(
        "Missing required environment variables: JWKS_URL, AUTH_ISSUER, or TOKEN_AUDIENCE"
    )

ACCEPTED_AUDIENCES = [a for a in (TOKEN_AUDIENCE, SPA_CLIENT_ID) if a]

# Claims that can carry "which identity domain did this person come from".
# Asgardeo names this differently depending on how the user authenticated
# (federated connection vs local vs organization), so check in order rather
# than pin one. Confirm against a real token from your tenant.
HOME_ORG_CLAIMS = ("idp", "identity_provider", "org_name", "org_handle", "user_org")


def _home_org(claims: dict) -> str:
    """Best-effort home organization / originating IdP for a person."""
    for claim in HOME_ORG_CLAIMS:
        value = claims.get(claim)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "primary"

logger.info("IT MCP server URL: %s", IT_MCP_SERVER_URL)

app = FastAPI(title="IT Agent")

# The service desk is called straight from the browser, so this process needs
# its own CORS policy — it is no longer only reachable from the HR Agent.
app.add_middleware(
    CORSMiddleware,
    allow_origins=obo_flow.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

it_agent_auth = ITAgentAuth()
sessions = DeskSessionStore()
exchanger = token_exchange.TokenExchangeClient(
    base_url=os.getenv("ASGARDEO_BASE_URL", ""),
    # Token exchange is usually a confidential-client grant. The App Native
    # Auth application is public, so this normally points at a separate one.
    client_id=os.getenv("EXCHANGE_CLIENT_ID") or os.getenv("ASGARDEO_CLIENT_ID", ""),
    client_secret=os.getenv("EXCHANGE_CLIENT_SECRET", ""),
    ssl_verify=os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true",
)
_validator = JWTValidator(
    jwks_url=JWKS_URL,
    issuer=AUTH_ISSUER,
    audience=ACCEPTED_AUDIENCES,
    ssl_verify=os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true",
)

SYSTEM_PROMPT = """You are the IT Service Desk assistant.

You answer IT questions using the tools available to you: IT policies, service
status, the software catalog, and support tickets.

Guidelines:
- Be concise and factual. Prefer the tools over your own knowledge.
- When you file a ticket, always report the ticket reference back.
- If a tool returns an "insufficient_scope" error, say plainly that the IT Agent
  is not permitted to perform that action. Do NOT ask the user to authorize
  anything — this agent acts on its own authority, not a user's.
- You have no access to HR data. If asked about leave, salary, or holidays, say
  that is outside IT's scope."""

# The desk prompt differs in one important way: here the agent carries the
# user's own authority, so a scope failure is a statement about THAT PERSON's
# permissions, not the agent's. Saying "the agent is not permitted" would
# misattribute the refusal.
DESK_SYSTEM_PROMPT = """You are the IT Service Desk assistant, helping a signed-in user.

You act with the permissions of the person you are talking to. You do not have
authority of your own here.

Guidelines:
- Be concise and factual. Prefer the tools over your own knowledge.
- When you file a ticket, always report the ticket reference back.
- If a tool returns an "insufficient_scope" error, that means THIS USER's role
  does not permit the action. Explain plainly what their role does allow. Do
  NOT suggest that you lack permission, and do NOT ask them to re-authorize.
- If a tool reports it only returned the user's own records, say so rather than
  implying it listed everything.
- You have no access to HR data. If asked about leave, salary, or holidays, say
  that is outside IT's scope."""


async def _authorize_caller(request: Request) -> tuple[dict | None, JSONResponse | None]:
    """Validate the calling agent's token.

    Returns (claims, None) when the caller is an agent holding INVOKE_SCOPE,
    otherwise (None, error_response).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JSONResponse(
            {"error": "unauthorized", "message": "Missing bearer token."},
            status_code=401,
        )

    token = auth_header[7:]
    try:
        claims = await _validator.validate_token(token)
    except TokenError as e:
        logger.warning("Caller token rejected (%s): %s", e.error_type, e.message)
        return None, JSONResponse(
            {"error": e.error_type, "message": e.message}, status_code=401
        )

    # Dumped BEFORE the guards below, so a token that is about to be refused is
    # still shown. Seeing what a denied caller actually presented is the point
    # of the denial — otherwise the refusal is just an assertion.
    dump_claims("[IT-AGENT] Caller Token (received on A2A path)", claims, token)

    scopes = claims.get("scope", "").split() if claims.get("scope") else []
    caller_sub = claims.get("sub")
    aut = claims.get("aut")

    # This endpoint is agent-to-agent only. A user token must not reach it,
    # even one that somehow carries the invoke scope.
    if aut != "AGENT":
        logger.warning(
            "[A2A DENIED] caller sub=%s is not an agent (aut=%s)", caller_sub, aut
        )
        return None, JSONResponse(
            {
                "error": "forbidden",
                "message": "This endpoint may only be called by an agent identity.",
            },
            status_code=403,
        )

    if INVOKE_SCOPE not in scopes:
        logger.warning(
            "[A2A DENIED] caller agent=%s lacks '%s' | present=%s",
            caller_sub, INVOKE_SCOPE, scopes,
        )
        return None, JSONResponse(
            {
                "error": "insufficient_scope",
                "required_scope": INVOKE_SCOPE,
                "message": f"Calling agent is not permitted to invoke the IT Agent "
                           f"(requires '{INVOKE_SCOPE}').",
            },
            status_code=403,
        )

    logger.info(
        "[A2A >> Caller Agent] agent(sub)=%s | scopes=%s",
        caller_sub, ", ".join(scopes) if scopes else "(none)",
    )
    return claims, None


async def _it_mcp_tools(access_token: str | None = None):
    """Return the IT MCP tools, reached with the given token.

    Passing None means "act as the agent" (Pattern 4). Passing a delegated
    token means the MCP server authorizes the *user* it was issued for
    (Pattern 7), which is the whole point of the service-desk path.
    """
    if access_token is None:
        token = await it_agent_auth.ensure_valid_token()
        access_token = token.access_token
        logger.info(
            "[IT-AGENT >> Agent Token] sub=(self) | scopes=%s",
            getattr(token, "scope", None) or "(none)",
        )

    client = MultiServerMCPClient({
        "it_server": {
            "transport": "streamable_http",
            "url": IT_MCP_SERVER_URL,
            "headers": {"Authorization": f"Bearer {access_token}"},
        },
    })
    return await client.get_tools()


@app.get("/api/tickets")
async def tickets(request: Request):
    """List IT tickets for a calling agent.

    Same authorization chain as /api/ask — the caller must be an agent holding
    the invoke scope, and this agent reads the tickets on its own token. No LLM
    involved: this is a straight read so the UI stays fast and deterministic.
    """
    claims, error = await _authorize_caller(request)
    if error:
        return error

    requested_for = request.query_params.get("requested_for", "")

    try:
        tools = await _it_mcp_tools()
        lister = next((t for t in tools if t.name == "list_support_tickets"), None)
        if lister is None:
            return JSONResponse(
                {"error": "tool_missing", "message": "list_support_tickets is unavailable."},
                status_code=502,
            )
        result = await lister.ainvoke({"requested_for": requested_for})
    except Exception as e:
        logger.exception("Ticket listing failed")
        return JSONResponse(
            {"error": "agent_error", "message": f"IT agent error: {e}"},
            status_code=500,
        )

    payload = _as_dict(result)
    if payload.get("error"):
        # Surface the MCP scope failure as-is; the caller renders it verbatim.
        logger.warning("Ticket listing denied: %s", payload.get("message"))
        return JSONResponse(payload, status_code=403)

    tickets = payload.get("tickets", [])
    logger.info("[IT-AGENT] returned %d ticket(s) to agent=%s", len(tickets), claims.get("sub"))
    return JSONResponse({"tickets": tickets})


def _as_dict(result) -> dict:
    """Normalize an MCP tool result (dict or JSON string) into a dict."""
    if isinstance(result, dict):
        return result
    try:
        parsed = json.loads(str(result))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


async def _delegated_mcp_token(user_token: str, requester_name: str):
    """Token to present to the IT MCP server for an A2A request.

    Returns (access_token_or_None, note). None means "use the agent's own
    token" — the Pattern 4 behaviour, where the IT Agent acts as itself.

    Exchanging the user's token here is what turns a forwarded *name* into
    forwarded *authority*: the result carries sub=user, act=IT Agent,
    act.act=HR Agent, so the resource server authorizes the person and the
    audit trail still names both agents.
    """
    if not A2A_DELEGATION:
        logger.info(
            "[EXCHANGE] skipped — A2A_DELEGATION is off; acting as the agent itself"
        )
        return None, ""
    if not user_token:
        # The calling agent sent no user token. Almost always this means the
        # user has not consented yet (so the HR Agent holds no OBO token to
        # forward), or that agent is running code from before this hop existed.
        logger.warning(
            "[EXCHANGE] no user token was forwarded by the calling agent — "
            "nothing to exchange, so this hop acts on the IT Agent's own "
            "authority. Has the user authorized, and is the calling agent "
            "running the current build?"
        )
        return None, ""
    if not exchanger.configured:
        logger.warning(
            "[EXCHANGE] A2A_DELEGATION is on but the exchange client is not "
            "configured (need ASGARDEO_BASE_URL + EXCHANGE_CLIENT_ID)"
        )
        return None, ""

    logger.info("[EXCHANGE] exchanging the user's token for a delegated one...")

    own = await it_agent_auth.ensure_valid_token()
    try:
        result = await exchanger.exchange(
            subject_token=user_token,
            actor_token=own.access_token,
            scopes=EXCHANGE_SCOPES,
        )
    except token_exchange.TokenExchangeError as e:
        # A failure here is a real downgrade in authority, never a detail to
        # swallow: without the exchange this agent would act on its own,
        # broader permissions instead of the user's.
        logger.error("[EXCHANGE] failed for requester=%s: %s", requester_name, e)
        if A2A_REQUIRE_DELEGATION:
            raise
        logger.warning(
            "[EXCHANGE] falling back to the IT Agent's own authority — the user's "
            "permissions are NOT being applied on this hop"
        )
        return None, ""

    token = result["access_token"]
    dump_encoded("[IT-AGENT] Exchanged Token (user authority, both agents)", token)
    logger.info(
        "[EXCHANGE >> Delegated Token] acting with %s's authority, carried by "
        "this agent on behalf of the calling agent", requester_name,
    )
    return token, " You are acting with this user's own permissions."


@app.post("/api/ask")
async def ask(request: Request):
    """Answer an IT question on behalf of a calling agent.

    Body: {"query": "...", "requester": {"sub": "...", "name": "..."}}
    The `requester` block is context for wording and audit — never authority.
    """
    claims, error = await _authorize_caller(request)
    if error:
        return error

    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse(
            {"error": "invalid_request", "message": "query cannot be empty."},
            status_code=400,
        )

    requester = body.get("requester") or {}
    requester_name = requester.get("name") or "an employee"
    caller_agent = claims.get("sub")

    logger.info(
        "[IT-AGENT] query from agent=%s for requester=%s: %r",
        caller_agent, requester_name, query[:120],
    )

    try:
        # The user's delegated token, forwarded by the calling agent. It is a
        # subject_token for the exchange below, never a bearer credential for
        # this endpoint — the caller was already authorized on its own token.
        delegated, authority_note = await _delegated_mcp_token(
            body.get("user_token") or "", requester_name
        )
    except token_exchange.TokenExchangeError as e:
        return JSONResponse(
            {
                "error": "delegation_failed",
                "message": f"Could not act with the user's authority: {e}",
            },
            status_code=502,
        )

    try:
        tools = await _it_mcp_tools(delegated)

        llm = ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0.3)
        agent = create_agent(llm, tools)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"This request comes from {requester_name} via the HR Agent."
                    f"{authority_note} Use that name for wording and for the "
                    f"`requested_for` field when filing a ticket."
                    f"\n\nQuestion: {query}"
                ),
            },
        ]
        response = await agent.ainvoke({"messages": messages})

    except Exception as e:
        logger.exception("IT agent invocation failed")
        detail = str(e)
        sub_excs = getattr(e, "exceptions", None)
        if sub_excs:
            for i, sub in enumerate(sub_excs):
                logger.error("  sub-exception %d: %r", i, sub, exc_info=sub)
            detail = "; ".join(repr(s) for s in sub_excs)
        return JSONResponse(
            {"error": "agent_error", "message": f"IT agent error: {detail}"},
            status_code=500,
        )

    answer = _extract_text(response["messages"][-1].content)
    tools_used = [
        c["name"]
        for m in response.get("messages", [])
        for c in (getattr(m, "tool_calls", None) or [])
    ]
    logger.info("[IT-AGENT] answered using tools=%s", tools_used or "(none)")

    return JSONResponse({"answer": answer, "tools_used": tools_used})


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


# ─── Pattern 7: the human-facing service desk ───────────────────────────────

async def _authorize_user(request: Request):
    """Validate a PERSON's token for the service-desk path.

    The mirror image of `_authorize_caller`: that one demands `aut == AGENT`,
    this one refuses it. An agent token must not reach the desk even if it
    somehow carried the desk scope, because everything downstream assumes a
    human whose own permissions decide the outcome.

    Returns (session, None) or (None, error_response).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JSONResponse(
            {"error": "unauthorized", "message": "Missing bearer token."},
            status_code=401,
        )

    desk_token = auth_header[7:]
    try:
        claims = await _validator.validate_token(desk_token)
    except TokenError as e:
        logger.warning("Desk token rejected (%s): %s", e.error_type, e.message)
        return None, JSONResponse(
            {"error": e.error_type, "message": e.message}, status_code=401
        )

    # Before the guards, for the same reason as the A2A path.
    dump_claims("[IT-AGENT] User Token (received on desk path)", claims, desk_token)

    if claims.get("aut") == "AGENT":
        logger.warning("[DESK DENIED] agent token presented on the human path")
        return None, JSONResponse(
            {
                "error": "forbidden",
                "message": "The service desk is for people. An agent should use "
                           "/api/ask, where it is authorized as an agent.",
            },
            status_code=403,
        )

    scopes = claims.get("scope", "").split() if claims.get("scope") else []
    if DESK_SCOPE not in scopes:
        logger.warning(
            "[DESK DENIED] user=%s lacks '%s' | present=%s",
            claims.get("sub"), DESK_SCOPE, scopes,
        )
        return None, JSONResponse(
            {
                "error": "insufficient_scope",
                "required_scope": DESK_SCOPE,
                "message": f"You are not permitted to use the IT service desk "
                           f"(requires '{DESK_SCOPE}').",
            },
            status_code=403,
        )

    sub = claims.get("sub")
    if not sub:
        return None, JSONResponse(
            {"error": "invalid_token", "message": "Token missing sub claim."},
            status_code=401,
        )

    session = sessions.get_or_create(sub)
    session.user_scopes = scopes
    session.home_org = _home_org(claims)
    first = claims.get("given_name") or ""
    last = claims.get("family_name") or claims.get("last_name") or ""
    session.user_name = (
        f"{first} {last}".strip()
        or claims.get("name")
        or claims.get("preferred_username")
    )

    logger.info(
        "[DESK >> User Token] user(sub)=%s | name=%s | home_org=%s | scopes=%s",
        sub, session.user_name or "?", session.home_org,
        ", ".join(scopes) if scopes else "(none)",
    )
    return session, None


@app.get("/api/desk/status")
async def desk_status(request: Request):
    """Whether this person may use the desk, and whether they have consented.

    The client uses `home_org` to show where the user was authenticated. That
    is the only place federation becomes visible: the token itself looks the
    same whichever provider vouched for the person.
    """
    session, error = await _authorize_user(request)
    if error:
        return error
    return JSONResponse({
        "enabled": True,
        "authorized": session.has_valid_obo,
        "user_name": session.user_name,
        "home_org": session.home_org,
        "from_partner_org": session.is_from_partner_org,
    })


@app.get("/api/desk/obo/url")
async def desk_obo_url(request: Request):
    """Consent URL so the agent may act with this person's permissions."""
    session, error = await _authorize_user(request)
    if error:
        return error

    auth_url, state, verifier = await obo_flow.get_authorization_url(it_agent_auth)
    session.obo_pkce_state = state
    session.obo_code_verifier = verifier
    return JSONResponse({"auth_url": auth_url})


@app.get("/api/desk/obo/callback")
async def desk_obo_callback(code: str = None, state: str = None, error: str = None):
    """Consent redirect lands here. A browser redirect carries no bearer token,
    so the PKCE state is what identifies whose consent this is."""
    if error:
        logger.warning("[IT-OBO] consent refused: %s", error)
        return HTMLResponse(obo_flow.callback_html(success=False, error=error))
    if not code or not state:
        return HTMLResponse(
            obo_flow.callback_html(success=False, error="Missing code or state")
        )

    session = sessions.find_by_obo_state(state)
    if not session:
        return HTMLResponse(
            obo_flow.callback_html(success=False, error="Invalid state parameter")
        )

    try:
        token, scopes, expires_at = await obo_flow.exchange_code(
            it_agent_auth, code, session.obo_code_verifier
        )
    except Exception as e:
        logger.error("[IT-OBO] token exchange failed: %s", e)
        return HTMLResponse(obo_flow.callback_html(success=False, error=str(e)))

    session.obo_token = token
    session.obo_scopes = scopes
    session.obo_expires_at = expires_at
    session.obo_pkce_state = None
    session.obo_code_verifier = None
    dump_encoded("[IT-AGENT] OBO Token just issued", token.access_token)
    logger.info(
        "[IT-OBO] delegated authority granted by user(sub)=%s from home_org=%s | scopes=%s",
        session.user_sub, session.home_org, scopes or "(none)",
    )
    return HTMLResponse(obo_flow.callback_html(success=True))


@app.post("/api/desk/chat")
async def desk_chat(request: Request):
    """Answer a person's IT question using THAT PERSON's permissions."""
    session, error = await _authorize_user(request)
    if error:
        return error

    body = await request.json()
    query = (body.get("message") or "").strip()
    if not query:
        return JSONResponse(
            {"type": "error", "message": "Message cannot be empty."}, status_code=400
        )

    # No delegated token yet (or it aged out) — the agent has nothing to act
    # with. It deliberately does NOT fall back to its own token: that would
    # silently answer with the agent's permissions instead of the user's.
    if not session.has_valid_obo:
        session.pending_message = query
        return JSONResponse({
            "type": "obo_required",
            "message": (
                "Your authorization has expired. Please re-authorize to continue."
                if session.obo_expired else
                "I need your authorization before I can act with your permissions."
            ),
        })

    try:
        tools = await _it_mcp_tools(session.obo_token.access_token)
        logger.info(
            "[DESK >> OBO Token] acting as user(sub)=%s | home_org=%s | scopes=%s",
            session.user_sub, session.home_org,
            ", ".join(session.obo_scopes) or "(none)",
        )

        llm = ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0.3)
        agent = create_agent(llm, tools)

        messages = [{"role": "system", "content": DESK_SYSTEM_PROMPT}]
        messages.extend(session.chat_history[-20:])
        messages.append({
            "role": "user",
            "content": (
                f"[Signed in as {session.user_name or 'a user'} "
                f"from {session.home_org}]\n\n{query}"
            ),
        })
        response = await agent.ainvoke({"messages": messages})

    except Exception as e:
        logger.exception("Desk invocation failed")
        detail = str(e)
        sub_excs = getattr(e, "exceptions", None)
        if sub_excs:
            for i, sub in enumerate(sub_excs):
                logger.error("  sub-exception %d: %r", i, sub, exc_info=sub)
            detail = "; ".join(repr(x) for x in sub_excs)
        return JSONResponse(
            {"type": "error", "message": f"IT agent error: {detail}"}, status_code=500
        )

    answer = _extract_text(response["messages"][-1].content)

    # A token that expired mid-conversation needs fresh consent. A missing
    # scope does NOT: that is this user's role, and re-consenting cannot add
    # a permission Asgardeo already declined to grant.
    for message in response.get("messages", []):
        if getattr(message, "type", None) == "tool" and "token_expired" in str(message.content):
            session.pending_message = query
            return JSONResponse({
                "type": "obo_required",
                "message": "Your authorization has expired. Please re-authorize to continue.",
            })

    tools_used = [
        c["name"]
        for m in response.get("messages", [])
        for c in (getattr(m, "tool_calls", None) or [])
    ]
    logger.info(
        "[DESK] answered user(sub)=%s using tools=%s",
        session.user_sub, tools_used or "(none)",
    )

    session.chat_history.append({"role": "user", "content": query})
    session.chat_history.append({"role": "assistant", "content": answer})
    del session.chat_history[:-40]

    return JSONResponse({
        "type": "response",
        "message": answer,
        "tools_used": tools_used,
        "home_org": session.home_org,
    })


@app.on_event("startup")
async def _log_delegation_config():
    """State the delegation posture at startup.

    These flags are read once at import, so a stale process is the usual
    reason a config change appears to have no effect. Printing them removes
    the guesswork.
    """
    if A2A_DELEGATION:
        logger.info(
            "[EXCHANGE] A2A delegation ON | exchange_client=%s | require=%s | scopes=%s",
            (os.getenv("EXCHANGE_CLIENT_ID") or os.getenv("ASGARDEO_CLIENT_ID", ""))[:12] + "…",
            A2A_REQUIRE_DELEGATION, " ".join(EXCHANGE_SCOPES),
        )
    else:
        logger.info("[EXCHANGE] A2A delegation OFF — set A2A_DELEGATION=true to enable")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "it-agent"})


if __name__ == "__main__":
    host = os.getenv("IT_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("IT_AGENT_PORT", os.getenv("PORT", "5002")))
    logger.info("IT agent ready on :%d", port)
    # Per-request access lines bury the token lines these logs exist to show.
    uvicorn.run(
        app, host=host, port=port,
        access_log=os.getenv("ACCESS_LOG", "").lower() == "true",
    )
