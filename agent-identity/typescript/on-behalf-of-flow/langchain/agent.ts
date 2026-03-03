import { stdin as input, stdout as output } from "node:process";
import * as readline from "node:readline/promises";
import { Server } from "http";

import express from "express";
import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { MultiServerMCPClient } from "@langchain/mcp-adapters";

import { AsgardeoJavaScriptClient, AuthCodeResponse } from "@asgardeo/javascript";

import dotenv from "dotenv";
import open from "open";

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const port = '3001';

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

const model = new ChatGoogleGenerativeAI({
    apiKey: process.env.GOOGLE_API_KEY || "",
    model: process.env.MODEL_NAME || "gemini-2.5-flash",
});

async function runAgent() {
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

    const client = new MultiServerMCPClient({
        math: {
            transport: "http",
            url: process.env.MCP_SERVER_URL || "http://localhost:8000/mcp",
            headers: {
                Authorization: "Bearer " + oboToken.accessToken,
            },
        },
    });

    const tools = await client.getTools();

    const agent = createReactAgent({
        llm: model,
        tools: tools,
    });

    const rl = readline.createInterface({ input, output });

    try {
        while (true) {
            try {
                const userInput = await rl.question("\nEnter your question (e.g., 'Add 45 and 99') or type 'exit' to quit: ");

                if (userInput.toLowerCase() === "exit") {
                    console.log("Goodbye!");
                    break;
                }

                const result = await agent.invoke({
                    messages: [{ role: "user", content: userInput }],
                });

                const finalResponse = result.messages[result.messages.length - 1];
                console.log("Agent: " + finalResponse.content);
            } catch (error) {
                console.error("Error running agent:", error);
                break;
            }
        }
    } finally {
        await client.close();
        rl.close();
        process.exit(0);
    }
}

runAgent().catch(console.error);
