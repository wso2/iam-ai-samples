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
import time

from dotenv import load_dotenv
from pathlib import Path

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

ASGARDEO_CONFIG = AsgardeoConfig(
    base_url=os.getenv("ASGARDEO_BASE_URL"),
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    redirect_uri=os.getenv("REDIRECT_URI"),
)

AGENT_CONFIG = AgentConfig(
    agent_id=os.getenv("AGENT_ID"),
    agent_secret=os.getenv("AGENT_SECRET"),
)

TASKS_MCP_SERVER_URL = os.getenv("TASKS_MCP_SERVER_URL", "http://127.0.0.1:8100/mcp")
CIBA_NOTIFICATION_CHANNEL = os.getenv("CIBA_NOTIFICATION_CHANNEL", "email")

INSUFFICIENT_SCOPE_SENTINEL = "insufficient_scope"


def build_mcp_config(access_token: str) -> dict:
    return {
        "tasks_server": {
            "transport": "streamable_http",
            "url": TASKS_MCP_SERVER_URL,
            "headers": {
                "Authorization": f"Bearer {access_token}",
            },
        }
    }


def has_insufficient_scope(response: dict) -> bool:
    """Check if the agent response contains an insufficient_scope error."""
    for msg in response.get("messages", []):
        content = msg.content if hasattr(msg, "content") else str(msg)
        if INSUFFICIENT_SCOPE_SENTINEL in content:
            return True
    return False


async def main():
    print("##########################################################################################################")
    print("##   This is a CIBA-based On-Behalf-Of (OBO) authentication sample for authenticating AI agents        ##")
    print("##                         using Asgardeo and LangChain framework                                      ##")
    print("##########################################################################################################")

    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid", "tasks:templates_read"])

        print("\nAgent token obtained successfully.")

        client = MultiServerMCPClient(build_mcp_config(agent_token.access_token))

        llm = ChatGoogleGenerativeAI(
            model=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
            temperature=0.9,
        )

        tools = await client.get_tools()
        agent = create_agent(llm, tools)

        obo_token = None
        obo_expires_at = 0

        while True:
            user_input = input("\nEnter your question or type 'exit' to quit: ")
            if user_input.lower() == "exit":
                print("Exiting the program. Goodbye!")
                break

            response = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]}
            )

            if has_insufficient_scope(response):
                # Check if we already have a valid OBO token
                if obo_token and time.time() < obo_expires_at:
                    print("OBO token is still valid but scopes are insufficient. Cannot retry.")
                    print("Agent Response:", response["messages"][-1].content)
                    continue

                print("\nThe agent needs higher privileges to complete this request.")
                username = input("Enter your Asgardeo username (email): ")

                try:
                    _, obo_token = await auth_manager.get_obo_token_with_ciba(
                        login_hint=username,
                        agent_token=agent_token,
                        scopes=["openid", "tasks:templates_read", "tasks:read", "tasks:write"],
                        binding_message=f"AI agent requests access to your tasks: {user_input!r}",
                        notification_channel=CIBA_NOTIFICATION_CHANNEL,
                        on_initiated=lambda r: print(
                            f"\nApproval request sent via {CIBA_NOTIFICATION_CHANNEL}. "
                            f"Waiting up to {r.expires_in}s for approval..."
                        ),
                    )

                    obo_expires_at = time.time() + obo_token.expires_in
                    print("OBO token obtained successfully. Retrying your request...\n")

                    client = MultiServerMCPClient(build_mcp_config(obo_token.access_token))
                    tools = await client.get_tools()
                    agent = create_agent(llm, tools)

                    response = await agent.ainvoke(
                        {"messages": [{"role": "user", "content": user_input}]}
                    )
                except Exception as e:
                    error_msg = str(e)
                    if "access_denied" in error_msg:
                        print("The user denied the approval request.")
                    elif "expired_token" in error_msg or "timed out" in error_msg:
                        print("The approval request expired. The user did not respond in time.")
                    elif "Client secret is required" in error_msg:
                        print(
                            "CLIENT_SECRET is not set. CIBA requires a confidential client.\n"
                            "Set CLIENT_SECRET in your .env file. See: "
                            "https://wso2.com/asgardeo/docs/guides/authentication/configure-ciba-grant/"
                        )
                    else:
                        print(f"CIBA step-up failed: {e}")
                    continue

            print("Agent Response:", response["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
