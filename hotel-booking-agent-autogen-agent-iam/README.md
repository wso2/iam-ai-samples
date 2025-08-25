# Securing AI Agents with Asgardeo

This project demonstrates how to secure AI agents using [Asgardeo](https://wso2.com/asgardeo/). We use a hotel booking system as a practical use case to showcase how to implement robust security measures for your AI agents, ensuring that they operate within a secure and controlled environment.

## The Challenge: Securing AI Agents

As AI agents become more prevalent, securing them becomes a critical concern. How do you control what actions an AI agent can perform on behalf of a user? How do you control what actions an AI agent can perform on its own identity?

This sample provides a comprehensive solution to these challenges, demonstrating how to:

- **Manage Agent Identities:** Securely manage the identities of your AI agents, ensuring that they can be trusted and verified.
- **Authenticate and Authorize Agents:** Authenticate and authorize AI agents acting autonomously or on behalf of a user.
- **Implement Fine-Grained Access Control:** Enforce granular permissions for your AI agents, controlling what actions they can perform.

## The Gardeo Hotel: A Secure AI Use Case

To illustrate these security concepts, we've built the "Gardeo Hotel", a modern, AI-powered hotel booking website. The site allows users to search rooms, book rooms and view their reservations. It also features an AI assistant that can provide suggestions based on requirements and book rooms using natural language.

This is not just a simple chatbot. The AI assistant is a powerful tool that can access and modify sensitive user data. Therefore, it is crucial to ensure that it is secure.

### System Components

![Architecture Overview](docs/resources/image.png)

The system is composed of several key components working together to provide a secure AI agent experience:

#### User-Facing Layer
- **Browser:** The client interface where users interact with the system.
- **User Facing Front End:** A React application that provides the UI for searching, booking, and managing reservations.

#### AI Agent Layer
- **Gardeo Guest Assistant Agent (User-Facing / Delegated):** Handles natural language requests from guests to search rooms and create bookings. Utilizes AGENT_TOKEN for neutral/look‑ahead tasks (e.g., pre-fetching availability) and switches to OBO_TOKEN when performing user-sensitive actions (booking creation, viewing a user's reservations) after consent.
- **Gardeo Staff Management Agent (Autonomous Background):** Runs periodically to optimize concierge / staff assignments. It cross-references guest profiles (language, interests) with staff availability and expertise to assign the most suitable concierge. Operates purely with its own AGENT_TOKEN (no end-user delegation) and enforces least-privilege scopes (e.g., staff.read, assignment.write) without triggering user consent flows.

#### Backend Services Layer
- **Staff Management API:** Handles employee data, scheduling, and staff operations.
- **Booking API:** Core business logic for search and bookings.

> Note: There is no separate centralized "Auth Gateway" service in this sample. Each API performs **direct JWT validation** against Asgardeo (issuer, audience, expiration, signature via JWKS) and enforces scopes locally.

### Security Architecture

The security model implements several key principles:

#### 1. Identity-Based Security
- Each AI agent has its own secure identity managed through Asgardeo.
- All interactions are traced back to authenticated identities.

#### 2. Tool-Based Access Control
- AI agents access backend services only through registered tools.
- Each tool represents a specific capability (e.g., room booking, staff scheduling) and maps to defined scopes.

#### 3. OAuth 2.0 Integration (Decentralized Validation)
- Tokens (agent or OBO) are obtained via OAuth 2.0 flows.
- Each backend service independently validates JWTs (no gateway layer).
- Fine-grained scopes control what each agent (or delegated user context) can access.

### Token & Authorization Flows

Two complementary flows are implemented:

| Flow | Purpose | Token Type | Typical Scopes | Trigger |
|------|---------|-----------|----------------|---------|
| Agent Credentials | Let an agent act autonomously using its own identity. | AGENT_TOKEN | agent.read, bookings.search | Background tasks, tool bootstrap |
| On-Behalf-Of (OBO) | Allow an agent to act using a specific end-user's delegated permissions. | OBO_TOKEN | bookings.read, bookings.create | User-initiated natural language action |

#### Agent Token Flow
1. Agent requests an AGENT_TOKEN (client credentials / agent credentials grant).
2. Token is cached (with TTL) by the internal `TokenManager`.
3. Used for operations that do not require end-user delegation (e.g., internal enrichment).

#### On-Behalf-Of Flow (PKCE + Authorization Code)
1. Tool detects need for user delegation and calls `get_oauth_token` with token_type = OBO_TOKEN + required scopes.
2. System creates state + PKCE code verifier and produces an authorization URL.
3. Front end prompts user to authenticate/consent at Asgardeo.
4. Redirect callback hits backend callback endpoint -> `process_callback(state, code)`.
5. Backend exchanges code along with agent token to obtain OBO token.
6. OBO token cached for the (agent, user, scope-set) until expiry.

### Data Flow and Security

1. **User Interaction:** User issues a natural language request (e.g., "Book me a deluxe room for tomorrow").
2. **Agent Authorization Need:** Agent chooses correct tools; if user context required, initiates OBO flow (unless cached token exists).
3. **Controlled Access:** Tools attach the proper token (agent or OBO) when invoking backend APIs.
4. **Policy / Scope Enforcement:** Each API validates JWT (issuer, audience, signature via JWKS) and required scopes.
5. **Audit Trail:** All calls are logged with correlation IDs (agent id + user id where applicable).

### Fine-Grained Permissions
- **Scope-Based Access:** OAuth 2.0 scopes define exactly what each agent or delegated session can do.
- **Dynamic Authorization:** Permissions can be adjusted at runtime by changing scope assignments or policies in Asgardeo.
- **Principle of Least Privilege:** Agents only obtain minimal scopes required for the operation.

### Secure Tool Integration

Tools encapsulate backend capability boundaries. Recommended pattern:
1. Tool declares: required scopes, whether user delegation is required, target resource/audience.
2. Before execution, tool requests appropriate token via `AutogenAuthManager.get_oauth_token(AuthConfig(...))`.
3. Tool never stores raw credentials; only short-lived tokens from the manager.
4. Errors (expired token, missing consent) trigger re-authorization flow automatically.

#### SecureFunctionTool (Dynamic Auth Flow Selection)
The class `SecureFunctionTool` in `ai-agents/autogen/tool.py` wraps a business function and transparently injects the correct OAuth token:
- Expects the original function signature to include a `token: OAuthToken` parameter. The wrapper removes this parameter from the exposed tool interface so the LLM never sees or supplies the token directly.
- Accepts an `AuthSchema` (contains `manager` + `config`). The `config` is an `AuthConfig` defining scopes and `token_type` (AGENT_TOKEN vs OBO_TOKEN).
- On `run()` it calls `auth.manager.get_oauth_token(auth.config)`:
  - If `token_type == OAuthTokenType.OBO_TOKEN` and no cached token exists, the OBO (authorization code + PKCE) flow is initiated (user consent required).
  - If `token_type == OAuthTokenType.AGENT_TOKEN`, the agent credentials flow is used (no user interaction).
- Retrieved token is injected back into the call arguments as `token` before executing the underlying function.
- If no `auth` is supplied, a blank token is passed (useful for public / non-secured tools).

This pattern ensures:
- The agent reasoning layer cannot exfiltrate tokens (they are never part of the prompt/tool schema).
- Authorization intent is explicitly declared per tool via `AuthConfig` (making reviews & audits easier).
- Switching a tool from autonomous to delegated execution is a one-line change (just adjust `token_type` / scopes).

Minimal conceptual example:
```python
# Original secure function
def create_booking(token: OAuthToken, room_id: str, date: str):
    # token already validated upstream; perform API call
    ...

# Wrap as secure tool
secure_tool = SecureFunctionTool(
    func=create_booking,
    description="Create a booking (requires user delegation)",
    auth=AuthSchema(manager=auth_manager, config=AuthConfig(scopes=["bookings.create"], token_type=OAuthTokenType.OBO_TOKEN)),
)
```

### Folder Highlights
- `ai-agents/auth/auth_manager.py`: Implements unified agent + OBO token acquisition with PKCE, state management and caching.
- `ai-agents/app/tools.py`: (Tools definition / integration layer – see code for specific mappings.)
- `backend/app`: FastAPI services performing direct JWT + scope validation.

## Getting Started

You can use either Docker or a native setup. For detailed instructions, see [SETUP.md](SETUP.md).

### Prerequisites
- Docker & Docker Compose (for containerized setup)
- Python 3.11+, Node.js 16+
- An Asgardeo account & configured applications (agent app + user-facing app)

### Quick Start
1. Clone the repository:
   ```bash
   git clone https://github.com/shashimalcse/iam-ai-samples.git
   cd iam-ai-samples/hotel-booking-agent-autogen-agent-iam
   ```

## Configuration

### Sample Configuration Guide (Asgardeo)
Follow these steps to configure the identities, applications, and scopes required by the sample.

#### 1. Create / Identify Your Organization
Log into the Asgardeo Console. Note your organization (tenant) name (used in issuer URLs):
```
https://api.asgardeo.io/t/{ORG_NAME}
```

#### 2. Create Agents
1. Navigate to the "Agents" section in Asgardeo console.
2. Create a new agent "Gardeo Guest Assistant Agent" (Keep the agent secret confidential).
3. Create a new agent "Gardeo Staff Management Agent" (Keep the agent confidential).

#### 3. Create Users
1. Navigate to the "Users" section.
2. Create a new user

#### 4. Define API & Scopes
1. Navigate to Resources->API Resources.
2. Create a new API resource (e.g., `Hotel API`).
3. Set an identifier : `http://localhost:8001/api`.
4. Add scopes (minimum for this sample):
   - `read_bookings`
   - `create_bookings`
   - `admin_read_bookings`
   - `admin_update_bookings`
   - `admin_read_staff`
5. Save the API resource.
6. Create a new API resource (e.g., `Staff Management Agent API`).
7. Set an identifier : `http://localhost:8002/v1/invoke`.
8. Add scopes (minimum for this sample):
   - `invoke`

#### 5. Create Roles and Assign Users and Permissions
1. Navigate to the "Roles" section.
2. Create a new role "Guest" and assign the user created in step 3.
3. Assign the following scopes to the "Guest" role:
   - `read_bookings`
   - `create_bookings`
4. Create another role "Staff" and assign the Gardeo Staff Management Agent in step 2.
5. Assign the following scopes to the "Staff" role:
   - `admin_read_staff`
   - `admin_update_bookings`
   - `admin_read_bookings`

#### 6. Create Application for Website and Assistant Agent
1. Create a new Application (Type: Standard-Based) with `Allow AI agents to sign into this application`.
2. Enable Code grant with callback URL : `http://localhost:8000/callback` and enable Public client.
3. Authorize Hotel API with the scopes created in step 4 in API Authroization section.
4. Switch to organization role audience in Roles section. (select application role audience if you created application roles step 5).
5. Copy: Client ID.

#### 7. Create Application for Management Agent
1. Create a new Application (Type: M2M)
2. Authorize Staff Management Agent API with the scopes created in step 4 in API Authroization section.
3. Authorize SCIM2 User API with the `internal_user_mgt_view` scope.

#### 8. Populate Environment Variables
Create a `.env` file in each service directory (e.g., `backend`) with the following the .env.example as a reference.

#### 9. Run & Test Flows
1. Start services:
   ```bash
   docker-compose up -d
   ```
4. Access the application at `http://localhost:3000`.

## Additional Resources
- [Asgardeo Documentation](https://wso2.com/asgardeo/docs/)
- [OAuth 2.0 Security Best Practices](https://tools.ietf.org/html/draft-ietf-oauth-security-topics)
- AI Agent Security Guidelines (add internal link or doc)

---

**Note:** This is a demonstration project. For production use, implement additional hardening: structured audit logging, token binding, secrets management (vault), continuous authorization (re-check policies), and compliance measures as required.
