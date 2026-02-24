"""
 Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any


  OAuth Callback Listener

  This module provides a lightweight local HTTP server used to capture OAuth 2.1
  redirect responses during OBO agent authentication flow.

  This listens on a localhost port, receives the authorization code returned by the
  identity provider (Asgardeo), and makes it available to the application.

"""
import os
import asyncio
import sys
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from pydantic import Field

# Asgardeo / Identity imports
from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

# Fix path to import common callback
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.oauth_callback import OAuthCallbackServer

# Load environment variables
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

# --- Custom CrewAI Tool ---

class MCPCalculatorTool(BaseTool):
    name: str = "add_numbers"
    description: str = "Adds two numbers using a secure remote MCP service. Input should be two integers."
    access_token: str = Field(..., exclude=True) # Pass the OBO token here

    def _run(self, a: int, b: int) -> str:
        # Here you would perform the actual HTTP call to your MCP_SERVER_URL
        # headers={"Authorization": f"Bearer {self.access_token}"}
        # For now, we simulate the tool execution:
        return f"The MCP server calculated that {a} + {b} equals {a + b}."

# --- Auth Logic ---

async def get_obo_token():
    """Handles the OAuth/OBO flow to get the user token."""
    ASGARDEO_CONFIG = AsgardeoConfig(
        base_url=os.getenv("ASGARDEO_BASE_URL"),
        client_id=os.getenv("CLIENT_ID"),
        redirect_uri=os.getenv("REDIRECT_URI")
    )
    AGENT_CONFIG = AgentConfig(
        agent_id=os.getenv("AGENT_ID"),
        agent_secret=os.getenv("AGENT_SECRET")
    )

    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid", "email"])
        auth_url, state, code_verifier = auth_manager.get_authorization_url_with_pkce(["openid", "email"])

        print(f"\nOpening browser for authentication...")
        webbrowser.open(auth_url)

        callback = OAuthCallbackServer(port=6274)
        callback.start()

        auth_code, _, error = await callback.wait_for_code()
        callback.stop()

        if not auth_code:
            raise Exception(f"Auth failed: {error}")

        obo_token = await auth_manager.get_obo_token(
            auth_code,
            agent_token=agent_token,
            code_verifier=code_verifier
        )
        return obo_token.access_token

# --- Main CrewAI Execution ---

async def main():
    # 1. Get the Token via OBO Flow
    try:
        access_token = await get_obo_token()
        print("Successfully obtained OBO Token.")
    except Exception as e:
        print(f"Failed to authenticate: {e}")
        return

    # 2. Initialize the CrewAI Tool with the token
    math_tool = MCPCalculatorTool(access_token=access_token)

    # 3. Define the CrewAI Agent
    calculator_agent = Agent(
        role="Calculation Specialist",
        goal="Perform accurate arithmetic by calling the external MCP tool.",
        backstory="You are a precise assistant that never guesses math; you always use your tools.",
        tools=[math_tool],
        llm=os.getenv("MODEL_NAME"), # Use 'gemini/gemini-1.5-flash' or similar
        verbose=False
    )

    while True:
        # 4. Define the Task
        user_question = input("\nEnter your question (e.g., 'Add 45 and 99') or type 'exit' to quit: ")

        # Exit the loop if the user types "exit"
        if user_question.lower() == "exit":
            print("Exiting the program. Goodbye!")
            break

        calculation_task = Task(
            description=f"Process this request: {user_question}",
            expected_output="A clear sentence providing the final numeric result from the tool.",
            agent=calculator_agent
        )

        # 5. Form the Crew and Execute
        calculation_crew = Crew(
            agents=[calculator_agent],
            tasks=[calculation_task],
            process=Process.sequential
        )

        result = calculation_crew.kickoff()

        print("\nAgent Response:", result.raw)


if __name__ == "__main__":
    asyncio.run(main())
