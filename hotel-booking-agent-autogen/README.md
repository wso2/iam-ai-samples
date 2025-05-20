# Building Secured AI Agents

This sample demonstrates how to build AI assistants that can securely access protected APIs using OAuth
authentication. The example shows a hotel booking assistant that interacts with secured APIs.

## Overview

The project consists of:

1. **Authentication SDK** (`auth.py`) - Handles OAuth flows including client credentials and user authorization
2. **Secure Function Tools** (`tool.py`) - Extends AutoGen's function tools with authentication capabilities
3. **Service Layer** (`service.py`) - Implements a WebSocket API for the hotel booking assistant
4. **API Tools** (`tools.py`) - API client functions for hotel services

## Prerequisites

- Python 3.10+
- Azure OpenAI service access
- Asgardeo tenant or other OAuth 2.0 provider
- (Hotel API service)[https://github.com/nadheesh/agent_demo_hotel_api]

## Configuration

Set up the following environment variables:

```
# API Service
HOTEL_API_BASE_URL=http://your-hotel-api-url

# Asgardeo (OAuth App for Hotel API)
ASGARDEO_CLIENT_ID=your_client_id
ASGARDEO_CLIENT_SECRET=your_client_secret  
ASGARDEO_TENANT_DOMAIN=https://your-tenant.asgardeo.io
ASGARDEO_REDIRECT_URI=http://localhost:8000/callback

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
```

## Key Components

### Authentication SDK (auth.py)

The `auth.py` module provides a flexible OAuth authentication framework:

- **Token Management**: Handles token acquisition, caching, and renewal
- **Multiple Token Types**: Supports both service-to-service (client) token and on-behalf-of user (OBO) token flows
- **Token Caching**: Efficiently manages tokens with TTL-based expiration

Key classes:

- `AuthManager`: Manages OAuth tokens and authentication flows
- `OAuthToken`: Represents token data with expiration tracking
- `AuthConfig`: Defines authentication requirements (scopes, token type)
- `AuthSchema`: Links tools with authentication requirements

### Secure Function Tool (tool.py)

The `SecureFunctionTool` extends AutoGen's `FunctionTool` with:

- Automatic token acquisition before function execution
- Permission enforcement through scopes
- Transparent function call modification to include tokens

### Building Authenticated Agents

Follow these steps to create agents with secure API access:

1. **Create an Auth Manager**:

```python
auth_manager = AuthManager(
    idp_base_url="https://api.asgardeo.io/t/<your-tenant-handle>",
    client_id="your_client_id",
    client_secret="your_client_secret",
    redirect_uri="http://localhost:8000/callback",
    message_handler=async_handler_function  # For authorization code flow
)
```

2. **Create Secure Function Tools**:

```python
# API function with token parameter
async def fetch_data(param1, param2, token: OAuthToken):
    # Use token.access_token for API calls
    headers = {"Authorization": f"Bearer {token.access_token}"}
    # Make API request...


# Create secure tool with client credentials (service-to-service)
service_tool = SecureFunctionTool(
    fetch_data,
    description="Fetches data from service API",
    name="FetchDataTool",
    auth=AuthSchema(
        auth_manager,
        AuthConfig(
            scopes=["read_data"],
            token_type=OAuthTokenType.CLIENT_TOKEN
        )
    )
)

# Create secure tool requiring user authorization
user_context_tool = SecureFunctionTool(
    make_transaction,
    description="Makes a transaction on behalf of the user",
    name="TransactionTool",
    auth=AuthSchema(
        auth_manager,
        AuthConfig(
            scopes=["write_data", "openid", "profile"],
            token_type=OAuthTokenType.OBO_TOKEN
        )
    )
)
```

3. **Create an Assistant with the secure tools**:

```python
assistant = AssistantAgent(
    "my_assistant",
    model_client=your_model_client,
    tools=[service_tool, user_context_tool],
    system_message="You are a helpful assistant..."
)
```

## Hotel Booking Assistant Example

The repository includes a complete example of a hotel booking assistant that:

1. Fetches hotel information using client credentials
2. Fetches room availability using client credentials
3. Books rooms using user authorization (OAuth authorization code flow)

### Running the Example

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables in a `.env` file

3. Start the FastAPI service:

```bash
uvicorn app.service:app --reload
```

4. Connect to the WebSocket endpoint at `ws://localhost:8000/chat?session_id=unique_id` or use [frontend.html](frontend.html)

### User Flow

1. User connects to chat and asks about hotels
2. Assistant uses client credential tools to fetch hotel/room data
3. When user wants to book, assistant uses the booking tool which requires user authentication
4. User is redirected to Asgardeo login, then returns with authorization code
5. Assistant completes the booking with user context

## Authentication Flows in Detail

### Client Credentials Flow

Used for service-to-service API calls where no user context is needed:

1. Tool is invoked by the agent
2. `SecureFunctionTool` requests token from `AuthManager`
3. `AuthManager` checks token cache, fetches new token if needed
4. Token is injected into tool function call
5. API call is made with service credentials

### Authorization Code Flow

Used when human-in-the-loop (user context) is required:

1. Tool is invoked by the agent
2. `SecureFunctionTool` requests token from `AuthManager`
3. `AuthManager` generates auth URL and state parameter
4. Auth request is sent through message handler to client
5. User is redirected to login page
6. After login, auth code is returned via callback endpoint
7. `AuthManager` exchanges code for token
8. Token is cached and injected into tool function
9. API call is made with user context

## Best Practices

1. **Scope Management**: Use specific, minimal scopes for each tool
2. **Error Handling**: Implement proper OAuth error handling
3. **Token Caching**: Configure appropriate TTL settings for tokens
4. **Security**: Never expose tokens to users or log them
5. **Function Design**: Design API functions to accept token as a parameter

## Extending the Framework

You can extend this framework for additional authentication methods:

- Add support for PKCE flow for public clients
- Implement refresh token logic for long-running sessions
- Add additional token stores (Redis, database)
- Support for JWT validation and introspection

## Troubleshooting

- **Authentication Failures**: Check client ID, secret, and redirect URI configuration
- **Token Expiration**: Verify token TTL settings and token refresh logic
- **Scope Issues**: Ensure your application is registered with all required scopes
- **Callback Problems**: Confirm redirect URI matches your OAuth provider configuration

## License

Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

This software is the property of WSO2 LLC. and its suppliers. Dissemination of any information or reproduction of any
material contained herein is strictly forbidden, unless permitted by WSO2 in accordance with the WSO2 Commercial
License.