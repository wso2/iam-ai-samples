# A2A Multi-Agent Travel Booking System

A production-ready multi-agent system demonstrating secure AI agent delegation using the **A2A Protocol**, **Asgardeo OAuth2**, and **OpenAI**.

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Chat Interface │────▶│  Orchestrator Agent  │────▶│  Booking Agent  │
│  (HTML/JS)      │     │  (localhost:8000)    │     │  (localhost:8001)│
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                               │                            │
                               ▼                            │
                        ┌──────────────┐                    │
                        │   Asgardeo   │◀───────────────────┘
                        │  (OAuth2 +   │   Token Validation
                        │  Delegation) │
                        └──────────────┘
```

## ✨ Features

- **A2A Protocol Compliant** - Uses official A2A SDK patterns for inter-agent communication
- **Startup Discovery** - Agents are automatically discovered and cached when the Orchestrator boots up.
- **Zero-Latency Routing** - Cached agent capabilities are injected directly into the LLM's system prompt, enabling immediate routing without redundant tool calls.
- **OAuth2 Delegation** - Secure "acting on behalf of" flow with Asgardeo (RFC 8693 Token Exchange).
- **Interactive Authentication** - Seamless browser-based login flow initiated by the Orchestrator.
- **JWT Token Validation** - All agent requests validated against Asgardeo JWKS.

## 📂 Design Patterns

### Hybrid Discovery & Zero-Latency Routing

This system uses a hybrid approach to agent discovery to maximize performance while maintaining flexibility:

1.  **Startup Phase (Discovery)**:
    *   When the Orchestrator starts, it automatically authenticates itself (getting an **Actor Token**).
    *   It immediately scans known URLs (e.g., `http://localhost:8001`) to fetch **Agent Cards**.
    *   These capabilities are cached in memory.

2.  **Runtime Phase (Routing)**:
    *   **User asks**: "Find flights to London"
    *   **Context Injection**: The Orchestrator injects the cached "Booking Agent" skills directly into the System Prompt.
    *   **LLM acts**: The LLM sees the available agent immediately and generates a routing decision (`call_agent`) **without** needing to call the `discover_agents` tool first.
    *   **Fallback**: If the LLM *doesn't* see a matching agent in the context, it can still choose to call `discover_agents` to refresh the list dynamically.

This pattern ensures the system is as fast as a hardcoded one, but as flexible as a dynamic one.

## 🔧 Prerequisites

- Python 3.10+
- Asgardeo Account (free tier available)
- OpenAI API Key

## ⚙️ Asgardeo Configuration

### Step 1: Create Organization
1. Go to [asgardeo.io](https://asgardeo.io) → **Get Started Free**
2. Create a new organization and note the name (`ASGARDEO_ORG`)

### Step 2: Register Application (Orchestrator)
1. **New Application** → **Standard-Based Application**
2. Name: `Orchestrator Agent`
3. Redirect URL: `http://localhost:8000/callback`
4. **Grant Types**: Authorization Code
5. **PKCE**: Mandatory (S256)
6. Copy `Client ID` and `Client Secret`

### Step 3: Register Booking API (Resource)
1. **API Resources** → **New API Resource**
2. Identifier: `booking-agent-api`
3. Scopes: `booking:read`, `booking:write`
4. Authorize these scopes in your Orchestrator Application

### Step 4: Register Agent Identity
1. **User Management** → **Agents** → **Register Agent**
2. Name: `Orchestrator Agent`
3. Copy `Agent ID` and `Agent Secret`
4. Link to Orchestrator Application under "Associated Applications"

### Step 5: Enable Delegation
1. Application Settings → **Delegation**
2. Enable "Allow Acting on Behalf of Users"
3. Add your Agent ID as an allowed actor

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd travel_a2a_other
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials from Asgardeo:

```bash
cp .env.example .env
```

### 3. Start the Agents

You need two terminal windows:

**Terminal 1: Booking Agent (Port 8001)**
```bash
python -m agents.booking_agent
```

**Terminal 2: Orchestrator Agent (Port 8000)**
```bash
python -m agents.orchestrator_agent
```
*Note: The Orchestrator will perform self-authentication and agent discovery immediately upon startup.*

### 4. Use the System

Open `chat_interface.html` in your browser.

1.  Type a message (e.g., "Hello")
2.  The Orchestrator will prompt you to log in via Asgardeo.
3.  Click the login button, authenticate in the popup/redirect.
4.  After success, type "Find me flights to Paris".
5.  **Observe**: The Orchestrator routes the request instantly to the Booking Agent using the delegated token!

## 🧪 Testing Utilities

- **Generate Auth URL**: Run `python auth/get_auth_url.py` to generate a valid PKCE-secured authorization URL for testing the flow manually in a browser.
- **Agent Card**: `curl http://localhost:8001/.well-known/agent-card.json`

## 📄 License

MIT License
