# End-to-End Flow: Employee Onboarding A2A — Method V2

> **Method V2 key difference from Method V1:** Each agent has its own WSO2 IS Application (`client_id/secret`) and its own Agent identity (`agent_id/secret`). The Orchestrator **downscopes** the user token using its own credentials before forwarding — this is **self-delegation** and requires no actor token. Each worker agent then performs a **second exchange** using its own application credentials and its own actor token to prove its identity before calling the downstream API.

---

## The Story

A manager opens a browser and types:

> *"Onboard kasuntha as Senior Software Engineer. Give him AWS and GitHub provisioning and HR permissions. Book an orientation on June 10 2026. Set up his payroll."*

What follows is a chain of identity-aware, scope-minimised token exchanges across four independent agents, a local WSO2 Identity Server, and multiple REST APIs. Every token narrows in scope as it moves downstream. Here is exactly how that happens.

---

## WSO2 IS Applications in This System

| Application | `client_id` | Used by |
|---|---|---|
| **Orchestrator App** | `ORCHESTRATOR_CLIENT_ID` | User login, actor token, self-delegation downscope |
| **HR App** | `HR_CLIENT_ID` | HR agent actor token + second exchange |
| **IT App** | `IT_CLIENT_ID` | IT agent actor token + second exchange (also used by MCP server) |
| **Payroll App** | `PAYROLL_CLIENT_ID` | Payroll agent actor token + second exchange |
| **Booking App** | `BOOKING_CLIENT_ID` | Booking agent actor token + second exchange |

There is **no shared Token Exchanger application**. Each agent authenticates with its own identity.

---

## Chapter 1 — The Manager Logs In

### Step 1.1 — Manager hits `/auth/login`

**File:** `agents/orchestrator/__main__.py` → `start_login(request)`

```
GET http://localhost:8000/auth/login
```

**`TokenBroker.create_session()`** (`src/auth/token_broker.py`) generates a PKCE pair and a `session_id`. The manager's browser is redirected to:

```
GET https://localhost:9443/oauth2/authorize
  ?response_type=code
  &client_id=<ORCHESTRATOR_CLIENT_ID>
  &scope=hr:write hr:read it:write it:read payroll:write booking:write openid profile
  &redirect_uri=http://localhost:8000/callback
  &state=<session_id>
  &code_challenge=<pkce.challenge>
  &code_challenge_method=S256
  &requested_actor=<ORCHESTRATOR_AGENT_ID>
```

> `requested_actor` is a WSO2 IS extension that binds the resulting token to the Orchestrator Agent's identity — the token will carry an `act` claim referencing the agent.

The manager authenticates on WSO2 IS's login page. WSO2 redirects to:

```
GET http://localhost:8000/callback?code=AUTH_CODE&state=<session_id>
```

---

### Step 1.2 — Callback: Get Orchestrator Actor Token (3-Step Flow)

**File:** `agents/orchestrator/__main__.py` → `oauth_callback(request)`  
**File:** `src/auth/token_broker.py` → `TokenBroker.handle_callback(code, state)`  
**File:** `src/auth/asgardeo.py` → `AsgardeoClient.get_actor_token()` → `_fetch_agent_actor_token(OrcApp_client_id, OrcApp_client_secret, OrcAgent_ID)`

Before exchanging the user's `AUTH_CODE`, the system proves the Orchestrator Agent's own identity via a 3-step authorization code flow.

#### Step 1.2a — Initiate Auth Flow → get `flowId`

```
POST https://localhost:9443/oauth2/authorize
Authorization: Basic base64(<ORCHESTRATOR_CLIENT_ID>:<ORCHESTRATOR_CLIENT_SECRET>)
Content-Type: application/x-www-form-urlencoded

response_type=code
&client_id=<ORCHESTRATOR_CLIENT_ID>
&scope=openid
&redirect_uri=http://localhost:8000/callback
&code_challenge=<pkce.challenge>
&code_challenge_method=S256
&response_mode=direct
```

**WSO2 IS Response:**
```json
{
  "flowStatus": "INCOMPLETE",
  "flowId": "3e4f1a2b-xxxx-xxxx-xxxx-abcdef123456",
  "nextStep": {
    "authenticators": [{ "authenticatorId": "QmFzaWNBdXRoZW50aWNhdG9yOkxPQ0FM" }]
  }
}
```

