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
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, HTTPException
from starlette.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect

from app.agent import create_agent, run_agent
from app.types import TextResponse
from sdk.auth import AuthRequestMessage, AuthManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

# Asgardeo related configurations
client_id = os.environ.get('ASGARDEO_CLIENT_ID')
client_secret = os.environ.get('ASGARDEO_CLIENT_SECRET')
idp_base_url = os.environ.get('ASGARDEO_TENANT_DOMAIN')
redirect_url = os.environ.get('ASGARDEO_REDIRECT_URI', 'http://localhost:8000/callback')

# Hotel API configs
hotel_api_base_url = os.environ.get('HOTEL_API_BASE_URL')

# Azure OpenAI configs
azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')

app = FastAPI()

auth_managers: Dict[str, AuthManager] = {}
state_mapping: Dict[str, str] = {}


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
        message_handler)

    # Store the auth manager by session_id
    auth_managers[session_id] = auth_manager

    hotel_assistant = await create_agent(base_url=hotel_api_base_url, auth_manager=auth_manager)

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
