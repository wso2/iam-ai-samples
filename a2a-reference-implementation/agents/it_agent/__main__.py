"""
IT Agent - HTTP Server Entry Point.
Mounts both the A2A protocol handler and the IT REST API.
"""

import sys
import os
import yaml
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

from src.apis.it_api import router as it_router
from .executor import ITExecutor


class TokenExtractMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, executor: ITExecutor):
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
    logger = logging.getLogger(__name__)
    host, port = 'localhost', 8002

    agent_card = AgentCard(
        name="IT Agent",
        description="Provisions IT accounts and services",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(id="provision_vpn", name="Provision VPN", description="Set up VPN access", tags=["it", "vpn"]),
            AgentSkill(id="provision_github", name="Provision GitHub", description="Grant GitHub access", tags=["it", "github"]),
            AgentSkill(id="provision_aws", name="Provision AWS", description="Set up AWS environment", tags=["it", "aws"])
        ]
    )

    executor = ITExecutor()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore()
    )

    a2a_server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = a2a_server.build()

    # Mount the IT REST API as a FastAPI sub-application
    # This allows the agent to call its own API at /api/it/*
    api_app = FastAPI(title="IT API", version="1.0.0")
    api_app.include_router(it_router, prefix="/it", tags=["IT"])
    app.mount("/api", api_app)

    app.add_middleware(TokenExtractMiddleware, executor=executor)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    print(f"\n🚀 Starting IT Agent")
    print(f"   Server: http://{host}:{port}")
    print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
