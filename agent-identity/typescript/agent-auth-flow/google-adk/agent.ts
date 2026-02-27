import { stdin as input, stdout as output } from "node:process";
import * as readline from "node:readline/promises";

import dotenv from "dotenv";

import { LlmAgent, MCPToolset, InMemoryRunner } from "@google/adk";

import { AsgardeoJavaScriptClient } from "@asgardeo/javascript";

dotenv.config({
  path: "../../.env",
});

// Update the configuration to use these variables
const asgardeoConfig = {
    afterSignInUrl: process.env.REDIRECT_URI,
    clientId: process.env.CLIENT_ID,
    baseUrl: process.env.ASGARDEO_BASE_URL,
};

const agentConfig = {
    agentID: process.env.AGENT_ID,
    agentSecret: process.env.AGENT_SECRET,
};

// Ensure GOOGLE_API_KEY is mapped to GOOGLE_GENAI_API_KEY
process.env.GOOGLE_GENAI_API_KEY = process.env.GOOGLE_API_KEY;

async function runAgent() {
    silenceADK(); // Silence the logs here
    
    // 1. Get Agent Token
    const asgardeoJavaScriptClient = new AsgardeoJavaScriptClient(asgardeoConfig);
    const agentToken = await asgardeoJavaScriptClient.getAgentToken(agentConfig);

    // 2. Define LLM Agent
    const rootAgent = new LlmAgent({
        name: "example_agent",
        model: "gemini-2.5-flash",
        instruction: `You are a helpful AI assistant.`,
        apiKey: process.env.GOOGLE_API_KEY,
        tools: [
            new MCPToolset({
                type: "StreamableHTTPConnectionParams",
                url: process.env.MCP_SERVER_URL,
                header: {
                    Authorization: `Bearer ${agentToken.accessToken}`,
                },
            }),
        ],
    });

    // 3. Initiate Runner with the Agent
    const runner = new InMemoryRunner({
        agent: rootAgent,
        appName: "my-custom-app",
    });

    // 4. Create a session for the user
    const userId = "user-123";
    const session = await runner.sessionService.createSession({
        appName: "my-custom-app",
        userId: userId,
    });

    // 5. Capture user input
    const rl = readline.createInterface({ input, output });
    console.log("--- AI Agent Started (Type 'exit' to quit) ---");

    while (true) {
        const userInput = await rl.question("You: ");

        if (userInput.toLowerCase() === "exit") {
            console.log("Goodbye!");
            break;
        }

        // 6. Define the User Message from input
        const userMessage = {
            role: "user",
            parts: [{ text: userInput }],
        };

        // 7. Run the agent loop
        // runAsync returns an async generator that yields events (thoughts, tool calls, responses)
        const eventStream = runner.runAsync({
            userId: userId,
            sessionId: session.id,
            newMessage: userMessage,
        });

        // 8. Consume events
        try {
            for await (const event of eventStream) {
                // Check if the event has text content to display
                if (event.content && event.content.parts) {
                    const text = event.content.parts.map((p) => p.text).join("");
                    if (text) {
                        console.log(`Agent : ${text}`);
                    }
                }
            }
        } catch (error) {
            console.error("Error running agent:", error);
        }
    }

    rl.close();
}

function silenceADK() {
    const originalWrite = process.stdout.write;
    // @ts-ignore
    process.stdout.write = function (chunk, encoding, callback) {
        if (typeof chunk === 'string' && chunk.includes('[ADK INFO]')) {
            return true; // Skip this log
        }
        return originalWrite.apply(process.stdout, [chunk, encoding, callback]);
    };
}

runAgent().catch(console.error);
