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
import express from 'express';
import cors from 'cors';
import { z } from 'zod';

const server = new McpServer({
    name: 'flight-search-server',
    version: '1.0.0'
});

const PORT = 3001;

const MOCK_FLIGHTS: Record<string, object> = {
    'FL-001': {
        flight_id: 'FL-001',
        airline: 'SkyWings',
        flight_number: 'SW204',
        origin: 'JFK',
        destination: 'LHR',
        departure_time: '08:00',
        arrival_time: '20:00',
        duration_minutes: 420,
        operates: 'Daily',
        cabin_class: 'economy',
        price_usd: 650,
        seats_available: 42,
        stops: [],
        baggage_policy: '1 checked bag (23kg) included',
        seat_map: { rows: 30, seats_per_row: 6, layout: '3-3' }
    },
    'FL-002': {
        flight_id: 'FL-002',
        airline: 'AeroLux',
        flight_number: 'AL891',
        origin: 'JFK',
        destination: 'LHR',
        departure_time: '14:30',
        arrival_time: '02:30+1',
        duration_minutes: 420,
        operates: 'Daily',
        cabin_class: 'business',
        price_usd: 2800,
        seats_available: 8,
        stops: [],
        baggage_policy: '2 checked bags (32kg each) included, priority boarding',
        seat_map: { rows: 6, seats_per_row: 4, layout: '1-2-1' }
    },
    'FL-003': {
        flight_id: 'FL-003',
        airline: 'TransGlobe',
        flight_number: 'TG115',
        origin: 'LAX',
        destination: 'DXB',
        departure_time: '23:55',
        arrival_time: '22:10+1',
        duration_minutes: 855,
        operates: 'Daily',
        cabin_class: 'economy',
        price_usd: 820,
        seats_available: 18,
        stops: [{ airport: 'DOH', duration_minutes: 90 }],
        baggage_policy: '1 checked bag (23kg) included',
        seat_map: { rows: 45, seats_per_row: 9, layout: '3-3-3' }
    }
};

server.registerTool(
    'search_flights',
    {
        title: 'Search Flights',
        description: 'Search for available flights between two airports on a given date',
        inputSchema: {
            origin: z.string().describe('IATA airport code for departure (e.g. JFK)'),
            destination: z.string().describe('IATA airport code for arrival (e.g. LHR)'),
            passengers: z.number().int().min(1).max(9).describe('Number of passengers'),
            cabin_class: z.enum(['economy', 'premium_economy', 'business', 'first']).describe('Cabin class')
        },
        outputSchema: {
            flights: z.array(z.object({
                flight_id: z.string(),
                airline: z.string(),
                flight_number: z.string(),
                departure_time: z.string(),
                arrival_time: z.string(),
                duration_minutes: z.number(),
                operates: z.string(),
                stops: z.number(),
                price_usd: z.number(),
                seats_available: z.number()
            })),
            total_results: z.number()
        }
    },
    async ({ origin, destination, passengers, cabin_class }) => {
        const toSummary = (f: any) => ({
            flight_id: f.flight_id,
            airline: f.airline,
            flight_number: f.flight_number,
            departure_time: f.departure_time,
            arrival_time: f.arrival_time,
            duration_minutes: f.duration_minutes,
            operates: f.operates,
            stops: f.stops.length,
            price_usd: f.price_usd * passengers,
            seats_available: f.seats_available
        });

        const results = Object.values(MOCK_FLIGHTS)
            .filter((f: any) =>
                (f.origin === origin.toUpperCase() || origin === '') &&
                (f.destination === destination.toUpperCase() || destination === '') &&
                f.cabin_class === cabin_class
            )
            .map(toSummary);

        // Fall back to all flights if no exact match (mock behaviour)
        const flights = results.length > 0
            ? results
            : Object.values(MOCK_FLIGHTS).slice(0, 2).map(toSummary);

        const output = { flights, total_results: flights.length };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'get_flight_details',
    {
        title: 'Get Flight Details',
        description: 'Get full details for a specific flight including stops, baggage policy, and seat map',
        inputSchema: {
            flight_id: z.string().describe('Flight ID returned from search_flights')
        },
        outputSchema: {
            flight: z.object({
                flight_id: z.string(),
                airline: z.string(),
                flight_number: z.string(),
                origin: z.string(),
                destination: z.string(),
                departure_time: z.string(),
                arrival_time: z.string(),
                duration_minutes: z.number(),
                operates: z.string(),
                cabin_class: z.string(),
                price_usd: z.number(),
                seats_available: z.number(),
                stops: z.array(z.object({ airport: z.string(), duration_minutes: z.number() })),
                baggage_policy: z.string(),
                seat_map: z.object({ rows: z.number(), seats_per_row: z.number(), layout: z.string() })
            }).nullable(),
            found: z.boolean()
        }
    },
    async ({ flight_id }) => {
        const flight = (MOCK_FLIGHTS[flight_id] as any) ?? null;
        const output = { flight, found: flight !== null };
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
    console.log(`Flight Search MCP Server running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