#### Step 1.2b — Authenticate Orchestrator Agent → get `auth_code`

```
POST https://localhost:9443/oauth2/authn
Content-Type: application/json

{
  "flowId": "3e4f1a2b-xxxx-xxxx-xxxx-abcdef123456",
  "selectedAuthenticator": {
    "authenticatorId": "QmFzaWNBdXRoZW50aWNhdG9yOkxPQ0FM",
    "params": {
      "username": "<ORCHESTRATOR_AGENT_ID>",
      "password": "<ORCHESTRATOR_AGENT_SECRET>"
    }
  }
}
```

**WSO2 IS Response:**
```json
{ "flowStatus": "SUCCESS_COMPLETED", "authData": { "code": "orch_auth_code_abc123" } }
```

#### Step 1.2c — Exchange Code for Orchestrator Actor Token

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<ORCHESTRATOR_CLIENT_ID>:<ORCHESTRATOR_CLIENT_SECRET>)
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=orch_auth_code_abc123
&redirect_uri=http://localhost:8000/callback
&code_verifier=<pkce.verifier>
```

**WSO2 IS Response:**
```json
{
  "access_token": "ORCH_ACTOR_TOKEN",
  "scope": "openid"
}
```

`ORCH_ACTOR_TOKEN` claims:
| Claim | Value |
|---|---|
| `sub` | `<ORCHESTRATOR_AGENT_ID>` |
| `aud` | `[<ORCHESTRATOR_CLIENT_ID>, ...]` |

Cached in `AsgardeoClient._actor_token` — the 3-step flow runs only once per process.

---

### Step 1.3 — Exchange Auth Code for User Delegated Token

**File:** `src/auth/asgardeo.py` → `exchange_code_for_delegated_token(AUTH_CODE, pkce_verifier, ORCH_ACTOR_TOKEN)`

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<ORCHESTRATOR_CLIENT_ID>:<ORCHESTRATOR_CLIENT_SECRET>)
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=AUTH_CODE
&redirect_uri=http://localhost:8000/callback
&code_verifier=<pkce.verifier>
&actor_token=ORCH_ACTOR_TOKEN
&actor_token_type=urn:ietf:params:oauth:token-type:access_token
```

**WSO2 IS Response:**
```json
{
  "access_token": "USER_DELEGATED_TOKEN",
  "scope": "hr:write hr:read it:write it:read payroll:write booking:write openid profile"
}
```

`USER_DELEGATED_TOKEN` claims:
| Claim | Value |
|---|---|
| `sub` | `<manager_user_id>` |
| `act.sub` | `<ORCHESTRATOR_AGENT_ID>` |
| `scope` | all agent scopes |
| `aud` | `[<ORCHESTRATOR_CLIENT_ID>, all agent client_ids, all agent_ids, ...]` |

> The token's `aud` includes all agent application `client_id` values because WSO2 IS registers them as allowed audiences on the Orchestrator application. This is what makes the downstream self-delegation downscope possible.

Stored via `executor.set_auth_token(USER_DELEGATED_TOKEN)`. Manager sees: **"Login successful!"**

---

## Chapter 2 — The Manager Sends the Request

**File:** `agents/orchestrator/__main__.py` → `api_request(request)`

```
POST http://localhost:8000/api/request
Authorization: Bearer USER_DELEGATED_TOKEN
Content-Type: application/json

{ "message": "Onboard kasuntha as Senior Software Engineer..." }
```

The middleware validates the token and stores it in the executor. Then:

**`OrchestratorAgent.process_workflow(user_input, access_token)`** (`agents/orchestrator/agent.py`)

Runs two phases:
1. **`decompose_to_tasks(user_input)`** — GPT-4o breaks the request into a plan
2. **`_execute_dag(tasks, access_token)`** — Tasks run in parallel waves

---

## Chapter 3 — Agent Discovery

**File:** `agents/orchestrator/agent.py` → `discover_agents()`

Reads `discovery.agent_urls` from `config.yaml`, fetches each agent's card:

```
GET http://localhost:8001/.well-known/agent-card.json
```

Cached result:
```json
{
  "http://localhost:8001": { "name": "HR Agent",               "skills": ["Create Employee"] },
  "http://localhost:8002": { "name": "IT Agent",               "skills": ["Provision VPN"] },
  "http://localhost:8004": { "name": "Finance & Payroll Agent","skills": ["Register Payroll"] },
  "http://localhost:8005": { "name": "Booking Agent",          "skills": ["Create Task"] }
}
```

