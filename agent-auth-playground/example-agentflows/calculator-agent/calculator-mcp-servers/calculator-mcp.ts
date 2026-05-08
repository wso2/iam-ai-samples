import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { McpAuthServer } from '@asgardeo/mcp-express';
import express from 'express';
import cors from 'cors';
import { z } from 'zod';
import { AsyncLocalStorage } from 'async_hooks';
import { env } from 'process';

const requestContext = new AsyncLocalStorage<{ scopes: string[] }>();

function checkScope(required: string): void {
    const ctx = requestContext.getStore();
    if (!ctx || !ctx.scopes.includes(required)) {
        throw new Error(`Insufficient scope. Required scope: '${required}'`);
    }
}

const server = new McpServer({
    name: 'calculator-server',
    version: '1.0.0'
});

const PORT = 3010;

const authServer = new McpAuthServer({
    baseUrl: env.BASE_URL,
    issuer: `${env.BASE_URL}/oauth2/token`,
    resource: `http://localhost:${PORT}/mcp`,
    audience: env.AUDIENCE_CALCULATOR_SERVER
});

server.registerTool(
    'add',
    {
        title: 'Add',
        description: 'Add two numbers together. Requires authentication.',
        inputSchema: {
            a: z.number().describe('First operand'),
            b: z.number().describe('Second operand')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ a, b }) => {
        checkScope('add');
        const result = a + b;
        const output = { result, expression: `${a} + ${b} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'subtract',
    {
        title: 'Subtract',
        description: 'Subtract the second number from the first. Requires authentication.',
        inputSchema: {
            a: z.number().describe('Minuend'),
            b: z.number().describe('Subtrahend')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ a, b }) => {
        checkScope('subtract');
        const result = a - b;
        const output = { result, expression: `${a} - ${b} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'multiply',
    {
        title: 'Multiply',
        description: 'Multiply two numbers. Requires authentication.',
        inputSchema: {
            a: z.number().describe('First factor'),
            b: z.number().describe('Second factor')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ a, b }) => {
        checkScope('multiply');
        const result = a * b;
        const output = { result, expression: `${a} × ${b} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'divide',
    {
        title: 'Divide',
        description: 'Divide the first number by the second. Requires authentication.',
        inputSchema: {
            a: z.number().describe('Dividend'),
            b: z.number().describe('Divisor (must not be zero)')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ a, b }) => {
        checkScope('divide');
        if (b === 0) {
            throw new Error('Division by zero is not allowed.');
        }
        const result = a / b;
        const output = { result, expression: `${a} ÷ ${b} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'power',
    {
        title: 'Power',
        description: 'Raise a base number to an exponent. Requires authentication.',
        inputSchema: {
            base: z.number().describe('Base number'),
            exponent: z.number().describe('Exponent')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ base, exponent }) => {
        checkScope('power');
        const result = Math.pow(base, exponent);
        const output = { result, expression: `${base} ^ ${exponent} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'sqrt',
    {
        title: 'Square Root',
        description: 'Calculate the square root of a non-negative number. Requires authentication.',
        inputSchema: {
            value: z.number().describe('Non-negative number')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ value }) => {
        checkScope('sqrt');
        if (value < 0) {
            throw new Error('Square root of a negative number is not supported.');
        }
        const result = Math.sqrt(value);
        const output = { result, expression: `√${value} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'modulo',
    {
        title: 'Modulo',
        description: 'Calculate the remainder of dividing the first number by the second. Requires authentication.',
        inputSchema: {
            a: z.number().describe('Dividend'),
            b: z.number().describe('Divisor (must not be zero)')
        },
        outputSchema: {
            result: z.number(),
            expression: z.string()
        }
    },
    async ({ a, b }) => {
        checkScope('modulo');
        if (b === 0) {
            throw new Error('Modulo by zero is not allowed.');
        }
        const result = a % b;
        const output = { result, expression: `${a} % ${b} = ${result}` };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

const app = express();

app.use(cors({
    origin: '*',
    exposedHeaders: ['Mcp-Session-Id']
}));
app.use(express.json());

// Expose Asgardeo OAuth2 discovery endpoints
app.use(authServer.router());

// Protect /mcp — requests without a valid Bearer token are rejected with 401
app.post('/mcp', authServer.protect(), async (req, res) => {
    console.log('Incoming authenticated MCP request:', JSON.stringify({ method: req.method, body: req.body }, null, 2));

    // Decode scopes from the already-validated Bearer token
    const token = (req.headers.authorization ?? '').replace('Bearer ', '');
    let scopes: string[] = [];
    try {
        const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
        scopes = typeof payload.scope === 'string' ? payload.scope.split(' ').filter(Boolean) : [];
    } catch {
        // Token is already validated by protect(); a decode failure means no scopes
    }

    const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true
    });

    await requestContext.run({ scopes }, async () => {
        res.on('close', () => transport.close());
        await server.connect(transport);
        await transport.handleRequest(req, res, req.body);
    });
});

app.listen(PORT, () => {
    console.log(`Calculator MCP Server (protected) running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
