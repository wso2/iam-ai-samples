import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

// Create an MCP server
export const server = new McpServer({
    name: 'demo-server',
    version: '1.0.0',
});

// Register a simple addition tool
export function registerMCPTools() {
    server.registerTool(
        'add',
        {
            title: 'Addition Tool',
            description: 'Add two numbers',
            inputSchema: { a: z.number(), b: z.number() },
        },
        async ({ a, b }) => {
            const result = a + b;
            return {
                content: [{ type: 'text', text: String(result) }],
            };
        }
    );
    console.log("✅ MCP Tools Registered");
}