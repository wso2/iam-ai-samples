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
    name: 'airport-lounge-server',
    version: '1.0.0'
});

const PORT = 3005;

const authServer = new McpAuthServer({
    baseUrl: env.BASE_URL,
    issuer: `${env.BASE_URL}/oauth2/token`,
    resource: `http://localhost:${PORT}/mcp`,
    audience: env.AUDIENCE_AIRPORT_LOUNGE_SERVER
});


const MOCK_LOUNGES: Record<string, object> = {
    'LNG-JFK-01': {
        lounge_id: 'LNG-JFK-01',
        name: 'SkyWings Horizon Lounge',
        airport: 'JFK',
        terminal: 'Terminal 4',
        location: 'Airside, Level 3, Gate B42',
        operator: 'SkyWings',
        opening_hours: '05:00 – 23:00',
        capacity: 120,
        current_occupancy: 47,
        amenities: ['Buffet Dining', 'Open Bar', 'Shower Suites', 'High-Speed WiFi', 'Business Centre', 'Nap Pods', 'Spa'],
        eligible_cabin_classes: ['business', 'first'],
        guest_fee_usd: 35
    },
    'LNG-JFK-02': {
        lounge_id: 'LNG-JFK-02',
        name: 'Plaza Premium Lounge JFK',
        airport: 'JFK',
        terminal: 'Terminal 1',
        location: 'Airside, Level 2',
        operator: 'Plaza Premium',
        opening_hours: '06:00 – 22:30',
        capacity: 80,
        current_occupancy: 31,
        amenities: ['Hot Food', 'Drinks', 'Shower Rooms', 'WiFi', 'Quiet Zone'],
        eligible_cabin_classes: ['economy', 'premium_economy', 'business', 'first'],
        guest_fee_usd: 45
    },
    'LNG-LHR-01': {
        lounge_id: 'LNG-LHR-01',
        name: 'AeroLux First Class Lounge',
        airport: 'LHR',
        terminal: 'Terminal 5',
        location: 'Airside, Level 5',
        operator: 'AeroLux',
        opening_hours: '04:30 – 22:00',
        capacity: 200,
        current_occupancy: 88,
        amenities: ['À La Carte Dining', 'Champagne Bar', 'Spa', 'Shower Suites', 'Cinema Room', 'Kids Zone', 'WiFi'],
        eligible_cabin_classes: ['first'],
        guest_fee_usd: 0
    },
    'LNG-LHR-02': {
        lounge_id: 'LNG-LHR-02',
        name: 'Aspire Lounge Heathrow',
        airport: 'LHR',
        terminal: 'Terminal 2',
        location: 'Airside, Departures Level',
        operator: 'Aspire',
        opening_hours: '05:00 – 21:00',
        capacity: 150,
        current_occupancy: 62,
        amenities: ['Buffet', 'Bar', 'WiFi', 'TV Lounge', 'Outdoor Terrace'],
        eligible_cabin_classes: ['economy', 'premium_economy', 'business', 'first'],
        guest_fee_usd: 40
    },
    'LNG-DXB-01': {
        lounge_id: 'LNG-DXB-01',
        name: 'TransGlobe Elite Lounge',
        airport: 'DXB',
        terminal: 'Terminal 3',
        location: 'Concourse B, Level 2',
        operator: 'TransGlobe',
        opening_hours: '00:00 – 24:00',
        capacity: 300,
        current_occupancy: 104,
        amenities: ['Fine Dining', 'Cigar Lounge', 'Infinity Pool', 'Spa', 'Prayer Room', 'Gaming Zone', 'WiFi'],
        eligible_cabin_classes: ['business', 'first'],
        guest_fee_usd: 0
    }
};

// In-memory reservation store
const RESERVATIONS: Record<string, object> = {};
let reservationCounter = 5001;

