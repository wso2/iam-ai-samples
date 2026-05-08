# Travel MCP Servers

A collection of Model Context Protocol (MCP) servers for a travel-booking demo. Three servers run without auth; two are protected with Asgardeo / WSO2 Identity Server OAuth2.

## Servers

| Server | File | Port | Auth |
| --- | --- | --- | --- |
| Flight Search | `flight-search-mcp-no-auth.ts` | 3001 | none |
| Hotel Search | `hotel-search-mcp-no-auth.ts` | 3002 | none |
| Currency Converter | `currency-converter-mcp-no-auth.ts` | 3003 | none |
| Booking Manager | `booking-manager-mcp-asgardeo-auth.ts` | 3004 | Asgardeo |
| Airport Lounge | `airport-lounge-mcp-asgardeo-auth.ts` | 3005 | Asgardeo |

Each server exposes its endpoint at `http://localhost:<port>/mcp`.

## Setup

1. Install dependencies:

   ```
   npm install
   ```

2. Copy `.env.example` to `.env` and fill in the Asgardeo / WSO2 IS values:

   ```
   BASE_URL=https://api.asgardeo.io/t/<your-org>
   AUDIENCE_BOOKING_MANAGER_SERVER=<client-id>
   AUDIENCE_AIRPORT_LOUNGE_SERVER=<client-id>
   ```

   The two no-auth servers do not need any environment variables.

## Run

Start all five servers in one terminal:

```
npm start
```