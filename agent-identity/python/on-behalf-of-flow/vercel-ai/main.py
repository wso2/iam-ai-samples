"""
 Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

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

import vercel_ai_sdk as ai

from dotenv import load_dotenv
from pathlib import Path

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

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

# 1. Define the agent logic (no decorators needed)
async def my_agent(llm, messages, auth_token):

    # Connect to MCP Server using the user's OBO token
    tools = await ai.mcp.get_http_tools(
        os.getenv("MCP_SERVER_URL"),
        headers={
            "Authorization": f"Bearer {auth_token}"
        }
    )

    # Execute the agent tool loop
    return await ai.stream_loop(llm, messages, tools=tools)


async def main():
    print("##########################################################################################################")
    print("##     This is an On-Behalf-Of (OBO) authentication sample application for authenticating AI agents     ##")
    print("##                         using Asgardeo and Vercel AI framework                                       ##")
    print("##########################################################################################################")

    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid", "email"])

        auth_url, state, code_verifier = auth_manager.get_authorization_url_with_pkce(["openid", "email"])

        print("Open this URL in your browser to authenticate:")
        print(auth_url)

        callback = OAuthCallbackServer(port=6274)
        callback.start()

        print("Waiting for authorization code from redirect...")

        auth_code, returned_state, error = await callback.wait_for_code()
        callback.stop()

        if auth_code is None:
            print(f"Authorization failed or cancelled. Error: {error}")
            return

        obo_token = await auth_manager.get_obo_token(auth_code, agent_token=agent_token, code_verifier=code_verifier)


    google_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    os.environ["OPENAI_API_KEY"] = google_key
    os.environ["OPENAI_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai/"

    llm = ai.openai.OpenAIModel(
        model=os.getenv("MODEL_NAME")
    )

    user_input = input("Enter your question: ")
    messages = ai.make_messages(user=user_input)

    result = ai.run(my_agent, llm, messages, obo_token.access_token)

    print("\nAgent Response: ", end="")

    # Stream the output token-by-token
    async for msg in result:
        if getattr(msg, "text_delta", None):
            print(msg.text_delta, end="", flush=True)

    print()

if __name__ == "__main__":
    asyncio.run(main())
