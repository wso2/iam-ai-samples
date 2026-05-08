## Running with npx

The fastest way to try Agent Auth Playground - no clone, no install, no config:

```bash
npx agent-auth-playground
```

That's it. The local server starts on `http://localhost:4829` and your browser opens automatically.

**CLI flags:**

| Flag | Default | Purpose |
|------|---------|---------|
| `--port <n>` | `4829` | Port to listen on |
| `--host <h>` | `localhost` | Host to bind to |
| `--no-open` | - | Don't open the browser automatically |
| `-h`, `--help` | - | Show help |
| `-v`, `--version` | - | Show version |

All configuration - LLM API keys (OpenAI, Gemini, Anthropic) and per-node Asgardeo OAuth2 credentials, is entered in the UI and stored in browser `localStorage`. The CLI itself takes no secrets and reads no env files.

---

## Running from source

### Prerequisites

- Node.js ≥ 18.18
- pnpm (`npm install -g pnpm`)

### Installation

```bash
git clone https://github.com/wso2/iam-ai-samples
cd agent-auth-playground
pnpm install
```

### Running Locally

```bash
pnpm dev               # Next.js dev server
pnpm build             # Production build 
pnpm start             # Serve the production build
```

The app runs on **port 4829** by default.
