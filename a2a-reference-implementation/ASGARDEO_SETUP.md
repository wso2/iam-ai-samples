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
| `approval-api` | `approval:read`, `approval:write` | Approval Service |
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

For each worker (HR, IT, Approval, Booking), you need an identity to perform **Token Exchange**.

### Example: HR Agent
1. **Create an Application** (Service App):
   - Name: `hr-service-app`
   - Grant Types: **Token Exchange**, Client Credentials.
   - Authorized for `hr-api`.
2. **Create an Agent**:
   - Name: `hr-agent`
   - Linked App: `hr-service-app`
3. **Configure**:
   - `HR_AGENT_CLIENT_ID`: From `hr-service-app`.
   - `HR_AGENT_CLIENT_SECRET`: From `hr-service-app`.
   - `HR_AGENT_ID`: From `hr-agent`.

*Repeat for IT, Approval, and Booking agents.*

---

## 5. Deployment Checks

Ensue your `.env` is updated:

```env
# HR Agent Identity
HR_AGENT_CLIENT_ID=...
HR_AGENT_CLIENT_SECRET=...
HR_AGENT_ID=...
```
