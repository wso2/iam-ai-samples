# Agent Identity Quickstart — Python Samples

This directory contains two Python-based sample implementations demonstrating how to authenticate AI agents with Asgardeo and securely interact with MCP servers. Each scenario showcases a different authentication model.

## Available Scenarios

### agent-auth-flow/

- AI agent authenticates **on its own** using Agent Credentials.
- No user interaction or redirection is involved.
- Ideal for system agents or background tasks acting independently.

### on-behalf-of-flow/

- AI agent authenticates **on behalf of a user** using _Authorization Code + PKCE_.
- The user signs in through Asgardeo, and the agent exchanges the authorization code for an **OBO token** representing the user.

Each directory includes its own README with setup instructions, environment variable configuration, and runnable examples using modern agent development frameworks.
