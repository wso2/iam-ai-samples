/**
 * Copyright (c) 2026, WSO2 LLC. (https://www.wso2.com).
 *
 * WSO2 LLC. licenses this file to you under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
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
    name: 'booking-manager-server',
    version: '1.0.0'
});

const PORT = 3004;

const authServer = new McpAuthServer({
    baseUrl: env.BASE_URL,
    issuer: `${env.BASE_URL}/oauth2/token`,
    resource: `http://localhost:${PORT}/mcp`,
    audience: env.AUDIENCE_BOOKING_MANAGER_SERVER
});

// In-memory mock booking store
const BOOKINGS: Record<string, object> = {
    'BK-10021': {
        booking_reference: 'BK-10021',
        status: 'confirmed',
        flight_id: 'FL-003',
        hotel_id: 'HTL-003',
        passenger_details: { name: 'Alice Smith', email: 'alice.smith@example.com', passport_number: 'P12345678' },
        created_at: '2024-06-01T10:00:00Z',
        total_usd: 1070
    }
};

let bookingCounter = 10022;

server.registerTool(
    'create_booking',
    {
        title: 'Create Booking',
        description: 'Create a new flight and/or hotel booking. Requires authentication.',
        inputSchema: {
            flight_id: z.string().describe('Flight ID from flight search results'),
            hotel_id: z.string().optional().describe('Hotel ID from hotel search results (optional)'),
            passenger_details: z.object({
                name: z.string(),
                email: z.string().email(),
                passport_number: z.string()
            }).describe('Primary passenger details')
        },
        outputSchema: {
            booking_reference: z.string(),
            status: z.string(),
            total_usd: z.number(),
            confirmation_message: z.string()
        }
    },
    async ({ flight_id, hotel_id, passenger_details }) => {
        checkScope('create_booking');
        const ref = `BK-${bookingCounter++}`;
        const booking = {
            booking_reference: ref,
            status: 'confirmed',
            flight_id,
            hotel_id: hotel_id ?? null,
            passenger_details,
            created_at: new Date().toISOString(),
            total_usd: 650 + (hotel_id ? 420 : 0)
        };
        BOOKINGS[ref] = booking;

        const output = {
            booking_reference: ref,
            status: 'confirmed',
            total_usd: booking.total_usd,
            confirmation_message: `Booking ${ref} confirmed. A confirmation email will be sent to ${passenger_details.email}.`
        };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'get_booking',
    {
        title: 'Get Booking',
        description: 'Retrieve full booking details by reference number. Requires authentication.',
        inputSchema: {
            booking_reference: z.string().describe('Booking reference (e.g. BK-10021)')
        },
        outputSchema: {
            booking: z.object({
                booking_reference: z.string(),
                status: z.string(),
                flight_id: z.string(),
                hotel_id: z.string().nullable(),
                passenger_details: z.object({ name: z.string(), email: z.string(), passport_number: z.string() }),
                created_at: z.string(),
                total_usd: z.number()
            }).nullable(),
            found: z.boolean()
        }
    },
    async ({ booking_reference }) => {
        checkScope('get_booking');
        const booking = (BOOKINGS[booking_reference] as any) ?? null;
        const output = { booking, found: booking !== null };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'cancel_booking',
    {
        title: 'Cancel Booking',
        description: 'Cancel an existing booking and get refund estimate. Requires authentication.',
        inputSchema: {
            booking_reference: z.string().describe('Booking reference to cancel'),
            reason: z.string().optional().describe('Reason for cancellation')
        },
        outputSchema: {
            booking_reference: z.string(),
            cancelled: z.boolean(),
            refund_usd: z.number(),
            refund_timeline: z.string(),
            message: z.string()
        }
    },
    async ({ booking_reference, reason }) => {
        checkScope('cancel_booking');
        const booking = BOOKINGS[booking_reference] as any;
        if (!booking) {
            const output = {
                booking_reference,
                cancelled: false,
                refund_usd: 0,
                refund_timeline: 'N/A',
                message: `Booking ${booking_reference} not found.`
            };
            return {
                content: [{ type: 'text', text: JSON.stringify(output) }],
                structuredContent: output
            };
        }

        booking.status = 'cancelled';
        booking.cancellation_reason = reason ?? 'Not specified';
        const refund = Math.round(booking.total_usd * 0.85 * 100) / 100;

        const output = {
            booking_reference,
            cancelled: true,
            refund_usd: refund,
            refund_timeline: '5-7 business days',
            message: `Booking ${booking_reference} has been cancelled. Refund of $${refund} will be processed within 5-7 business days.`
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
    console.log(`Booking Manager MCP Server (protected) running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
