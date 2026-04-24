# MCP Auth Python Tasks Server - Asgardeo Integration

A secured MCP server that exposes task-management tools with **per-tool scope enforcement**, designed to demonstrate the CIBA-based OBO step-up flow. Runs on port **8100** so it coexists with the existing calculator server on port 8000.

## Prerequisites

- Python 3.12 or higher
- Asgardeo account and application setup
- pip (Python package installer)

## Project Structure

```
├── main.py              # FastMCP server with task tools and per-tool scope checks
├── jwt_validator.py     # JWT validation module
├── .env                 # Environment variables configuration
├── README.md            # This file
└── requirements.txt     # Python dependencies
```

## Installation

1. **Create a virtual environment (recommended)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install required dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Copy `.env.example` to `.env` and fill in your Asgardeo configuration:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `AUTH_ISSUER` | Asgardeo token issuer URL |
   | `CLIENT_ID` | OAuth2 client ID from Asgardeo |
   | `JWKS_URL` | Asgardeo JWKS endpoint URL |
   | `MCP_SERVER_PORT` | Server port (default: `8100`) |

## Asgardeo Configuration

### API Resource & Scopes

Register an API resource in Asgardeo with the following scopes:

| Scope | Description |
|---|---|
| `tasks:templates_read` | Read task templates (non-user-specific) |
| `tasks:read` | Read user's personal tasks |
| `tasks:write` | Create tasks for the user |

Authorize your MCP Client Application for these scopes.

## Running the Server

```bash
python main.py
```

The server starts on `http://localhost:8100/mcp` using the `streamable-http` transport.

## Available Tools

| Tool | Required Scope | Description |
|---|---|---|
| `list_task_templates` | `tasks:templates_read` | Returns a static list of suggested task templates. No user data. |
| `list_my_tasks` | `tasks:read` | Returns the caller's personal tasks (keyed by `sub` claim). |
| `create_my_task` | `tasks:write` | Creates a task for the caller. |

> **Note:** `list_my_tasks` and `create_my_task` require an OBO token with the user's `sub` claim. Task storage is in-memory and resets on server restart.
