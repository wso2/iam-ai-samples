import { McpServer, ResourceTemplate } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import jwt from 'jsonwebtoken';
import { z } from 'zod';
import { McpAuthServer } from '@asgardeo/mcp-express';
import { GRPC } from "@cerbos/grpc";
import { randomUUID } from "node:crypto";

// Extend Express Request to include user
interface AuthenticatedRequest extends Request {
    user?: {
        id: string;
        roles: string[];
        scopes: string[];
    };
    sessionId?: string;
}

const port = '3000';
const cerbos_pdp_port = '3593';
const cerbos = new GRPC(`localhost:${cerbos_pdp_port}`, { tls: false });

// MCP Auth Server setup — for WSO2 Identity Server integration (comment if using Asgardeo instead of WSO2 IS)
const mcpAuthServer = new McpAuthServer({
    baseUrl: 'https://localhost:9443',
    issuer: 'https://localhost:9443/oauth2/token',
    resource: `http://localhost:${port}/mcp`,
});

// MCP Auth Server setup - for Asgardeo integration (uncomment and update config if using Asgardeo instead of WSO2 IS)
// const mcpAuthServer = new McpAuthServer({
//     baseUrl: 'https://api.asgardeo.io/t/{your_org}',
//     issuer: 'https://api.asgardeo.io/t/{your_org}/oauth2/token',
//     resource: `http://localhost:${port}/mcp`,
// });

