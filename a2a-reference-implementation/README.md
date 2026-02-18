# A2A + MCP Reference Implementation with WSO2 Identity Server

A reference implementation demonstrating the **Agent-to-Agent (A2A) protocol** with **Model Context Protocol (MCP)**, secured by **WSO2 Identity Server** using OAuth 2.0 token exchange (RFC 8693). Each agent uses **LLM-powered request classification** (OpenAI gpt-4o-mini) instead of hardcoded keyword matching.

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
            A2A    │      │      │      │    A2A
          ┌────────┘      │      │      └────────┐
          ▼               ▼      ▼               ▼
   ┌────────────┐  ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ HR Agent   │  │ IT Agent │ │ Approval │ │ Booking  │
   │ port 8001  │  │ port 8002│ │ port 8003│ │ port 8004│
   │ LLM class. │  │ LLM cls. │ │ LLM cls. │ │ LLM cls. │
   └─────┬──────┘  └────┬─────┘ └────┬─────┘ └────┬─────┘
         │               │            │             │
         ▼               ▼            ▼             ▼
   ┌──────────┐  ┌─────────────┐ ┌──────────┐ ┌──────────┐
   │ HR API   │  │ MCP Server  │ │Approval  │ │Booking   │
   │ /api/hr  │  │ (STDIO)     │ │  API     │ │  API     │
   └──────────┘  │ LLM routing │ └──────────┘ └──────────┘
                 │ + token      │
                 │   narrowing  │
                 └──────┬──────┘
                        ▼
                  ┌──────────┐
                  │ IT API   │
                  │ /api/it  │
                  └──────────┘
```

### Key Components

| Component | Port | Description |
|-----------|------|-------------|
| **Orchestrator** | 8000 | Receives user requests, uses LLM (GPT-4o) to decompose into sub-tasks, exchanges tokens per agent via Token Broker, dispatches via A2A protocol |
| **HR Agent** | 8001 | Manages employee profiles. LLM classifies → calls HR API |
| **IT Agent** | 8002 | IT provisioning (VPN, GitHub, AWS). Routes through MCP Server |
| **Approval Agent** | 8003 | Approval workflows. LLM classifies → calls Approval API |
| **Booking Agent** | 8004 | Task scheduling & deliveries. LLM classifies → calls Booking API |
| **IT MCP Server** | STDIO | Intermediary between IT Agent and IT API. LLM-powered routing + scope-narrowing token exchange (no actor token) |
| **Visualizer** | 8200 | Real-time WebSocket UI showing token flows and agent interactions |

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

1. User authenticates via OAuth 2.0 Authorization Code + PKCE (response_mode=direct)
2. Orchestrator obtains a **delegated token** (all scopes)
3. For each agent, Token Broker performs **RFC 8693 Token Exchange**:
   - Gets **agent actor token** (3-step flow: authorize → authn → token)
   - Exchanges: subject_token (user) + actor_token (agent) → scoped token
   - Uses **Token Exchanger App** credentials for authentication
4. Agent receives a **scoped token** (only its required scopes)

### MCP Server Token Narrowing (IT Agent → IT API)

The IT MCP Server demonstrates an additional scope-narrowing layer:
- Receives IT Agent's token (it:read + it:write)
- For read operations: exchanges to **it:read only**
- For write operations: exchanges to **it:write only**
- Uses simplified exchange (no actor token, just Token Exchanger credentials)

---

## Prerequisites

- **Python 3.11+**
- **WSO2 Identity Server** (local at https://localhost:9443 or Asgardeo cloud)
- **OpenAI API Key** (for LLM classification and task decomposition)
- **Node.js** (optional, for MCP Inspector testing)

---

## Setup Guide

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd a2a-reference-impl
pip install -r requirements.txt
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

Copy the example and fill in your credentials:

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

The `config.yaml` file defines agent URLs, scopes, and discovery settings. The defaults work out of the box for local development — no changes needed unless you modify ports.

---

## Running the Application

### Start All Services

Open **6 separate terminals** and run each service:

```bash
# Terminal 1: Visualizer (token flow UI)
python visualizer_server.py

# Terminal 2: HR Agent
python -m agents.hr_agent