---

## Chapter 4 — LLM Decomposes the Request

**File:** `agents/orchestrator/agent.py` → `decompose_to_tasks()` → `_call_openai()`

GPT-4o returns:
```json
[
  { "step": 1, "agent_name": "HR Agent",               "task": "Create employee record for kasuntha as Senior Software Engineer, grant HR permissions", "depends_on": [] },
  { "step": 2, "agent_name": "IT Agent",               "task": "Provision GitHub and AWS access for kasuntha", "depends_on": [1] },
  { "step": 3, "agent_name": "Finance & Payroll Agent","task": "Register kasuntha in payroll", "depends_on": [1] },
  { "step": 4, "agent_name": "Booking Agent",          "task": "Schedule orientation program for kasuntha on June 10 2026", "depends_on": [1] }
]
```

---

## Chapter 5 — DAG Execution

```
Wave 1:  [Step 1 — HR Agent]
Wave 2:  [Step 2 — IT Agent | Step 3 — Payroll Agent | Step 4 — Booking Agent]  ← parallel
```

---

## Chapter 6 — Orchestrator Downscopes Token for Each Agent (Method V2)

**File:** `agents/orchestrator/agent.py` → `call_agent()` → `token_broker.exchange_token_for_agent()`  
**File:** `src/auth/token_broker.py` → `exchange_token_for_agent(source_token, agent_key, target_scopes)`

**This is the key Method V2 step.** Before forwarding to any agent, the orchestrator performs a **self-delegation downscope** using its own `client_id/secret`. No actor token is sent — WSO2 IS allows the issuing application to exchange its own tokens without one.

### Why orchestrator credentials, not agent credentials?

WSO2 IS token exchange validates that the authenticating client (`client_id` in Basic Auth) is in the subject token's `aud`. The `USER_DELEGATED_TOKEN` was issued by the **Orchestrator App**, so only the Orchestrator App can exchange it. The agent apps' `client_id` values are not the issuer.

### Example: Downscope for HR Agent

**File:** `src/auth/asgardeo.py` → `perform_token_exchange()`

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<ORCHESTRATOR_CLIENT_ID>:<ORCHESTRATOR_CLIENT_SECRET>)
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=USER_DELEGATED_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&scope=hr:write hr:read
```

> No `actor_token` parameter — WSO2 IS self-delegation does not require one.

**WSO2 IS Response:**
```json
{ "access_token": "HR_DOWNSCOPED_TOKEN", "scope": "hr:write hr:read" }
```

`HR_DOWNSCOPED_TOKEN` claims:
| Claim | Value |
|---|---|
| `sub` | `<manager_user_id>` — user identity preserved |
| `scope` | `hr:write hr:read` — narrowed from full set |
| `aud` | includes `<HR_CLIENT_ID>` — HR app can now exchange this token |

The same downscope runs for each agent before that agent is called:

| Agent | Scopes in downscoped token |
|---|---|
| HR Agent | `hr:write hr:read` |
| IT Agent | `it:write it:read` |
| Finance & Payroll Agent | `payroll:write` |
| Booking Agent | `booking:write` |

Each downscoped token is then forwarded to its agent via A2A JSON-RPC:

```
POST http://localhost:8001
Authorization: Bearer HR_DOWNSCOPED_TOKEN
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": { "message": { "role": "user", "parts": [{ "kind": "text", "text": "Create employee record for kasuntha..." }] } }
}
```

---

## Chapter 7 — HR Agent: Second Token Exchange

**File:** `agents/hr_agent/agent.py` → `process_request(query, token=HR_DOWNSCOPED_TOKEN)`

The HR Agent receives a token already scoped to `hr:write hr:read`. Before calling the HR API, it performs a **second RFC 8693 exchange** using its own application credentials and its own actor token, to assert the HR Agent's identity in the delegation chain.

### Step 7.1 — Get HR Agent Actor Token (3-Step Flow)

Uses **HR App** credentials (`HR_CLIENT_ID / HR_CLIENT_SECRET`) throughout:

#### 7.1a — Initiate Auth Flow

```
POST https://localhost:9443/oauth2/authorize
Authorization: Basic base64(<HR_CLIENT_ID>:<HR_CLIENT_SECRET>)

