# Overview

Agent Auth Playground runs entirely in your browser. Open the app and you're ready to build and test authentication-aware AgentFlows.

---

## Before You Begin

You'll need an API key from at least one AI provider. The key is stored only in your browser and is sent only to that provider's API when you run an AgentFlow.

| Provider | Where to get a key |
|----------|--------------------|
| Google Gemini | [aistudio.google.com](https://aistudio.google.com) |
| OpenAI | [platform.openai.com](https://platform.openai.com) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |

An account on Asgardeo or WSO2 Identity Server is required to test OAuth2 authentication flows. Sign up for free at [asgardeo.io](https://asgardeo.io) or download WSO2 Identity Server from the [official website](https://wso2.com/products/downloads/?product=wso2is).

---

## AgentFlow Patterns

### Simple chatbot

```
Chat Trigger → AI Agent → AI Service
```

The agent answers questions directly using the LLM. No external tools.

### Agent with tools (MCP)

```
Chat Trigger → AI Agent → AI Service
                  └──→ MCP Client
```

Add one or more **MCP Client** nodes connected to the AI Agent's right handle. The agent can then call tools from external MCP servers. The LLM decides which tool to call at each step.

See [MCP Client](nodes/mcp-client.md) to learn how to connect to an MCP server.

### Agent with OAuth2-protected tools

#### Agent authenticates itself (Agent Flow)

```
Chat Trigger → AI Agent (Agent ID + Secret) → AI Service
                  └──→ MCP Client (OAuth2: Agent Flow)
```

Before connecting to the MCP server, the agent authenticates with Asgardeo using its own credentials and gets an access token.


#### Agent acting on behalf of the user (OBO)

```
Chat Trigger → AI Agent (Agent ID + Secret) → AI Service
                  └──→ MCP Client (OAuth2: OBO Flow)
```

When you send your first message, the chat panel shows an **Authorize** button. You log in to Asgardeo and grant consent. The agent then calls the MCP server using a token that carries your identity.

---

## Key Concepts

### Everything stays in your browser

AgentFlows, chat history, API keys, and auth tokens are all stored in your browser's local storage. Nothing is saved on any server. Clearing your browser data resets everything.

### Node connections are enforced

Each node type has fixed handles that only connect to specific other nodes. The canvas prevents invalid connections, so you can't accidentally wire things incorrectly.

| From | Handle | To |
|------|--------|-----|
| Chat Trigger | Right | AI Agent |
| AI Agent | Top | AI Service |
| AI Agent | Right | MCP Clients |

### Inspect the Auth Flow

After the AgentFlow finishes, click **View Auth Flow** in the chat panel header. This opens an interactive sequence diagram showing exactly what happened during execution - giving you a clear picture of the auth flow between the agent, Asgardeo, and the MCP server.

Use this to understand how your AgentFlow behaved, debug unexpected results, or explore what tokens were used.