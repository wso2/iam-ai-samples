# Agent Identity Quickstart — Agent Authentication Flow

This guide walks you through running the **Agent Authentication Flow** sample for authenticating AI agents using **Asgardeo** and securely connecting to an MCP server through modern agent frameworks such as **LangChain** and **Google ADK**.

In this flow, the AI agent authenticates by itself (not on behalf of a user) using its Agent Credentials and obtains a valid access token to call MCP tools securely.

This example corresponds to the _“AI agent acting on its own”_ scenario described in the [Agent Authentication Guide](https://wso2.com/asgardeo/docs/guides/agentic-ai/ai-agents/agent-authentication/).

## Prerequisites

- Python 3.10 or higher
- An Asgardeo account and application setup
- pip (Python package installer)
- An MCP server secured with Asgardeo (you may use your own or follow the [MCP Auth Server quickstart](https://wso2.com/asgardeo/docs/quick-starts/mcp-auth-server/#add-auth-to-the-mcp-server) to set one up quickly).

## Directory Overview

```
agent-identity/python/agent-auth-flow/
├── README.md           # You are here
├── google-adk/         # Agent Authentication flow using the Google Agent Development Kit
│   ├── main.py
│   └── requirements.txt
└── langchain/          # Agent Authentication flow using LangChain framework
    ├── main.py
    └── requirements.txt
```

Each framework folder (`google-adk` and `langchain`) contains a runnable `main.py` demonstrating how an agent:

- Authenticates itself with Asgardeo using Agent Credentials, and
- Calls a secured MCP server using the issued token.

## Register an AI Agent in Asgardeo

1. Sign in to `Asgardeo Console → Agents`
2. Click `+ New Agent`
3. Provide:
   - Name (required)
   - Description (optional)
4. Click `Create`

You will receive:
- Agent ID
- Agent Secret (shown once) → store securely

You will need these values for the `.env` file.

## Configure an MCP Client Application

For the agent to authenticate and talk to a secured MCP server:

1. Go to `Applications → New Application`
2. Select `MCP Client Application`
3. Provide:
    - Application name
    - Authorized Redirect URL (eg: http://localhost:6274/oauth/callback)
      
        _The **authorized redirect URL** is the location Asgardeo uses to send users after a successful login. In the direct agent authentication flow, this value isn’t used because no user sign-in occurs. However, the same application can also be used for the **On-Behalf-Of (OBO)** flow, where user redirection is required. Therefore, for consistency and future use, we can set the redirect URL to:
http://localhost:6274/oauth/callback._
4. Finish the wizard

Make note of:
- **Client ID** (in the _Protocol_ tab)
- **Tenant name** (visible in the Asgardeo URL)

## Set Up the Project Locally

Navigate into either the `google-adk` or `langchain` folder depending on which framework you want to run.

Example:
```bash
   cd agent-identity/python/agent-auth-flow/langchain
```

### Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

Each folder includes its own `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Configure Environment Variables

Update the `.env` file located at `agent-identity/python` by replacing the following placeholders with your actual values:

- `<your-tenant>` → Your tenant ID (visible in the Asgardeo console URL)
- `<your-client-id>` → from the MCP application
- `<your-agent-id>` / `<your-agent-secret>` → Values from your AI agent registration
- `<google-api-key>` → You can generate one from [Google AI Studio](https://aistudio.google.com/app/api-keys)
- `<mcp-server-url>` → your secured MCP server endpoint

If you don’t already have an MCP server running, you can quickly set one up by following the [MCP Authentication Quickstart](https://github.com/wso2/iam-ai-samples/tree/main/mcp-auth/python) guide. When using the default configuration from that guide, your MCP server URL will be: http://127.0.0.1:8000/mcp.

## Running the Agent Authentication Flow

Ensure the secured MCP Server is up and running.

Navigate into either the `google-adk` or `langchain` folder depending on the framework of your choice and simply run:

```bash
python main.py
```

### What the agent will do:

1. Authenticate with Asgardeo using `Agent Credentials`
2. Obtain a valid `agent access token`
3. Connect to your MCP server using:

```bash
Authorization: Bearer <token>
```
4. Invoke MCP tools through LLM reasoning

Example interaction:

```bash
Enter your question: Can you add six and 9?
Agent Response: The sum of 6 and 9 is 15.
```

## Understanding the Agent Authentication Flow

This flow is used when:

    ✔ The agent is acting independently
    ✔ No end-user is involved
    ✔ Tokens represent the agent itself

If you want to authenticate on behalf of a user using PKCE and authorization code flow, refer to:
➡ `agent-identity/python/on-behalf-of-flow/README.md`
