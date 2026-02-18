"""
Booking Agent - HTTP Server Entry Point.
Mounts both the A2A protocol handler and the Booking REST API.
"""

import sys
import os
import logging
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)
load_dotenv(os.path.join(project_root, '.env'))

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Mount

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from src.apis.booking_api import router as booking_router
from .executor import BookingExecutor


class TokenExtractMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, executor):
        super().__init__(app)
        self.executor = executor

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            self.executor.set_auth_token(auth_header[7:])
        else:
            self.executor.set_auth_token(None)
        return await call_next(request)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    host, port = 'localhost', 8004

    agent_card = AgentCard(
        name="Booking Agent",
        description="Schedules tasks and deliveries",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(id="schedule_task", name="Schedule Task", description="Schedule orientation or tasks", tags=["booking", "schedule"]),
            AgentSkill(id="book_delivery", name="Book Delivery", description="Book equipment delivery", tags=["booking", "delivery"])
        ]
    )

    executor = BookingExecutor()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore()
    )

    a2a_server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_server.build()

    # Mount the Booking REST API as a FastAPI sub-application
    # This allows the agent to call its own API at /api/booking/*
    api_app = FastAPI(title="Booking API", version="1.0.0")
    api_app.include_router(booking_router, prefix="/booking", tags=["Booking"])
    app.mount("/api", api_app)

    app.add_middleware(TokenExtractMiddleware, executor=executor)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    print(f"\n🚀 Starting Booking Agent")
    print(f"   Server: http://{host}:{port}")
    print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