server.registerTool(
    'search_lounges',
    {
        title: 'Search Airport Lounges',
        description: 'Search available lounges at an airport. Requires a valid booking reference to confirm travel eligibility.',
        inputSchema: {
            airport_code: z.string().length(3).describe('IATA airport code (e.g. JFK, LHR, DXB)'),
            booking_reference: z.string().describe('Valid booking reference (e.g. BK-10021) to confirm travel eligibility')
        },
        outputSchema: {
            lounges: z.array(z.object({
                lounge_id: z.string(),
                name: z.string(),
                capacity: z.number(),
                current_occupancy: z.number(),
                guest_fee_usd: z.number()
            })),
            total_results: z.number(),
            booking_reference: z.string()
        }
    },
    async ({ airport_code, booking_reference }) => {
        checkScope('search_lounges');
        const lounges = Object.values(MOCK_LOUNGES)
            .filter((l: any) => l.airport === airport_code.toUpperCase())
            .map((l: any) => ({
                lounge_id: l.lounge_id,
                name: l.name,
                capacity: l.capacity,
                current_occupancy: l.current_occupancy,
                guest_fee_usd: l.guest_fee_usd
            }));

        const output = { lounges, total_results: lounges.length, booking_reference };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'get_lounge_details',
    {
        title: 'Get Lounge Details',
        description: 'Get full details of a specific lounge including amenities, location, and eligibility. Requires a valid booking reference.',
        inputSchema: {
            lounge_id: z.string().describe('Lounge ID returned from search_lounges'),
            booking_reference: z.string().describe('Valid booking reference to confirm travel eligibility')
        },
        outputSchema: {
            lounge: z.object({
                lounge_id: z.string(),
                name: z.string(),
                airport: z.string(),
                terminal: z.string(),
                location: z.string(),
                operator: z.string(),
                opening_hours: z.string(),
                capacity: z.number(),
                current_occupancy: z.number(),
                amenities: z.array(z.string()),
                eligible_cabin_classes: z.array(z.string()),
                guest_fee_usd: z.number()
            }).nullable(),
            found: z.boolean(),
            booking_reference: z.string()
        }
    },
    async ({ lounge_id, booking_reference }) => {
        checkScope('get_lounge_details');
        const lounge = (MOCK_LOUNGES[lounge_id] as any) ?? null;
        const output = { lounge, found: lounge !== null, booking_reference };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'reserve_lounge',
    {
        title: 'Reserve Lounge Slot',
        description: 'Reserve a lounge slot for a specific arrival time. Requires a valid booking reference.',
        inputSchema: {
            lounge_id: z.string().describe('Lounge ID to reserve'),
            booking_reference: z.string().describe('Valid booking reference tied to this reservation'),
            arrival_time: z.string().describe('Expected lounge arrival time in HH:MM format (e.g. 09:30)'),
            guests: z.number().int().min(1).max(6).describe('Number of guests including the primary traveller')
        },
        outputSchema: {
            reservation_id: z.string(),
            lounge_id: z.string(),
            lounge_name: z.string(),
            booking_reference: z.string(),
            arrival_time: z.string(),
            guests: z.number(),
            total_guest_fee_usd: z.number(),
            confirmation_message: z.string()
        }
    },
    async ({ lounge_id, booking_reference, arrival_time, guests }) => {
        checkScope('reserve_lounge');
        const lounge = MOCK_LOUNGES[lounge_id] as any;
        const reservationId = `RES-${reservationCounter++}`;
        const guestFee = lounge ? lounge.guest_fee_usd * Math.max(0, guests - 1) : 0;
        const loungeName = lounge?.name ?? lounge_id;

        const reservation = { reservation_id: reservationId, lounge_id, booking_reference, arrival_time, guests, total_guest_fee_usd: guestFee };
        RESERVATIONS[reservationId] = reservation;

        const output = {
            reservation_id: reservationId,
            lounge_id,
            lounge_name: loungeName,
            booking_reference,
            arrival_time,
            guests,
            total_guest_fee_usd: guestFee,
            confirmation_message: `Lounge slot reserved at ${loungeName} for ${guests} guest(s) arriving at ${arrival_time}. Reservation ID: ${reservationId}.`
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

app.use(authServer.router());

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
    console.log(`Airport Lounge Access MCP Server (protected) running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
