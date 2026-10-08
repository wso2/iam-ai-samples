# Your Data

Auth Playground stores everything in your **browser's local storage**. There is no server database, no account, and no data sent anywhere except to the AI provider APIs you configure.

---

## What This Means for You

- **Private by default** - your AgentFlows and API keys are visible only to you, in this browser.
- **No sync** - data is not shared between different browsers or devices.
- **Clearing browser data resets everything** - use the in-app controls if you only want to clear specific things.

---

## What Gets Stored

| What | Where it lives |
|------|---------------|
| AgentFlows (nodes, edges, layout) | Browser local storage |
| Chat message history | Browser local storage, per AgentFlow |
| AI Agent memory (conversation context) | Browser local storage, per agent |
| LLM credentials (API keys) | Browser local storage, shared across all AgentFlows |
| Agent credentials (client ID + secret) | Browser local storage, shared across all AgentFlows |
| OBO authorization tokens | Browser local storage, per AgentFlow per MCP node |

---

## Credentials

Credentials are stored in two separate stores:

- **LLM credentials** — API keys for AI providers (Gemini, OpenAI, Anthropic). Entering a key in one AgentFlow makes it available across all your AgentFlows in that browser. To remove a key, clear the API Key field in any AI Service node.
- **Agent credentials** — Agent identity information used by AI Agent nodes for OAuth2 authentication flows. These are also shared across all AgentFlows in that browser. To remove them, clear the fields in the AI Agent node configuration panel.

---

## Agent Memory

When an AI Agent node has **Messages to Keep** set, recent conversations are saved and provided as context the next time you chat. This lets the agent remember things you told it in past sessions.

To clear an agent's memory:
1. Select the AI Agent node on the canvas.
2. Click **Clear Memory** in the configuration panel.

Memory is cleared automatically when you delete the AgentFlow.

---

## OBO Tokens

When you complete the OBO authorization flow (logging in and granting consent), the resulting token is saved in your browser until it expires. Once expired, you'll be prompted to authorize again.

You can manually clear OBO tokens by clicking the **Remove obtained tokens** button.
Tokens are also cleared automatically when the associated AgentFlow is deleted.

---

## Storage Limits

Browser local storage is limited to approximately **5 MB** per site. AgentFlow definitions and settings take very little space. Long conversations with many messages can grow over time - if you notice things slowing down, use the chat clear button periodically.

---

## Clearing Everything

To wipe all Auth Playground data:

1. Open your browser's DevTools (usually F12).
2. Go to **Application** → **Local Storage**.
3. Find the entry for this site and click **Clear ALL**.