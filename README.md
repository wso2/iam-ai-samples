# IAM AI Samples

This repo includes the samples that demonstrate securing AI applications using the WSO2 IAM platform.

## Samples

1) [Hotel Booking Agent with AutoGen](hotel-booking-agent-autogen/README.md) - Hotel Booking AI agent secured with traditional IAM concepts and primitives provided by the AutoGen framework.
2) [Hotel Booking Agent with AutoGen With SecureFunctionTool Extension](hotel-booking-agent-autogen-with-securetool/README.md) - Hotel Booking AI agent secured with traditional IAM concepts and dedicated secureFunctionTool extension that extends Autogen framework primitives and validates permissions before tool invocation.
3) [Hotel Booking Agent with Agent IAM](hotel-booking-agent-autogen-agent-iam/README.md) - Hotel Booking AI agent secured with AI Agent Identity Management provided by Asgardeo.
4) [MCP Auth/Python](mcp-auth/python/README.md) - Example implementation of a protected Python MCP server secured with the WSO2 IAM platform
5) [MCP Auth/TypeScript](mcp-auth/typescript/README.md) - Example implementation of a protected TypeScript MCP server secured with the WSO2 IAM platform
6) [Agent Authentication/Python](agent-auth/python/README.md) - Demonstrates how AI agents authenticate with Asgardeo using either direct Agent Credentials or user-delegated OBO tokens. These samples show how agents securely obtain and use access tokens to call backend services or MCP tool servers.