response_type=code &client_id=<HR_CLIENT_ID> &scope=openid
&response_mode=direct &code_challenge=<pkce.challenge> &code_challenge_method=S256
&redirect_uri=http://localhost:8000/callback
```

Response: `{ "flowId": "9b2c3d4e-..." }`

#### 7.1b — Authenticate HR Agent

```
POST https://localhost:9443/oauth2/authn

{
  "flowId": "9b2c3d4e-...",
  "selectedAuthenticator": {
    "authenticatorId": "QmFzaWNBdXRoZW50aWNhdG9yOkxPQ0FM",
    "params": { "username": "<HR_AGENT_ID>", "password": "<HR_AGENT_SECRET>" }
  }
}
```

Response: `{ "authData": { "code": "hr_auth_code_xyz789" } }`

#### 7.1c — Exchange Code for HR Actor Token

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<HR_CLIENT_ID>:<HR_CLIENT_SECRET>)

grant_type=authorization_code &code=hr_auth_code_xyz789
&redirect_uri=http://localhost:8000/callback &code_verifier=<pkce.verifier>
```

Response: `{ "access_token": "HR_AGENT_ACTOR_TOKEN" }` — `sub` = `<HR_AGENT_ID>`

---

### Step 7.2 — RFC 8693 Second Exchange → `HR_EXCHANGED_TOKEN`

**File:** `src/auth/asgardeo.py` → `perform_token_exchange(subject_token=HR_DOWNSCOPED_TOKEN, client_id=HR_CLIENT_ID, actor_token=HR_AGENT_ACTOR_TOKEN, target_scopes=["hr:write","hr:read"])`

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<HR_CLIENT_ID>:<HR_CLIENT_SECRET>)
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=HR_DOWNSCOPED_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&actor_token=HR_AGENT_ACTOR_TOKEN
&actor_token_type=urn:ietf:params:oauth:token-type:access_token
&scope=hr:write hr:read
```

**WSO2 IS Response:**
```json
{ "access_token": "HR_EXCHANGED_TOKEN", "scope": "hr:write hr:read" }
```

`HR_EXCHANGED_TOKEN` claims:
| Claim | Value |
|---|---|
| `sub` | `<manager_user_id>` — original user identity preserved end-to-end |
| `act.sub` | `<ORCHESTRATOR_AGENT_ID>` — delegation chain from login |
| `act.act.sub` | `<HR_AGENT_ID>` — HR Agent asserted its identity |
| `scope` | `hr:write hr:read` |

---

## Chapter 8 — HR Agent Calls the HR API

**File:** `agents/hr_agent/agent.py` → tool dispatch

`HR_EXCHANGED_TOKEN` is stored in a `ContextVar` so tool functions can read it:

```python
_current_token.set(HR_EXCHANGED_TOKEN)
```

GPT-4o-mini calls `create_employee()`:

```
POST http://localhost:8001/api/hr/employees
Authorization: Bearer HR_EXCHANGED_TOKEN

{ "name": "kasuntha", "role": "Senior Software Engineer", "team": "Engineering", ... }
```

HR API (`src/apis/hr_api.py`): `require_scope(token, "hr:write")` ✓ → creates record → returns `{ "employee_id": "EMP-XXXX" }`.

Then `grant_privileges()` (also `hr:write`):

```
POST http://localhost:8001/api/hr/employees/EMP-XXXX/privileges
Authorization: Bearer HR_EXCHANGED_TOKEN

{ "privileges": ["hr:read", "hr:write"] }
```

---

## Chapter 9 — Wave 2: IT, Payroll, Booking Run in Parallel

Each follows the same two-step pattern. The orchestrator already downscoped the token before dispatching each agent.

### IT Agent

**File:** `agents/it_agent/agent.py` → `process_request(token=IT_DOWNSCOPED_TOKEN)`

Gets IT actor token (3-step, `IT_CLIENT_ID/SECRET` + `IT_AGENT_ID/SECRET`), exchanges `IT_DOWNSCOPED_TOKEN` → `IT_EXCHANGED_TOKEN` (scope: `it:write it:read`).

The IT Agent routes through the **MCP Server** (`src/mcp/it_mcp_server.py`) via SSE. The MCP server reuses the IT Agent's credentials and actor token to perform a **third scope-narrowing exchange** per tool call — least privilege at the API boundary:

| MCP Tool | Scope narrowed to |
|---|---|
| `provision_vpn` | `it:write` only |
| `provision_github` | `it:write` only |
| `provision_aws` | `it:write` only |
| `list_provisions` | `it:read` only |

```
POST https://localhost:9443/oauth2/token
Authorization: Basic base64(<IT_CLIENT_ID>:<IT_CLIENT_SECRET>)

