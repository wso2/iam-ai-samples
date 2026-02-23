# A2A + MCP Reference Implementation with WSO2 Identity Server

A reference implementation demonstrating the **Agent-to-Agent (A2A) protocol** with **Model Context Protocol (MCP)**, secured by **WSO2 Identity Server** using OAuth 2.0 token exchange (RFC 8693).

Each agent uses a **modern AI framework** for autonomous request handling instead of hardcoded keyword matching:
- **Orchestrator** — OpenAI GPT-4o for LLM task decomposition
- **HR Agent** — [Vercel AI SDK](https://github.com/vercel/ai) (Python) for autonomous tool-calling
- **IT Agent** — OpenAI GPT-4o-mini for LLM-routing via MCP
- **Approval Agent** — [CrewAI](https://www.crewai.com/) multi-agent framework
- **Booking Agent** — [Google ADK](https://google.github.io/adk-docs/) (Agent Development Kit)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER REQUEST                                   │
│              "Onboard John Doe as Software Engineer"                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │     ORCHESTRATOR (port 8000)   │
               │  ┌──────────────────────────┐  │
               │  │ LLM Task Decomposition   │  │◄── OpenAI GPT-4o
               │  │ (breaks into sub-tasks)  │  │
               │  └──────────────────────────┘  │
               │  ┌──────────────────────────┐  │
               │  │ Token Broker             │  │◄── WSO2 IS (RFC 8693)
               │  │ (exchanges tokens per    │  │    Token Exchange
               │  │  agent with actor token) │  │
               │  └──────────────────────────┘  │
               └───┬──────┬──────┬──────┬───────┘
       A2A         │      │      │      │    A2A
     ┌─────────────┘      │      │      └─────────────┐
     ▼                    ▼      ▼                    ▼
┌──────────────┐  ┌──────────┐ ┌──────────┐ ┌────────────────┐
│  HR Agent    │  │ IT Agent │ │ Approval │ │ Booking Agent  │
│  port 8001   │  │ port 8002│ │ port 8003│ │   port 8005    │
│ Vercel AI SDK│  │ LLM+MCP  │ │  CrewAI  │ │  Google ADK    │
└──────┬───────┘  └────┬─────┘ └────┬─────┘ └───────┬────────┘
       │               │            │               │
       ▼               ▼            ▼               ▼
 ┌──────────┐  ┌─────────────┐ ┌──────────┐ ┌──────────┐
 │ HR API   │  │ MCP Server  │ │Approval  │ │Booking   │
 │ /api/hr  │  │  port 8020  │ │  API     │ │  API     │
 └──────────┘  │ LLM routing │ └──────────┘ └──────────┘
               │ + scope      │
               │   narrowing  │
               └──────┬──────┘
                      ▼
                ┌──────────┐
                │ IT API   │
                │ /api/it  │
                └──────────┘
```

### Key Components

| Component | Port | Framework | Description |
|-----------|------|-----------|-------------|
| **Orchestrator** | 8000 | OpenAI GPT-4o | Receives user requests, uses LLM to decompose into sub-tasks, exchanges tokens per agent, dispatches via A2A protocol |
| **HR Agent** | 8001 | **Vercel AI SDK** | Manages employee profiles using autonomous `@ai.tool` functions and `ai.run()` loop |
| **IT Agent** | 8002 | OpenAI GPT-4o-mini | IT provisioning (VPN, GitHub, AWS). Routes through MCP Server |
| **Approval Agent** | 8003 | **CrewAI** | Approval workflows using a CrewAI `Crew` with autonomous tool execution |
| **Booking Agent** | 8005 | **Google ADK** | Task scheduling & equipment delivery using Google Agent Development Kit |
| **IT MCP Server** | 8020 | FastMCP (SSE) | Intermediary between IT Agent and IT API. LLM-powered routing + scope-narrowing token exchange |
| **Visualizer** | 8200 | WebSocket | Real-time UI showing token flows and agent interactions |

---

## What's New — Agent Framework Upgrades

This implementation modernised each agent's LLM integration from raw OpenAI HTTP calls to production-grade AI frameworks:

### ✅ Approval Agent → CrewAI

The Approval Agent was refactored from a raw HTTP → OpenAI classification loop to a **CrewAI**-powered autonomous agent:

- A `crewai.Agent` with an `approval_manager` role handles the full decision flow
- Four `@crewai.tool` functions wrap the Approval REST API: `create_request`, `approve_request`, `reject_request`, `list_requests`
- Token propagation uses a `ContextVar` set before Crew kickoff so tools can make authenticated API calls without exposing secrets to the LLM
- `Crew.kickoff_async()` drives execution; the result is returned directly to the A2A client

### ✅ Booking Agent → Google ADK

The Booking Agent was migrated from a custom FastAPI+executor stack to **Google ADK** (`google-adk`):

- Uses `google.adk.agents.LlmAgent` with `google.adk.runners.Runner` for the agent loop
- A custom `A2aAgentExecutor` subclass captures the auth token from Starlette middleware and injects it via `ContextVar` before ADK tool execution
- `litellm` bridges ADK to the OpenAI `gpt-4o-mini` model
- ADK's native A2A support eliminates the need for a custom executor and message-passing boilerplate

### ✅ HR Agent → Vercel AI SDK (Python)

The HR Agent was migrated from a raw HTTP → OpenAI classification prompt to the **Vercel AI SDK Python package** (`vercel-ai-sdk`):

- Four module-level `@ai.tool` async functions (`create_employee`, `get_employee`, `list_employees`, `grant_privileges`) expose the HR API to the LLM
- Auth token is shared via a `contextvars.ContextVar` (`_current_token`), set by `HRAgent.process_request()` before calling `ai.run()`
- `ai.run(_hr_agent_fn, llm, query)` provides the Runtime context required by `@ai.tool` and `ai.stream_loop()`
- The LLM autonomously decides which tool(s) to call based on the natural language request — no classification prompt needed

> **Design note:** `@ai.tool` must decorate **module-level** async functions. Applying it to class methods causes a Pydantic schema error on the implicit `self` parameter. The `ContextVar` pattern solves token sharing cleanly without workarounds.

---

## Token Flow

```
User ──login──► WSO2 IS ──delegated token──► Orchestrator
                                                  │
                                    Token Broker performs
                                    RFC 8693 Token Exchange
                                    per agent (with actor token)
                                                  │
                              ┌───────────────────┼───────────────────┐
                              ▼                   ▼                   ▼
                      HR Token              IT Token            Booking Token
                    (hr:read,             (it:read,           (booking:read,
                     hr:write)             it:write)           booking:write)
                              │                   │
                              ▼                   ▼
                         HR API          MCP Server narrows scope:
                                         it:read+it:write → it:write only
                                         (Token Exchange, no actor token)
                                                  │
                                                  ▼
                                              IT API
```

### Token Exchange Flow (Orchestrator → Agent)

1. User authenticates via OAuth 2.0 Authorization Code + PKCE (`response_mode=direct`)
2. Orchestrator obtains a **delegated token** (all scopes)
3. For each agent, Token Broker performs **RFC 8693 Token Exchange**:
   - Gets **agent actor token** (3-step flow: authorize → authn → token)
   - Exchanges: subject_token (user) + actor_token (agent) → scoped token
   - Uses **Token Exchanger App** credentials for authentication
4. Agent receives a **scoped token** (only its required scopes)

### MCP Server Token Narrowing (IT Agent → IT API)

The IT MCP Server (SSE transport on port 8020) demonstrates an additional scope-narrowing layer:
- Receives IT Agent's token (`it:read + it:write`)
- For write operations: exchanges to **`it:write` only**
- Uses simplified exchange (no actor token, just Token Exchanger credentials)

---

## Prerequisites

- **Python 3.12** (required for CrewAI and Google ADK pre-built wheels)
- **WSO2 Identity Server** (local at `https://localhost:9443` or Asgardeo cloud)
- **OpenAI API Key** (for LLM classification and task decomposition)
- **Node.js** (optional, for MCP Inspector testing)

### Python Virtual Environment

```bash
python3.12 -m venv .venv
.venv\Scripts\activate        # Windows
# or: source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

> **Important:** All services must be started using the `.venv` Python interpreter to ensure `crewai`, `google-adk`, `vercel-ai-sdk`, and `litellm` are available.

---

## Setup Guide

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd a2a-reference-impl
python3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. Configure WSO2 Identity Server

See [ASGARDEO_SETUP.md](ASGARDEO_SETUP.md) for detailed WSO2 IS configuration.

#### Summary of Required Entities

**API Resources** — Create in WSO2 IS Console:

| Identifier | Scopes |
|------------|--------|
| `onboarding-api` | `hr:read`, `hr:write`, `it:read`, `it:write`, `approval:read`, `approval:write`, `booking:read`, `booking:write` |

**Applications:**

| Application | Grant Types | Purpose |
|-------------|------------|---------| 
| `onboarding-orchestrator` | Authorization Code, Client Credentials, Refresh Token | Main application for the orchestrator |
| `token-exchanger` | Token Exchange, Client Credentials | Performs all token exchanges on behalf of agents |
| `mcp-it-server` (optional) | Token Exchange | Registered for MCP server scope narrowing |

**AI Agents** (User Management → Agents):

| Agent Name | Linked Application | Purpose |
|------------|-------------------|---------| 
| `orchestrator-agent` | `onboarding-orchestrator` | Orchestrator identity |
| `hr-agent` | `onboarding-orchestrator` | HR worker identity |
| `it-agent` | `onboarding-orchestrator` | IT worker identity |
| `approval-agent` | `onboarding-orchestrator` | Approval worker identity |
| `booking-agent` | `onboarding-orchestrator` | Booking worker identity |

> **Note:** Worker agents don't need their own applications. They are registered as AI Agents linked to the orchestrator's application. The Token Exchanger app performs exchanges using agent actor tokens.

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# WSO2 Identity Server
ASGARDEO_ORG_NAME=carbon.super
ASGARDEO_BASE_URL=https://localhost:9443
ASGARDEO_TOKEN_URL=https://localhost:9443/oauth2/token
ASGARDEO_AUTHORIZE_URL=https://localhost:9443/oauth2/authorize
ASGARDEO_JWKS_URL=https://localhost:9443/oauth2/jwks

# Orchestrator Application
ORCHESTRATOR_CLIENT_ID=<from onboarding-orchestrator app>
ORCHESTRATOR_CLIENT_SECRET=<from onboarding-orchestrator app>

# Orchestrator Agent
ORCHESTRATOR_AGENT_ID=<from orchestrator-agent>
ORCHESTRATOR_AGENT_SECRET=<agent password>

# Worker Agent IDs (registered as AI Agents in WSO2 IS)
HR_AGENT_ID=<from hr-agent>
HR_AGENT_SECRET=<agent password>
IT_AGENT_ID=<from it-agent>
IT_AGENT_SECRET=<agent password>
APPROVAL_AGENT_ID=<from approval-agent>
APPROVAL_AGENT_SECRET=<agent password>
BOOKING_AGENT_ID=<from booking-agent>
BOOKING_AGENT_SECRET=<agent password>

# Token Exchanger Application
TOKEN_EXCHANGER_CLIENT_ID=<from token-exchanger app>
TOKEN_EXCHANGER_CLIENT_SECRET=<from token-exchanger app>

# MCP IT Server (optional, for scope narrowing demo)
MCP_IT_CLIENT_ID=<from mcp-it-server app>
MCP_IT_CLIENT_SECRET=<from mcp-it-server app>

# OpenAI
OPENAI_API_KEY=sk-proj-...

# API Audience
API_AUDIENCE=onboarding-api
```

### 4. Configuration File

`config.yaml` defines agent URLs, required scopes, and discovery settings. The Orchestrator reads this file at startup to dynamically discover agent endpoints — no hardcoded port mappings in code.

---

## Running the Application

### Start All Services (Windows — PowerShell)

The quickest way is to use the provided startup script which opens each service in its own terminal window:

```powershell
.\start_all_adk.ps1
```

### Manual Start (any OS)

Open **7 separate terminals** using the `.venv` Python interpreter:

```bash
# Terminal 1: IT MCP Server (must start before IT Agent)
.venv/bin/python src/mcp/it_mcp_server.py --transport sse --port 8020

# Terminal 2: HR Agent  (Vercel AI SDK)
.venv/bin/python -m agents.hr_agent

# Terminal 3: IT Agent
.venv/bin/python -m agents.it_agent

# Terminal 4: Approval Agent  (CrewAI)
.venv/bin/python -m agents.approval_agent

# Terminal 5: Booking Agent  (Google ADK)
.venv/bin/python -m agents.booking_agent_adk

# Terminal 6: Orchestrator (start last)
.venv/bin/python -m agents.orchestrator

# Terminal 7: Visualizer
.venv/bin/python visualizer_server.py
```

### Verify Services

| Service | Health / Discovery URL |
|---------|------------------------|
| Orchestrator | http://localhost:8000/health |
| HR Agent | http://localhost:8001/.well-known/agent-card.json |
| IT Agent | http://localhost:8002/.well-known/agent-card.json |
| Approval Agent | http://localhost:8003/.well-known/agent-card.json |
| Booking Agent | http://localhost:8005/.well-known/agent-card.json |
| IT MCP Server | http://localhost:8020/ |
| Visualizer | http://localhost:8200/ |

---

## Usage

### Step 1: Authenticate

```
http://localhost:8000/auth/login
```

This starts the OAuth 2.0 Authorization Code + PKCE flow with WSO2 IS.

### Step 2: Send Requests

```bash
# Full onboarding (all 5 agents)
curl -X POST http://localhost:8000/api/demo \
  -H "Content-Type: application/json" \
  -d '{"message": "Onboard Alice as Senior Software Engineer with IT tools and a booking for orientation"}'

# HR only
curl -X POST http://localhost:8000/api/demo \
  -H "Content-Type: application/json" \
  -d '{"message": "Create employee profile for John Doe as Data Scientist"}'

# IT provisioning (routes through MCP)
curl -X POST http://localhost:8000/api/demo \
  -H "Content-Type: application/json" \
  -d '{"message": "Set up GitHub and AWS access for employee EMP-001"}'

# Approval workflow (CrewAI)
curl -X POST http://localhost:8000/api/demo \
  -H "Content-Type: application/json" \
  -d '{"message": "Approve HR privilege grant for Bob"}'

# Booking (Google ADK)
curl -X POST http://localhost:8000/api/demo \
  -H "Content-Type: application/json" \
  -d '{"message": "Schedule orientation and equipment delivery for EMP-001"}'
```

### Step 3: Watch the Visualizer

Open http://localhost:8200/ to see real-time token flows, agent interactions, and LLM decisions.

---

## Project Structure

```
├── agents/
│   ├── orchestrator/           # Port 8000 — LLM task decomposition + dynamic routing
│   │   ├── __main__.py         #   Entry point, OAuth endpoints, A2A server
│   │   ├── agent.py            #   LLM decomposition, A2A client, token exchange
│   │   │                       #   Reads agent URLs dynamically from config.yaml
│   │   └── executor.py         #   A2A executor adapter
│   ├── hr_agent/               # Port 8001 — Employee management (Vercel AI SDK)
│   │   ├── __main__.py         #   Entry point, mounts HR API + A2A server
│   │   ├── agent.py            #   @ai.tool module-level functions + ai.run() loop
│   │   │                       #   Token shared via ContextVar (_current_token)
│   │   └── executor.py         #   A2A executor adapter
│   ├── it_agent/               # Port 8002 — IT provisioning via MCP (SSE)
│   │   ├── __main__.py         #   Entry point, mounts IT API + A2A server
│   │   ├── agent.py            #   Sends requests to MCP handle_it_request tool
│   │   └── executor.py         #   A2A executor adapter
│   ├── approval_agent/         # Port 8003 — Approval workflows (CrewAI)
│   │   ├── __main__.py         #   Entry point, mounts Approval API + A2A server
│   │   ├── agent.py            #   crewai.Crew + @tool API wrappers
│   │   │                       #   Token shared via ContextVar (current_token)
│   │   └── executor.py         #   A2A executor adapter
│   └── booking_agent_adk/      # Port 8005 — Task scheduling (Google ADK)
│       ├── __main__.py         #   Entry point, ADK Runner + custom A2aAgentExecutor
│       └── agent.py            #   google.adk.agents.LlmAgent with booking tools
├── src/
│   ├── apis/                   # FastAPI REST API routers
│   │   ├── hr_api.py           #   POST/GET /employees (requires hr:read, hr:write)
│   │   ├── it_api.py           #   POST/GET /provision/* (requires it:read, it:write)
│   │   ├── approval_api.py     #   POST/GET /requests (requires approval:*)
│   │   └── booking_api.py      #   POST/GET /tasks, /deliveries (requires booking:*)
│   ├── auth/                   # Authentication & token management
│   │   ├── asgardeo.py         #   WSO2 IS client (OAuth, actor tokens, token exchange)
│   │   ├── token_broker.py     #   Centralized token broker (session, exchange, audit)
│   │   ├── jwt_validator.py    #   JWT validation for API endpoints
│   │   └── utils.py            #   PKCE utilities
│   ├── mcp/                    # Model Context Protocol
│   │   └── it_mcp_server.py    #   MCP server (SSE, port 8020) with LLM routing + scope narrowing
│   ├── config.py               #   Pydantic settings (loads from .env)
│   ├── config_loader.py        #   YAML config loader (config.yaml)
│   └── log_broadcaster.py      #   Visualizer log broadcasting
├── visualizer/                 # Token flow visualization UI
├── config.yaml                 #   Agent config (URLs, scopes, discovery seed URLs)
├── requirements.txt            #   Python dependencies
├── start_all_adk.ps1           #   Windows PowerShell startup script
├── visualizer_server.py        #   WebSocket server for visualizer (port 8200)
├── ASGARDEO_SETUP.md           #   WSO2 IS configuration guide
└── .env.example                #   Environment variable template
```

---

## How Each Agent Works

### Orchestrator (GPT-4o)
1. Receives natural language request from user
2. **LLM decomposes** the request into ordered sub-tasks for available agents
3. Agent URLs are loaded **dynamically from `config.yaml`** — no hardcoded port mappings
4. For each task: performs **token exchange** (RFC 8693) to get a scoped token
5. Dispatches task to the target agent via **A2A protocol** (JSON-RPC)
6. Collects and aggregates results

### HR Agent (Vercel AI SDK)
1. Receives A2A request with `hr:read + hr:write` scoped token
2. Sets `_current_token` ContextVar so module-level tools can authenticate
3. `ai.run(_hr_agent_fn, llm, query)` drives an autonomous `stream_loop`
4. The LLM decides which `@ai.tool` to call (`create_employee`, `get_employee`, etc.)
5. Tools call the HR REST API directly using the token from ContextVar
6. Streamed `text_delta` output is aggregated and returned via A2A

### Approval Agent (CrewAI)
1. Receives A2A request with `approval:read + approval:write` scoped token
2. Stores token in a ContextVar; CrewAI `@tool` functions read it for API calls
3. A single `crewai.Crew` with an `approval_manager` agent and a task wrapping the query is kicked off
4. The agent autonomously calls `create_approval_request`, `approve_request`, etc.
5. Crew final output is returned via A2A protocol

### Booking Agent (Google ADK)
1. Receives A2A request with `booking:read + booking:write` scoped token
2. Custom `A2aAgentExecutor` injects the token into `_current_token` ContextVar before ADK executes
3. `google.adk.agents.LlmAgent` drives tool selection (schedule tasks, order equipment)
4. ADK tools call the Booking REST API with the scoped token
5. ADK response is translated back to A2A format

### IT Agent + MCP Server
1. IT Agent receives request with `it:read + it:write` token
2. Connects to MCP Server via **SSE transport** on port 8020
3. MCP Server's **LLM classifies** the request (vpn/github/aws/list)
4. MCP Server **narrows token scope** (e.g., `it:write` only for provisioning)
5. Calls IT API with the narrowed token
6. Returns result back through MCP → IT Agent → Orchestrator

---

## Protocols & Standards

| Protocol | Usage |
|----------|-------|
| **A2A (Agent-to-Agent)** | Communication between orchestrator and worker agents. JSON-RPC over HTTP with AgentCard discovery at `/.well-known/agent-card.json` |
| **MCP (Model Context Protocol)** | Communication between IT Agent and IT MCP Server. SSE transport (port 8020) |
| **OAuth 2.0 (Authorization Code + PKCE)** | User authentication via WSO2 IS with `response_mode=direct` |
| **RFC 8693 (Token Exchange)** | Delegated token exchange — orchestrator exchanges user token for agent-scoped tokens |
| **JWT** | Token format with scope and audience validation at API endpoints |

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python 3.12 | Runtime (required for framework compatibility) |
| FastAPI | REST API endpoints |
| Starlette | A2A agent HTTP servers |
| a2a-sdk | Official A2A protocol SDK |
| **vercel-ai-sdk** | HR Agent — autonomous tool-calling loop |
| **crewai** | Approval Agent — multi-agent crew framework |
| **google-adk** | Booking Agent — Google Agent Development Kit |
| **litellm** | OpenAI bridge for Google ADK |
| mcp (FastMCP) | IT MCP Server — Model Context Protocol SDK |
| OpenAI GPT-4o | LLM task decomposition (orchestrator) |
| OpenAI GPT-4o-mini | LLM request routing (IT Agent + MCP) |
| WSO2 Identity Server | OAuth 2.0, token exchange, JWT validation |
| httpx | Async HTTP client |
| pydantic-settings | Configuration management |
| structlog | Structured logging |
| WebSocket | Real-time visualizer updates |
