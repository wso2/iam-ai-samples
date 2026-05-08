# AI Agent

The AI Agent is the reasoning engine of your AgentFlow. It receives your message, consults an AI model (via the connected AI Service), and decides what to do - call a tool, call another tool, or give a final answer.

---

## Connections

| Handle | Direction | Connects to |
|--------|-----------|-------------|
| Left | Input | Chat Trigger |
| Top | Output | AI Service (required) |
| Right | Output | MCP Client (optional, one or more) |

The **top handle - AI Service** connection is required. The agent cannot run without an AI model to consult.

The **right handle - MCP Client** connections are optional. Add them when you want the agent to be able to call external tools.

---

## Configuration

Double-click the AI Agent node to open its configuration.

### Identity

| Field | Required | Description |
|-------|----------|-------------|
| **Agent Name** | No | A friendly label shown in the auth flow diagram and logs |
| **Agent Credentials** | Only if using OAuth2 | A saved credential set selected from the dropdown. Required when a connected MCP Client node has OAuth2 enabled. |

Agent credentials are stored globally and reused across all your AgentFlows. You can create, edit, and delete them directly from the AI Agent configuration panel.

#### Credential Fields

| Field | Description |
|-------|-------------|
| **Name** | A friendly label to identify this credential set in the dropdown |
| **Agent ID** | The agent username used to authenticate with Asgardeo |
| **Agent Secret** | The password for the Agent ID |
| **Base URL** | Your Asgardeo organization URL (e.g. `https://api.asgardeo.io/t/your-org`) or WSO2 IS URL (e.g. `https://localhost:9443`) |
| **Agent Application Client ID** | The OAuth2 application client ID registered in Asgardeo for this agent |

To obtain these values, follow the steps  below:
  1. Register an Interactive AI Agent by following this [guide](https://wso2.com/asgardeo/docs/guides/agentic-ai/ai-agents/register-and-manage-agents/#registering-an-ai-agent). Make sure to set the callback URL to `http://localhost:4829` during registration.
  2. Double-click the AI Agent node. In the **+ Add Agent Credentials** section, enter the obtained Agent ID, Agent Secret, Base URL, and Agent Application Client ID (You need to enable PKCE and Public client by visiting to this application), then click **Save**.
  3. Click **Test Fetching an Agent Token** button to verify that the credentials are correct and a token can be fetched successfully.

### Behavior

| Field | Default | Description |
|-------|---------|-------------|
| **System Prompt** | `You are a helpful assistant.` | Instructions sent to the AI model on every step. Use this to define the agent's persona, tone, and constraints. |
| **Max Tool Steps** | `6` | How many tool calls the agent can make before it must produce a final answer. Range: 1–12. |

### Memory

| Field | Default | Description |
|-------|---------|-------------|
| **Messages to Keep** | (empty) | If set, the last N conversations are saved and provided as context the next time you send a message. Leave empty to disable memory. |

---

## Tips

- **System Prompt first** — the clearest way to shape your agent's behavior is a well-written system prompt. Be specific about what the agent should and shouldn't do.
- **Max Tool Steps** — start with the default (6) and increase only if your agent regularly run out of steps. More steps means longer execution time.
- **Memory** — useful for conversational agents where context from previous messages matters. For stateless task automation, leave it disabled.
