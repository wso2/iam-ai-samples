# Agent Identity Quickstart - On-Behalf-Of (OBO) Flow

This guide explains how to run the `On-Behalf-Of (OBO) authentication flow` using Asgardeo with modern agent frameworks such as **LangChain** and **Google ADK**.

In this scenario, the AI agent authenticates on behalf of a user, using:

- Authorization Code Flow
- PKCE (Proof Key for Code Exchange) to ensure only your agent can securely exchange the authorization code for the OBO token
- Token exchange to obtain an OBO token that represents the user

Your agent then uses that OBO token to securely call MCP tools.

This example corresponds to the _“AI agent acting on behalf of a user”_ scenario described in the [Agent Authentication Guide](https://wso2.com/asgardeo/docs/guides/agentic-ai/ai-agents/agent-authentication/).

## Prerequisites

- Python 3.10 or higher
- An Asgardeo account and application setup
- pip (Python package installer)
- An MCP server secured with Asgardeo (you may use your own or follow the [MCP Auth Server quickstart](https://wso2.com/asgardeo/docs/quick-starts/mcp-auth-server/#add-auth-to-the-mcp-server) to set one up quickly).

## Directory Overview

This sample is located under:

```
agent-identity/python/on-behalf-of-flow/
├── README.md               # You are here
├── google-adk/             # OBO flow using the Google Agent Development Kit
│   ├── main.py
│   ├── oauth_callback.py   # lightweight callback server for Authorization code + PKCE flow
│   └── requirements.txt
└── langchain/              # OBO flow using LangChain
    ├── main.py
    ├── oauth_callback.py
    └── requirements.txt
```
Each framework folder (`google-adk` and `langchain`) contains the **OBO-enabled agent** plus the local callback server implementation.

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
    - Authorized Redirect URL 
      
      _The **authorized redirect URL** is the location Asgardeo sends users to after a successful login, typically the callback endpoint of the client application that connects to the MCP server. In this guide, we use the redirect URL: http://localhost:6274/oauth/callback, which corresponds to the local callback server that listens for Asgardeo’s redirection and captures the authorization code._
4. Finish the wizard

Make note of:
- **Client ID** (in the _Protocol_ tab)
- **Tenant name** (visible in the Asgardeo URL)

## Set Up the Project Locally

Navigate into either the `google-adk` or `langchain` folder depending on which framework you want to run.

Example:
```bash
   cd agent-identity/python/on-behalf-of-flow/langchain
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

## Understanding the OBO Flow

Here’s what happens when you run this sample:

1. The agent authenticates with its own Agent Credentials
2. The agent prepares an authorization URL for the user
3. A local callback server (`oauth_callback.py`) listens on port 6274
4. You open the authorization URL
5. You log in as a user (It is required to create a test user first in Asgardeo by following the instructions in the [Onboard a User guide](https://wso2.com/asgardeo/docs/guides/users/manage-users/#onboard-single-user{:target="_blank"}) to try out the login feature).
6. Upon successful login, Asgardeo redirects back to
```bash
http://localhost:6274/oauth/callback
```
7. The callback server captures:
- `code`
- `state`
8. The agent exchanges:
- authorization code
- PKCE code verifier
- agent token

  → and receives an `OBO token` from Asgardeo that represents the authenticated user
9. The agent then uses:
```bash
Authorization: Bearer <obo_token>
```
to call your MCP server.

## Running the OBO Flow

Ensure the secured MCP Server is up and running.

Navigate into either the `google-adk` or `langchain` folder depending on the framework of your choice and simply run:

```bash
python main.py
```

You will see the below:

```bash
Open this URL in your browser to authenticate:
https://api.asgardeo.io/...<full authorize URL>...

Waiting for authorization code...
```

### Steps:

1. Click or paste the URL into your browser
2. Log in as your test user
3. Upon success, the callback page will say: **Authentication successful. You can close this window.**
4. Return to the terminal and the agent continues automatically

Then you’ll be prompted:

```bash
Enter your question:
```

Example:

```bash
Enter your question: what is 76 + 8?
Agent Response: The sum of 76 and 8 is 84.
```

Your AI agent has now made a secure On-Behalf-Of call to your MCP server.
