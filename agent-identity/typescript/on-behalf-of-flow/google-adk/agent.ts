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

import "dotenv/config";
import express from "express";
import { LlmAgent, MCPToolset, InMemoryRunner } from "@google/adk";

import { AsgardeoJavaScriptClient } from "@asgardeo/javascript";

import dotenv from "dotenv";
import open from "open";

const port = '3001';

dotenv.config({
  path: "../../.env",
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

process.env.GOOGLE_GENAI_API_KEY = process.env.GOOGLE_API_KEY;

async function runAgent() {
    silenceADK();

    console.log("##########################################################################################################")
    console.log("##     This is an On-Behalf-Of (OBO) authentication sample application for authenticating AI agents     ##")
    console.log("##                         using Asgardeo and Google ADK framework                                      ##")
    console.log("##########################################################################################################")

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
                    Promise.reject(new Error("No authorization code found."));
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

    const rootAgent = new LlmAgent({
        name: "example_agent",
        model: process.env.GOOGLE_GENAI_MODEL || "gemini-2.5-flash",
        instruction: `You are a helpful AI assistant.`,
        apiKey: process.env.GOOGLE_API_KEY,
        tools: [
            new MCPToolset({
                type: "StreamableHTTPConnectionParams",
                url: process.env.MCP_SERVER_URL,
                header: {
                    Authorization: `Bearer ${oboToken.accessToken}`,
                },
            }),
        ],
    });

    const runner = new InMemoryRunner({
        agent: rootAgent,
        appName: "my-custom-app",
    });

    const userId = "user-123";
    const session = await runner.sessionService.createSession({
        appName: "my-custom-app",
        userId: userId,
    });

    const rl = readline.createInterface({ input, output });

    try {
        while (true) {
            const userInput = await rl.question("\nEnter your question (e.g., 'Add 45 and 99') or type 'exit' to quit: ");

            if (userInput.toLowerCase() === "exit") {
                await runner.sessionService.deleteSession({
                    appName: "my-custom-app",
                    sessionId: session.id,
                });
                break;
            }

            // ...existing code...
        }
    } finally {
        rl.close();
        process.exit(0);
    }
}

function silenceADK() {
    const originalWrite = process.stdout.write;
    // @ts-ignore
    process.stdout.write = function (chunk, encoding, callback) {
        if (typeof chunk === 'string' && chunk.includes('[ADK INFO]')) {
            return true;
        }
        return originalWrite.apply(process.stdout, [chunk, encoding, callback]);
    };
}

runAgent().catch(console.error);