grant_type=token-exchange
&subject_token=IT_EXCHANGED_TOKEN
&actor_token=IT_AGENT_ACTOR_TOKEN   ← same actor token, reused
&scope=it:write                     ← narrowed to single operation scope
```

Then calls IT API:
```
POST http://localhost:8002/api/it/provision/github
Authorization: Bearer IT_WRITE_ONLY_TOKEN
```

### Finance & Payroll Agent

**File:** `agents/payroll_agent/agent.py` → `process_request(token=PAYROLL_DOWNSCOPED_TOKEN)`

Gets Payroll actor token (3-step, `PAYROLL_CLIENT_ID/SECRET` + `PAYROLL_AGENT_ID/SECRET`), exchanges `PAYROLL_DOWNSCOPED_TOKEN` → `PAYROLL_EXCHANGED_TOKEN` (scope: `payroll:write`).

```
POST http://localhost:8004/api/payroll/payroll
Authorization: Bearer PAYROLL_EXCHANGED_TOKEN

{ "employee_id": "EMP-XXXX", "employee_name": "kasuntha", "role": "Senior Software Engineer" }
```

Payroll API (`src/apis/payroll_api.py`): `require_scope(token, "payroll:write")` ✓

Then creates expense account (also `payroll:write`).

### Booking Agent

**File:** `agents/booking_agent_adk/__main__.py` → `CustomA2aAgentExecutor.execute()`

Gets Booking actor token (3-step, `BOOKING_CLIENT_ID/SECRET` + `BOOKING_AGENT_ID/SECRET`), exchanges `BOOKING_DOWNSCOPED_TOKEN` → `BOOKING_EXCHANGED_TOKEN` (scope: `booking:write`).

Stores in `ContextVar`, Google ADK runs tools:

```
POST http://localhost:8005/api/booking/tasks
Authorization: Bearer BOOKING_EXCHANGED_TOKEN

{ "employee_id": "EMP-XXXX", "task_type": "orientation", "scheduled_date": "2026-06-10" }
```

Booking API: `require_scope(token, "booking:write")` ✓

---

## Chapter 10 — Results Returned

```json
{
  "status": "success",
  "responses": {
    "HR Agent":               "Employee kasuntha created (EMP-XXXX). HR privileges granted.",
    "IT Agent":               "GitHub and AWS provisioned for EMP-XXXX.",
    "Finance & Payroll Agent":"Payroll registered (PAY-XXXX). Expense account created (EXP-XXXX).",
    "Booking Agent":          "Orientation scheduled for June 10 2026."
  }
}
```

---

## Complete Token Flow — All Payloads

```
═══════════════════════════════════════════════════════════════════════════
PHASE A — USER LOGIN
═══════════════════════════════════════════════════════════════════════════

[A1] GET /oauth2/authorize  (browser redirect)
     client_id=OrcApp  scope=hr:write hr:read it:write it:read payroll:write booking:write openid
     requested_actor=OrcAgent_ID  code_challenge=S256(pkce.verifier)

[A2] _initiate_auth_flow → POST /oauth2/authorize
     Authorization: Basic OrcApp  response_mode=direct
     → { flowId }

[A3] _authenticate_agent → POST /oauth2/authn
     { flowId, username=OrcAgent_ID, password=OrcAgent_SECRET }
     → { code: orch_auth_code }

[A4] _exchange_code_for_actor_token → POST /oauth2/token
     Authorization: Basic OrcApp
     grant=authorization_code  code=orch_auth_code  code_verifier=pkce.verifier
     → ORCH_ACTOR_TOKEN  (sub=OrcAgent_ID)

[A5] exchange_code_for_delegated_token → POST /oauth2/token
     Authorization: Basic OrcApp
     grant=authorization_code  code=AUTH_CODE  code_verifier=pkce.verifier
     actor_token=ORCH_ACTOR_TOKEN
     → USER_DELEGATED_TOKEN  (sub=manager, act.sub=OrcAgent_ID, scope=ALL)

