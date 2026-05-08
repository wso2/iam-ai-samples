# AI Service

The AI Service node connects your AgentFlow to an external AI model. The AI Agent calls it at each step of its reasoning loop to decide what to do next.

---

## Connections

| Handle | Direction | Connects to |
|--------|-----------|-------------|
| Bottom | Input | AI Agent (top handle) |

The AI Service only accepts connections from the **top handle** of AI Agent nodes.

---

## Configuration

Click the AI Service node to configure it in the right panel.

| Field | Default | Description |
|-------|---------|-------------|
| **Provider** | Gemini | The AI company whose API you want to use: Google Gemini, OpenAI, Anthropic, or Azure OpenAI |
| **Model** | `gemini-2.5-flash` | The specific model variant. Options update automatically when you change the provider. |
| **Credentials** | — | A saved credential set for the selected provider, chosen from the dropdown |
| **Temperature** | `0.7` | Creativity level: `0` = consistent, `2` = highly varied |
| **Max Tokens** | `1000` | Maximum tokens the model can generate per response |

### Credentials

LLM credentials are stored globally and reused across all your AgentFlows. The credential fields shown depend on the selected provider:

| Provider | Fields |
|----------|--------|
| **Gemini** (API key) | Name, API Key |
| **Gemini** (GCP access token) | Name, GCP Access Token, GCP Project ID |
| **OpenAI** | Name, API Key |
| **Anthropic** | Name, API Key |
| **Azure OpenAI** | Name, API Key, Resource Name, Deployment Name, API Version |

You can create, edit, and delete credentials directly from the AI Service configuration panel. Each credential is scoped to its provider - switching providers shows only the credentials that match.

---

## Tips

- **Temperature for agents** — setting Temperature to `0` makes the agent's tool-calling decisions more predictable and easier to debug.
- **Max Tokens for agents** — each agent step only needs to produce a short JSON response (`call this tool` or `final answer`). Keeping Max Tokens at 500–1500 is usually sufficient and faster.
- **Switching providers** — you can change the provider and model at any time. Existing API keys for other providers are preserved.
