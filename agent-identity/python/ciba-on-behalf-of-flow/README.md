# Agent Identity Quickstart - CIBA-based On-Behalf-Of (OBO) Flow

This guide explains how to run the `CIBA-based On-Behalf-Of (OBO) authentication flow` using Asgardeo with the **LangChain** framework.

In this scenario, the AI agent **steps up** from its own agent credentials to a **user-delegated OBO token** using the **CIBA (Client-Initiated Backchannel Authentication)** grant — without requiring a browser redirect on the agent's host. Instead, the user receives an **email notification** and approves the request on any device they choose.

This is ideal for:
- Back-office agents and CLI-only environments
- Server-side workers with no browser access
- Scenarios where the user authenticates on a different device

This example corresponds to the _"AI agent acting on behalf of a user"_ scenario described in the [Agent Authentication Guide](https://wso2.com/asgardeo/docs/guides/agentic-ai/ai-agents/agent-authentication/).

## Prerequisites

- Python 3.10 or higher
- An Asgardeo account and application setup
- pip (Python package installer)
- The Tasks MCP server from this repo (see [mcp-auth/python-tasks/](../../../mcp-auth/python-tasks/))

## Directory Overview

```
agent-identity/python/ciba-on-behalf-of-flow/
├── .env.example            # Environment variables template
├── README.md               # You are here
└── langchain/              # CIBA OBO flow using LangChain
    ├── main.py
    └── requirements.txt
```

No `common/` directory is needed — CIBA requires no local callback server.

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

## Configure an MCP Client Application with CIBA Enabled

CIBA requires a **confidential client** with a `client_secret`. To configure:

1. Go to `Applications → New Application`
2. Select `MCP Client Application` (or `Standard-Based Application` if CIBA is not available in the MCP template)
3. Provide:
   - Application name
   - Authorized Redirect URL: `http://localhost:6274/oauth/callback`
4. Finish the wizard

### Enable the CIBA grant

1. Go to the application's **Protocol** tab
2. Under **Allowed grant types**, enable:
   - `Client Credentials` (agent flow)
   - `Token Exchange` (OBO)
   - **`CIBA`**
3. Ensure a **Client Secret** is generated (confidential client) — copy it for your `.env` file

### Configure CIBA notification channel

1. In the application settings, navigate to the **CIBA** configuration
2. Enable the **Email** notification channel
3. The default expiry time (120 seconds) is suitable for testing

> **Note:** If the MCP Client Application template does not expose the CIBA grant toggle, create a **Standard-Based Application** instead. The scope configuration remains the same.

Make note of:
- **Client ID** (in the _Protocol_ tab)
- **Client Secret** (in the _Protocol_ tab)
- **Tenant name** (visible in the Asgardeo URL)

## Register the API Resource and Scopes

1. Go to `API Resources → + New API Resource`
2. Create an API resource (e.g., `tasks-api`)
3. Add the following scopes:

   | Scope | Description |
   |---|---|
   | `tasks:templates_read` | Read task templates |
   | `tasks:read` | Read user's personal tasks |
   | `tasks:write` | Create tasks for the user |

4. Go back to your MCP Client Application → **API Authorization** tab
5. Authorize the application for the `tasks-api` scopes

## Set Up the Project Locally

```bash
cd agent-identity/python/ciba-on-behalf-of-flow/langchain
```

### Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment Variables

Copy the `.env.example` in this directory to `.env` and replace the placeholders with your actual values:

```bash
cp .env.example .env
```

- `<your-tenant>` → Your tenant ID (visible in the Asgardeo console URL)
- `<your-client-id>` → from the MCP application
- `<your-client-secret>` → **Required for CIBA** — from the MCP application's Protocol tab
- `<your-agent-id>` / `<your-agent-secret>` → Values from your AI agent registration
- `<google-api-key>` → You can generate one from [Google AI Studio](https://aistudio.google.com/app/api-keys)

The CIBA-specific variables in `.env.example`:

```bash
CLIENT_SECRET=<your-client-secret>                    # Required for CIBA
TASKS_MCP_SERVER_URL=http://127.0.0.1:8100/mcp        # Tasks server
CIBA_NOTIFICATION_CHANNEL=email                       # email | sms | external
```

### User Pre-requisite

The end-user whose approval is requested must have a **verified email** on their Asgardeo profile. You can onboard a test user by following the [Onboard a User guide](https://wso2.com/asgardeo/docs/guides/users/manage-users/#onboard-single-user).

## Understanding the CIBA OBO Flow

Here's what happens when you run this sample:

1. The agent authenticates with its own Agent Credentials and obtains an **agent token**
2. The agent connects to the Tasks MCP server using the agent token
3. The agent successfully calls `list_task_templates` (low-scope tool — agent token is sufficient)
4. The agent attempts to call `list_my_tasks` → MCP server rejects with `insufficient_scope`
5. The agent prompts for the user's Asgardeo username (email)
6. The agent initiates a **CIBA request** with:
   - `login_hint` = the user's email
   - `actor_token` = the agent's token
   - `scopes` = `["openid", "tasks:templates_read", "tasks:read", "tasks:write"]`
   - `notification_channel` = `email`
7. Asgardeo sends an **email** to the user with an approval link
8. The user clicks the approval link on any device
9. The agent polls the token endpoint and receives an **OBO token** (`act.sub` = agent, `sub` = user)
10. The agent rebuilds the MCP client with the OBO token and retries — `list_my_tasks` now succeeds
11. Subsequent requests (e.g., `create_my_task`) use the cached OBO token without re-triggering CIBA

## Running the Flow

You need **two terminals**:

### Terminal A — Start the Tasks MCP Server

```bash
cd mcp-auth/python-tasks
python main.py
```

The server starts on `http://localhost:8100/mcp`.

### Terminal B — Run the Agent

```bash
cd agent-identity/python/ciba-on-behalf-of-flow/langchain
python main.py
```

## Example Transcript

```
##  This is a CIBA-based On-Behalf-Of (OBO) authentication sample...

Agent token obtained successfully.

Enter your question or type 'exit' to quit: list task templates
Agent Response: Here are the available task templates:
1. Weekly Report - Prepare and submit the weekly status report
2. Code Review - Review pending pull requests and provide feedback
...

Enter your question or type 'exit' to quit: show my tasks

The agent needs higher privileges to complete this request.
Enter your Asgardeo username (email): alice@example.com

Approval request sent via email. Waiting up to 120s for approval...
OBO token obtained successfully. Retrying your request...

Agent Response: You have no tasks yet.

Enter your question or type 'exit' to quit: add a task called buy milk
Agent Response: Task "buy milk" has been created successfully.

Enter your question or type 'exit' to quit: show my tasks
Agent Response: Here are your tasks:
1. buy milk (pending)

Enter your question or type 'exit' to quit: exit
Exiting the program. Goodbye!
```

> **Note:** After the first CIBA step-up, subsequent requests use the cached OBO token — no re-approval is needed until the token expires.

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Email not received | User's email not verified in Asgardeo | Verify the user's email in `Users → <user> → Profile` |
| `access_denied` error | User rejected the approval request | Try again — the user must click "Allow" in the email |
| `expired_token` / timeout | User did not respond within the expiry window (default 120s) | Try again and approve promptly |
| `slow_down` during polling | Polling too fast | Handled automatically by the SDK — no action needed |
| `Client secret is required` | `CLIENT_SECRET` not set in `.env` | CIBA requires a confidential client — add `CLIENT_SECRET` to your `.env` file. See [Configure CIBA grant](https://wso2.com/asgardeo/docs/guides/authentication/configure-ciba-grant/) |
| `insufficient_scope` after step-up | OBO token doesn't include the required scopes | Check API resource authorization in your Asgardeo application |
