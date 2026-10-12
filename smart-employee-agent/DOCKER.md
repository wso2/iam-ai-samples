# Docker Deployment — Employee Portal

Run the three core services (HR Server, Agent, Client) using Docker Compose. The optional `it` profile starts the IT agent and IT MCP server for Patterns 4 and 7.

## Prerequisites

- Docker and Docker Compose v2 installed
- `.env` files configured in each service directory:
  - `hr-server/.env` (copy from `hr-server/.env.example`)
  - `agent/.env` (copy from `agent/.env.example`)
  - `client/.env` (copy from `client/.env.example`)
- Configure Asgardeo and the Gemini API key using the [main setup guide](README.md).
- For the `it` profile, also configure `it-agent/.env` and `it-server/.env`.

## Quick Start

```bash
# Build and start all services
docker compose up --build
```

This starts:

| Service     | Container Port | Host Port | Description                     |
|-------------|----------------|-----------|---------------------------------|
| `hr-server` | 8000           | 8000      | HR MCP + REST API server        |
| `agent`     | 5001           | 5001      | AI Agent server (LangChain)     |
| `client`    | 3000           | 3000      | Browser SPA (dev server)        |

Core startup dependencies: **hr-server** → **agent** → **client**. The IT services are excluded unless the profile is enabled:

```bash
# Configure both IT .env files and set IT_AGENT_ENABLED=true first.
docker compose --profile it up --build
```

The IT profile exposes `it-agent` on port 5002 and `it-server` on port 8001.

Open the app at **http://localhost:3000**.

## Viewing Logs

Each service runs in its own container, so logs are fully separated:

```bash
# All services together
docker compose logs

# Individual service logs
docker compose logs hr-server
docker compose logs agent
docker compose logs client

# Follow logs in real time (stream)
docker compose logs -f hr-server
docker compose logs -f agent
docker compose logs -f client

# Follow all services in real time
docker compose logs -f

# Show only the last 50 lines
docker compose logs --tail=50 hr-server

# Combine: last 50 lines then follow
docker compose logs --tail=50 -f hr-server
```

### What to look for in HR Server logs

The HR server logs MCP token details at INFO level. REST token lines are DEBUG logs. These logs demonstrate the three IAM patterns:

**Pattern 2 — Agent token (direct access, no user context):**
```
[MCP >> Agent Token] sub=5f3a8b2c-1234-... | name=Employee Portal | scopes=hr_basic_mcp, openid
```

**Pattern 3 — OBO token (agent acting on behalf of user):**
```
[MCP >> OBO Token] user(sub)=a1b2c3d4-5678-... | name=John Doe | agent(act.sub)=5f3a8b2c-1234-... | scopes=hr_basic_mcp, hr_self_mcp, openid, profile
```

**Pattern 1 — REST requests (browser SPA with user token, DEBUG logging):**
```
[REST /api/holidays >> User Token] sub=a1b2c3d4-5678-... | name=John Doe | scopes=hr_basic_rest, hr_self_rest
```

## Common Operations

```bash
# Start in detached mode (background)
docker compose up --build -d

# Stop all services
docker compose down

# Rebuild a single service
docker compose build hr-server
docker compose up -d hr-server

# Reload .env changes by recreating the affected services
docker compose up -d --no-deps --force-recreate hr-server agent

# View running containers
docker compose ps
```

## Networking

Inside Docker Compose, services reference each other by name:
- The **agent** connects to the HR server at `http://hr-server:8000/mcp`
- The **HR server** sends leave-approved webhooks to `http://agent:5001/api/events/leave-approved`.
- The **client** serves browser config pointing to `http://localhost:5001` and `http://localhost:8000` (the browser runs on the host, not inside Docker)

These internal URL overrides are set in `docker-compose.yml`. Browser redirect URIs continue to use localhost. For employee CIBA Calendar consent, configure the same `CIBA_CLIENT_ID` and `AGENT_WEBHOOK_SECRET` in both service `.env` files, plus the CIBA client secret in the agent. See [Pattern 5](README.md#pattern-5-employee-calendar-consent-with-ciba).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Agent can't reach HR server | Check `docker compose logs hr-server` — it must be healthy before the agent starts |
| Browser gets CORS errors | Ensure `ALLOWED_ORIGINS` in `hr-server/.env` includes `http://localhost:3000` |
| Token validation fails | Verify `JWKS_URL` and `AUTH_ISSUER` are reachable from inside the container |
| Webhook returns 403 / no CIBA email | Match the shared webhook secrets and recreate both containers after editing `.env` |
| Calendar token is missing | Apply the API-only token-sharing properties and the Google-only adaptive script from [Pattern 6](README.md#pattern-6-third-party-delegated-access-google-calendar) |
| OBO callback fails | Ensure `OBO_REDIRECT_URI` in `agent/.env` is `http://localhost:5001/api/obo/callback` |
