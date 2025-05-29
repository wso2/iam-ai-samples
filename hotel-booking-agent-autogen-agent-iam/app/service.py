"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you’ve
  entered into with WSO2 governing the purchase of this software and any
"""

import logging
import os
from typing import Literal, Dict

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, HTTPException
from pydantic import BaseModel
from starlette.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect

from app.prompt import agent_system_prompt
from app.tools import fetch_hotels, fetch_rooms, make_booking
from autogen.tool import SecureFunctionTool
from sdk.auth import AuthRequestMessage, AuthManager, AuthSchema, AuthConfig, AgentConfig, OAuthTokenType
from fastapi.responses import FileResponse

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

# Asgardeo related configurations
client_id = os.environ.get('ASGARDEO_CLIENT_ID')
client_secret = os.environ.get('ASGARDEO_CLIENT_SECRET')
idp_base_url = os.environ.get('ASGARDEO_TENANT_DOMAIN')
redirect_url = os.environ.get('ASGARDEO_REDIRECT_URI', 'http://localhost:8000/callback')

# Azure OpenAI configs
azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')
azure_openai_api_version = os.environ.get('AZURE_OPENAI_API_VERSION')

app = FastAPI()


class TextResponse(BaseModel):
    type: Literal["message"] = "message"
    content: str


model_client = AzureOpenAIChatCompletionClient(
    azure_deployment=deployment_name,
    api_version=azure_openai_api_version,
    azure_endpoint=azure_openai_endpoint,
    model="gpt-4o"
)

auth_managers: Dict[str, AuthManager] = {}
state_mapping: Dict[str, str] = {}


async def run_agent(assistant: AssistantAgent, websocket: WebSocket):
    # Start the chat loop
    while True:
        user_input = await websocket.receive_text()

        if user_input.strip().lower() == "exit":
            await websocket.close()
            break

        # Send the user message to the agent
        response = await assistant.on_messages(
            [TextMessage(content=user_input, source="user")], cancellation_token=CancellationToken())

        # Log the response
        for i, msg in enumerate(response.inner_messages):
            print(f"Step {i + 1}: {msg.content}")
        print(f"Final Response: {response.chat_message.content}")

        # Send the response back to the client
        await websocket.send_json(TextResponse(content=response.chat_message.content).model_dump())

@app.get('/')
async def index():
    return FileResponse('static/index.html')

@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for chat functionality"""

    # Create callback function to handle auth request redirects
    async def message_handler(message: AuthRequestMessage):
        state_mapping[message.state] = session_id
        await websocket.send_json(message.model_dump())

    # Create a auth manager instance for the chat session.
    # Auth manager is shared by all the tools in the session.
    auth_manager = AuthManager(
        idp_base_url,
        client_id,
        client_secret,
        redirect_url,
        message_handler,
        agent_config=AgentConfig(
            agent_id=os.environ.get('AGENT_ID'),
            agent_name=os.environ.get('AGENT_NAME'),
            agent_secret=os.environ.get('AGENT_SECRET'),
        ))

    # Store the auth manager by session_id
    auth_managers[session_id] = auth_manager

    # Create the set of tools required
    fetch_hotels_tool = SecureFunctionTool(
        fetch_hotels,
        description="Fetches all hotels and information about them",
        name="FetchHotelsTool",
        auth=AuthSchema(auth_manager, AuthConfig(
            scopes=["read_hotels"],
            token_type=OAuthTokenType.AGENT_TOKEN,
            resource="booking_api"
        )),
        strict=True
    )

    fetch_hotel_rooms_tool = SecureFunctionTool(
        fetch_rooms,
        description="Fetch the rooms available, and information related such as price, amenities, etc.",
        name="FetchHotelRoomsTool",
        auth=AuthSchema(auth_manager, AuthConfig(scopes=["read_rooms"],
                                                             token_type=OAuthTokenType.AGENT_TOKEN,
                                                             resource="booking_api")),
        strict=True
    )

    book_hotel_tool = SecureFunctionTool(
        make_booking,
        description="Books the hotel room selected by the user.",
        name="BookHotelTool",
        auth=AuthSchema(auth_manager, AuthConfig(scopes=["create_bookings", "openid", "profile"],
                                                 token_type=OAuthTokenType.OBO_TOKEN,
                                                 resource="booking_api")),
        strict=True
    )

    # Create a agent instance for the chat session
    hotel_assistant = AssistantAgent(
        "hotel_booking_assistant",
        model_client=model_client,
        tools=[fetch_hotels_tool, fetch_hotel_rooms_tool, book_hotel_tool],
        reflect_on_tool_use=True,
        system_message=agent_system_prompt)

    # Initiate a web-socket connection
    await websocket.accept()

    try:
        # Welcome message
        await websocket.send_json(TextResponse(
            content="Welcome to Gardeo Hotel Booking! How can I help you today?"
        ).model_dump())

        # Continue to run the agent
        await run_agent(hotel_assistant, websocket)
    except WebSocketDisconnect:
        print(f"Client with session_id {session_id} disconnected")
    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
    finally:
        auth_managers.pop(session_id, None)


@app.get("/callback")
async def callback(
        code: str,
        state: str):
    # Check if the state is valid
    session_id = state_mapping.pop(state, None)
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid state.")

    # Get the auth manager for the session
    auth_manager = auth_managers.get(session_id)
    if not auth_manager:
        raise HTTPException(status_code=400, detail="Invalid session.")

    try:
        token = await auth_manager.process_callback(state, code)

        return HTMLResponse(
            content=f"""
            <html>
            <head>
                <title>Authorization Successful</title>
                <script>
                    function communicateAndClose() {{
                        if (window.opener) {{
                            try {{
                                const message = {{
                                    type: 'auth_callback',
                                    token: {token.model_dump_json()},
                                    state: '{state}'
                                }};

                                // Use postMessage to send token to opener
                                window.opener.postMessage(message, "*");

                                // Show success message
                                document.getElementById('status').textContent = 'Authorization successful! Closing window...';

                                // Close the window after a short delay
                                setTimeout(function() {{
                                    window.close();
                                }}, 1500);
                            }} catch (err) {{
                                console.error('Error communicating with parent window:', err);
                                document.getElementById('status').textContent = 'Error: ' + err.message;
                            }}
                        }} else {{
                            document.getElementById('status').textContent = 'Cannot find opener window.';
                        }}
                    }}

                    window.onload = communicateAndClose;
                </script>
            </head>
            <body>
                <div style="text-align: center; font-family: Arial, sans-serif; margin-top: 50px;">
                    <h2>Authorization Successful</h2>
                    <p id="status">Processing authorization...</p>
                    <p>You can close this window and return to the booking assistant.</p>
                </div>
            </body>
            </html>
            """
        )
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
