# MCP Client

The MCP Client node connects your AI Agent to an external tool server that implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Once connected, the agent can discover and call that server's tools as part of its reasoning loop.

---

## Connections

| Handle | Direction | Connects to |
|--------|-----------|-------------|
| Left | Input | AI Agent (right handle) |

Connect one or more MCP Client nodes to the **right handle** of an AI Agent. The agent sees all tools from all connected MCP servers as one unified list.

---

## Configuration

Double-click the MCP Client node to open its configuration.

### Basic

| Field | Required | Description |
|-------|----------|-------------|
| **MCP Server Name** | No | A friendly label shown in the auth flow diagram. Defaults to the node ID if left blank. |
| **MCP Server Endpoint** | **Yes** | The URL of the MCP server (e.g., `https://my-tools.example.com/mcp`). |

### Authentication

By default, MCP connections are unauthenticated. Toggle **Use MCP OAuth2** to enable authentication via [Asgardeo](https://wso2.com/asgardeo/).

| Field | Default | Description |
|-------|---------|-------------|
| **Use MCP OAuth2** | Off | Enable Asgardeo OAuth2 authentication before connecting |
| **Auth Flow** | Agent | Choose **Agent** (agent authenticates itself) or **OBO** (agent acts on behalf of the logged-in user) |
| **OAuth2 Configuration** | — | A saved configuration set containing Base URL, Client ID, and Scope. Select an existing one from the dropdown or click **+ Add** to create a new one. |

#### OAuth2 Configuration fields

When adding or editing an OAuth2 Configuration, fill in:

| Field | Description |
|-------|-------------|
| **Name** | A friendly label for reuse across nodes (e.g., `Bookings API – Dev`) |
| **Base URL** | Your Asgardeo organization URL (e.g., `https://api.asgardeo.io/t/your-org`) or WSO2 IS URL |
| **Client ID** | MCP client application client ID registered in Asgardeo/WSO2 IS |
| **Scope** | *(optional)* Space-separated OAuth2 scopes (e.g., `openid read_bookings`) |
| **Redirect URI** | Set automatically to the app's origin. Shown read-only for reference — register this value in your Asgardeo application. |

OAuth2 Configurations are saved globally in your browser and are not embedded in the workflow file. This means you can share or export a workflow without exposing your OAuth2 credentials, and reuse the same configuration across multiple MCP Client nodes.

> **Agent Credentials** (Agent ID and Secret) are configured on the **AI Agent** node as a saved credential set. The MCP Client reads them from the connected agent automatically.

---

## Auth Flows

### No authentication (default)

The MCP Client connects to the server with no authorization header. Use this for local development servers, public MCP endpoints, or any server that doesn't require authentication.

### Agent Flow

The agent authenticates with its own Agent ID and Secret before connecting. No user interaction is required.

**When to use:** The MCP server is a protected API and the agent acts autonomously (no user identity needs to be forwarded).

**What you need:**
- Toggle on `Use MCP OAuth2` and select `Agent Flow`
- An **OAuth2 Configuration** selected (or created via **+ Add**) with the Base URL, Client ID, and Scope from your registered MCP client application in Asgardeo
- **Agent Credentials** selected on the connected AI Agent node

When the AgentFlow runs, the agent authenticates with Asgardeo/WSO2 IS silently and obtains an access token. All tool calls include that token as an authorization header.

### OBO Flow (On-Behalf-Of)

The agent acts on behalf of you (the logged-in user). You must grant consent before the first message is processed.

**When to use:** The MCP server enforces per-user authorization. The request must carry the user's identity.

**What you need:**
- Toggle on `Use MCP OAuth2` and select `OBO Flow`
- An **OAuth2 Configuration** selected (or created via **+ Add**) with the Base URL, Client ID, and Scope from your registered MCP client application in Asgardeo
- **Agent Credentials** selected on the connected AI Agent node

When a tool call is needed, the chat panel shows an **Authorize** button. Clicking it opens a login popup where you authenticate with Asgardeo and grant consent. The resulting token is saved in your browser and reused for subsequent messages until it expires.

---

## Multiple MCP Clients

You can connect multiple MCP Client nodes to a single AI Agent. The agent sees all tools from all servers as one combined list.
Each MCP Client node maintains its own auth state, so you can mix and match authentication methods as needed.