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

import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { MultiServerMCPClient } from "@langchain/mcp-adapters";

import { AsgardeoJavaScriptClient } from "@asgardeo/javascript";

import dotenv from "dotenv";

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

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
    console.log("##########################################################################################################")
    console.log("##      This is an Agent Authentication Flow sample application for authenticating AI agents            ##")
    console.log("##                         using Asgardeo and LangChain framework                                       ##")
    console.log("##########################################################################################################")

    const asgardeoJavaScriptClient = new AsgardeoJavaScriptClient(asgardeoConfig);
    const agentToken = await asgardeoJavaScriptClient.getAgentToken(agentConfig);

    const client = new MultiServerMCPClient({
        math: {
            transport: "http",
            url: process.env.MCP_SERVER_URL || "http://localhost:8000/mcp",
            headers: {
                Authorization: "Bearer " + agentToken.accessToken,
            },
        },
    });

    const tools = await client.getTools();

    const agent = createReactAgent({
        llm: model,
        tools: tools,
    });

    const rl = readline.createInterface({ input, output });

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

    await client.close();
    rl.close();
}

runAgent().catch(console.error);