═══════════════════════════════════════════════════════════════════════════
PHASE B — ORCHESTRATOR DOWNSCOPES  (self-delegation, no actor_token)
═══════════════════════════════════════════════════════════════════════════

[B1] exchange_token_for_agent(hr_agent) → POST /oauth2/token
     Authorization: Basic OrcApp          ← orchestrator is the token issuer
     grant=token-exchange
     subject_token=USER_DELEGATED_TOKEN
     scope=hr:write hr:read               ← no actor_token
     → HR_DOWNSCOPED_TOKEN  (sub=manager, scope=hr:write hr:read)

[B2] exchange_token_for_agent(it_agent) → POST /oauth2/token
     Authorization: Basic OrcApp
     subject_token=USER_DELEGATED_TOKEN  scope=it:write it:read
     → IT_DOWNSCOPED_TOKEN

[B3] exchange_token_for_agent(payroll_agent) → POST /oauth2/token
     Authorization: Basic OrcApp
     subject_token=USER_DELEGATED_TOKEN  scope=payroll:write
     → PAYROLL_DOWNSCOPED_TOKEN

[B4] exchange_token_for_agent(booking_agent) → POST /oauth2/token
     Authorization: Basic OrcApp
     subject_token=USER_DELEGATED_TOKEN  scope=booking:write
     → BOOKING_DOWNSCOPED_TOKEN

═══════════════════════════════════════════════════════════════════════════
PHASE C — HR AGENT SECOND EXCHANGE  (own app + own actor token)
═══════════════════════════════════════════════════════════════════════════

[C1] _initiate_auth_flow → POST /oauth2/authorize
     Authorization: Basic HRApp  response_mode=direct
     → { flowId }

[C2] _authenticate_agent → POST /oauth2/authn
     { flowId, username=HR_AGENT_ID, password=HR_AGENT_SECRET }
     → { code: hr_auth_code }

[C3] _exchange_code_for_actor_token → POST /oauth2/token
     Authorization: Basic HRApp
     grant=authorization_code  code=hr_auth_code  code_verifier=pkce.verifier
     → HR_AGENT_ACTOR_TOKEN  (sub=HR_AGENT_ID)

[C4] perform_token_exchange → POST /oauth2/token
     Authorization: Basic HRApp          ← agent's own app
     grant=token-exchange
     subject_token=HR_DOWNSCOPED_TOKEN
     actor_token=HR_AGENT_ACTOR_TOKEN    ← proves agent identity
     scope=hr:write hr:read
     → HR_EXCHANGED_TOKEN  (sub=manager, act.sub=OrcAgent, act.act.sub=HR_AGENT_ID)

[C5] POST /api/hr/employees
     Authorization: Bearer HR_EXCHANGED_TOKEN
     require_scope("hr:write") ✓

═══════════════════════════════════════════════════════════════════════════
PHASE D — IT MCP THIRD EXCHANGE  (per-operation scope narrowing)
═══════════════════════════════════════════════════════════════════════════

(IT agent first runs same 3-step + exchange as C1–C4 → IT_EXCHANGED_TOKEN scope=it:write it:read)

[D1] MCP exchange_token_for_scope → POST /oauth2/token
     Authorization: Basic ITApp          ← IT agent's app (reused by MCP server)
     grant=token-exchange
     subject_token=IT_EXCHANGED_TOKEN
     actor_token=IT_AGENT_ACTOR_TOKEN    ← IT agent's actor token (reused by MCP server)
     scope=it:write                      ← narrowed to single operation
     → IT_WRITE_ONLY_TOKEN

[D2] POST /api/it/provision/github
     Authorization: Bearer IT_WRITE_ONLY_TOKEN
     require_scope("it:write") ✓
