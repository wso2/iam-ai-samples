# Demo MCP Server

A TypeScript MCP (Model Context Protocol) server with Asgardeo authentication, featuring a set of simple calculation tools.

## Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- Asgardeo account with an MCP Client application configured

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**
   - Create a `.env` file and update the values as needed:
     ```dotenv
     PORT=3000
     BASE_URL=https://api.asgardeo.io/t/<your-organization-name>
     MCP_RESOURCE=http://localhost:3000/mcp
     ```

3. **Configure Asgardeo Application:**
   - Ensure you have an MCP Client application registered in Asgardeo

## Running the Server

Start the MCP server with authentication:

```bash
npm start
```

The server will run on `http://localhost:3000/mcp` (or the port specified in `.env`).
