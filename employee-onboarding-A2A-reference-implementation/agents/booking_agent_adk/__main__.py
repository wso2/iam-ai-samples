"""
ADK Booking Agent - Server Entry Point.

Uses Google ADK Runner with A2AStarletteApplication for built-in A2A protocol.
ADK's Runner handles LLM calls (OpenAI via LiteLLM) and tool execution.
No custom executor.py needed.

Architecture:
  A2AStarletteApplication → DefaultRequestHandler → A2aAgentExecutor
    → ADK Runner(root_agent) → LlmAgent(openai/gpt-4o-mini) → tools
"""

import os
import sys
import logging

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

import uvicorn
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, InMemoryPushNotificationConfigStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor

from agents.booking_agent_adk.agent import root_agent, _current_token
from src.apis.booking_api import router as booking_router


from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue

class CustomA2aAgentExecutor(A2aAgentExecutor):
    """
    Subclass of A2A Executor that bridges the Starlette token middleware
    into the ADK event loop context.
    """
    def __init__(self, runner: Runner):
        super().__init__(runner=runner)
        self._current_request_token = None

    def set_auth_token(self, token: str):
        self._current_request_token = token

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Crucial: set the contextvar right before ADK Runner execution
        _current_token.set(self._current_request_token)
        return await super().execute(context, event_queue)


class TokenMiddleware(BaseHTTPMiddleware):
    """
    Extracts the Bearer token from each incoming A2A request and passes it
    to the custom executor so it can be injected into the ADK context.
    """
    def __init__(self, app, executor: CustomA2aAgentExecutor):
        super().__init__(app)
        self.executor = executor

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        self.executor.set_auth_token(token)
        return await call_next(request)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    host = "localhost"
    port = 8005

    # Agent Card — describes this agent to other agents (A2A protocol)
    agent_card = AgentCard(
        name="Booking Agent",
        description=(
            "Schedules onboarding tasks (orientation, training) and "
            "equipment deliveries (laptop, phone, monitor) for new employees."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="create_task",
                name="Schedule Onboarding Task",
                description="Schedule an orientation, training, or other onboarding session for an employee",
                tags=["booking", "task", "orientation", "training"]
            ),
            AgentSkill(
                id="schedule_delivery",
                name="Schedule Equipment Delivery",
                description="Schedule delivery of a laptop, phone, monitor or other equipment to an employee",
                tags=["booking", "delivery", "laptop", "equipment"]
            ),
            AgentSkill(
                id="list_tasks",
                name="List Scheduled Tasks",
                description="List all scheduled onboarding tasks, optionally filtered by employee",
                tags=["booking", "list", "tasks"]
            ),
            AgentSkill(
                id="list_deliveries",
                name="List Scheduled Deliveries",
                description="List all scheduled equipment deliveries, optionally filtered by employee",
                tags=["booking", "list", "deliveries"]
            ),
        ]
    )

    # ADK Runner — handles LLM calls and tool execution for root_agent
    # Uses InMemorySessionService for stateless operation
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="booking_agent_adk",
        session_service=session_service,
    )

    # Custom Executor bridges ADK Runner to A2A protocol and injects context token
    agent_executor = CustomA2aAgentExecutor(
        runner=runner,
    )

    # DefaultRequestHandler manages A2A task lifecycle
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore(),
    )

    # A2AStarletteApplication exposes standard A2A endpoints
    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    app = a2a_server.build()

    # Mount the Booking REST API (used internally by tool functions via HTTP)
    api_app = FastAPI(title="Booking API", version="1.0.0")
    api_app.include_router(booking_router, prefix="/booking", tags=["Booking"])
    app.mount("/api", api_app)

    # Token extraction middleware — sets the token on the custom executor
    app.add_middleware(TokenMiddleware, executor=agent_executor)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    print(f"\n[STARTING] Booking Agent (ADK)")
    print(f"   Framework: Google ADK + A2AStarletteApplication")
    print(f"   Model: openai/gpt-4o-mini (via LiteLLM)")
    print(f"   Server: http://{host}:{port}")
    print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    print(f"   Booking API: http://{host}:{port}/api/booking")
    print(f"   Tools: create_task, schedule_delivery, list_tasks, list_deliveries")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
