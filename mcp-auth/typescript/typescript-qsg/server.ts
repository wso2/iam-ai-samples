import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { server, registerMCPTools } from './mcp-server.js';
import { configuredAuthServer as auth } from '@asgardeo/mcp-express';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors({ origin: '*', exposedHeaders: ['Mcp-Session-Id'] }));
app.use(express.json());

registerMCPTools();
app.use(auth.router());

app.post('/mcp', auth.protect(), async (req, res) => {
    const transport = new StreamableHTTPServerTransport({
        enableJsonResponse: true,
    });

    res.on('close', () => transport.close());

    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
});

app.listen(PORT, () => {
    console.log(`🚀 Server running at http://localhost:${PORT}/mcp`);
});