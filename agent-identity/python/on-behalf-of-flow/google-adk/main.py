"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any
"""

import os
import asyncio
import sys

from pathlib import Path
from dotenv import load_dotenv

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.oauth_callback import OAuthCallbackServer

# Load environment variables from .env file
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

ASGARDEO_CONFIG = AsgardeoConfig(
    base_url=os.getenv("ASGARDEO_BASE_URL"),
    client_id=os.getenv("CLIENT_ID"),
    redirect_uri=os.getenv("REDIRECT_URI")
)

AGENT_CONFIG = AgentConfig(
    agent_id=os.getenv("AGENT_ID"),
    agent_secret=os.getenv("AGENT_SECRET")
)

async def build_toolset():
    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        # Get agent token
        agent_token = await auth_manager.get_agent_token(["openid", "email"])

        # Generate user authorization URL
        auth_url, state, code_verifier = auth_manager.get_authorization_url_with_pkce(["openid", "email"])

        print("Open this URL in your browser to authenticate:")
        print(auth_url)

        callback = OAuthCallbackServer(port=6274)
        callback.start()

        print("Waiting for authorization code from redirect...")

        # Wait for redirect
        auth_code, returned_state, error = await callback.wait_for_code()
        callback.stop()

        if auth_code is None:
            print(f"Authorization failed or cancelled. Error: {error}")
            return

        print("Received authorization code")

        # Exchange auth code for user token (OBO flow)
        obo_token = await auth_manager.get_obo_token(auth_code, agent_token=agent_token, code_verifier=code_verifier)

    # Connect to MCP Server with Auth Header
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=os.getenv("MCP_SERVER_URL"),
            headers={"Authorization": f"Bearer {obo_token.access_token}"}
        )
    )

async def main():

    mcp_toolset = await build_toolset()

    if mcp_toolset is None:
        print("Failed to build toolset. Exiting.")
        return

    # Define LLM Agent (Gemini)
    agent = LlmAgent(
        model=os.getenv("MODEL_NAME"),
        name="add_agent",
        description="Adds two numbers using an MCP server.",
        instruction="When the user asks to add numbers, call the MCP tool `add(a, b)`.",
        tools=[mcp_toolset],
    )

    # Setup runner + session
    runner = InMemoryRunner(agent, app_name="add_numbers_app")

    session = await runner.session_service.create_session(
        app_name="add_numbers_app",
        user_id="user"
    )

    question = input("Enter your question: ")

    try:
        async for event in runner.run_async(
                user_id="user",
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=question)]
                ),
        ):
            if event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    print(text)

    finally:
        await mcp_toolset.close()
        await runner.close()

if __name__ == "__main__":
    asyncio.run(main())
