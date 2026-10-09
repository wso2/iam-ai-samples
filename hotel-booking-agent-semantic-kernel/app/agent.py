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
import os

from dotenv import load_dotenv
from fastapi import WebSocket
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
from semantic_kernel.kernel import Kernel

from app.plugins import HotelAPIPlugin
from app.prompt import agent_system_prompt
from app.types import TextResponse
from sdk.auth import AuthManager

load_dotenv()

# Azure OpenAI configs
azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
azure_openai_api_key = os.environ.get('AZURE_OPENAI_API_KEY')
deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')


async def create_agent(base_url: str, auth_manager: AuthManager):
    # Create the instance of the Kernel
    kernel = Kernel()

    # Add the chat completion service to the Kernel
    kernel.add_service(AzureChatCompletion(
        api_key=azure_openai_api_key,
        deployment_name=deployment_name,
        endpoint=azure_openai_endpoint,
        api_version="2024-02-01",
        service_id="azure_openai_chat"
    ))

    # Get the AI Service settings
    settings = kernel.get_prompt_execution_settings_from_service_id(service_id="azure_openai_chat")

    # Configure the function choice behavior to auto invoke kernel functions
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

    # Add the Plugin to the Kernel
    kernel.add_plugin(HotelAPIPlugin(base_url, auth_manager), plugin_name="hotel_api")

    # Create the agent
    agent = ChatCompletionAgent(
        kernel=kernel,
        name="HotelBookingAgent",
        instructions=agent_system_prompt,
        arguments=KernelArguments(settings=settings)
    )

    return agent


async def run_agent(agent: ChatCompletionAgent, websocket: WebSocket):
    # Start the chat loop
    thread: ChatHistoryAgentThread = None
    answer: str = ""
    while True:
        user_input = await websocket.receive_text()

        if user_input.strip().lower() == "exit":
            await websocket.close()
            break

        # Send the user message to the agent
        async for response in agent.invoke(messages=user_input, thread=thread):
            print(f"{response.content}")
            thread = response.thread
            answer = response.content.content
        print(f"Final Response: {answer}")

        # Send the response back to the client
        await websocket.send_json(TextResponse(content=answer).model_dump())
