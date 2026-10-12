# Employee Portal

A sample application demonstrating **seven IAM patterns for AI agents** using [Asgardeo](https://asgardeo.io). An AI-powered Corporate Concierge handles HR leave management with fine-grained access control — from basic queries with the agent's own credentials, to elevated actions on behalf of individual users.

**Key difference from v1:** No internal employee IDs (like EMP001). Any Asgardeo user with the right role/permissions can use the system immediately. User identity comes directly from the JWT `sub` claim, and users are auto-registered on first interaction.

## Seven IAM Patterns

| Pattern | Description | Token Type | Example |
|---------|-------------|------------|---------|
| **1. Agent as Resource Server** | Client authenticates directly with Asgardeo, sends JWT to agent | User Token (PKCE) | Client calls `POST /api/chat` with Bearer token |
| **2. Agent as Autonomous Client** | Agent authenticates as itself for basic operations | Agent Token (App Native Auth) | Agent queries company holidays, leave policy |
| **3. Agent on Behalf of User** | Agent acts with user's elevated privileges via OBO token | OBO Token (Auth Code + Actor Token) | Agent applies leave, checks balance for user |
| **4. Agent Delegating to Agent** | One agent invokes another; each authorizes independently | Two Agent Tokens (caller + callee) | HR Agent asks the IT Agent about VPN, files an IT ticket |
| **5. Out-of-Band Consent (CIBA)** | Agent asks the employee for Calendar consent after HR approves leave | Employee OBO Token via CIBA (Agent Token as `actor_token`) | Employee approves Calendar sync on their phone |
| **6. Third-Party Delegated Access** | Agent calls Google using a federated token shared by Asgardeo | Google access token in `federated_tokens` | Agent writes approved leave to the consenting employee's Google Calendar |
| **7. Federated User → Agent** | A person authenticated by a *different* IdP uses an agent directly, with their own authority | User Token (federated) → OBO Token | A partner-org IT admin resolves tickets through the IT Agent |

Patterns 4, 5 and 6 are **optional** and off by default:

- Pattern 4 — set `IT_AGENT_ENABLED=true` in `agent/.env`. See [Pattern 4: Agent-to-Agent](#pattern-4-agent-to-agent-delegation).
- Pattern 5 — enable employee Calendar consent with `CIBA_ENABLED=true` together with Pattern 6. See [Pattern 5: Employee Calendar Consent](#pattern-5-employee-calendar-consent-with-ciba).
- Pattern 6 — set `GOOGLE_CALENDAR_ENABLED=true` in `agent/.env`. See [Pattern 6: Third-Party Delegated Access](#pattern-6-third-party-delegated-access-google-calendar).
- Pattern 7 — runs on top of Pattern 4's IT agent. See [Pattern 7: Federated Partner-Org Access](#pattern-7-federated-partner-org-access).

Patterns 1-3 are the core of the sample and always on.

## Architecture

```mermaid
graph TB
    subgraph Asgardeo
        SPA_APP["SPA Application<br/><i>PKCE, REST scopes</i>"]
        MCP_APP["MCP Client Application<br/><i>Agent Auth, OBO, MCP scopes</i>"]
    end

    subgraph "Browser (localhost:3000)"
        CLIENT["Client SPA"]
    end

    subgraph "Agent Server (localhost:5001)"
        AGENT["AI Agent<br/><i>LangChain + Gemini</i>"]
    end

    subgraph "HR Server (localhost:8000)"
        HR_REST["/api/leaves<br/><i>REST API</i>"]
        HR_MCP["/mcp<br/><i>MCP Protocol</i>"]
        HR_DATA["service/store.py<br/><i>In-memory store</i>"]
    end

    %% Authentication flows
    CLIENT -- "1. PKCE Login" --> SPA_APP
    AGENT -- "2. Agent Auth" --> MCP_APP
    CLIENT -- "3. OBO Consent Popup" --> MCP_APP

    %% User → REST (direct, with SPA token + *_rest scopes)
    CLIENT -- "User Token<br/>(*_rest scopes)" --> HR_REST

    %% User → Agent (chat)
    CLIENT -- "User Token<br/>(agent_access)" --> AGENT

    %% Agent → MCP (with agent/OBO token + *_mcp scopes)
    AGENT -- "Agent Token<br/>(hr_basic_mcp)" --> HR_MCP
    AGENT -. "OBO Token<br/>(*_mcp scopes)" .-> HR_MCP

    %% In-memory data
    HR_REST --> HR_DATA
    HR_MCP --> HR_DATA
```

**3 components**: Client SPA, Agent Server, HR Server (MCP + REST in one process). No database required — all business data is stored in-memory.

**Two action paths, one business layer.** Every leave action — apply, approve, reject — can be performed in two ways:
- **Manual UI** — the SPA calls REST endpoints on the HR server using the user's `*_rest` scopes from PKCE login.
- **Chat** — the SPA sends messages to the agent server, which calls MCP tools using the agent's `*_mcp` scopes (or OBO-elevated for user-specific actions).

Both paths execute the same `service/hr_service.py` functions, so behavior is identical regardless of which surface a user prefers.

**No SCIM2 identity resolution.** Unlike v1, there is no M2M application and no `GET /scim2/Users/{sub}` lookup. User identity comes directly from JWT claims (`sub` + `name`). Users are auto-registered with default leave balances on first interaction.

**Two core Asgardeo applications** provide clean IAM separation:
- **SPA Application** — Browser authenticates via PKCE and receives tokens with `*_rest` scopes for direct REST API access (dashboard)
- **MCP Client Application** — Agent authenticates as a first-class identity (App Native Auth) and receives tokens with `*_mcp` scopes for MCP tool invocation. Also handles OBO flow when the agent needs to act on behalf of a user.

Patterns 5-6 add a separate confidential **CIBA application** for employee Calendar consent and a Google OIDC connection for sharing the upstream token.

## Project Structure

```
smart-employee-agent/
├── client/                     # Browser SPA (port 3000)
│   ├── index.html              # Tabbed UI: Dashboard, Apply, Manage, Chat
│   ├── app.js                  # PKCE login, REST API client, chat, OBO popup
│   ├── styles.css              # Layout and styling
│   ├── serve.py                # Dev server with /config endpoint
│   └── .env.example
├── agent/                      # Agent Server (port 5001)
│   ├── main.py                 # FastAPI + LangChain + JWT validation
│   ├── session.py              # Per-user session store
│   ├── agent_auth.py           # Agent token management (App Native Auth)
│   ├── obo_flow.py             # OBO flow handling (PKCE + token exchange)
│   ├── ciba_flow.py            # Employee CIBA consent + polling — Pattern 5
│   ├── google_calendar.py      # Federated Google token + Calendar API — Pattern 6, optional
│   ├── requirements.txt
│   └── .env.example
├── it-agent/                   # IT Agent (port 5002) — Pattern 4, optional
│   ├── main.py                 # A2A guard + own LLM + own MCP client
│   ├── agent_auth.py           # IT Agent's OWN agent identity
│   ├── jwt_validator.py        # Validates the CALLING agent's token
│   ├── requirements.txt
│   └── .env.example
├── it-server/                  # IT MCP Server (port 8001) — Pattern 4, optional
│   ├── main.py                 # MCP app + /reset
│   ├── config.py
│   ├── mcp_server/server.py    # FastMCP app + 6 IT service-desk tools
│   ├── service/                # it_service.py + in-memory store
│   ├── auth/                   # jwt_validator, context, scopes
│   ├── requirements.txt
│   └── .env.example
└── hr-server/                  # HR Server: MCP + REST in one process (port 8000)
    ├── main.py                 # Composes MCP + REST and starts uvicorn
    ├── config.py               # Centralized env loading + ALLOWED_ORIGINS
    ├── mcp_server/
    │   └── server.py           # FastMCP app + 9 @mcp.tool definitions
    ├── rest_api/
    │   └── server.py           # REST routes: holidays, policy, balance, leaves CRUD, reset
    ├── service/
    │   ├── store.py            # In-memory state, seed data, ensure_user
    │   └── hr_service.py       # Business logic shared by MCP + REST
    ├── auth/
    │   ├── jwt_validator.py    # JWT validation via JWKS
    │   ├── context.py          # Per-request context vars (sub, scopes, ...)
    │   └── scopes.py           # require_scope / require_user / audit helpers
    ├── requirements.txt
    └── .env.example
```

## Prerequisites

- Python 3.10+
- An [Asgardeo](https://asgardeo.io) account (free tier works)
- A [Google AI Studio](https://aistudio.google.com/) API key (for Gemini LLM)

### Create the Gemini API key

1. Sign in to [Google AI Studio's API Keys page](https://aistudio.google.com/apikey).
2. Create an API key in a Google Cloud project. If your existing project is not listed, import it from **Dashboard > Projects** first.
3. Copy the key into `agent/.env`:

   ```dotenv
   GOOGLE_API_KEY=<your-gemini-api-key>
   MODEL_NAME=gemini-2.5-flash
   ```

4. For Pattern 4, configure `GOOGLE_API_KEY` in `it-agent/.env` too. Restart each agent after changing its environment.

The Gemini API key is separate from the Google OAuth client used for Calendar federation. Keep the key in the server-side `.env` files. Google AI Studio creates keys restricted to the Gemini API; unrestricted standard keys are rejected. See [Google's API key guide](https://ai.google.dev/gemini-api/docs/api-key).

---

## Asgardeo Configuration

### Step 1: Create API Resources

#### REST API Resources (for SPA)

**Agent API Resource** (REST)
- Identifier: `agent-api`
- Scopes: `agent_access`

**HR REST API Resource**
- Identifier: `hr-rest-api`
- Scopes:

| Scope | Description |
|-------|-------------|
| `hr_basic_rest` | Company holidays, leave policy |
| `hr_self_rest` | Own leave balance and requests for dashboard |
| `hr_read_rest` | All leave requests for dashboard |
| `hr_approve_rest` | Approve/reject leave requests |

#### MCP Resources (for Agent)

**HR MCP Resource**
- Identifier: `hr-mcp`
- Scopes:

| Scope | Description |
|-------|-------------|
| `hr_basic_mcp` | Company holidays, leave policy |
| `hr_self_mcp` | Own leave balance, own leave requests, apply for leave |
| `hr_read_mcp` | All leave requests, leave request details |
| `hr_approve_mcp` | Approve/reject pending leave requests |

### Step 2: Register an AI Agent

Agents in Asgardeo are first-class identities (like users) — not OAuth clients.

1. Go to **Console > Agents**
2. Click **+ New Agent**
3. Provide a name (e.g., "Corporate Concierge") and optional description
4. Click **Create**

You will receive:
- **Agent ID** → used in `agent/.env` as `AGENT_ID`
- **Agent Secret** (shown once — store securely) → used in `agent/.env` as `AGENT_SECRET`

### Step 3: Create an SPA Application (for Browser)

The SPA handles browser PKCE login and dashboard REST access.

1. Go to **Applications > New Application > Single-Page Application**
2. Provide a name (e.g., "Smart Employee Client")
3. Authorized redirect URL: `http://localhost:3000/callback`
4. Finish the wizard
5. Under **API Authorization**, subscribe to the REST API Resources:
   - `agent-api` (grant `agent_access`)
   - `hr-rest-api` (grant all: `hr_basic_rest`, `hr_self_rest`, `hr_read_rest`, `hr_approve_rest`)
6. **Configure User Attributes:**
   - Navigate to the **User Attributes** section of the application
   - Under the **profile** section, ensure `given_name`, `family_name` and `email` are selected as **Requested** and **Mandatory**
7. **Configure Access Token:**
   - Navigate to the **Protocol** tab → **Access Token** section
   - Set **Token Type** to **JWT**
   - Under the **Access Token Attributes** dropdown, select `given_name`, `family_name` and `email`
8. Note the **SPA Client ID** → used in:
   - `client/.env` as `CLIENT_ID`
   - `agent/.env` as `TOKEN_AUDIENCE` (for validating user JWTs)
   - `hr-server/.env` as `SPA_CLIENT_ID`

9. Under **Roles**, set the application's **Role audience** to **Organization**. This sample shares organization roles across the SPA, MCP client and optional CIBA application.

### Step 4: Create an MCP Client Application (for Agent)

The MCP Client handles agent authentication (App Native Auth) and OBO flow.

1. Go to **Applications > New Application > MCP Client Application**
2. Provide a name (e.g., "Employee Portal")
3. Authorized redirect URL: `http://localhost:5001/api/obo/callback`
4. Finish the wizard
5. Under **API Authorization**, subscribe to the MCP Resources:
   - `hr-mcp` (grant all: `hr_basic_mcp`, `hr_self_mcp`, `hr_read_mcp`, `hr_approve_mcp`)
6. **Configure User Attributes:**
   - Navigate to the **User Attributes** section of the application
   - Under the **profile** section, ensure `given_name`, `family_name` and `email` are selected as **Requested** and **Mandatory**
7. **Configure Access Token:**
   - Navigate to the **Protocol** tab → **Access Token** section
   - Set **Token Type** to **JWT**
   - Under the **Access Token Attributes** dropdown, select `given_name`, `family_name` and `email`
8. Note the **MCP Client ID** → used in:
   - `agent/.env` as `ASGARDEO_CLIENT_ID`
   - `hr-server/.env` as `CLIENT_ID`

9. Under **Roles**, set **Role audience** to **Organization**.

### Step 5: Create Roles

Go to **User Management > Roles > New Role** and select **Organization** as the audience for every role below. Add its API/MCP permissions, then assign its users or agents. Also select **Organization** as the role audience on every application that issues the sample's tokens. Authorizing a resource on the application and assigning role permissions are both required.

| Role | REST Scopes (SPA) | MCP Scopes (Agent/OBO) |
|------|-------------------|----------------------|
| `employee` | `agent_access`, `hr_basic_rest`, `hr_self_rest` | `hr_basic_mcp`, `hr_self_mcp` |
| `hr_admin` | All employee scopes + `hr_read_rest`, `hr_approve_rest` | All employee + `hr_read_mcp`, `hr_approve_mcp` |
| `hr_agent` | None | `hr_basic_mcp` |

Assign `hr_agent` to the **Corporate Concierge agent identity** from Step 2. Assign `employee` and `hr_admin` to human users. The agent's own role grants basic access; personal and administrative actions use the user's OBO permissions.

### Step 6: Create Demo Users

Create any number of users in your Asgardeo organization and assign them the appropriate role. **No specific usernames required** — any user with the right role will work immediately.

| Example User | Role | What They Can Do |
|-------------|------|------------------|
| Any user | `employee` | View holidays/policy, check own balance, apply for leave |
| Any user | `hr_admin` | Everything an employee can do + view all requests, approve/reject |

> **No identity linking needed.** Users are auto-registered on first interaction with default leave balances (Annual: 20, Sick: 10, Personal: 5).

---

## Setup & Run

### 1. HR Server (Terminal 1)

```bash
cd hr-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env:
#   AUTH_ISSUER=https://api.asgardeo.io/t/<tenant>/oauth2/token
#   CLIENT_ID=<mcp-client-app-client-id>
#   SPA_CLIENT_ID=<spa-app-client-id>
#   JWKS_URL=https://api.asgardeo.io/t/<tenant>/oauth2/jwks

python main.py   # Runs on port 8000
```

### 2. Agent Server (Terminal 2)

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env:
#   ASGARDEO_BASE_URL=https://api.asgardeo.io/t/<tenant>
#   ASGARDEO_CLIENT_ID=<mcp-client-app-client-id>
#   AGENT_ID=<agent-id-from-console-agents>
#   AGENT_SECRET=<agent-secret-from-console-agents>
#   TOKEN_AUDIENCE=<spa-app-client-id>
#   OBO_REDIRECT_URI=http://localhost:5001/api/obo/callback
#   JWKS_URL=https://api.asgardeo.io/t/<tenant>/oauth2/jwks
#   AUTH_ISSUER=https://api.asgardeo.io/t/<tenant>/oauth2/token
#   GOOGLE_API_KEY=<your-google-api-key>

python main.py   # Runs on port 5001
```

### 3. Client (Terminal 3)

```bash
cd client
pip install python-dotenv   # Only dependency

cp .env.example .env
# Edit .env:
#   ASGARDEO_BASE_URL=https://api.asgardeo.io/t/<tenant>
#   CLIENT_ID=<spa-app-client-id>

python serve.py   # Runs on port 3000
```

### 4. Open the App

Go to **http://localhost:3000**. Click "Sign In" and log in with any Asgardeo user that has the `employee` or `hr_admin` role.

---

## Usage

The app has **four tabs**:

| Tab | Visible to | Purpose |
|---|---|---|
| **Dashboard** | Everyone | Stat cards (balance for employees, status counts for admins), upcoming holidays, leaves table with filters. Row click opens a details drawer. |
| **Apply for Leave** | `hr_self_rest` | Form with leave-type dropdown, date pickers, reason. Live summary shows requested days plus warnings if notice period or balance would be violated. |
| **Manage Requests** | `hr_approve_rest` | Pending queue with inline ✓ Approve / ✗ Reject buttons. Reject opens a reason modal. Tab badge shows the pending count. |
| **Chat** | Everyone | Conversational AI Assistant. Backed by the agent server + MCP tools, with the OBO popup for elevated actions. |

Manual actions (tabs 1–3) call the **REST API** with the SPA's `*_rest` scopes. Chat (tab 4) calls the **agent server**, which uses the MCP tools with `*_mcp` scopes via OBO. Both paths invoke the same `service/hr_service.py` business logic.

### Basic Queries (Agent Token — No OBO Needed)

These work immediately with the agent's own `hr_basic_mcp` credentials:

- "What are the company holidays this year?"
- "What is the leave policy?"

### Elevated Actions (OBO Required)

When you ask something that requires the user's own scopes, the agent returns an **"Authorize"** button:

- "What is my leave balance?" → needs `hr_self_mcp`
- "Apply for 5 days annual leave March 10-14" → needs `hr_self_mcp`
- "Show my leave requests" → needs `hr_self_mcp`

Click **Authorize Me** → popup opens → consent → popup closes → agent retries with OBO token.

### Role-Specific Actions

**As an Employee:**
- "What is my leave balance?" → shows default 20/10/5
- "Apply for sick leave March 5-6, not feeling well" → creates LR001
- "Show my leave requests" → lists own requests

**As an HR Admin:**
- "Show all pending leave requests" → lists all org requests
- "Get details for LR001" → full request details
- "Approve leave request LR001" → approves, deducts balance
- "Reject LR002 — insufficient notice" → rejects with reason

### Role Limitations

If a user tries an action beyond their role, the agent explains politely:
- Employee asks "Approve leave LR001" → agent explains Employee role can't approve

---

## MCP Tools (9 tools)

| Tool | MCP Scope | Identity | Token |
|------|-----------|----------|-------|
| `get_company_holidays` | `hr_basic_mcp` | No | Agent |
| `get_leave_policy` | `hr_basic_mcp` | No | Agent |
| `get_my_leave_balance` | `hr_self_mcp` | Yes | OBO |
| `get_my_leave_requests` | `hr_self_mcp` | Yes | OBO |
| `apply_leave` | `hr_self_mcp` | Yes | OBO |
| `get_all_leave_requests` | `hr_read_mcp` | No | OBO |
| `get_leave_request_details` | `hr_read_mcp` | No | OBO |
| `approve_leave_request` | `hr_approve_mcp` | Yes | OBO |
| `reject_leave_request` | `hr_approve_mcp` | Yes | OBO |

---

## REST API (used by the manual UI)

These are the REST endpoints exposed by `hr-server` for the SPA. The browser calls them directly with its PKCE-issued SPA token; no OBO required.

| Method | Path | Required scope | Purpose |
|---|---|---|---|
| `GET`  | `/api/holidays`                    | `hr_basic_rest` | Company holidays |
| `GET`  | `/api/leave-policy`                | `hr_basic_rest` | Leave types and rules |
| `GET`  | `/api/leave-balance`               | `hr_self_rest` | Caller's own balance |
| `GET`  | `/api/leaves`                      | `hr_self_rest` \| `hr_read_rest` | Caller's leaves (employee) or all leaves with filters (admin) |
| `GET`  | `/api/leaves/{id}`                 | `hr_self_rest` (own) \| `hr_read_rest` (any) | Leave details |
| `POST` | `/api/leaves`                      | `hr_self_rest` | Apply for leave |
| `POST` | `/api/leaves/{id}/approve`         | `hr_approve_rest` | Approve a pending request |
| `POST` | `/api/leaves/{id}/reject`          | `hr_approve_rest` | Reject a pending request |
| `POST` | `/reset`                           | `hr_approve_rest` \| `hr_approve_mcp` | Reset all in-memory data (demo only) |

The `hr_approve_rest` scope is granted to the `hr_admin` role per the Asgardeo configuration above. Employee tokens never receive it, so approve/reject actions return HTTP 403 from the REST surface.

---

## Test Checklist

### Authentication Tests

| # | Test | Expected |
|---|------|----------|
| 1 | PKCE login (Employee) | Login succeeds, role badge shows "Employee" (green) |
| 2 | PKCE login (HR Admin) | Login succeeds, role badge shows "HR Admin" (blue) |
| 3 | Sign out | Returns to login overlay, clears token |

### Dashboard Tests

| # | Test | User | Expected |
|---|------|------|----------|
| 4 | Dashboard loads | Employee | Shows "My Leave Requests" (own data only) |
| 5 | Dashboard loads | HR Admin | Shows "All Leave Requests" (all employees) |
| 6 | Dashboard refresh | Any | After a chat action, dashboard updates automatically |

### Basic Chat (Agent Token — No OBO)

| # | Test | Expected |
|---|------|----------|
| 7 | "What are the company holidays?" | Returns list of holidays (no authorize button) |
| 8 | "What is the leave policy?" | Returns leave type rules |

### OBO Flow Tests

| # | Test | Expected |
|---|------|----------|
| 9 | Ask "my leave balance" (first time) | "Authorize Me" button appears |
| 10 | Click Authorize → consent | Popup closes → agent retries → shows balance (20/10/5) |
| 11 | Ask "apply for sick leave Mar 5-6" | Works without re-authorization |
| 12 | Multiple elevated requests | All work without re-authorization |

### Employee Role Tests

| # | Test | Expected |
|---|------|----------|
| 13 | "What is my leave balance?" | Shows annual: 20, sick: 10, personal: 5 |
| 14 | "Show my leave requests" | Shows own requests |
| 15 | "Apply for personal leave March 20-21 for moving" | Creates new leave request (LR001) |
| 16 | "Approve leave LR001" | **Role limitation**: agent explains Employee can't approve |

### HR Admin Tests

| # | Test | Expected |
|---|------|----------|
| 17 | "Show all pending leave requests" | Returns all pending requests across org |
| 18 | "Get details for LR001" | Returns full details including employee name |
| 19 | "Approve leave request LR001" | Approves, records reviewer, deducts balance |
| 20 | "Reject LR002 — insufficient notice" | Rejects with reason |

### Error & Reset Tests

| # | Test | Expected |
|---|------|----------|
| 21 | Chat without login | 401 → auto sign-out |
| 22 | Empty message | Error: "Message cannot be empty" |
| 23 | Click "Reset Data" | Resets all in-memory data → signs out → fresh start |

### Patterns 5-6 Tests (Employee CIBA Consent and Calendar)

Requires Google token sharing and the mandatory script, `CIBA_ENABLED=true`,
`GOOGLE_CALENDAR_ENABLED=true`, matching webhook secrets and the CIBA audience.

| Test | Expected |
|---|---|
| Admin approves through Manage Requests or chat | Leave is approved; employee receives CIBA prompt |
| Employee signs in through Google and consents | Own leave verified with `hr_self_mcp`; Google token creates event |
| Employee refuses or times out | Leave stays Approved; no Calendar event |
| CIBA response has no Google token | Clear configuration error; no direct OAuth/email fallback |
| Google token lacks Calendar scope | Granted scopes logged; no event write |
| Expired Google token | Fresh Asgardeo authorization required; no Google token-endpoint call |
| Multi-day leave | Event includes every leave day (exclusive end date) |
| Webhook secrets differ | HTTP 403; employee CIBA flow does not start |

---

## Pattern 4: Agent-to-Agent Delegation

Two agents, two identities, two independent authorization decisions. The HR
Agent handles everything; when a question is about IT, it delegates to a
separate IT Agent that owns its own MCP server.

```
User ──consent──> HR Agent ──HR agent token──> HR MCP   (hr_basic_mcp)
                     │
                     │  ask_it_agent tool
                     │  presents the HR Agent's OWN token
                     │  (must carry it_agent_invoke)
                     ▼
                  IT Agent ──IT agent token──> IT MCP   (it_basic_mcp, it_ticket_mcp)
```

### What this demonstrates

- **Invoking an agent is itself a permission.** The IT Agent refuses any caller
  whose token lacks `it_agent_invoke`, and refuses non-agent callers outright
  (`aut != AGENT`), so a user token can never reach it even if it somehow
  carried the scope.
- **Neither agent can use the other's tools.** The HR Agent's token has no
  `it_*` scopes, so pointing it straight at the IT MCP server fails with
  `insufficient_scope`. Delegation is the only path, and it goes through an
  identity that is separately authorized.
- **Separate blast radius.** Compromising the HR Agent yields no IT access
  beyond what `it_agent_invoke` allows — which is "ask the IT Agent", not "use
  IT tools".

### The trade-off (read this)

On the HR → IT hop the **user is context, not authority**. The IT Agent acts on
its own identity, so the user's name and `sub` are forwarded as unverified data
used for wording and the ticket's `requested_for` field. The IT MCP server
authorizes the *agent*, never the user.

That is a deliberate choice, and it has a real consequence: the IT Agent can
file a ticket naming anyone. It fits a service-desk agent acting for the whole
org, and it is what the current SDK supports — `AsgardeoTokenClient.get_token()`
implements only `authorization_code` and `refresh_token`, with no
`urn:ietf:params:oauth:grant-type:token-exchange`. A nested delegation chain
(`sub`=user, `act`=IT Agent, `act.act`=HR Agent) would carry the user's authority
across both hops, but is not reachable through the SDK today.

If you need the user's authority on the second hop, do not use this pattern
as-is — give the IT MCP tools user-scoped guards and propagate a real delegated
token instead.

### Asgardeo configuration

On top of the Pattern 1-3 setup:

1. **MCP Resource** — "IT Service MCP", identifier `it_service_api`, scopes:
   `it_basic_mcp`, `it_ticket_mcp`.
2. **API Resource** — "Agent Invocation API", identifier `agent_invocation_api`,
   scope: `it_agent_invoke`.
3. **Authorize both** on the existing **MCP Client Application** (API
   Authorization tab). Role permission alone is not enough — the application
   must also be allowed to request the scope.
4. **Register a second agent**: Console > Agents > New Agent, "IT Agent".
   Copy its Agent ID and Secret into `it-agent/.env` as `IT_AGENT_ID` /
   `IT_AGENT_SECRET`.
5. **Roles**:
   - HR Agent's role gains `it_agent_invoke`.
   - New role `it_agent` with `it_basic_mcp` + `it_ticket_mcp`, assigned to the
     IT Agent.

Create `it_agent` with audience **Organization**, and keep the MCP Client application's role audience set to **Organization**.

### Client IDs and token audiences

With the shared MCP Client Application used in this README:

| Component | Variable | Application client ID |
|---|---|---|
| HR agent | `ASGARDEO_CLIENT_ID` | MCP client |
| IT agent | `ASGARDEO_CLIENT_ID` | MCP client |
| IT agent | `TOKEN_AUDIENCE` | MCP client: the audience of the **calling HR agent's token** |
| IT agent | `SPA_CLIENT_ID` | SPA: needed for Pattern 7 browser calls |
| IT server | `CLIENT_ID` | MCP client: the audience of the IT agent's tool-call token |

`it-agent/.env` must use the MCP client ID for `TOKEN_AUDIENCE`, while `agent/.env` uses the SPA client ID for its own `TOKEN_AUDIENCE`. These servers validate different callers. If you register a separate MCP application for the IT agent, its `ASGARDEO_CLIENT_ID` and `it-server/.env`'s `CLIENT_ID` use that IT application's ID, but its inbound `TOKEN_AUDIENCE` still uses the HR agent's MCP application ID.

> After changing roles or permissions, **restart the agent that holds the
> token**. Agent tokens are cached for their full lifetime (~1 hour), so a
> running process keeps presenting its pre-change token until it expires.

### Run it

```bash
# Terminal 4 — IT MCP server
cd it-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # AUTH_ISSUER, JWKS_URL, CLIENT_ID (same MCP client app)
python main.py            # Runs on port 8001

# Terminal 5 — IT agent
cd it-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # IT_AGENT_ID, IT_AGENT_SECRET, GOOGLE_API_KEY, ...
python main.py            # Runs on port 5002
```

Then in `agent/.env` set `IT_AGENT_ENABLED=true` and restart the HR agent.

### Try it

| Ask the chat | What should happen |
|---|---|
| "What are the upcoming holidays?" | HR tools only — the IT Agent is never called |
| "Is the VPN working?" | HR Agent delegates; IT Agent reports the VPN as Degraded |
| "What software can I request?" | IT Agent returns the catalog with approval rules |
| "Raise a ticket, my laptop won't boot" | IT Agent files a ticket, reports the `IT00x` reference |
| "How many leave days do I have?" | Still HR + OBO — delegation does not affect Pattern 3 |

### Seeing tickets in the UI

An **IT Tickets** tab appears in the Concierge once the IT Agent is reachable.
It shows every ticket with the audit trail intact — who it was raised for, and
which agent actually filed it:

| Ref | Subject | Status | Requested for | Filed by |
|-----|---------|--------|---------------|----------|
| IT002 | Laptop won't boot | Open | John | IT Agent 709a00cc-… (requested by John) |

The tab reveals itself automatically: `GET /api/it/tickets` returns 404 when
`IT_AGENT_ENABLED=false`, so there is no extra client-side configuration.

The read follows the same authority chain as chat, minus the LLM:

```
Browser ──user JWT──> Agent /api/it/tickets     (Pattern 1: user token validated)
Agent   ──agent token──> IT Agent /api/tickets  (Pattern 4: it_agent_invoke checked)
IT Agent ──agent token──> IT MCP                (it_ticket_mcp checked)
```

The browser's token is never forwarded past the HR agent. Raise a ticket in the
chat, then hit Refresh on the tab to watch it appear.

### Reading the logs

Each hop names itself, so a single question is traceable across four processes:

```
# HR agent
[CHAT >> Agent Token] user(sub)=... | scopes=hr_basic_mcp openid it_agent_invoke
[A2A >> IT Agent] requester=Lashini | query='is the VPN down?'

# IT agent
[A2A >> Caller Agent] agent(sub)=<hr-agent-uuid> | scopes=... it_agent_invoke
[IT-AGENT >> Agent Token] sub=(self) | scopes=it_basic_mcp it_ticket_mcp openid

# IT MCP
[IT-MCP >> Agent Token] sub=<it-agent-uuid> | aut=AGENT | scopes=it_basic_mcp, ...

# HR agent again
[A2A << IT Agent] tools_used=['get_service_status']
```

Denials are equally explicit:

```
[A2A DENIED] caller agent=<uuid> lacks 'it_agent_invoke' | present=['hr_basic_mcp', 'openid']
[SCOPE DENIED] Required: 'it_ticket_mcp' | Present: ['hr_basic_mcp', 'openid']
```

## Pattern 5: Employee Calendar Consent with CIBA

After an HR Admin approves leave through the dashboard or chat, the HR server
notifies the agent. The employee can be away from the portal: Asgardeo sends a
CIBA authentication link to their verified email address. The employee signs in
through Google and decides whether to add the approved leave to their Calendar.

```text
HR Admin -> HR REST/MCP: approve leave
HR server -> Agent webhook: leave-approved event
Agent -> Asgardeo CIBA: ask the employee for Calendar consent
Employee -> Google sign-in + consent through Asgardeo
Asgardeo -> Agent: employee OBO token + Google federated token
Agent -> HR MCP: verify the employee owns this approved leave
Agent -> Google Calendar: create the event with the employee's Google token
```

CIBA does **not** ask an admin to approve leave. The admin's normal REST/OBO
permissions authorize that decision. CIBA requests only the employee's consent
for the follow-up Calendar action. There is no `CIBA_APPROVER` setting.

### Asgardeo configuration

1. Complete the [Google federation setup in Pattern 6](#pattern-6-third-party-delegated-access-google-calendar).
2. Create a separate **Standard-Based Application (OIDC)**, for example
   **Employee Calendar Consent**. Keep it **confidential** (Public Client off)
   and record its client ID and client secret.
3. Under **Protocol > Allowed grant types**, enable **CIBA**. Set its request
   expiry to **300 seconds** and enable **Email** notification delivery. This
   sample polls for approval; it does not deliver the External channel's
   `auth_url` itself. Configure an organization email provider and use employees
   with verified email addresses. See the [CIBA configuration guide](https://wso2.com/asgardeo/docs/guides/authentication/configure-ciba-grant/).
4. Set access tokens to **JWT** and role audience to **Organization**. Authorize
   `hr-mcp` with `hr_self_mcp`. The employee's organization role must grant that
   scope too. Request `given_name`, `family_name` and `email`, and include them
   in **Access Token Attributes**.
5. Configure **Google as the only authenticator in the application's first
   login step**, and add the mandatory [adaptive authentication script](#mandatory-calendar-authentication-script).
   Leaving Username & Password as an alternative can authenticate the employee
   without obtaining a Google token.

The CIBA application's client secret is different from the agent identity's
`AGENT_SECRET`. No callback endpoint in the agent is needed for the CIBA grant.

### Configure the services

Generate one shared webhook secret:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Update the existing keys in `agent/.env`; keep only one entry for each key:

```dotenv
CIBA_ENABLED=true
CIBA_CLIENT_ID=<employee-calendar-consent-app-client-id>
CIBA_CLIENT_SECRET=<employee-calendar-consent-app-client-secret>
CIBA_NOTIFY_SCOPES=openid profile email hr_self_mcp
CIBA_NOTIFY_TIMEOUT_SECONDS=300
AGENT_WEBHOOK_SECRET=<generated-shared-secret>
GOOGLE_CALENDAR_ENABLED=true
FEDERATED_IDP_NAME=Google
FEDERATED_TOKEN_SCOPE=https://www.googleapis.com/auth/calendar.events
```

Update `hr-server/.env`:

```dotenv
CIBA_CLIENT_ID=<same-employee-calendar-consent-app-client-id>
AGENT_WEBHOOK_URL=http://localhost:5001/api/events/leave-approved
AGENT_WEBHOOK_SECRET=<same-generated-shared-secret>
```

`CIBA_CLIENT_ID` makes the HR MCP server accept the audience of the employee's
CIBA token. The webhook secret authenticates the HR server's event; it does not
substitute for the employee's consent or token permissions. In Docker Compose,
the webhook URL is overridden to `http://agent:5001/api/events/leave-approved`.
Restart both native services, or recreate the containers after editing `.env`.

### Try it and diagnose failures

1. Sign in as an employee and create a leave request.
2. As an HR Admin, approve it in **Manage Requests** or through chat.
3. The employee receives the Asgardeo CIBA email. Open it, sign in through
   Google, grant Calendar access, and approve the Calendar action.
4. The agent verifies the approved leave using the employee's `hr_self_mcp`
   token, then adds an all-day event to the employee's Calendar.

Expected log sequence:

```text
[EVENT >> Agent] leave-approved sent for LR001
[OFFLINE << HR] leave-approved for LR001
[OFFLINE >> CIBA] asked ... to confirm Calendar sync for LR001
[CIBA] federated_tokens:
[OFFLINE >> Verified] LR001 confirmed as Approved ...
[GOOGLE >> Calendar] event created ...
```

- **Webhook 403:** the two `AGENT_WEBHOOK_SECRET` values differ, a later duplicate
  key overrides the intended value, or the agent still has its pre-restart config.
- **JWT audience failure:** set the same `CIBA_CLIENT_ID` in both services.
- **Missing `hr_self_mcp`:** check CIBA application authorization, organization
  role audience and the employee's role permissions.
- **No `federated_tokens`:** check the connection's API-only token-sharing
  settings, the Google-only login step and the mandatory script. Successful
  CIBA authentication alone does not establish Google Calendar access.
- **Missing Calendar scope:** inspect the Google entry's `scope`, not the
  top-level Asgardeo `scope`. The grant must permit Calendar event writes.

The approval remains successful if CIBA is declined, times out, or Calendar
fails. A failed webhook is not automatically replayed; approve a new request
when testing a configuration fix. There is no direct Google OAuth popup or
fallback email link in this sample.

## Pattern 6: Third-Party Delegated Access (Google Calendar)

The employee's Google access token is **shared by Asgardeo in
`federated_tokens`**, alongside the Asgardeo access token. The Asgardeo token
verifies HR permissions; the Google token authorizes the Calendar API. The agent
calls Google's Calendar API directly, but does not call Google's OAuth token
endpoint or store Google client secrets or refresh tokens.

### Google Cloud setup

1. Select the Google Cloud project whose OAuth client will be used by the
   Asgardeo connection. Under **APIs & Services > Library**, enable **Google
   Calendar API**.
2. Under **Google Auth Platform**, configure Branding and Audience. For an
   External app in **Testing**, add each demo employee's Google account under
   **Audience > Test users**.
3. Under **Data Access > Add or remove scopes**, add
   `https://www.googleapis.com/auth/calendar.events`. The Google sign-in scopes
   `openid`, `profile` and `email` supply identity attributes. Calendar event
   access is the only additional Google API scope this demo requests.
4. Under **Clients**, create a **Web application** OAuth client, with redirect:

   ```text
   https://api.asgardeo.io/t/<tenant>/commonauth
   ```

5. Configure that client ID and secret **on the Asgardeo connection**. The Gemini
   `GOOGLE_API_KEY` is a separate credential and remains in the agents' `.env` files.

Declaring a scope in Data Access does not grant it to a token. The Google
authorization request must ask for it and the employee must grant it. Unverified
apps can be tested with listed test users; a verification warning is expected.
See [Google's consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent)
and [verification exceptions for testing](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification#exceptions-to-verification-requirements).

### Asgardeo Google connection and API-only token sharing

Create a **Standard-Based OIDC connection**, named **Google** in these examples,
using Google's authorization, token and user-info endpoints:

| Setting | Value |
|---|---|
| Authorization endpoint | `https://accounts.google.com/o/oauth2/v2/auth` |
| Token endpoint | `https://oauth2.googleapis.com/token` |
| User-info endpoint | `https://openidconnect.googleapis.com/v1/userinfo` |
| Scopes / additional query parameter | `scope=openid email profile https://www.googleapis.com/auth/calendar.events` |
| Callback | `https://api.asgardeo.io/t/<tenant>/commonauth` |

Map Google's name/email claims, enable JIT provisioning and add the connection
to the SPA login flow. Sign in through Google once to provision the employee,
then assign their `employee` **organization role** to that Asgardeo user. The
employee who creates the leave and consents must be the same identity.

Token sharing is configured on the **connection's federated authenticator** via
the Identity Provider Management API; it is not a toggle in the console UI.
Follow the [management API authentication guide](https://wso2.com/asgardeo/docs/apis/authentication/#get-an-access-token)
to obtain a management access token with `internal_idp_view` and
`internal_idp_update`. Use that management token only for the following setup
calls, not the sample's SPA, agent or CIBA tokens.

```bash
ASGARDEO_BASE_URL=https://api.asgardeo.io/t/<tenant>
# Set MANAGEMENT_ACCESS_TOKEN locally to the management API bearer token.

# Find the Google connection's ID.
curl --fail-with-body -sS \
  -H "Authorization: Bearer $MANAGEMENT_ACCESS_TOKEN" \
  "$ASGARDEO_BASE_URL/api/server/v1/identity-providers"

# Find its federated authenticator ID.
curl --fail-with-body -sS \
  -H "Authorization: Bearer $MANAGEMENT_ACCESS_TOKEN" \
  "$ASGARDEO_BASE_URL/api/server/v1/identity-providers/<idp-id>/federated-authenticators"

# Fetch the existing authenticator body before updating it.
curl --fail-with-body -sS \
  -H "Authorization: Bearer $MANAGEMENT_ACCESS_TOKEN" \
  "$ASGARDEO_BASE_URL/api/server/v1/identity-providers/<idp-id>/federated-authenticators/<authenticator-id>" \
  -o google-authenticator.json
```

In the local `google-authenticator.json`, preserve the existing authenticator
fields and `properties` array, adding/updating these two entries:

```json
[
  {"key":"ShareFederatedToken","value":"true"},
  {"key":"FederatedTokenAllowedScope","value":"https://www.googleapis.com/auth/calendar.events"}
]
```

Also ensure the connection's scope configuration requests
`openid email profile https://www.googleapis.com/auth/calendar.events`. If the
GET response masks a client secret, supply the real Google client secret in the
local update body. Apply it with:

```bash
curl --fail-with-body -sS -X PUT \
  -H "Authorization: Bearer $MANAGEMENT_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @google-authenticator.json \
  "$ASGARDEO_BASE_URL/api/server/v1/identity-providers/<idp-id>/federated-authenticators/<authenticator-id>"
```

Re-read the authenticator and confirm both properties were saved. See the
[Identity Provider Management API](https://wso2.com/asgardeo/docs/apis/idp/) for
request schemas. Keep the local management token and payload containing client
credentials out of Git.

### Mandatory Calendar authentication script

On the **CIBA application**, configure a single login step with **Google as its
only authenticator**. Enable conditional/adaptive authentication and apply:

```javascript
var onLoginRequest = function(context) {
    executeStep(1, {
        authenticationOptions: [{ idp: 'Google' }],
        stepOptions: { forceAuth: 'true' },
        authenticatorParams: {
            federated: {
                'Google': {
                    share_federated_token: 'true',
                    federated_token_scope: 'https://www.googleapis.com/auth/calendar.events'
                }
            }
        }
    }, {});
};
```

Replace both occurrences of `Google` with your connection's configured name.
The script supplies token-sharing parameters and **forces the Google
authentication step** rather than reusing an existing Asgardeo SSO session.
Script-supplied sharing parameters take precedence over request query values.
The older `OBO_PROMPT_CONSENT` option only forces an OBO consent screen; it does
not replace this script. See [WSO2's authentication script reference](https://is.docs.wso2.com/en/latest/references/conditional-auth/api-reference/).

For in-session Calendar requests through the OBO popup, configure the same
Google-only step and script on the MCP Client Application. This changes its
user login flow, not the HR/IT agent credential flow. Pattern 7's partner login
uses the SPA and the IT agent's separate desk OBO flow; configure its partner
connection as described in that section rather than replacing it with Google.

### Enable and verify

Set the flags and connection name from [Pattern 5](#configure-the-services), then
restart the agent. `FEDERATED_IDP_NAME` must match the connection name, not an
authenticator class such as `OpenIDConnectAuthenticator`.

The token response must contain both kinds of authority:

```json
{
  "access_token": "<Asgardeo employee OBO token>",
  "scope": "openid hr_self_mcp",
  "federated_tokens": [{
    "idp": "Google",
    "scope": "openid https://www.googleapis.com/auth/calendar.events",
    "tokenValidityPeriod": "3599",
    "accessToken": "<Google access token>"
  }]
}
```

The Google token's scopes must include `https://www.googleapis.com/auth/calendar.events`. The top-level
`hr_self_mcp` scope is for HR and grants no Google permissions. By default the
CIBA log prints the federated response with token values redacted. Set
`DEBUG_FEDERATED_TOKENS_RAW=true` to print only the complete Google federated
values during a demo; it does not enable the Asgardeo JWT dumps. Restart after
changing this flag, and turn it off after inspection.

Google grants and OBO sessions are held in memory and disappear on restart or
sign-out. Expired Google tokens require fresh authentication through Asgardeo;
the agent never attempts a Google refresh-token exchange. Multi-day events use
Google's exclusive end date so the complete leave range is covered.

An employee can also ask **“Add approved leave LR001 to my Google Calendar”** in
chat. If their federated grant is missing or expired, the portal offers its
existing OBO **Authorize** button to get a fresh Google grant through Asgardeo.
An admin's approval alone never writes an event; the employee's explicit chat
request or their CIBA approval authorizes Calendar sync.

---

## Pattern 7: Federated Partner-Org Access

Patterns 1–6 all assume the person using an agent belongs to *your*
organization. This one does not.

**The scenario:** the IT service desk is outsourced. The engineers who work the
ticket queue are staff of a partner company, with accounts in that company's
own identity provider. Your organization never creates their accounts, never
resets their passwords, and never offboards them — yet they must work your
tickets every day.

### What this demonstrates

- **Lifecycle stays with the home organization.** Disable an engineer in the
  partner's directory and they lose access here immediately, with no action
  taken locally and no orphaned account left behind. This is the property that
  local accounts cannot give you, and it is the clearest argument for
  federation.
- **The agents never learn about the second IdP.** Federation resolves at the
  identity provider, so both agents keep receiving ordinary first-party tokens
  and their validation is unchanged. That is the architectural win — and the
  demo problem, since it makes the second provider invisible. The sample
  therefore surfaces the origin deliberately (a badge in the UI, `home_org` in
  every log line) and lets it appear in the audit trail of every action.
- **Two inbound paths, two kinds of authority.** The IT Agent now answers on
  both, and the guards are exact mirror images:

  | Path | Caller | Guard | Acts as |
  |---|---|---|---|
  | `/api/ask`, `/api/tickets` | another agent | must be `aut=AGENT` + `it_agent_invoke` | itself (Pattern 4) |
  | `/api/desk/*` | a person | must **not** be `aut=AGENT`, needs `it_desk_access` | **the user**, via OBO |

  Neither path is reachable with the other's token, so which authority applies
  is never ambiguous.
- **The user's own permissions decide the outcome.** On the desk path the agent
  obtains a delegated token (`sub` = the person, `act.sub` = the IT Agent) and
  calls the IT MCP server with it. The server authorizes *the human*. It never
  falls back to the agent's own token — that would silently answer with the
  agent's permissions instead of the user's.
- **A real privilege boundary.** Closing a ticket needs `it_resolve_mcp`, which
  ordinary employees do not have. An employee asking to resolve a ticket is
  refused by the resource server, not by prompt wording. That same scope also
  controls whole-queue visibility: without it you see only tickets raised for
  you, and no name you type widens that.

### Asgardeo configuration

On top of the Pattern 4 setup:

1. **Partner tenant** — create a second Asgardeo organization for the partner,
   then register a **Standard-Based Application (OpenID Connect)** in it. This
   app is what makes the *primary* tenant an OIDC client of the partner.
   - **Grant type:** Authorization Code (the only one needed).
   - **Authorized redirect URL:**
     `https://api.asgardeo.io/t/<primary-tenant>/commonauth`
     Note this is the **primary** tenant's URL, not the partner's — the partner
     authenticates the user and hands them back to the broker. Use the same
     value for the logout redirect if you want single logout.
   - Keep it confidential (client secret). Do not mark it a public client or
     force PKCE; the primary tenant authenticates with the secret.
   - **User Attributes:** share `given_name`, `family_name`, `email` and
     `groups`. Without `groups` the role mapping below has nothing to match,
     and engineers sign in successfully but with no permissions.
2. **Primary tenant → Connections** — add an OIDC/Enterprise connection
   pointing at the partner tenant's endpoints, using that application's client
   ID and secret.
3. **Add the connection to the SPA's login flow**, so the sign-in page offers
   "Sign in with the partner organization".
4. **Enable JIT provisioning** on the connection, so federated users
   materialize locally and can hold roles.
5. **New scopes** on the existing IT API resources:
   - `it_resolve_mcp` on the IT Service MCP resource — closing tickets, and whole-queue
     visibility.
   - `it_desk_access` on the Agent API resource — permission to use the service
     desk at all.
6. **Roles:**

   | Role | Assigned to | IT scopes |
   |---|---|---|
   | `employee` | local staff | `it_desk_access`, `it_basic_mcp`, `it_ticket_mcp` |
   | `it_service_desk` | federated partner users | the above **plus** `it_resolve_mcp` |

   Map the partner directory's group onto `it_service_desk` so engineers get
   their permissions on first login without anyone provisioning them by hand.
7. **Register the desk callback** — add
   `http://localhost:5002/api/desk/obo/callback` to the IT agent's MCP Client
   Application and set it as `IT_REDIRECT_URI` in `it-agent/.env`. Unlike Pattern
   4 this is a real browser redirect. If the HR MCP application has the
   Google-only Calendar login script from Pattern 6, create a **separate MCP
   Client Application for the IT Service Desk** so its login flow can use the
   partner connection. Authorize the IT MCP scopes on that application, enable
   App-Native Authentication for the IT agent, set JWT access tokens and
   Organization role audience, and configure its partner/employee login options.
   In that case set:

   ```dotenv
   # it-agent/.env
   ASGARDEO_CLIENT_ID=<it-mcp-client-app-client-id>
   TOKEN_AUDIENCE=<hr-mcp-client-app-client-id>
   SPA_CLIENT_ID=<spa-app-client-id>
   IT_REDIRECT_URI=http://localhost:5002/api/desk/obo/callback
   ```

   ```dotenv
   # it-server/.env
   CLIENT_ID=<it-mcp-client-app-client-id>
   ```

Also set `SPA_CLIENT_ID` in `it-agent/.env`: browser tokens are minted for the
SPA and agent tokens for the MCP client app, so the IT agent accepts both
audiences and tells them apart by `aut`.

Create the `it_service_desk` role with audience **Organization** and set the partner application's role audience to **Organization** too.

### Try it

| Step | As | Action | What should happen |
|---|---|---|---|
| 1 | Employee | Ask the assistant to raise an IT ticket | Ticket filed via the HR → IT delegation (Pattern 4) |
| 2 | Partner engineer | Sign in with the partner organization | Redirects to the **partner tenant's** login page, returns authenticated |
| 3 | Partner engineer | Open **IT Service Desk** | Badge reads "Signed in via … (partner org)" |
| 4 | Partner engineer | Send a message → **Authorize** | Consent popup; afterwards the agent acts with their permissions |
| 5 | Partner engineer | "Show open tickets", then "resolve IT001, replaced the SSD" | Whole queue visible; ticket closes |
| 6 | Employee | Open the desk and try to resolve a ticket | Refused for lack of `it_resolve_mcp`; sees only their own tickets |
| 7 | Partner admin | Disable the engineer in the **partner tenant**, retry sign-in | Access gone, with nothing changed locally |

Step 7 is the payoff, and it needs no code at all.

### Reading the logs

```
# a person on the desk path — note home_org
[DESK >> User Token] user(sub)=... | name=Priya Raj | home_org=HelixIT | scopes=it_desk_access openid
[IT-OBO] delegated authority granted by user(sub)=... from home_org=HelixIT | scopes=['it_basic_mcp', 'it_ticket_mcp', 'it_resolve_mcp']
[DESK >> OBO Token] acting as user(sub)=... | home_org=HelixIT | scopes=it_basic_mcp, it_ticket_mcp, it_resolve_mcp

# the IT MCP server sees the human, with the agent as actor
[IT-MCP >> OBO Token] user(sub)=... | home_org=HelixIT | agent(act.sub)=<it-agent-uuid> | scopes=...
[AUDIT] IT001 resolved by user(sub)=... from home_org=HelixIT
```

Denials name which guard fired:

```
[DESK DENIED] agent token presented on the human path
[DESK DENIED] user=<uuid> lacks 'it_desk_access' | present=['openid']
[SCOPE DENIED] Required: 'it_resolve_mcp' | Present: ['it_basic_mcp', 'it_ticket_mcp']
[IT-MCP] queue scoped to own tickets for user(sub)=<uuid> | 1 ticket(s)
```

### Limits (read this)

- **The home-organization claim is best-effort.** Asgardeo names it differently
  depending on how the user authenticated, so the code checks several claims in
  order and falls back to `primary`. Confirm against a real federated token in
  your tenant before relying on a specific claim.
- **Sessions and delegated tokens are in memory**, lost on restart. A real
  deployment persists them encrypted, keyed by user.
- **Tickets carry an owning organization but the demo does not host two
  customer orgs.** If you extend this to a partner serving several customers,
  enforce that dimension on read as well, or engineers will see across
  customers.
- **Federation is configured, not coded.** Nothing in either agent knows the
  partner IdP exists. If you want the agent itself to validate foreign tokens,
  that is a different design (multi-issuer validation) with different
  trade-offs.

## Seeing the tokens

Delegated HR tokens and Google federated tokens stay in the agent process's
memory. By default logs omit credential values; the explicit raw-token debug
flags below print them for inspection. The decoded claims show what a resource
server authorizes.

Every MCP call prints one line naming the kind of token that carried it:

```
[MCP >> OBO Token]   user(sub)=<user-uuid> | name=Nimal Perera | agent(act.sub)=<agent-uuid> | scopes=hr_self_mcp openid
[MCP >> Agent Token] sub=<agent-uuid> | name=... | scopes=hr_basic_mcp openid
```

Same server, same tools, different authority — and only the first has an `act`
claim. That contrast is Pattern 3 in one screen.

For a fuller view, set `DEBUG_TOKENS=true` in any component's `.env` and
restart it. Each token is then printed with its claims broken out:

```
╭─ [IT-MCP] OBO Token ────────────────────────────────────────────
│ DELEGATED — a person's authority, carried by an agent
│   sub      = 8f2a-user-uuid   (whose authority)
│   act.sub  = c41b-it-agent-uuid   (who is carrying it)
│ scopes     = it_basic_mcp it_ticket_mcp it_resolve_mcp openid
│ audience   = <mcp-client-id>
│ issuer     = https://api.asgardeo.io/t/<tenant>/oauth2/token
│ expires    = 2026-08-31T11:57:58+00:00 (in 59m 59s)
│ other claims:
│   { "family_name": "Raj", "given_name": "Priya", "idp": "HelixIT" }
╰──────────────────────────────────────────────────────────────────
```

### Getting the actual token

`DEBUG_TOKENS=true` prints claims only. To get the encoded JWT itself — to
paste into jwt.io and show the `act` claim on screen — set
`DEBUG_TOKENS_RAW=true` instead. It implies `DEBUG_TOKENS`, and prints the
token unwrapped on its own line so it can be copied in one go:

```
  encoded token (CREDENTIAL — do not share, expires soon):
eyJhbGciOiJSUzI1NiIsIn...
```

> **This writes a live bearer token to the log.** Anyone who reads that log —
> or a screenshot of it, or a pasted terminal dump — can replay the token until
> it expires. Use it on a throwaway tenant and turn it off afterwards. The
> component logs a warning on startup while it is on, so you cannot forget
> quietly.

Both default to false. Enable on:

| Component | Shows |
|---|---|
| `hr-server` | every HR tool call, agent vs. delegated |
| `it-server` | every IT tool call, including `home_org` for federated users |
| `agent` | its own agent token at startup/refresh, the actor token, and the delegated token at consent |
| `it-agent` | the same three, for its own separate agent identity |

The agent-side dumps are worth watching in order. The agent's **own** token has
no `act` claim — it is acting as itself. The **actor** token is that same
identity being presented during the exchange, and its `sub` reappears as
`act.sub` in the **delegated** token that comes back. Seeing all three in
sequence shows exactly where the delegation is constructed.

## Troubleshooting

### "Agent error" on startup
- Ensure the HR server is running before starting the agent
- Verify `AGENT_ID` and `AGENT_SECRET` in `agent/.env` match the values from Console > Agents
- Verify `ASGARDEO_CLIENT_ID` in `agent/.env` matches the MCP Client Application's Client ID

### Dashboard shows no data / 403
- Confirm the user's role grants the required REST scopes (`hr_self_rest` for employees, `hr_read_rest` for HR Admins)
- Check that `SPA_CLIENT_ID` in the MCP server `.env` matches the SPA application

### OBO popup fails
- Allow popups for `localhost:3000` in your browser
- Verify `OBO_REDIRECT_URI=http://localhost:5001/api/obo/callback` matches the MCP Client Application's redirect URI in Asgardeo
- Ensure the agent has been registered and has valid credentials

### JWT validation fails
- Ensure `AUTH_ISSUER` and `JWKS_URL` match across all `.env` files
- `TOKEN_AUDIENCE` in `agent/.env` must be the **SPA** app's Client ID (not the MCP Client's)
- `ASGARDEO_CLIENT_ID` in `agent/.env` must be the **MCP Client** app's Client ID
- `CLIENT_ID` in `hr-server/.env` must be the **MCP Client** app's Client ID
- `SPA_CLIENT_ID` in `hr-server/.env` must be the **SPA** app's Client ID

### Token missing scopes
- Check that API Resources are authorized for the application in Asgardeo
- Verify role-to-scope assignments include the needed scopes
- Ensure the user is assigned to the correct role

### CIBA and Google Calendar troubleshooting

- For webhook, audience, permissions and federated-token errors, use the
  [Pattern 5 diagnostic checklist](#try-it-and-diagnose-failures).
- `TOKEN_AUDIENCE` in the IT agent is the **calling HR agent's MCP client ID**;
  it is not the SPA ID. Browser access uses the separate `SPA_CLIENT_ID`.
- When Google returns only sign-in scopes, check that `calendar.events` is
  declared in Google Data Access, requested by the connection/script and granted
  by the employee. Existing sign-in consent is not proof of Calendar permission.
- Changing `.env` requires a native process restart or Docker container
  recreation. Check for duplicate keys when a new value appears to be ignored.

### Offline regression checks

From `smart-employee-agent/agent`, activate its virtual environment and run:

```bash
python -m unittest discover -s tests -v
```

These checks mock Asgardeo and Google. They cover employee CIBA refusal/expiry,
leave ownership, missing scopes/tokens, webhook authentication, Calendar event
boundaries and federated-only credential logging. They do not send emails or
create real Calendar events.
