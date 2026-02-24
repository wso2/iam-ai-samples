# Asgardeo Configuration Guide for A2A Reference Implementation

## Understanding Asgardeo Entities

The A2A architecture requires specific entities in Asgardeo to manage identity, delegation, and token exchange.

| Component | Asgardeo Entity | Purpose |
|-----------|-----------------|---------|
| **Orchestrator** | App + Agent | Initiates workflows, acts on behalf of users. |
| **Worker Agents (HR, IT, etc.)** | App (optional) + Agent | Performs token exchange using its own identity. |
| **APIs (HR, IT, etc.)** | API Resource | Validates tokens (audiences & scopes). |

---

## 🔍 Where to find your Credentials

### 1. Client ID & Client Secret
These belong to the **Application**.
1. Go to **Applications**.
2. Select your application (e.g., `onboarding-orchestrator`).
3. Go to the **Protocol** tab (OIDC).
4. Copy **Client ID** and **Client Secret**.

### 2. Agent ID
This belongs to the **Agent**.
1. Go to **User Management** > **Agents**.
2. Select your agent (e.g., `hr-agent`).
3. In the Overview or Connection details, copy the **Agent ID** (a UUID).
   * *Note: This is DIFFERENT from the Client ID.*
4. If you see an **Agent Secret**, copy that too (though often the Agent authenticates via its associated Client's credentials or mutual TLS).

---

## 1. API Resources (Audiences)

Create the following API Resources to define the "Audiences" our agents will target.

| Identifier | Scopes | Description |
|------------|--------|-------------|
| `onboarding-api` | (All below) | Primary resource for Orchestrator |
| `hr-api` | `hr:read`, `hr:write` | HR Service |
| `it-api` | `it:read`, `it:write` | IT Service |
| `approval-api` | `approval:read`, `approval:write` | Finance & Payroll Service |
| `booking-api` | `booking:read`, `booking:write` | Booking Service |

---

## 2. Orchestrator Identity

### Application
- **Name**: `onboarding-orchestrator`
- **Protocol**: OIDC
- **Grant Types**: Auth Code, Client Credentials, Refresh Token
- **Callback**: `http://localhost:8000/callback`
- **Scopes**: authorize for `onboarding-api` (all scopes)

### Agent
- **Name**: `orchestrator-agent`
- **Linked App**: `onboarding-orchestrator`
- **Description**: "AI Director Agent"

---

## 3. Worker Agent Identities

For each worker (HR, IT, Payroll, Booking), you need an identity to perform **Token Exchange**.

> **Architecture note:** Worker agents do **not** need their own Applications. They are registered as AI Agents linked to the `onboarding-orchestrator` application. The `token-exchanger` app performs RFC 8693 token exchange using each agent's actor token.

### HR Agent
1. Go to **User Management → Agents → New Agent**
2. **Name**: `hr-agent` — **Linked App**: `onboarding-orchestrator`
3. Copy the **Agent ID** (UUID) and set an **Agent Secret**
4. Add to `.env`: `HR_AGENT_ID=<uuid>` and `HR_AGENT_SECRET=<password>`
5. Scopes granted: `hr:read`, `hr:write`

### IT Agent
1. Go to **User Management → Agents → New Agent**
2. **Name**: `it-agent` — **Linked App**: `onboarding-orchestrator`
3. Copy the **Agent ID** and set an **Agent Secret**
4. Add to `.env`: `IT_AGENT_ID=<uuid>` and `IT_AGENT_SECRET=<password>`
5. Scopes granted: `it:read`, `it:write`

### Finance & Payroll Agent
1. Go to **User Management → Agents → New Agent**
2. **Name**: `payroll-agent` — **Linked App**: `onboarding-orchestrator`
3. Copy the **Agent ID** and set an **Agent Secret**
4. Add to `.env`: `PAYROLL_AGENT_ID=<uuid>` and `PAYROLL_AGENT_SECRET=<password>`
5. Scopes granted: `approval:read`, `approval:write` *(the payroll API reuses the approval-api resource)*

### Booking Agent
1. Go to **User Management → Agents → New Agent**
2. **Name**: `booking-agent` — **Linked App**: `onboarding-orchestrator`
3. Copy the **Agent ID** and set an **Agent Secret**
4. Add to `.env`: `BOOKING_AGENT_ID=<uuid>` and `BOOKING_AGENT_SECRET=<password>`
5. Scopes granted: `booking:read`, `booking:write`

---

## 4. Token Exchanger Application

This is the **only** application that needs `Token Exchange` grant type. All RFC 8693 exchanges (orchestrator → worker agents) go through this app.

1. Go to **Applications → New Application → Standard-Based App**
2. **Name**: `token-exchanger`
3. **Grant Types**: Token Exchange, Client Credentials
4. **Authorized API Resources**: `onboarding-api` (all scopes)
5. Copy **Client ID** and **Client Secret**
6. Add to `.env`: `TOKEN_EXCHANGER_CLIENT_ID=<id>` and `TOKEN_EXCHANGER_CLIENT_SECRET=<secret>`

---

## 5. Deployment Checks

Ensure your `.env` is fully populated:

```env
# Orchestrator Application
ORCHESTRATOR_CLIENT_ID=...
ORCHESTRATOR_CLIENT_SECRET=...
ORCHESTRATOR_AGENT_ID=...
ORCHESTRATOR_AGENT_SECRET=...

# Worker Agents (all linked to onboarding-orchestrator app)
HR_AGENT_ID=...
HR_AGENT_SECRET=...

IT_AGENT_ID=...
IT_AGENT_SECRET=...

# Finance & Payroll Agent (uses approval:read, approval:write scopes)
PAYROLL_AGENT_ID=...
PAYROLL_AGENT_SECRET=...

BOOKING_AGENT_ID=...
BOOKING_AGENT_SECRET=...

# Token Exchanger Application
TOKEN_EXCHANGER_CLIENT_ID=...
TOKEN_EXCHANGER_CLIENT_SECRET=...
```

> **Tip:** The most common cause of `Missing agent_id` errors is a blank or missing `PAYROLL_AGENT_ID` / `PAYROLL_AGENT_SECRET` in `.env`. Double-check these are set to the UUID values from Asgardeo — not left blank.
