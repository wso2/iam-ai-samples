import { McpServer, ResourceTemplate } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import express from 'express';
import cors from 'cors'; // Add this import
import { z } from 'zod';
import {McpAuthServer} from '@asgardeo/mcp-express';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

const port = parseInt(process.env.PORT || '3000');

// Initialize McpAuthServer (Asgardeo auth middleware)
const mcpAuthServer = new McpAuthServer({
  baseUrl: process.env.BASE_URL!,
  issuer: `${process.env.BASE_URL}/oauth2/token`,
  resource: process.env.MCP_RESOURCE || `http://localhost:${port}/mcp`
});

// Create an MCP server
const server = new McpServer({
    name: 'demo-auth-server',
    version: '1.0.0'
});

// Register a simple addition tool
server.registerTool(
    'add',
    {
        title: 'Addition Tool',
        description: 'Add two numbers',
        inputSchema: { a: z.number(), b: z.number() },
        outputSchema: { result: z.number() }
    },
    async ({ a, b }) => {
        const output = { result: a + b };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

// Register a dynamic greeting resource
server.registerResource(
    'greeting',
    new ResourceTemplate('greeting://{name}', { list: undefined }),
    {
        title: 'Greeting Resource',
        description: 'Dynamic greeting generator'
    },
    async (uri, { name }) => ({
        contents: [
            {
                uri: uri.href,
                text: `Hello, ${name}!`
            }
        ]
    })
);

// Set up Express app
const app = express();

// Enable CORS (add this block)
app.use(
    cors({
        origin: '*', // Allow all origins for development; restrict in production (e.g., ['https://your-client-domain.com'])
        exposedHeaders: ['Mcp-Session-Id'],
    })
);

app.use(express.json());
app.use(mcpAuthServer.router());

// Handle MCP requests at /mcp endpoint
app.post('/mcp', mcpAuthServer.protect(), async (req, res) => {
    // Create a new transport for each request (stateless mode)
    const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true
    });

    res.on('close', () => {
        transport.close();
    });

    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
});

// Start the server
app.listen(port, () => {
    console.log(`Demo MCP Server running on http://localhost:${port}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
