# A2A Reference Implementation — Complete Codebase Documentation

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Project Structure](#3-project-structure)
4. [Configuration](#4-configuration)
5. [Authentication & Token Flows](#5-authentication--token-flows)
   - [5.1 PKCE Utilities](#51-pkce-utilities)
   - [5.2 User Login (Authorization Code + PKCE)](#52-user-login-authorization-code--pkce)
   - [5.3 Actor Token — 3-Step Flow](#53-actor-token--3-step-flow)
   - [5.4 Token Exchange (RFC 8693)](#54-token-exchange-rfc-8693)
   - [5.5 Token Broker](#55-token-broker)
   - [5.6 JWT Validation](#56-jwt-validation)
6. [A2A Protocol Implementation](#6-a2a-protocol-implementation)
   - [6.1 Agent Card (Discovery)](#61-agent-card-discovery)
   - [6.2 JSON-RPC Communication](#62-json-rpc-communication)
   - [6.3 Executor Pattern](#63-executor-pattern)
7. [Agents](#7-agents)
   - [7.1 Orchestrator Agent](#71-orchestrator-agent)
   - [7.2 HR Agent](#72-hr-agent)
   - [7.3 IT Agent](#73-it-agent)
   - [7.4 Approval Agent](#74-approval-agent)
   - [7.5 Booking Agent](#75-booking-agent)
8. [LLM-Based Task Decomposition](#8-llm-based-task-decomposition)
9. [End-to-End Workflow Scenarios](#9-end-to-end-workflow-scenarios)
   - [9.1 Single Agent — Create Employee](#91-single-agent--create-employee)
   - [9.2 Multi-Agent — Onboard + Provision VPN](#92-multi-agent--onboard--provision-vpn)
   - [9.3 Approval → HR Privilege Grant](#93-approval--hr-privilege-grant)
10. [Visualizer](#10-visualizer)
11. [Running the System](#11-running-the-system)

---

## 1. Overview

This is a **reference implementation** of the **Agent-to-Agent (A2A) protocol** integrated with **WSO2 Identity Server (Asgardeo)** for secure, delegated authentication between AI agents.

The system demonstrates:

- **A2A Protocol**: Google's open standard for agent-to-agent communication via JSON-RPC, Agent Cards, and task-based messaging.
- **Asgardeo AI Agent Authentication**: WSO2's 3-step actor token flow for AI agents, followed by RFC 8693 Token Exchange for delegation.
- **LLM-Powered Orchestration**: OpenAI GPT-4o decomposes natural language user requests into ordered tasks across multiple specialized agents.
- **Scope-Based Access Control**: Each agent validates that incoming tokens contain the required OAuth 2.0 scopes before processing requests.

### Key Technologies

| Component | Technology |
|---|---|
| Identity Provider | WSO2 Identity Server (Asgardeo) |
| OAuth 2.0 Flows | Authorization Code + PKCE, Token Exchange (RFC 8693) |
| A2A SDK | `a2a-sdk` (official Google A2A Python SDK) |
| Web Framework | Starlette (via A2A SDK) + Uvicorn |
| LLM | OpenAI GPT-4o |
| HTTP Client | `httpx` (async) |
| JWT | `python-jose` |
| Config | `pydantic-settings` + YAML |

---

## 2. Architecture

```
                          ┌─────────────────────────┐
                          │       User (Browser)     │
                          └──────────┬──────────────┘
                                     │ 1. GET /auth/login
                                     ▼
                          ┌─────────────────────────┐
                          │  WSO2 Identity Server    │
                          │  (Asgardeo)              │
                          │                          │
                          │  • /oauth2/authorize     │
                          │  • /oauth2/authn         │
                          │  • /oauth2/token         │
                          │  • /oauth2/jwks          │
                          └──────────┬──────────────┘
                                     │ 2. Auth Code + Actor Token
                                     │    → Delegated Token
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR AGENT (Port 8000)                 │
│                                                                  │
│  ┌────────────┐   ┌──────────────┐   ┌────────────────────────┐ │
│  │ TokenBroker│   │ OrchestratorAgent │  │ A2A Server (Starlette)│ │
│  │            │   │                   │  │                      │ │
│  │ • Sessions │   │ • LLM Decompose   │  │ • Agent Card         │ │
│  │ • Exchange │   │ • Agent Discovery  │  │ • JSON-RPC endpoint  │ │
│  │ • Audit    │   │ • call_agent()     │  │ • /auth/login        │ │
│  └────────────┘   └──────────────┘   │  • /api/demo           │ │
│                                       └────────────────────────┘ │
└────────────────────────┬─────────────────────────────────────────┘
                         │  Token Exchange (RFC 8693) per agent
                         │  + A2A JSON-RPC message/send
                         ▼
    ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────┐
    │ HR Agent │  │ IT Agent │  │ Approval     │  │ Booking      │
    │ (8001)   │  │ (8002)   │  │ Agent (8003) │  │ Agent (8004) │
    │          │  │          │  │              │  │              │
    │ • hr:r/w │  │ • it:r/w │  │ • approval:  │  │ • booking:   │
    │ • Create │  │ • VPN    │  │   r/w        │  │   r/w        │
    │   Employee│ │ • GitHub │  │ • Approve    │  │ • Schedule   │
    │ • Grant  │  │ • AWS    │  │ • Route      │  │ • Deliveries │
    │   Privs  │  │          │  │              │  │              │
    └──────────┘  └──────────┘  └──────────────┘  └──────────────┘
```

### Communication Pattern

1. **User → Orchestrator**: HTTP request (browser login or `/api/demo`)
2. **Orchestrator → WSO2 IS**: OAuth flows (authorize, authn, token, exchange)
3. **Orchestrator → Worker Agents**: A2A JSON-RPC over HTTP with Bearer tokens
4. **Worker Agents → Orchestrator**: JSON-RPC response with task result

Worker agents **never** call each other directly. All coordination flows through the Orchestrator.

---

## 3. Project Structure

```
├── config.yaml                  # Central configuration (agents, URLs, scopes)
├── .env                         # Secrets (client IDs, agent creds, API keys)
├── requirements.txt             # Python dependencies
│
├── agents/                      # A2A Agent implementations
│   ├── orchestrator/            # Central orchestrator (port 8000)
│   │   ├── __main__.py          # HTTP server, routes, middleware
│   │   ├── agent.py             # Core logic: discovery, LLM, call_agent
│   │   └── executor.py          # A2A SDK executor pattern
│   ├── hr_agent/                # HR worker (port 8001)
│   │   ├── __main__.py          # HTTP server
│   │   ├── agent.py             # HR logic: create employee, grant privileges
│   │   └── executor.py          # A2A SDK executor
│   ├── it_agent/                # IT worker (port 8002)
│   ├── approval_agent/          # Approval worker (port 8003)
│   └── booking_agent/           # Booking worker (port 8004)
│
├── src/                         # Shared infrastructure
│   ├── config.py                # Pydantic Settings (loads .env)
│   ├── config_loader.py         # YAML config loader with ${VAR} resolution
│   ├── log_broadcaster.py       # Sends logs to visualizer WebSocket
│   ├── auth/                    # Authentication layer
│   │   ├── asgardeo.py          # WSO2 IS client (3-step flow, token exchange)
│   │   ├── token_broker.py      # Centralized token management
│   │   ├── jwt_validator.py     # JWT validation against JWKS
│   │   └── utils.py             # PKCE generation
│   └── a2a/                     # Legacy A2A types (predates SDK adoption)
│       ├── client.py            # Manual A2A client (discovery + send_task)
│       ├── server.py            # Manual A2A server (JSON-RPC handler)
│       ├── types.py             # A2A data types
│       └── orchestrator.py      # Legacy LangGraph executor
│
├── visualizer/                  # Browser-based token flow visualizer
│   ├── index.html               # Frontend UI
│   ├── app.js                   # WebSocket client + animations
│   ├── styles.css               # Styling
│   └── log_server.py            # WebSocket server for log streaming
│
└── test_agent_app.py            # Diagnostic: tests agent auth against WSO2 IS
```

---

## 4. Configuration

### 4.1 Environment Variables (`.env`)

```dotenv
# WSO2 Identity Server
ASGARDEO_ORG_NAME=carbon.super
ASGARDEO_BASE_URL=https://localhost:9443/t/carbon.super

# Orchestrator Application (registered in WSO2 IS)
ORCHESTRATOR_CLIENT_ID=44V0jxLPDNW7aenxFIUsV8JZdhca
ORCHESTRATOR_CLIENT_SECRET=<secret>

# Orchestrator Agent (AI Agent registered in WSO2 IS)
ORCHESTRATOR_AGENT_ID=orchestrator-agent
ORCHESTRATOR_AGENT_SECRET=<secret>

# Token Exchanger Application (for RFC 8693 exchanges)
TOKEN_EXCHANGER_CLIENT_ID=TUu_bUEpzBBynKHCz4qQ399oIt0a
TOKEN_EXCHANGER_CLIENT_SECRET=<secret>

# Worker Agent Credentials (AI Agents in WSO2 IS)
HR_AGENT_ID=hr-agent
HR_AGENT_SECRET=<secret>
IT_AGENT_ID=it-agent
IT_AGENT_SECRET=<secret>
# ... etc.

# OpenAI
OPENAI_API_KEY=sk-...
```

**`src/config.py`** — Loads `.env` into a typed `Settings` object via `pydantic-settings`:

```python
class Settings(BaseSettings):
    asgardeo_org_name: str
    orchestrator_client_id: str
    orchestrator_client_secret: str
    orchestrator_agent_id: str
    orchestrator_agent_secret: str
    token_exchanger_client_id: Optional[str] = None
    token_exchanger_client_secret: Optional[str] = None
    openai_api_key: str
    # ... auto-constructs asgardeo URLs from org_name
```

### 4.2 YAML Configuration (`config.yaml`)

Defines agent metadata, URLs, required scopes, and discovery endpoints. Uses `${VAR}` placeholders resolved against environment variables:

```yaml
agents:
  hr_agent:
    name: "HR Agent"
    url: "http://localhost:8001"
    required_scopes: ["hr:read", "hr:write"]
    agent_id: "${HR_AGENT_ID}"
    agent_secret: "${HR_AGENT_SECRET}"

orchestrator:
  discovery:
    agent_urls:
      - "http://localhost:8001"
      - "http://localhost:8002"
      - "http://localhost:8003"
      - "http://localhost:8004"
  llm:
    model: "gpt-4o"
```

**`src/config_loader.py`** — Resolves `${VAR}` placeholders recursively:

```python
def resolve_env_vars(obj):
    """Recursively replace ${VAR_NAME} with os.getenv(VAR_NAME)."""
    if isinstance(obj, str):
        return re.sub(r'\$\{([^}]+)\}', lambda m: os.getenv(m.group(1), ""), obj)
    elif isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    # ...
```

---

## 5. Authentication & Token Flows

All authentication happens through WSO2 Identity Server. The system uses **three distinct OAuth 2.0 flows** that chain together.

### 5.1 PKCE Utilities

**File**: `src/auth/utils.py`

Generates PKCE (Proof Key for Code Exchange) challenge pairs used in all authorization code flows:

```python
def generate_pkce() -> PKCEChallenge:
    verifier = secrets.token_urlsafe(64)                          # Random string
    digest = hashlib.sha256(verifier.encode('ascii')).digest()    # SHA-256 hash
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()  # Base64 URL-safe
    return PKCEChallenge(verifier=verifier, challenge=challenge, method="S256")
```

The `verifier` is stored server-side. The `challenge` (hash of verifier) is sent in the authorize request. When exchanging the code, the `verifier` is sent so the server can verify it matches the original `challenge`.

---

### 5.2 User Login (Authorization Code + PKCE)

**Purpose**: Get a **delegated access token** for the user, bound to the orchestrator agent.

**Files**: `agents/orchestrator/__main__.py` (routes), `src/auth/token_broker.py` (session), `src/auth/asgardeo.py` (HTTP calls)

#### Flow Diagram

```
User Browser                Orchestrator                 WSO2 Identity Server
    │                           │                               │
    │  GET /auth/login          │                               │
    │ ─────────────────────────>│                               │
    │                           │                               │
    │                           │  (create session, PKCE pair)  │
    │                           │                               │
    │  302 Redirect             │                               │
    │ <─────────────────────────│                               │
    │                           │                               │
    │  GET /oauth2/authorize?client_id=...&scope=...&requested_actor=orchestrator-agent
    │ ─────────────────────────────────────────────────────────>│
    │                           │                               │
    │  (User logs in, consents) │                               │
    │                           │                               │
    │  302 Redirect → /callback?code=AUTH_CODE&state=SESSION_ID │
    │ <─────────────────────────────────────────────────────────│
    │                           │                               │
    │  GET /callback?code=...   │                               │
    │ ─────────────────────────>│                               │
    │                           │                               │
    │                           │  POST /oauth2/token           │
    │                           │  grant_type=authorization_code│
    │                           │  code=AUTH_CODE                │
    │                           │  code_verifier=PKCE_VERIFIER  │
    │                           │  actor_token=ORCH_ACTOR_TOKEN │
    │                           │ ─────────────────────────────>│
    │                           │                               │
    │                           │  { access_token: DELEGATED }  │
    │                           │ <─────────────────────────────│
    │                           │                               │
    │  { session_id, success }  │                               │
    │ <─────────────────────────│                               │
```

#### Code Walkthrough

**Step 1 — `/auth/login` route** creates a session and redirects:

```python
# agents/orchestrator/__main__.py
async def start_login(request: Request):
    broker = get_token_broker()
    session = broker.create_session()  # Generates session_id + PKCE pair

    scopes = ["hr:read", "hr:write", "it:read", "it:write",
              "approval:read", "approval:write", "booking:read", "booking:write"]

    auth_url = broker.get_authorization_url(session_id=session.session_id, scopes=scopes)
    return RedirectResponse(url=auth_url)
```

**Step 2 — Build the authorize URL** with `requested_actor`:

```python
# src/auth/asgardeo.py
def build_user_authorize_url(self, scopes, state, pkce):
    params = {
        "response_type": "code",
        "client_id": self.settings.orchestrator_client_id,
        "scope": " ".join(scopes + ["openid", "profile"]),
        "redirect_uri": self.settings.app_callback_url,
        "state": state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "requested_actor": self.settings.orchestrator_agent_id  # Binds agent to token
    }
    return f"{self.settings.asgardeo_authorize_url}?{urlencode(params)}"
```

> **Key parameter**: `requested_actor` tells WSO2 IS to bind the resulting delegated token to the orchestrator agent. The token will contain an `act` (actor) claim.

**Step 3 — `/callback` route** exchanges code for delegated token:

```python
# src/auth/token_broker.py
async def handle_callback(self, code: str, state: str) -> UserSession:
    session = self._sessions.get(state)

    # Ensure we have the orchestrator's actor token first
    if not self._actor_token:
        await self.initialize()   # → 3-step flow (Section 5.3)

    # Exchange code + actor_token → delegated token
    token_response = await self.asgardeo.exchange_code_for_delegated_token(
        code, session.pkce.verifier, self._actor_token.token
    )

    session.delegated_token = token_response.access_token
    return session
```

The resulting **delegated token** contains:
- `sub`: The user's subject ID
- `scope`: All requested scopes (hr:read, hr:write, it:read, etc.)
- `act.sub`: The orchestrator agent's ID (proves the agent is acting on behalf of the user)

---

### 5.3 Actor Token — 3-Step Flow

**Purpose**: Get an **actor token** that proves an AI agent's identity. This token is used as the `actor_token` parameter in the delegated token exchange and in RFC 8693 exchanges.

**File**: `src/auth/asgardeo.py` → `_fetch_agent_actor_token()`

#### Flow Diagram

```
Orchestrator                                          WSO2 Identity Server
    │                                                        │
    │  STEP 1: POST /oauth2/authorize                        │
    │  ┌─────────────────────────────────────────┐           │
    │  │ response_type: code                      │           │
    │  │ client_id: <app_client_id>               │           │
    │  │ scope: openid                            │           │
    │  │ redirect_uri: http://localhost:8000/callback │       │
    │  │ code_challenge: <PKCE_CHALLENGE>          │           │
    │  │ code_challenge_method: S256               │           │
    │  │ response_mode: direct                     │  ← Key!  │
    │  │ Authorization: Basic <app_client_id:secret> │        │
    │  └─────────────────────────────────────────┘           │
    │ ──────────────────────────────────────────────────────>│
    │                                                        │
    │  { flowId: "abc-123-..." }                             │
    │ <──────────────────────────────────────────────────────│
    │                                                        │
    │  STEP 2: POST /oauth2/authn                            │
    │  ┌─────────────────────────────────────────┐           │
    │  │ flowId: "abc-123-..."                    │           │
    │  │ selectedAuthenticator:                    │           │
    │  │   authenticatorId: "QmFzaWN..."          │           │
    │  │   params:                                 │           │
    │  │     username: "orchestrator-agent"        │   Agent   │
    │  │     password: "<agent_secret>"            │   creds   │
    │  └─────────────────────────────────────────┘           │
    │ ──────────────────────────────────────────────────────>│
    │                                                        │
    │  { code: "AUTH_CODE_XYZ" }                             │
    │ <──────────────────────────────────────────────────────│
    │                                                        │
    │  STEP 3: POST /oauth2/token                            │
    │  ┌─────────────────────────────────────────┐           │
    │  │ grant_type: authorization_code           │           │
    │  │ client_id: <app_client_id>               │  In body  │
    │  │ client_secret: <app_client_secret>       │  (not     │
    │  │ code: AUTH_CODE_XYZ                      │   Basic   │
    │  │ redirect_uri: ...                        │   Auth)   │
    │  │ code_verifier: <PKCE_VERIFIER>           │           │
    │  └─────────────────────────────────────────┘           │
    │ ──────────────────────────────────────────────────────>│
    │                                                        │
    │  { access_token: "ACTOR_TOKEN_..." }                   │
    │ <──────────────────────────────────────────────────────│
```

#### Which Credentials for Which Agent?

| Agent | Step 1 & 3 App Credentials | Step 2 Agent Credentials |
|---|---|---|
| Orchestrator Agent | **Orchestrator App** (`ORCHESTRATOR_CLIENT_ID/SECRET`) | `ORCHESTRATOR_AGENT_ID/SECRET` |
| HR Agent | **Token Exchanger App** (`TOKEN_EXCHANGER_CLIENT_ID/SECRET`) | `HR_AGENT_ID/SECRET` |
| IT Agent | **Token Exchanger App** | `IT_AGENT_ID/SECRET` |
| Approval Agent | **Token Exchanger App** | `APPROVAL_AGENT_ID/SECRET` |
| Booking Agent | **Token Exchanger App** | `BOOKING_AGENT_ID/SECRET` |

> The orchestrator uses its own app credentials because it is the primary application. Worker agents use the Token Exchanger application credentials because they participate in the exchange flow, not as standalone apps.

#### Code

```python
# src/auth/asgardeo.py

async def _fetch_agent_actor_token(self, client_id, client_secret, agent_id):
    pkce = generate_pkce()

    async with self._create_fresh_client() as fresh_client:
        # Step 1: POST /oauth2/authorize with response_mode=direct → flowId
        flow_id = await self._initiate_auth_flow(fresh_client, client_id, client_secret, pkce)

        # Step 2: POST /oauth2/authn with flowId + agent username/password → auth code
        auth_code = await self._authenticate_agent(fresh_client, flow_id, agent_id)

        # Step 3: POST /oauth2/token with code + PKCE verifier → actor token
        actor_token = await self._exchange_code_for_actor_token(
            fresh_client, client_id, client_secret, auth_code, pkce.verifier, agent_id
        )
        return actor_token
```

**Step 1 — `_initiate_auth_flow`**: The `response_mode=direct` parameter is critical — it tells WSO2 IS to return the response as JSON (with a `flowId`) instead of a browser redirect:

```python
async def _initiate_auth_flow(self, client, client_id, client_secret, pkce):
    data = {
        "response_type": "code",
        "client_id": client_id,
        "scope": "openid",
        "redirect_uri": self.settings.app_callback_url,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "response_mode": "direct"              # ← Machine-readable JSON response
    }

    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = await client.post(
        self.settings.asgardeo_authorize_url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_auth}"
        }
    )
    result = response.json()
    return result.get("flowId")   # e.g., "7b2e4f1a-..."
```

**Step 2 — `_authenticate_agent`**: Authenticates using the agent's username/password through the BasicAuthenticator. The `authenticatorId` is the Base64 encoding of `"BasicAuthenticator:LOCAL"`:

```python
async def _authenticate_agent(self, client, flow_id, agent_id):
    payload = {
        "flowId": flow_id,
        "selectedAuthenticator": {
            "authenticatorId": "QmFzaWNBdXRoZW50aWNhdG9yOkxPQ0FM",
            "params": {
                "username": agent_id,           # e.g., "hr-agent"
                "password": agent_secret         # From config.yaml
            }
        }
    }
    response = await client.post(authn_url, json=payload)
    result = response.json()
    return result.get("authData", {}).get("code")   # Authorization code
```

**Step 3 — `_exchange_code_for_actor_token`**: Sends `client_id` and `client_secret` in the **request body** (not Basic Auth header):

```python
async def _exchange_code_for_actor_token(self, client, client_id, client_secret, code, verifier, agent_id):
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,              # In body
        "client_secret": client_secret,      # In body (NOT Basic Auth header)
        "code": code,
        "redirect_uri": self.settings.app_callback_url,
        "code_verifier": verifier,
    }
    response = await client.post(self.settings.asgardeo_token_url, data=data)
    result = response.json()
    return ActorToken(token=result["access_token"], actor_id=agent_id, ...)
```

---

### 5.4 Token Exchange (RFC 8693)

**Purpose**: Exchange the user's delegated token (broad scopes) for a **downscoped token** specific to one worker agent. The exchanged token carries both the user's identity (`sub`) and the target agent's identity (`act.sub`).

**File**: `src/auth/asgardeo.py` → `perform_token_exchange()`

#### Flow

```
Orchestrator                                          WSO2 Identity Server
    │                                                        │
    │  POST /oauth2/token                                    │
    │  ┌──────────────────────────────────────────┐          │
    │  │ grant_type: urn:ietf:params:oauth:        │          │
    │  │            grant-type:token-exchange       │          │
    │  │ subject_token: <USER_DELEGATED_TOKEN>     │          │
    │  │ subject_token_type: ...access_token       │          │
    │  │ actor_token: <AGENT_ACTOR_TOKEN>          │          │
    │  │ actor_token_type: ...access_token         │          │
    │  │ scope: hr:read hr:write                   │          │
    │  │ Authorization: Basic <token_exchanger>    │          │
    │  └──────────────────────────────────────────┘          │
    │ ─────────────────────────────────────────────────────> │
    │                                                        │
    │  { access_token: <EXCHANGED_TOKEN> }                   │
    │ <───────────────────────────────────────────────────── │
```

The exchanged token is scoped down to only the target agent's required scopes (e.g., `hr:read hr:write`).

#### Code

```python
# src/auth/asgardeo.py

async def perform_token_exchange(self, subject_token, client_id, client_secret,
                                  actor_token=None, target_audience=None, target_scopes=None):
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": subject_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
    }

    if actor_token:
        data["actor_token"] = actor_token
        data["actor_token_type"] = "urn:ietf:params:oauth:token-type:access_token"

    if target_scopes:
        data["scope"] = " ".join(target_scopes)

    # Uses Token Exchanger App credentials via Basic Auth
    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = await client.post(
        self.settings.asgardeo_token_url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_auth}"
        }
    )
    return response.json()["access_token"]
```

#### Token Contents After Exchange

```json
{
  "sub": "user-123",
  "scope": "hr:read hr:write",
  "act": {
    "sub": "hr-agent"
  },
  "iss": "https://localhost:9443/t/carbon.super",
  "aud": "onboarding-api"
}
```

The `act` (actor) claim proves delegation: the HR agent is acting on behalf of user-123.

---

### 5.5 Token Broker

**Purpose**: Centralized token management that orchestrates all three flows together.

**File**: `src/auth/token_broker.py`

```python
class TokenBroker:
    def __init__(self):
        self.asgardeo = get_asgardeo_client()
        self._actor_token = None          # Orchestrator's actor token
        self._sessions = {}               # session_id → UserSession
        self.agents_config = load_yaml_config().get("agents", {})

    async def initialize(self):
        """Get orchestrator's actor token at startup (3-step flow)."""
        self._actor_token = await self.asgardeo.get_actor_token()

    async def exchange_token_for_agent(self, source_token, agent_key, target_audience, target_scopes):
        """
        Full exchange pipeline for a worker agent:
        1. Get the worker agent's actor token (3-step flow with Token Exchanger creds)
        2. Exchange: user delegated token + agent actor token → scoped token
        """
        agent_config = self.agents_config[agent_key]
        agent_id = agent_config["agent_id"]

        # Step 1: Get agent's actor token
        agent_actor_token = await self.asgardeo._fetch_agent_actor_token(
            client_id=self.settings.token_exchanger_client_id,
            client_secret=self.settings.token_exchanger_client_secret,
            agent_id=agent_id
        )

        # Step 2: RFC 8693 exchange
        exchanged_token = await self.asgardeo.perform_token_exchange(
            subject_token=source_token,
            client_id=self.settings.token_exchanger_client_id,
            client_secret=self.settings.token_exchanger_client_secret,
            actor_token=agent_actor_token.token,
            target_scopes=target_scopes
        )

        return exchanged_token
```

---

### 5.6 JWT Validation

**Purpose**: Worker agents validate incoming tokens against WSO2 IS JWKS endpoint. There are two validation approaches in the codebase:

**Production-grade** (`src/auth/jwt_validator.py`) — Full JWKS signature verification:

```python
class JWTValidator:
    async def validate(self, token: str) -> TokenClaims:
        jwks = await self.get_jwks()       # Cached fetch from /oauth2/jwks
        header = jwt.get_unverified_header(token)

        # Find the signing key by kid
        key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])

        # Verify signature + expiry
        claims = jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})

        return TokenClaims(
            sub=claims["sub"], scope=claims["scope"],
            act=ActorClaim(sub=claims["act"]["sub"]) if "act" in claims else None,
            raw_token=token
        )
```

**Demo-mode** (in each worker agent) — Decodes without signature verification:

```python
# agents/hr_agent/agent.py
def validate_token(self, token):
    claims = jwt.get_unverified_claims(token)    # No signature check
    token_scopes = claims.get("scope", "").split()
    has_required = any(s in token_scopes for s in self.required_scopes)
    if not has_required:
        return {"valid": False, "error": f"Missing scopes: {self.required_scopes}"}
    return {"valid": True, "claims": claims}
```

---

## 6. A2A Protocol Implementation

The A2A (Agent-to-Agent) protocol is Google's open standard for agent interoperability. This implementation uses the official `a2a-sdk` Python package.

### 6.1 Agent Card (Discovery)

Every agent serves an **Agent Card** at `/.well-known/agent-card.json`. This is how agents advertise their capabilities.

```python
# agents/hr_agent/__main__.py

agent_card = AgentCard(
    name="HR Agent",
    description="Manages employee profiles and onboarding",
    url=f"http://localhost:8001/",
    version="1.0.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[
        AgentSkill(
            id="create_employee",
            name="Create Employee Profile",
            description="Create a new employee profile in the HR system",
            tags=["hr", "employee", "profile"],
            examples=["Create employee John Doe"]
        ),
    ]
)
```

**Example Agent Card response** (`GET http://localhost:8001/.well-known/agent-card.json`):

```json
{
  "name": "HR Agent",
  "description": "Manages employee profiles and onboarding",
  "url": "http://localhost:8001/",
  "version": "1.0.0",
  "capabilities": { "streaming": true },
  "skills": [
    {
      "id": "create_employee",
      "name": "Create Employee Profile",
      "description": "Create a new employee profile in the HR system",
      "tags": ["hr", "employee", "profile"]
    }
  ]
}
```

### 6.2 JSON-RPC Communication

A2A uses **JSON-RPC 2.0** over HTTP. The orchestrator sends `message/send` requests:

```json
// POST http://localhost:8001/
{
  "jsonrpc": "2.0",
  "id": "a1b2c3d4",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        { "kind": "text", "text": "Create employee John Doe" }
      ],
      "messageId": "msg-001"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "a1b2c3d4",
  "result": {
    "kind": "message",
    "parts": [
      {
        "kind": "text",
        "text": "✅ Employee created!\n- ID: EMP-JOHN-DO\n- Name: John Doe"
      }
    ]
  }
}
```

### 6.3 Executor Pattern

The A2A SDK uses an **Executor pattern** to decouple the HTTP/JSON-RPC layer from agent logic.

```python
# agents/hr_agent/executor.py

class HRExecutor(AgentExecutor):
    def __init__(self, config=None):
        self.agent = HRAgent(config)       # Business logic
        self._current_token = None

    def set_auth_token(self, token):
        self._current_token = token

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        # Extract text from A2A message
        query = ""
        for part in context.message.parts:
            if hasattr(part, 'root') and hasattr(part.root, 'text'):
                query = part.root.text

        # Process via agent logic
        response = await self.agent.process_request(query, self._current_token)

        # Enqueue response back through A2A SDK
        message = Message(
            role="agent",
            parts=[Part(root=TextPart(text=response))],
            message_id=f"response-{context.message.message_id}"
        )
        await event_queue.enqueue_event(message)
```

The **server setup** wires everything together:

```python
# agents/hr_agent/__main__.py

executor = HRExecutor(agent_config)

request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
    push_config_store=InMemoryPushNotificationConfigStore()
)

a2a_server = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
)

app = a2a_server.build()
app.add_middleware(TokenExtractMiddleware, executor=executor)  # Extract Bearer token
```

**`TokenExtractMiddleware`** intercepts every request to extract the Bearer token before the A2A SDK processes the JSON-RPC payload:

```python
class TokenExtractMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.executor.set_auth_token(auth_header[7:])
        return await call_next(request)
```

---

## 7. Agents

### 7.1 Orchestrator Agent

**Port**: 8000  
**File**: `agents/orchestrator/agent.py`  
**Role**: Central coordinator — discovers agents, decomposes tasks via LLM, performs token exchange, and calls worker agents.

**Key Methods**:

| Method | Purpose |
|---|---|
| `discover_agents()` | Fetches Agent Cards from all configured URLs |
| `decompose_to_tasks(user_input)` | LLM breaks input into ordered agent tasks |
| `process_workflow(user_input, access_token)` | Full pipeline: decompose → execute each task |
| `call_agent(agent_url, query, access_token)` | Token exchange + A2A JSON-RPC call to one agent |
| `stream(query, context_id, access_token)` | Entry point: stream response back to caller |

**HTTP Routes** (defined in `agents/orchestrator/__main__.py`):

| Route | Method | Purpose |
|---|---|---|
| `/auth/login` | GET | Start OAuth login flow |
| `/callback` | GET | Handle OAuth callback |
| `/api/demo` | GET/POST | Accept any user request, LLM decompose + execute |
| `/api/chat` | GET | Chat interface with streaming |
| `/.well-known/agent-card.json` | GET | A2A Agent Card |
| `/` | POST | A2A JSON-RPC endpoint |

### 7.2 HR Agent

**Port**: 8001  
**Required Scopes**: `hr:read`, `hr:write`  
**File**: `agents/hr_agent/agent.py`

**Capabilities**:
- `create_employee()`: Create employee profiles (simulated)
- `grant_privileges()`: Grant HR privileges to a user (post-approval)
- `process_request()`: Intent detection via keyword matching

### 7.3 IT Agent

**Port**: 8002  
**Required Scopes**: `it:read`, `it:write`  
**File**: `agents/it_agent/agent.py`

**Capabilities**:
- Provision VPN access
- Provision GitHub Enterprise access
- Provision AWS dev environments

### 7.4 Approval Agent

**Port**: 8003  
**Required Scopes**: `approval:read`, `approval:write`  
**File**: `agents/approval_agent/agent.py`

**Capabilities**:
- `create_approval_request()`: Create and auto-approve (simulated)
- `_classify_privilege_domain()`: Determines which agent should handle post-approval fulfillment (HR, IT, or Booking)
- Returns `route_to` field in response for downstream routing

### 7.5 Booking Agent

**Port**: 8004  
**Required Scopes**: `booking:read`, `booking:write`  
**File**: `agents/booking_agent/agent.py`

**Capabilities**:
- Schedule orientation sessions
- Book deliveries (equipment pickup)
- Manage task calendar

---

## 8. LLM-Based Task Decomposition

The orchestrator uses **OpenAI GPT-4o** to intelligently break user requests into ordered tasks.

**File**: `agents/orchestrator/agent.py` → `decompose_to_tasks()`

### How It Works

1. The orchestrator builds a prompt describing all discovered agents and their capabilities
2. Sends the user's request to GPT-4o with `response_format: json_object`
3. GPT-4o returns a structured plan with ordered steps
4. The orchestrator executes each step sequentially

### System Prompt

```
You are a task planner for an AI agent orchestrator.

Available Agents:
  - name: "HR Agent", url: "http://localhost:8001", skills: [Create Employee, ...]
  - name: "IT Agent", url: "http://localhost:8002", skills: [Provision VPN, ...]
  - name: "Approval Agent", url: "http://localhost:8003", skills: [Request Approval, ...]
  - name: "Booking Agent", url: "http://localhost:8004", skills: [Create Task, ...]

Rules:
- CAREFULLY identify ALL distinct actions in the user request.
- Order tasks logically (e.g., create profile before provisioning access).

Privilege / Access Workflow:
- When the request involves granting privileges, the Approval Agent MUST be invoked FIRST.
- AFTER approval, route to the appropriate agent to grant the privileges.
```

### Example: LLM Decomposition

**Input**: `"Create employee profile and provision VPN for Sarah Connor"`

**LLM Output**:
```json
{
  "tasks": [
    { "step": 1, "agent_url": "http://localhost:8001", "agent_name": "HR Agent",
      "task": "Create employee profile for Sarah Connor" },
    { "step": 2, "agent_url": "http://localhost:8002", "agent_name": "IT Agent",
      "task": "Provision VPN access for Sarah Connor" }
  ],
  "summary": "Create HR profile then provision VPN for Sarah Connor"
}
```

### Fallback (No LLM)

If OpenAI is unavailable, a keyword-based fallback routes by matching keywords to agents:

```python
keyword_map = {
    "hr": (["employee", "profile", "hr", "hire", "onboard"], "http://localhost:8001"),
    "it": (["vpn", "github", "aws", "provision"], "http://localhost:8002"),
    "approval": (["approve", "approval", "permission"], "http://localhost:8003"),
    "booking": (["schedule", "booking", "orientation"], "http://localhost:8004"),
}
```

---

## 9. End-to-End Workflow Scenarios

### 9.1 Single Agent — Create Employee

**Request**: `GET /api/demo?message=Create employee John Doe`

```
┌────────┐    ┌──────────────┐    ┌─────────┐    ┌──────────┐
│  User  │───>│ Orchestrator │───>│  GPT-4o │───>│ HR Agent │
│        │    │              │    │         │    │  (8001)  │
│        │    │ 1. Decompose │    │ 1 task  │    │          │
│        │    │ 2. Exchange  │    └─────────┘    │ Create   │
│        │    │    Token     │──────────────────>│ Employee │
│        │    │ 3. Call HR   │                   │          │
│        │<───│ 4. Return    │<──────────────────│ Result   │
└────────┘    └──────────────┘                   └──────────┘
```

**Token flow**:
1. User's delegated token (all scopes) → Token Exchange → Scoped token (`hr:read hr:write`)
2. Scoped token sent as `Authorization: Bearer` to HR Agent
3. HR Agent validates scopes → processes request

**Response**:
```json
{
  "status": "success",
  "plan": [{ "step": 1, "agent": "HR Agent", "task": "Create employee John Doe" }],
  "results": [{
    "step": 1, "agent": "HR Agent", "status": "success",
    "response": "✅ Employee created!\n- ID: EMP-JOHN-DO\n- Name: John Doe"
  }]
}
```

### 9.2 Multi-Agent — Onboard + Provision VPN

**Request**: `POST /api/demo { "message": "Create profile and provision VPN for Sarah Connor" }`

```
┌────────┐    ┌──────────────┐    ┌─────────┐
│  User  │───>│ Orchestrator │───>│  GPT-4o │
│        │    │              │    │ 2 tasks │
│        │    │              │    └─────────┘
│        │    │              │
│        │    │ Step 1:      │    ┌──────────┐
│        │    │  Exchange    │───>│ HR Agent │ Token: hr:read hr:write
│        │    │  → Call HR   │<───│ (8001)   │
│        │    │              │    └──────────┘
│        │    │ Step 2:      │    ┌──────────┐
│        │    │  Exchange    │───>│ IT Agent │ Token: it:read it:write
│        │    │  → Call IT   │<───│ (8002)   │
│        │<───│              │    └──────────┘
└────────┘    └──────────────┘
```

**Token exchanges** (two separate exchanges):
1. User delegated token + HR Agent actor token → `hr:read hr:write` scoped token
2. User delegated token + IT Agent actor token → `it:read it:write` scoped token

**Response**:
```json
{
  "status": "success",
  "plan": [
    { "step": 1, "agent": "HR Agent", "task": "Create employee profile for Sarah Connor" },
    { "step": 2, "agent": "IT Agent", "task": "Provision VPN access for Sarah Connor" }
  ],
  "results": [
    { "step": 1, "agent": "HR Agent", "status": "success",
      "response": "✅ Employee created!\n- ID: EMP-SARAH-C..." },
    { "step": 2, "agent": "IT Agent", "status": "success",
      "response": "✅ VPN access provisioned!" }
  ]
}
```

### 9.3 Approval → HR Privilege Grant

**Request**: `GET /api/demo?message=Grant HR admin privileges to Bob Johnson`

This demonstrates the **approval-first routing**:

```
┌────────┐    ┌──────────────┐    ┌─────────┐
│  User  │───>│ Orchestrator │───>│  GPT-4o │
│        │    │              │    │ 2 tasks │  Approval → then → HR
│        │    │              │    └─────────┘
│        │    │              │
│        │    │ Step 1:      │    ┌───────────────┐
│        │    │  Exchange    │───>│ Approval Agent│ Token: approval:read approval:write
│        │    │  → Call Appr │<───│ (8003)        │ Returns: approved + route_to: "hr"
│        │    │              │    └───────────────┘
│        │    │ Step 2:      │    ┌──────────┐
│        │    │  Exchange    │───>│ HR Agent │ Token: hr:read hr:write
│        │    │  → Call HR   │<───│ (8001)   │ Grants privileges
│        │<───│              │    └──────────┘
└────────┘    └──────────────┘
```

**LLM Plan**:
```json
{
  "tasks": [
    { "step": 1, "agent_name": "Approval Agent",
      "task": "Request approval for granting HR admin privileges to Bob Johnson" },
    { "step": 2, "agent_name": "HR Agent",
      "task": "Grant HR admin privileges to Bob Johnson (approved by Approval Agent)" }
  ]
}
```

**Combined Response**:
```
✅ Approval Agent: Approval request created and approved!
  - ID: APR-PRI-001
  - Status: approved
  🔀 Routing: forwarded to HR Agent

✅ HR Agent: HR privileges granted!
  - User: Bob Johnson
  - Status: granted
  - Effective: immediately
```

---

## 10. Visualizer

A browser-based UI that shows token flows and agent communication in real-time.

**Files**: `visualizer/index.html`, `visualizer/app.js`, `visualizer/styles.css`, `visualizer/log_server.py`

**How it works**:
1. `log_server.py` runs a WebSocket server on port 8200
2. All code calls `log_and_broadcast(message)` which both prints and sends to the WebSocket
3. The browser frontend connects via WebSocket and renders animations

```python
# src/log_broadcaster.py

def log_and_broadcast(message: str):
    """Print message and also send to visualizer."""
    print(message)
    broadcast_log_sync(message)   # POST http://localhost:8200/log

# Used throughout the codebase:
vlog(f"[TOKEN EXCHANGE FOR HR_AGENT]")
vlog(f"[SUBJECT_TOKEN]: {token}")
vlog(f"[EXCHANGED_TOKEN]: {exchanged}")
```

The visualizer parses log messages with markers like `[TOKEN EXCHANGE]`, `[ACTOR_TOKEN]`, `[STEP 1]` to trigger UI animations.

---

## 11. Running the System

### Prerequisites

1. WSO2 Identity Server running at `https://localhost:9443`
2. Applications registered: Orchestrator App + Token Exchanger App
3. AI Agents registered in WSO2 IS (orchestrator-agent, hr-agent, etc.)
4. `.env` file with all credentials
5. Python 3.11+ with dependencies installed

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start Worker Agents (separate terminals)

```bash
python -m agents.hr_agent          # Port 8001
python -m agents.it_agent          # Port 8002
python -m agents.approval_agent    # Port 8003
python -m agents.booking_agent     # Port 8004
```

### Start Orchestrator

```bash
python -m agents.orchestrator      # Port 8000
```

### Start Visualizer (optional)

```bash
python visualizer_server.py        # Port 8200
```

### Test the System

1. **Login**: Open `http://localhost:8000/auth/login` in a browser
2. **Authenticate**: Log in with a user account in WSO2 IS and grant consent
3. **Send request**:
   ```bash
   # Single agent
   curl "http://localhost:8000/api/demo?message=Create employee John Doe"

   # Multi-agent
   curl "http://localhost:8000/api/demo?message=Create profile and provision VPN for Sarah"

   # Approval workflow
   curl "http://localhost:8000/api/demo?message=Grant HR admin privileges to Bob"
   ```

### Test Agent Auth (diagnostic)

```bash
python test_agent_app.py
```

This tests each agent's 3-step actor token flow against WSO2 IS to verify credentials are working.

---

## Summary of Token Chain

```
┌──────────────────────────────────────────────────────────────────────┐
│                        COMPLETE TOKEN CHAIN                          │
│                                                                      │
│  1. User Login                                                       │
│     Browser → WSO2 IS → Auth Code → Delegated Token                 │
│     (scope: ALL, act.sub: orchestrator-agent)                       │
│                                                                      │
│  2. Orchestrator Actor Token (3-step)                                │
│     POST /authorize (response_mode=direct) → flowId                 │
│     POST /authn (agent username/password) → auth code               │
│     POST /token (client_id/secret in body) → actor token            │
│     (Used in Step 1 to bind delegation)                             │
│                                                                      │
│  3. Per-Agent Token Exchange (RFC 8693)                              │
│     For each worker agent call:                                      │
│       a. Get agent's actor token (3-step with Token Exchanger creds)│
│       b. Exchange: delegated token + agent actor → scoped token     │
│       c. Send scoped token as Bearer to worker agent                │
│                                                                      │
│  Token Hierarchy:                                                    │
│    Delegated Token (all scopes, act=orchestrator)                   │
│      └── Exchanged Token (hr:read hr:write, act=hr-agent)           │
│      └── Exchanged Token (it:read it:write, act=it-agent)           │
│      └── Exchanged Token (approval:read approval:write, act=...)    │
│      └── Exchanged Token (booking:read booking:write, act=...)      │
└──────────────────────────────────────────────────────────────────────┘
```
