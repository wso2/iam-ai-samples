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
import uuid
import asyncio
from typing import Literal, Dict


from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelFamily
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.dependencies import validate_token, TokenData
from fastapi import Security

from app.prompt import system_prompt
from app.tools import (
    update_booking_admin, get_available_staff, get_booking_admin
)
from autogen.tool import SecureFunctionTool
from auth import AutogenAuthManager, AuthSchema, AuthConfig, OAuthTokenType

from asgardeo_ai import AgentConfig
from asgardeo.models import AsgardeoConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Asgardeo related configurations
client_id = os.environ.get('ASGARDEO_CLIENT_ID')
base_url = os.environ.get('ASGARDEO_BASE_URL')
redirect_uri = os.environ.get('ASGARDEO_REDIRECT_URI', 'http://localhost:8002/callback')

# agent configurations
agent_id = os.environ.get('AGENT_ID')
agent_name = os.environ.get('AGENT_NAME')
agent_secret = os.environ.get('AGENT_SECRET')

asgardeo_config = AsgardeoConfig(
    base_url=base_url,
    client_id=client_id,
    redirect_uri=redirect_uri
)

# Interactive booking agent config
agent_config = AgentConfig(
    agent_id=agent_id,
    agent_secret=agent_secret,
)

# Gemini configs
gemini_api_key = os.environ.get('GEMINI_API_KEY')

app = FastAPI()


class TextResponse(BaseModel):
    type: Literal["message"] = "message"
    content: str

class AssignmentRequest(BaseModel):
    event_type: str
    booking_id: int
    user_id: str
    hotel_id: int
    priority: str = "normal"
    timestamp: str
    source: str = "hotel_api"

class AssignmentResponse(BaseModel):
    task_id: str
    status: str
    message: str
    estimated_completion: str


model_client = OpenAIChatCompletionClient(
    model="gemini-2.5-flash",
    base_url="https://generativelanguage.googleapis.com/v1beta",
    api_key=gemini_api_key,
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": False,
        "family": ModelFamily.GEMINI_2_5_FLASH,
        "structured_output": True,
    },
)

auth_managers: Dict[str, AutogenAuthManager] = {}
state_mapping: Dict[str, str] = {}


async def run_agent(webhook_data: AssignmentRequest, task_id: str) -> None:
    """Create and run a agent for staff management tasks"""
    try:
        logger.info(f"Starting agent task {task_id} for booking {webhook_data.booking_id}")
    
        
        # Create a background auth manager instance with separate agent identity
        auth_manager = AutogenAuthManager(
            config=asgardeo_config,
            agent_config=agent_config, 
            message_handler=None  # No message handler for background tasks
        )
        
        get_booking_admin_tool = SecureFunctionTool(
            get_booking_admin,
            description="Get the booking information by booking ID",
            name="GetBookingByIdTool",
            auth=AuthSchema(auth_manager, AuthConfig(
                scopes=["admin_read_bookings"],
                token_type=OAuthTokenType.AGENT_TOKEN,
                resource="booking_api"
            ))
        )
        
        update_booking_tool = SecureFunctionTool(
            update_booking_admin,
            description="Assign Contact Person by Updating the booking",
            name="UpdateBookingTool",
            auth=AuthSchema(auth_manager, AuthConfig(
                scopes=["admin_update_bookings"],
                token_type=OAuthTokenType.AGENT_TOKEN,
                resource="booking_api"
            ))
        )
        
        get_available_staff_tool = SecureFunctionTool(
            get_available_staff,
            description="Get available staff for booking assignments",
            name="GetAvailableStaffTool",
            auth=AuthSchema(auth_manager, AuthConfig(
                scopes=["admin_read_staff"],
                token_type=OAuthTokenType.AGENT_TOKEN,
                resource="booking_api"
            ))
        )
    
        # Create a specialized agent for assignment tasks
        assignment_agent = AssistantAgent(
            "staff_management_agent",
            model_client=model_client,
            tools=[
                get_booking_admin_tool,
                get_available_staff_tool,
                update_booking_tool,
            ],
            reflect_on_tool_use=True,
            system_message=system_prompt,
            max_tool_iterations=20,
            )

        response = await asyncio.wait_for(
            assignment_agent.run(
                task=f"Assign contact person for booking id : {webhook_data.booking_id} , hotel id : {webhook_data.hotel_id}"
            ),
            timeout=300  # 5 minutes timeout
        )

        logger.info(f"Agent task {task_id} completed successfully")

    except Exception as e:
        logger.error(f"Agent task {task_id} failed: {str(e)}", exc_info=True)

@app.post("/v1/invoke")
async def invoke(request: AssignmentRequest, token_data: TokenData = Security(validate_token, scopes=["invoke"])):
    """Endpoint to invoke the staff management agent for staff assignment"""
    try:
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Calculate estimated completion time (2-5 minutes from now)
        import datetime
        estimated_completion = datetime.datetime.now() + datetime.timedelta(minutes=3)
        
        # Create background task for assignment
        asyncio.create_task(run_agent(request, task_id))

        logger.info(f"Assignment task {task_id} queued for booking {request.booking_id}")

        return AssignmentResponse(
            task_id=task_id,
            status="queued",
            message=f"Staff assignment task queued",
            estimated_completion=estimated_completion.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process webhook")
