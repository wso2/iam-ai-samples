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
    name: 'hotel-search-server',
    version: '1.0.0'
});

const PORT = 3002;

const MOCK_HOTELS: Record<string, object> = {
    'HTL-001': {
        hotel_id: 'HTL-001',
        name: 'Grand Meridian Hotel',
        location: 'London',
        address: '15 Park Lane, London W1K 1QA, UK',
        star_rating: 5,
        review_score: 9.2,
        review_count: 3840,
        price_per_night_usd: 420,
        amenities: ['Free WiFi', 'Spa', 'Pool', 'Gym', 'Restaurant', 'Bar', 'Concierge', 'Valet Parking'],
        room_types: [
            { type: 'Deluxe King', price_usd: 420, max_guests: 2, bed: 'King', area_sqm: 38 },
            { type: 'Suite', price_usd: 850, max_guests: 3, bed: 'King + sofa bed', area_sqm: 72 }
        ],
        cancellation_policy: 'Free cancellation up to 48 hours before check-in'
    },
    'HTL-002': {
        hotel_id: 'HTL-002',
        name: 'City Hub Hostel',
        location: 'London',
        address: '82 Shoreditch High St, London E1 6JJ, UK',
        star_rating: 2,
        review_score: 8.5,
        review_count: 1240,
        price_per_night_usd: 55,
        amenities: ['Free WiFi', 'Shared Kitchen', 'Common Room', 'Luggage Storage'],
        room_types: [
            { type: 'Dorm Bed (8-person)', price_usd: 30, max_guests: 1, bed: 'Bunk', area_sqm: 5 },
            { type: 'Private Double', price_usd: 90, max_guests: 2, bed: 'Double', area_sqm: 18 }
        ],
        cancellation_policy: 'Free cancellation up to 24 hours before check-in'
    },
    'HTL-003': {
        hotel_id: 'HTL-003',
        name: 'Desert Bloom Resort',
        location: 'Dubai',
        address: 'Sheikh Zayed Road, Dubai, UAE',
        star_rating: 5,
        review_score: 9.5,
        review_count: 5210,
        price_per_night_usd: 680,
        amenities: ['Free WiFi', 'Private Beach', 'Infinity Pool', 'Spa', '3 Restaurants', 'Butler Service', 'Airport Transfer'],
        room_types: [
            { type: 'Deluxe Sea View', price_usd: 680, max_guests: 2, bed: 'King', area_sqm: 52 },
            { type: 'Ocean Villa', price_usd: 1800, max_guests: 4, bed: '2x King', area_sqm: 160 }
        ],
        cancellation_policy: 'Free cancellation up to 72 hours before check-in. Non-refundable rates available at 20% discount.'
    }
};

server.registerTool(
    'search_hotels',
    {
        title: 'Search Hotels',
        description: 'Search for available hotels in a given location for specific dates',
        inputSchema: {
            location: z.string().describe('City or area name (e.g. London, Dubai)'),
            rooms: z.number().int().min(1).max(5).describe('Number of rooms required')
        },
        outputSchema: {
            hotels: z.array(z.object({
                hotel_id: z.string(),
                name: z.string(),
                star_rating: z.number(),
                review_score: z.number(),
                price_per_night_usd: z.number(),
                amenities: z.array(z.string())
            })),
            total_results: z.number()
        }
    },
    async ({ location, rooms }) => {
        const results = Object.values(MOCK_HOTELS)
            .filter((h: any) => h.location.toLowerCase() === location.toLowerCase())
            .map((h: any) => ({
                hotel_id: h.hotel_id,
                name: h.name,
                star_rating: h.star_rating,
                review_score: h.review_score,
                price_per_night_usd: h.price_per_night_usd * rooms,
                amenities: h.amenities
            }));

        // Fall back to all hotels if no exact location match (mock behaviour)
        const hotels = results.length > 0 ? results : Object.values(MOCK_HOTELS).map((h: any) => ({
            hotel_id: h.hotel_id,
            name: h.name,
            star_rating: h.star_rating,
            review_score: h.review_score,
            price_per_night_usd: h.price_per_night_usd * rooms,
            amenities: h.amenities
        }));

        const output = { hotels, total_results: hotels.length };
        return {
            content: [{ type: 'text', text: JSON.stringify(output) }],
            structuredContent: output
        };
    }
);

server.registerTool(
    'get_hotel_details',
    {
        title: 'Get Hotel Details',
        description: 'Get full details for a specific hotel including room types, cancellation policy',
        inputSchema: {
            hotel_id: z.string().describe('Hotel ID returned from search_hotels')
        },
        outputSchema: {
            hotel: z.object({
                hotel_id: z.string(),
                name: z.string(),
                location: z.string(),
                address: z.string(),
                star_rating: z.number(),
                review_score: z.number(),
                review_count: z.number(),
                price_per_night_usd: z.number(),
                amenities: z.array(z.string()),
                room_types: z.array(z.object({
                    type: z.string(),
                    price_usd: z.number(),
                    max_guests: z.number(),
                    bed: z.string(),
                    area_sqm: z.number()
                })),
                cancellation_policy: z.string()
            }).nullable(),
            found: z.boolean()
        }
    },
    async ({ hotel_id }) => {
        const hotel = (MOCK_HOTELS[hotel_id] as any) ?? null;
        const output = { hotel, found: hotel !== null };
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
    console.log(`Hotel Search MCP Server running on http://localhost:${PORT}/mcp`);
}).on('error', error => {
    console.error('Server error:', error);
    process.exit(1);
});
