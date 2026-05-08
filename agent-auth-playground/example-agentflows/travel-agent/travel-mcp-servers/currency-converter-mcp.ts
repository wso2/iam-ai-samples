import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import express from 'express';
import cors from 'cors';
import { z } from 'zod';

const server = new McpServer({
    name: 'currency-converter-server',
    version: '1.0.0'
});

const PORT = 3003;

// Mock exchange rates relative to USD
const RATES_FROM_USD: Record<string, number> = {
    USD: 1.0,
    EUR: 0.92,
    GBP: 0.79,
    JPY: 157.45,
    AUD: 1.53,
    CAD: 1.36,
    SGD: 1.34,
    AED: 3.67,
    THB: 35.12,
    INR: 83.47,
    MXN: 17.15,
    BRL: 5.05,
    LKR : 323.50
};

function convertAmount(amount: number, from: string, to: string): { converted: number; rate: number } {
    const fromRate = RATES_FROM_USD[from.toUpperCase()];
    const toRate = RATES_FROM_USD[to.toUpperCase()];
    if (!fromRate || !toRate) return { converted: 0, rate: 0 };
    const rate = toRate / fromRate;
    return { converted: Math.round(amount * rate * 100) / 100, rate: Math.round(rate * 100000) / 100000 };
}

server.registerTool(
    'convert_currency',
    {
        title: 'Convert Currency',
        description: 'Convert an amount from one currency to another using current exchange rates',
        inputSchema: {
            amount: z.number().positive().describe('Amount to convert'),
            from_currency: z.string().length(3).describe('Source currency ISO 4217 code (e.g. USD)'),
            to_currency: z.string().length(3).describe('Target currency ISO 4217 code (e.g. EUR)')
        },
        outputSchema: {
            original_amount: z.number(),
            from_currency: z.string(),
            converted_amount: z.number(),
            to_currency: z.string(),
            exchange_rate: z.number(),
            error: z.string().optional()
        }
    },
    async ({ amount, from_currency, to_currency }) => {
        const from = from_currency.toUpperCase();
        const to = to_currency.toUpperCase();

        if (!RATES_FROM_USD[from] || !RATES_FROM_USD[to]) {
            const output = {
                original_amount: amount,
                from_currency: from,
                converted_amount: 0,
                to_currency: to,
                exchange_rate: 0,
                error: `Unsupported currency. Supported: ${Object.keys(RATES_FROM_USD).join(', ')}`
            };
            return {
                content: [{ type: 'text', text: JSON.stringify(output) }],
                structuredContent: output
            };
        }

        const { converted, rate } = convertAmount(amount, from, to);
        const output = {
            original_amount: amount,
            from_currency: from,
            converted_amount: converted,
            to_currency: to,
            exchange_rate: rate
        };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'get_exchange_rates',
    {
        title: 'Get Exchange Rates',
        description: 'Get current exchange rates for all supported travel currencies relative to a base currency',
        inputSchema: {
            base_currency: z.string().length(3).describe('Base currency ISO 4217 code (e.g. USD)')
        },
        outputSchema: {
            base_currency: z.string(),
            rates: z.record(z.string(), z.number()),
            supported_currencies: z.array(z.string()),
            error: z.string().optional()
        }
    },
    async ({ base_currency }) => {
        const base = base_currency.toUpperCase();

        if (!RATES_FROM_USD[base]) {
            const output = {
                base_currency: base,
                rates: {},
                supported_currencies: Object.keys(RATES_FROM_USD),
                error: `Unsupported base currency. Supported: ${Object.keys(RATES_FROM_USD).join(', ')}`
            };
            return {
                content: [{ type: 'text', text: JSON.stringify(output) }],
                structuredContent: output
            };
        }

        const rates: Record<string, number> = {};
        for (const currency of Object.keys(RATES_FROM_USD)) {
            if (currency !== base) {
                const { rate } = convertAmount(1, base, currency);
                rates[currency] = rate;
            }
        }

        const output = {
            base_currency: base,
            rates,
            supported_currencies: Object.keys(RATES_FROM_USD)
        };
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

app.post('/mcp', async (req, res) => {
    console.log('Incoming MCP request:', JSON.stringify({ method: req.method, body: req.body }, null, 2));

    const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true
    });

    res.on('close', () => transport.close());
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
});

app.listen(PORT, () => {
    console.log(`Currency Converter MCP Server running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