// Helper to create math tools by abstracting common properties and logic
// This reduces boilerplate and makes it easier to add new tools in the future
// Each tool is defined with its name, description, operation logic, and required scope
const createMathTool = (name: string, description: string, op: (a: number, b: number) => number, requiredScope: string) => ({
    name,
    title: `${name.charAt(0).toUpperCase() + name.slice(1)} Tool`,
    description,
    inputSchema: { a: z.number(), b: z.number() },
    outputSchema: { result: z.number() },
    requiredScope,
    handler: async ({ a, b }: { a: number, b: number }) => {
        const output = { result: op(a, b) };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
});

// The getServer function initializes the MCP server and defines the available tools based on the authenticated user and session. 
// It performs both discovery checks (to determine which tools to show) and runtime checks (to enforce access control when a tool is invoked).
async function getServer({ user, sessionId }: { user: NonNullable<AuthenticatedRequest['user']>, sessionId: string }) {
    const server = new McpServer({
        name: 'demo-auth-server',
        version: '1.0.0'
    });

    const tools: Record<string, any> = {
        add: createMathTool('Addition', // Tool name
            'Add two numbers', // Tool description
             (a, b) => a + b, // Operation
              'add'), // Required scope
        subtract: createMathTool('Subtraction', 'Subtract two numbers', (a, b) => a - b, 'subtract'),
        multiply: createMathTool('Multiplication', 'Multiply two numbers', (a, b) => a * b, 'multiply'),
        divide: {
            ...createMathTool('Division', 'Divide two numbers', (a, b) => a / b, 'divide'),
            handler: async ({ a, b }: { a: number, b: number }) => {
                if (b === 0) throw new Error('Division by zero');
                const output = { result: a / b };
                return {
                    content: [{ type: 'text', text: JSON.stringify(output) }],
                    structuredContent: output
                };
            }
        }
    };

    const toolNames = Object.keys(tools);

    // 1. Tool Discovery/Listing Check (e.g. based on roles/groups)
    const discoveryCheck = await cerbos.checkResource({
        principal: { id: user.id, roles: user.roles },
        resource: { kind: "mcp::math_discovery", id: sessionId },
        actions: toolNames,
    });

    console.debug("Discovery Check Result:", discoveryCheck);

    for (const toolName of toolNames) {
        if (discoveryCheck.isAllowed(toolName)) {
            const tool = tools[toolName];
            server.tool(tool.name, tool.description, tool.inputSchema, async (args) => {
                // 2. Runtime Execution Check (strict scope-based check)
                const allowed = await cerbos.isAllowed({
                    principal: {
                        id: user.id,
                        roles: user.roles,
                        attr: { scopes: user.scopes }
                    },
                    resource: { 
                        kind: "mcp::math_tools", 
                        id: sessionId, 
                        attr: { required_scope: tool.requiredScope } },
                    action: toolName
                });

                if (!allowed) {
                    const logDetails = `Forbidden: User ${user.id} requires scope '${tool.requiredScope}' to perform '${toolName}'`;
                    console.debug(logDetails);
                    throw new Error(logDetails);
                }
                return tool.handler(args);
            });
        }
    }
    
    // Greeting resource (always available)
    server.resource(
        'greeting',
        new ResourceTemplate('greeting://{name}', { list: undefined }),
        async (uri, { name }) => ({
            contents: [{ uri: uri.href, text: `Hello, ${name}!` }]
        })
    );

    return server;
}

const app = express();

app.use(cors({ origin: '*', exposedHeaders: ['Mcp-Session-Id'] }));
app.use(express.json());

// 1. OAuth/OIDC metadata & token endpoints (e.g. .well-known, token exchange)
app.use(mcpAuthServer.router());

// JWT decode — extracts user context from a validated token
const extractUser = (req: Request, res: Response, next: NextFunction) => {
    const authReq = req as AuthenticatedRequest;
    const authHeader = req.headers.authorization;
    
    let user;

    if (authHeader?.startsWith('Bearer ')) {
        try {
            const decoded = jwt.decode(authHeader.split(' ')[1]) as any;
            if (decoded && typeof decoded === 'object') {
                const scopes = decoded.scope ? (Array.isArray(decoded.scope) ? decoded.scope : decoded.scope.split(' ')) : (decoded.scp ? (Array.isArray(decoded.scp) ? decoded.scp : [decoded.scp]) : []);
                user = {
                    id: decoded.sub || "unknown",
                    roles: decoded.roles || decoded.groups || ["everyone"],
                    scopes: Array.isArray(scopes) ? scopes : [scopes]
                };
            }
        } catch (e) {
            console.error("Token decode failed", e);
            return res.status(401).json({ error: "Invalid token" });
        }
    }
    console.debug("Authenticated user:", user);

    authReq.user = user;
    next();
};

// ─── Session Cache ───────────────────────────────────────────
// Stores the MCP server + transport per session so that:
//   - Tool Discovery check runs ONCE (when session is created)
//   - Subsequent requests (tools/call) reuse the same server
const sessions = new Map<string, { server: McpServer; transport: StreamableHTTPServerTransport }>();

// Execution order: 1. router() → 2. protect() → 3. extractUser → 4. handler
app.post('/mcp', mcpAuthServer.protect(), extractUser, async (req: Request, res: Response) => {
    const authReq = req as AuthenticatedRequest;
    if (!authReq.user) return res.status(403).json({ error: "Unauthorized" });

    const sessionId = req.headers['mcp-session-id'] as string | undefined;

    // ── Existing session: reuse server (no tool discovery check) ──
    if (sessionId && sessions.has(sessionId)) {
        const { transport } = sessions.get(sessionId)!;
        try {
            await transport.handleRequest(req, res, req.body);
        } catch (error) {
            console.error(`[Session] Error handling request for session ${sessionId}:`, error);
            if (!res.headersSent) {
            res.status(500).json({ error: "Internal server error" });
            }
        }
        return;
    }

    // ── New session: create server + run tool discovery check once ──
    const newSessionId = randomUUID();
    console.log(`[Session] Creating new session ${newSessionId} for user ${authReq.user.id}`);

    const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => newSessionId,
        enableJsonResponse: true,
    });

    const server = await getServer({
        user: authReq.user,
        sessionId: newSessionId,
    });

    // Cache the session
    sessions.set(newSessionId, { server, transport });

    // Clean up when the transport closes
    transport.onclose = () => {
        console.log(`[Session] Closed ${newSessionId}`);
        sessions.delete(newSessionId);
    };

    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
});

app.listen(port, () => {
    console.log(`MCP Server running on http://localhost:${port}/mcp`);
}).on('error', console.error);