# Terminal 3: IT Agent
python -m agents.it_agent

# Terminal 4: Approval Agent
python -m agents.approval_agent

# Terminal 5: Booking Agent
python -m agents.booking_agent

# Terminal 6: Orchestrator (start last — it discovers agents on startup)
python -m agents.orchestrator
```

### Verify Services

| Service | Health Check |
|---------|-------------|
| Orchestrator | http://localhost:8000/health |
| HR Agent | http://localhost:8001/.well-known/agent-card.json |
| IT Agent | http://localhost:8002/.well-known/agent-card.json |
| Approval Agent | http://localhost:8003/.well-known/agent-card.json |
| Booking Agent | http://localhost:8004/.well-known/agent-card.json |
| Visualizer | http://localhost:8200/ |

---

## Usage

### Step 1: Authenticate

Open your browser and navigate to:

```
http://localhost:8000/auth/login
```

This starts the OAuth 2.0 Authorization Code + PKCE flow with WSO2 IS. After successful login, you'll receive a delegated token.

### Step 2: Send Requests

Use the demo endpoint to send natural language requests:

```bash
# Simple onboarding
curl "http://localhost:8000/api/demo?message=Onboard+John+Doe+as+Software+Engineer"

# Multi-agent workflow
curl "http://localhost:8000/api/demo?message=Create+HR+profile+and+provision+VPN+for+Jane+Smith"

# IT provisioning (goes through MCP)
curl "http://localhost:8000/api/demo?message=Set+up+GitHub+access+for+employee+EMP-001"

# Approval workflow
curl "http://localhost:8000/api/demo?message=Grant+HR+admin+privileges+to+Bob"

