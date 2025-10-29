# MCP Auth Quickstart

A TypeScript MCP (Model Context Protocol) server with Asgardeo authentication, featuring a simple addition tool and greeting resource.

## Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- Asgardeo account with an [MCP Client application configured](https://wso2.com/asgardeo/docs/guides/agentic-ai/mcp/register-mcp-client-app/#register-an-mcp-client-application)

## Setup

1. **Clone or download the project**

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**
   - Create a `.env` file and update the values as needed:
     ```
     PORT=3000
     BASE_URL=https://api.asgardeo.io/t/myagents
     MCP_RESOURCE=http://localhost:3000/mcp
     ```

4. **Configure Asgardeo Application:**
   - Ensure you have an MCP Client application registered in Asgardeo
   - Use MCP inspector callback (`http://localhost:6274/oauth/callback`) as the Authorized Redirect URL
   - Note the `client-id` for testing

## Running the Server

Start the MCP server with authentication:

```bash
npm start
```

The server will run on `http://localhost:3000/mcp` (or the port specified in `.env`).

## Testing with MCP Inspector

1. **Run the inspector:**
   ```bash
   npx @modelcontextprotocol/inspector http://localhost:3000/mcp
   ```

2. **Configure Authentication:**
   - In the MCP Inspector, go to Authentication settings
   - Under "OAuth 2.0 Flow", enter your Asgardeo `client-id`
   - Follow the OAuth flow to authenticate

        You need to create a test user in Asgardeo by following the instructions in the [Onboard a Single User guide](https://wso2.com/asgardeo/docs/guides/users/onboard-users/#onboard-single-user) to authenticate.

   <img width="2992" height="2125" alt="screencapture-localhost-6274-2025-10-28-17_00_36" src="https://github.com/user-attachments/assets/f53ec739-bc6d-4269-a18c-af29b1a80bb8" />

3. **Test the server:**
   - List available tools and resources
   - Try the "add" tool with sample values
   - Query the "greeting" resource with URIs like `greeting://world`

## MCP Endpoints

- `POST /mcp` - MCP protocol endpoint (requires authentication)
- OAuth is automatically handled by the Asgardeo MCP SDK middleware

## Security

- All MCP requests require a valid authentication (Bearer token)
- CORS is enabled for development (Make sure to restrict in production)
- Unauthorized requests return 401 with WWW-Authenticate headers

## Development

- Built with TypeScript and Express
- Uses `@modelcontextprotocol/sdk` for MCP implementation
- Auth support via `@asgardeo/mcp-express`

## Troubleshooting

- Ensure your Asgardeo application has the correct redirect URI: `http://localhost:6274/oauth/callback`
- Check that the `.env` file has the correct Asgardeo base URL for your tenant
- Verify the MCP Inspector is running on the correct port

## License

Apache License 2.0
