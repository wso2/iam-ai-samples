"""
HR Agent - HTTP Server Entry Point.
Mounts both the A2A protocol handler and the HR REST API.
"""

import sys
import os
import yaml
import logging
from dotenv import load_dotenv

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

# Load environment
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

from src.apis.hr_api import router as hr_router
from .executor import HRExecutor


def load_config():
    """Load configuration from config.yaml"""
    config_path = os.path.join(project_root, 'config.yaml')

    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('agents', {}).get('hr_agent', {}), config

    return {}, {}


class TokenExtractMiddleware(BaseHTTPMiddleware):
    """Extract Bearer token from Authorization header."""

    def __init__(self, app, executor: HRExecutor):
        super().__init__(app)
        self.executor = executor

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get('Authorization', '')

        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            self.executor.set_auth_token(token)
        else:
            self.executor.set_auth_token(None)

        return await call_next(request)


def main():
    """Start the HR Agent server."""
    agent_config, global_config = load_config()

    # Setup logging
    log_level = agent_config.get('logging', {}).get('level', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Server configuration
    host = 'localhost'
    port = 8001

    # Create agent card
    agent_card = AgentCard(
        name="HR Agent",
        description="Manages employee profiles and onboarding",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="create_employee",
                name="Create Employee Profile",
                description="Create a new employee profile in the HR system",
                tags=["hr", "employee", "profile"],
                examples=["Create employee John Doe"]
            ),
            AgentSkill(
                id="list_employees",
                name="List Employees",
                description="List all employees",
                tags=["hr", "employees", "list"],
                examples=["Show all employees"]
            )
        ]
    )

    # Setup executor and handler
    executor = HRExecutor(agent_config)

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore()
    )

    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    app = a2a_server.build()

    # Mount the HR REST API as a FastAPI sub-application
    # This allows the agent to call its own API at /api/hr/*
    api_app = FastAPI(title="HR API", version="1.0.0")
    api_app.include_router(hr_router, prefix="/hr", tags=["HR"])
    app.mount("/api", api_app)

    # Add middleware
    app.add_middleware(TokenExtractMiddleware, executor=executor)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    print(f"\n🚀 Starting HR Agent")
    print(f"   Server: http://{host}:{port}")
    print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")

    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
