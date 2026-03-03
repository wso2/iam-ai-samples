/*
Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

import { stdin as input, stdout as output } from "node:process";
import * as readline from "node:readline/promises";
import { Server } from "http";

import express from "express";
import { streamText, tool, jsonSchema } from "ai";
import { google } from "@ai-sdk/google";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

import { AsgardeoJavaScriptClient, AuthCodeResponse } from "@asgardeo/javascript";

import dotenv from "dotenv";
import open from "open";

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const port = "3001";

dotenv.config({
  path: resolve(__dirname, "../../.env"),
});

const asgardeoConfig = {
    afterSignInUrl: process.env.REDIRECT_URI || "",
    clientId: process.env.CLIENT_ID || "",
    baseUrl: process.env.ASGARDEO_BASE_URL || "",
};

const agentConfig = {
    agentID: process.env.AGENT_ID || "",
    agentSecret: process.env.AGENT_SECRET || "",
};

async function getMCPTools(url: string, authToken: string) {
    const transport = new StreamableHTTPClientTransport(
        new URL(url),
        {
            requestInit: {
                headers: {
                    Authorization: `Bearer ${authToken}`,
                },
            },
        }
    );

    const client = new Client({
        name: "vercel-ai-agent",
        version: "1.0.0",
    });

    await client.connect(transport);

    const { tools: mcpTools } = await client.listTools();

    const tools: Record<string, any> = {};
    for (const mcpTool of mcpTools) {
        tools[mcpTool.name] = tool({
            description: mcpTool.description || "",
            parameters: jsonSchema(
                mcpTool.inputSchema || { type: "object" as const, properties: {} }
            ),
            execute: async (args: any) => {
                const result = await client.callTool({
                    name: mcpTool.name,
                    arguments: args,
                });
                if (result.content && Array.isArray(result.content)) {
                    return result.content
                        .filter((c: any) => c.type === "text")
                        .map((c: any) => c.text)
                        .join("\n");
                }
                return JSON.stringify(result);
            },
        });
    }

    return { tools, client };
}

async function runAgent() {
    console.log("##########################################################################################################");
    console.log("##     This is an On-Behalf-Of (OBO) authentication sample application for authenticating AI agents     ##");
    console.log("##                         using Asgardeo and Vercel AI framework                                       ##");
    console.log("##########################################################################################################");

    const asgardeoJavaScriptClient = new AsgardeoJavaScriptClient(asgardeoConfig);

    const authURL = await asgardeoJavaScriptClient.getOBOSignInURL(agentConfig);
    console.log("Opening authentication URL in your browser...");
    await open(authURL);

    const app = express();
    let server: Server;

    let authCodeResponse: AuthCodeResponse | undefined;

    const authCodePromise = new Promise<AuthCodeResponse>((resolve) => {
        app.get("/callback", async (req, res) => {
            try {
                const code = req.query.code as string;
                const session_state = req.query.session_state as string;
                const state = req.query.state as string;

                if (!code) {
                    res.status(400).send("No authorization code found.");
                    return;
                }

                authCodeResponse = {
                    code: code,
                    state: state,
                    session_state: session_state,
                };

                resolve(authCodeResponse);

                res.send("<h1>Login Successful!</h1><p>You can close this window.</p>");
            } catch (err) {
                res.status(500).send("Internal Server Error");
            } finally {
                if (server) {
                    server.close();
                }
            }
        });
    });

    server = app
        .listen(port, () => {
        })
        .on("error", (error) => {
            console.error("Server error:", error);
            process.exit(1);
        });

    authCodeResponse = await authCodePromise;

    const oboToken = await asgardeoJavaScriptClient.getOBOToken(agentConfig, authCodeResponse);

    process.env.GOOGLE_GENERATIVE_AI_API_KEY = process.env.GOOGLE_API_KEY || "";

    const llm = google(process.env.MODEL_NAME || "gemini-2.5-flash");

    const { tools, client: mcpClient } = await getMCPTools(
        process.env.MCP_SERVER_URL || "",
        oboToken.accessToken,
    );

    const rl = readline.createInterface({ input, output });

    try {
        while (true) {
            try {
                const userInput = await rl.question("\nEnter your question (e.g., 'Add 45 and 99') or type 'exit' to quit: ");

                if (userInput.toLowerCase() === "exit") {
                    console.log("Exiting the program. Goodbye!");
                    break;
                }

                const messages = [{ role: "user" as const, content: userInput }];

                const result = streamText({
                    model: llm,
                    messages: messages,
                    tools: tools,
                    maxSteps: 5,
                });

                process.stdout.write("\nAgent Response: ");

                for await (const chunk of result.textStream) {
                    process.stdout.write(chunk);
                }

                console.log();
            } catch (error) {
                console.error("Error running agent:", error);
                break;
            }
        }
    } finally {
        await mcpClient.close();
        rl.close();
        process.exit(0);
    }
}

runAgent().catch(console.error);