```

---

## Token Lineage Summary

```
USER_DELEGATED_TOKEN
  sub:     <manager>
  act.sub: <OrchestratorAgent>
  scope:   hr:write hr:read it:write it:read payroll:write booking:write
  │
  │  Orchestrator self-delegation (no actor_token, OrcApp credentials)
  ├──────────────────────────────────────────────────────────────────────
  │
  ├─→ HR_DOWNSCOPED_TOKEN          scope: hr:write hr:read
  │     │  HR agent: own actor token (HRApp creds + HR_AGENT_ID/SECRET)
  │     └─→ HR_EXCHANGED_TOKEN     scope: hr:write hr:read
  │           sub: <manager>  act.sub: <OrcAgent>  act.act.sub: <HR_AGENT_ID>
  │
  ├─→ IT_DOWNSCOPED_TOKEN          scope: it:write it:read
  │     │  IT agent: own actor token (ITApp creds + IT_AGENT_ID/SECRET)
  │     └─→ IT_EXCHANGED_TOKEN     scope: it:write it:read
  │           │  MCP: per-tool narrowing (same ITApp + IT actor token reused)
  │           ├─→ IT_WRITE_ONLY_TOKEN   scope: it:write  (provision ops)
  │           └─→ IT_READ_ONLY_TOKEN    scope: it:read   (list ops)
  │
  ├─→ PAYROLL_DOWNSCOPED_TOKEN     scope: payroll:write
  │     │  Payroll agent: own actor token (PayrollApp + PAYROLL_AGENT_ID/SECRET)
  │     └─→ PAYROLL_EXCHANGED_TOKEN  scope: payroll:write
  │           sub: <manager>  act.sub: <OrcAgent>  act.act.sub: <PAYROLL_AGENT_ID>
  │
  └─→ BOOKING_DOWNSCOPED_TOKEN     scope: booking:write
        │  Booking agent: own actor token (BookingApp + BOOKING_AGENT_ID/SECRET)
        └─→ BOOKING_EXCHANGED_TOKEN  scope: booking:write
              sub: <manager>  act.sub: <OrcAgent>  act.act.sub: <BOOKING_AGENT_ID>
```

The manager's identity (`sub`) flows unchanged through every token. Scope only ever narrows — never broadens. Each agent asserts its own identity in the delegation chain via its actor token.

---

## Method V2 vs Method V1

| Aspect | Method V1 | Method V2 |
|---|---|---|
| **WSO2 IS Apps** | 1 shared Token Exchanger + Orchestrator | Orchestrator + one app per agent |
| **Orchestrator forwards token as** | Raw `USER_DELEGATED_TOKEN` | Downscoped `*_DOWNSCOPED_TOKEN` |
| **Downscope authenticated by** | n/a (no downscope) | Orchestrator App (token issuer, self-delegation) |
| **Actor token in downscope** | n/a | None — not required for self-delegation |
| **Agent exchanges using** | Shared Token Exchanger credentials | Own application credentials + own actor token |
| **Scope at agent entry** | Full scope set | Only the scopes that agent needs |
| **MCP server identity** | Own credentials | Reuses IT Agent's credentials |

---

## Key Files Reference

| File | Role |
|---|---|
| `agents/orchestrator/__main__.py` | HTTP server: `start_login`, `oauth_callback`, `api_request` |
| `agents/orchestrator/agent.py` | Core orchestration: `discover_agents`, `decompose_to_tasks`, `_execute_dag`, `call_agent` |
| `src/auth/token_broker.py` | Session management + **`exchange_token_for_agent()`** (self-delegation downscope) |
| `src/auth/asgardeo.py` | All WSO2 IS HTTP calls: `_fetch_agent_actor_token`, `perform_token_exchange`, `exchange_code_for_delegated_token` |
| `agents/hr_agent/agent.py` | HR Agent: 3-step actor token + second RFC 8693 exchange |
| `agents/it_agent/agent.py` | IT Agent: 3-step actor token + second exchange, routes to MCP |
| `agents/payroll_agent/agent.py` | Payroll Agent: 3-step actor token + second exchange (CrewAI) |
| `agents/booking_agent_adk/__main__.py` | Booking Agent: Google ADK, actor token + second exchange |
| `src/mcp/it_mcp_server.py` | IT MCP Server: per-tool scope narrowing using IT Agent's credentials |
| `src/apis/hr_api.py` | HR REST API: `require_scope("hr:write")` / `require_scope("hr:read")` |
| `src/apis/it_api.py` | IT REST API: `require_scope("it:write")` / `require_scope("it:read")` |
| `src/apis/payroll_api.py` | Payroll REST API: `require_scope("payroll:write")` / `require_scope("payroll:read")` |
| `src/apis/booking_api.py` | Booking REST API: `require_scope("booking:write")` / `require_scope("booking:read")` |
| `config.yaml` | Per-agent: `url`, `required_scopes`, `client_id/secret`, `agent_id/secret` |
| `.env` | All secrets: `*_CLIENT_ID/SECRET`, `*_AGENT_ID/SECRET`, `OPENAI_API_KEY` |
