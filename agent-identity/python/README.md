# Agent Identity Quickstart — Python Samples

This directory contains Python-based sample implementations demonstrating how to authenticate AI agents with Asgardeo and securely interact with MCP servers. Each scenario showcases a different authentication model.

## Available Scenarios

### agent-auth-flow/

- AI agent authenticates **on its own** using Agent Credentials.
- No user interaction or redirection is involved.
- Ideal for system agents or background tasks acting independently.

### on-behalf-of-flow/

- AI agent authenticates **on behalf of a user** using _Authorization Code + PKCE_.
- The user signs in through Asgardeo, and the agent exchanges the authorization code for an **OBO token** representing the user.

### ciba-on-behalf-of-flow/

- AI agent authenticates **on behalf of a user** using the **CIBA grant** — no browser redirect required.
- The agent detects an `insufficient_scope` error from the MCP server, prompts for the user's email, and initiates a CIBA request. The user approves via email on any device, and the agent receives an OBO token with elevated scopes.
- Ideal for CLI-only environments, back-office agents, and server-side workers.

Each directory includes its own README with setup instructions, environment variable configuration, and runnable examples using modern agent development frameworks.
