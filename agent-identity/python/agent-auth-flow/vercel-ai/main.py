import os
import asyncio

from dotenv import load_dotenv
from pathlib import Path

from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

# Import the official Vercel AI SDK for Python
import vercel_ai_sdk as ai

# Load environment variables
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

# --- THE FIX ---
# Removed @ai.stream! We just define it as a normal async function.
# Since it is called by ai.run(), the connection pool is still safely active.
async def my_agent(llm, messages, auth_token):

    tools = await ai.mcp.get_http_tools(
        os.getenv("MCP_SERVER_URL"),
        headers={
            "Authorization": f"Bearer {auth_token}"
        }
    )

    return await ai.stream_loop(llm, messages, tools=tools)


async def main():

    async with AgentAuthManager(ASGARDEO_CONFIG, AGENT_CONFIG) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid"])

    # Map your Google API key to the OpenAI environment variable for compatibility
    google_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    os.environ["OPENAI_API_KEY"] = google_key
    os.environ["OPENAI_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai/"

    llm = ai.openai.OpenAIModel(
        model=os.getenv("MODEL_NAME")
    )

    user_input = input("Enter your question: ")
    messages = ai.make_messages(user=user_input)

    result = ai.run(my_agent, llm, messages, agent_token.access_token)

    print("\nAgent Response: ", end="")

    async for msg in result:
        if getattr(msg, "text_delta", None):
            print(msg.text_delta, end="", flush=True)

    print()


# Run app
if __name__ == "__main__":
    asyncio.run(main())
