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
from pathlib import Path
from dotenv import load_dotenv

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from crewai import Agent, Task, Crew
from crewai.mcp import MCPServerHTTP

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

async def get_agent_token():
    """Asynchronously fetches the agent token from Asgardeo."""
    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        return await auth_manager.get_agent_token(["openid"])

def main():
    # 1. Fetch authentication token
    # We do this first to keep the CrewAI execution fully synchronous and avoid event loop conflicts.
    print("Authenticating with Asgardeo...")
    agent_token = asyncio.run(get_agent_token())

    # 2. Get the user question
    question = input("Enter your question: ")

    # 3. Configure the MCP server for CrewAI
    # We map StreamableHTTPConnectionParams directly to MCPServerHTTP
    mcp_server = MCPServerHTTP(
        url=os.getenv("MCP_SERVER_URL"),
        headers={"Authorization": f"Bearer {agent_token.access_token}"},
        streamable=True
    )

    # 4. Define the CrewAI Agent
    agent = Agent(
        role="Calculation Specialist",
        goal="Add two numbers accurately using an MCP server.",
        backstory="You are an intelligent agent that strictly uses the provided MCP tool 'add(a, b)' to compute the addition of numbers when requested by a user.",
        mcps=[mcp_server],
        verbose=False
    )

    # 5. Define the Task
    task = Task(
        description=f"Address the user's request: '{question}'",
        expected_output="The exact calculated sum of the numbers based on the MCP tool execution.",
        agent=agent
    )

    # 6. Setup and run the Crew
    crew = Crew(
        agents=[agent],
        tasks=[task]
    )

    result = crew.kickoff()

    print("\nAgent Response:", result.raw)

if __name__ == "__main__":
    main()