# Booking
curl "http://localhost:8000/api/demo?message=Schedule+orientation+for+the+new+marketing+intern"
```

Or use the chat endpoint:

```bash
curl "http://localhost:8000/api/chat?message=Onboard+Alice+as+Data+Scientist"
```

### Step 3: Watch the Visualizer

Open http://localhost:8200/ to see real-time token flows:
- Token exchanges between orchestrator and agents
- MCP server scope narrowing
- Agent-to-API calls with scoped tokens
- LLM classification decisions

---

## Project Structure

```
├── agents/                     # A2A Agent servers
│   ├── orchestrator/           # Port 8000 — LLM task decomposition + routing
│   │   ├── __main__.py         #   Entry point, OAuth endpoints, A2A server
│   │   ├── agent.py            #   LLM decomposition, A2A client, token exchange
│   │   └── executor.py         #   A2A executor adapter
│   ├── hr_agent/               # Port 8001 — Employee management
│   │   ├── __main__.py         #   Entry point, mounts HR API + A2A server
│   │   ├── agent.py            #   LLM classification → HR API calls
│   │   └── executor.py         #   A2A executor adapter
│   ├── it_agent/               # Port 8002 — IT provisioning via MCP
│   │   ├── __main__.py         #   Entry point, mounts IT API + A2A server
│   │   ├── agent.py            #   Sends requests to MCP handle_it_request tool
│   │   └── executor.py         #   A2A executor adapter
│   ├── approval_agent/         # Port 8003 — Approval workflows
│   │   ├── __main__.py         #   Entry point, mounts Approval API + A2A server
│   │   ├── agent.py            #   LLM classification → Approval API calls
│   │   └── executor.py         #   A2A executor adapter
│   └── booking_agent/          # Port 8004 — Task scheduling
│       ├── __main__.py         #   Entry point, mounts Booking API + A2A server
│       ├── agent.py            #   LLM classification → Booking API calls
│       └── executor.py         #   A2A executor adapter
├── src/
│   ├── apis/                   # FastAPI REST API routers
│   │   ├── hr_api.py           #   POST/GET /employees (requires hr:read, hr:write)
│   │   ├── it_api.py           #   POST/GET /provision/* (requires it:read, it:write)
│   │   ├── approval_api.py     #   POST/GET /requests (requires approval:read, approval:write)
│   │   └── booking_api.py      #   POST/GET /tasks, /deliveries (requires booking:*)
│   ├── auth/                   # Authentication & token management
│   │   ├── asgardeo.py         #   WSO2 IS client (OAuth, actor tokens, token exchange)
│   │   ├── token_broker.py     #   Centralized token broker (session, exchange, audit)
│   │   ├── jwt_validator.py    #   JWT validation for API endpoints
│   │   └── utils.py            #   PKCE utilities
│   ├── mcp/                    # Model Context Protocol
│   │   └── it_mcp_server.py    #   MCP server with LLM routing + scope narrowing
│   ├── config.py               #   Pydantic settings (loads from .env)
│   ├── config_loader.py        #   YAML config loader (config.yaml)
│   └── log_broadcaster.py      #   Visualizer log broadcasting
├── visualizer/                 # Token flow visualization UI
│   ├── index.html              #   Main HTML page
│   ├── styles.css              #   Styles
│   └── app.js                  #   WebSocket client for live logs
├── config.yaml                 #   Agent configuration (URLs, scopes, discovery)
├── requirements.txt            #   Python dependencies
├── visualizer_server.py        #   WebSocket server for visualizer (port 8200)
├── demo_token_flow.py          #   Standalone token flow demo script
├── test_agent_app.py           #   Agent authentication test script
├── ASGARDEO_SETUP.md           #   WSO2 IS configuration guide
└── .env.example                #   Environment variable template
```

---

## How Each Agent Works

### Orchestrator (GPT-4o)
1. Receives natural language request from user
2. **LLM decomposes** the request into ordered sub-tasks for available agents
3. For each task: performs **token exchange** (RFC 8693) to get a scoped token
4. Dispatches task to the target agent via **A2A protocol** (JSON-RPC)
5. Collects and aggregates results

### Worker Agents (GPT-4o-mini)
Each worker agent uses LLM classification to determine the correct action:

1. Receives A2A request with scoped token
2. **LLM classifies** the request into an action + extracted parameters
3. Calls the appropriate **REST API endpoint** with the scoped token
4. Returns formatted result via A2A protocol

### IT Agent + MCP Server
The IT Agent demonstrates an additional MCP layer:

1. IT Agent receives request with `it:read + it:write` token
2. Sends raw request to MCP Server's `handle_it_request` tool (STDIO transport)
3. MCP Server's **LLM classifies** the request (vpn/github/aws/list)
4. MCP Server **narrows token scope** (e.g., it:write only for provisioning)
5. Calls IT API with the narrowed token
6. Returns result back through MCP → IT Agent → Orchestrator

---

## Testing

### Test Agent Authentication

Verify all agents can authenticate through WSO2 IS:

```bash
python test_agent_app.py
```

### Test Token Flow (Standalone)

Run the complete token exchange flow without starting servers:

```bash
python demo_token_flow.py
```

### Test MCP Server (Inspector)

Test the MCP server tools directly using the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector python src/mcp/it_mcp_server.py
```

---

## Protocols & Standards

| Protocol | Usage |
|----------|-------|
| **A2A (Agent-to-Agent)** | Communication between orchestrator and worker agents. JSON-RPC over HTTP with AgentCard discovery at `/.well-known/agent-card.json` |
| **MCP (Model Context Protocol)** | Communication between IT Agent and IT MCP Server. STDIO transport with FastMCP SDK |
| **OAuth 2.0 (Authorization Code + PKCE)** | User authentication via WSO2 IS with `response_mode=direct` |
| **RFC 8693 (Token Exchange)** | Delegated token exchange — orchestrator exchanges user token for agent-scoped tokens |
| **JWT** | Token format with scope and audience validation at API endpoints |

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python 3.11+ | Runtime |
| FastAPI | REST API endpoints |
| Starlette | A2A agent HTTP servers |
| a2a-sdk | Official A2A protocol SDK |
| mcp | Official MCP protocol SDK |
| OpenAI GPT-4o | LLM task decomposition (orchestrator) |
| OpenAI GPT-4o-mini | LLM request classification (all agents + MCP) |
| WSO2 Identity Server | OAuth 2.0, token exchange, JWT validation |
| httpx | Async HTTP client |
| pydantic-settings | Configuration management |
| structlog | Structured logging |
| WebSocket | Real-time visualizer updates |
