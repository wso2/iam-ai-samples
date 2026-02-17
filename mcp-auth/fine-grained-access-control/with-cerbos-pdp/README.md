# Secure MCP Server with WSO2 IAM and Cerbos

This sample demonstrates how to secure a Model Context Protocol (MCP) server with fine-grained tool-level access control using WSO2 Identity Server (or Asgardeo) for authentication and Cerbos PDP for authorization.

It implements a two-tier access control mechanism:
1. **Tool Discovery**: Controls which tools are visible to the user based on their roles.
2. **Tool Execution**: Controls whether a user can execute a tool based on the scopes in their access token.

## Prerequisites

- **Node.js** (v18 or higher)
- **Docker** (to run Cerbos PDP)
- **WSO2 Identity Server** or **Asgardeo** account
- **MCP Client** (e.g., Claude Desktop, Zed, or a CLI client)

## Setup

Clone this repository and navigate to the `mcp-auth/fine-grained-access-control/with-cerbos-pdp/` directory.

### 1. Install dependencies

```bash
npm install
```

### 2. Run Cerbos PDP

This sample includes a `policies` directory with the necessary Cerbos policies.

```bash
docker run --rm --name cerbos -d -p 3593:3593 -v $(pwd)/policies:/policies \
  ghcr.io/cerbos/cerbos:latest server
```

Refer to the [Cerbos](https://github.com/cerbos/cerbos) for more details on running the PDP and writing policies.

### 3. Configure WSO2 Identity Server / Asgardeo

#### Register an MCP Server

1. **Log in** to the WSO2 Identity Server / Asgardeo Console.
2. Go to **Resources** > **MCP Servers**.
3. Click **+ New MCP Server**.
4. Enter the **Identifier** and a **Display Name**.
5. Go to the **Scopes** tab and add the following scopes with desired descriptions:
    - `add`
    - `subtract`
    - `multiply`
    - `divide`

6. Click **Create**.

#### Register an MCP Client Application

1. Go to **Applications** > **New Application**.
2. Select the **MCP Client Application** template.
3. Enter a **Name** for your application.
4. Set the **Authorized redirect URL**.
    - If testing with the **MCP Inspector** (web-based), use: `http://localhost:6274/oauth/callback`
    - Or use the callback URL specific to your MCP client (e.g., Claude Desktop).
5. Click **Create**.
6. In the **Roles** tab, configure **Role Audience** as "Organization".
7. In the **Protocol** tab, under **Access Token** > **Access token attributes**, select "roles", so that the roles are included in the access token.
8. Click **Update**.

#### Authorize the Client

1. In your newly created **MCP Client Application**, go to the **Authorization** tab.
2. Click **Authorize a resource**.
3. Select the **MCP Server** you created earlier from the **Resource** dropdown.
4. In **Authorized Scopes**, select the scopes this client should be able to request (e.g., all math scopes).
5. Click **Finish**.

### 4. Configure User Roles

To test the fine-grained access, create users with different roles:

1. **Create Roles**: (e.g., `admin`, `user`).
    - `admin` role should have access to all tools (all scopes).
    - `user` role should have limited access (e.g., only `add` and `subtract`).
2. **Assign Users**:
    - Assign `admin` role to one user (should have access to all tools).
    - Assign `user` role to another (might have limited access based on your policies).

### 5. Configure the Server

Open `server.ts` and update the authentication configuration with your WSO2/Asgardeo details:

```typescript
const mcpAuthServer = new McpAuthServer({
    baseUrl: 'https://api.asgardeo.io/t/<your_org>', // Update this
    issuer: 'https://api.asgardeo.io/t/<your_org>/oauth2/token', // Update this
    resource: `http://localhost:${port}/mcp`,
});
```

### 6. Run the Server

```bash
npm start
```

## How it Works

The server implements a two-phase authorization strategy:

1. **Tool Discovery (Role-Based)**:
   When the client connects, the server checks the `mcp::math_discovery` policy in Cerbos.
   - **Admins** see all available tools.
   - **Guests** see a restricted list (e.g., only `add`, `subtract`, and `multiply`).

2. **Tool Execution (Scope-Based)**:
   When a tool is invoked, the server checks the `mcp::math` policy.
   - The user's token must contain the specific **scope** (e.g., `add`) required for the operation.
   - This ensures that even if a tool is discovered, it cannot be executed without the proper OAuth2 scope.

## Testing with MCP Inspector

1. Open the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (or run it locally via `npx @modelcontextprotocol/inspector`).
2. Connect to your server at `http://localhost:3000/mcp`.
3. In the Inspector's **Authentication** or connection settings:
    - Select **OAuth 2.0**.
    - Enter the **Client ID** from your WSO2 MCP Client Application.
    - Set the **Authorization URL** and **Token URL** (found in your WSO2 application's *Protocol* tab).
    - Request the scopes: `openid profile add subtract multiply divide`
4. Log in with your test users to observe different behaviors.
    - **Admin User**: Should see and be able to execute all tools.
    - **Guest**: Should see limited tools and get "Forbidden" errors when trying to execute tools without the required scopes.

## How to do just-in-time authorization demand for a tool that the MCP Host can see but doesn't have access to?


When a user authenticates, the MCP client initially requests a token with **minimal privileges** — typically just `openid` and `profile` scopes. The tool discovery phase uses **roles** (included in the token) to determine which tools are visible to the user via Cerbos policies.

Here's how just-in-time authorization works:

1. **Initial Token with Least Privileges**: The MCP client obtains an access token with only basic scopes (e.g., `openid profile`). Tool discovery is driven by the user's **roles** in the token, so the user can still see the tools they are entitled to.

2. **Tool Invocation Returns Forbidden**: When the user attempts to execute a tool (e.g., `multiply`), the server checks for the required scope (e.g., `multiply`) in the access token. Since the token was obtained with minimal scopes, this check fails and the server returns a **Forbidden** response, indicating the specific scope required (e.g., `multiply`).

3. **Client Initiates a New Authorization Request**: Upon receiving the forbidden response, the MCP client can automatically initiate a **new OAuth2 authorization request** to WSO2 Identity Server, this time including the additional required scope(s) (e.g., `openid profile multiply`). The user is prompted to **authorize** the additional scope.

4. **SSO and Token Reissuance**: If the user already has an active session with WSO2 IS (via SSO), they won't need to re-enter credentials. If the user's role in WSO2 grants them permission for that scope, a **new access token** is issued with the additional scope included. The MCP client can then retry the tool invocation with the upgraded token.

5. **Access Denied If Unauthorized**: If the user's role does not permit the requested scope, WSO2 IS will deny the scope upgrading request, and the user will continue to be unable to execute the tool.

6. **Principle of Least Privilege**: This pattern allows for dynamic, just-in-time access control where clients can request elevated permissions as needed, without obtaining excessive privileges upfront. 



