"""
Orchestrator Agent - HTTP Server Entry Point.
A2A server with OAuth and token broker integration.
"""

import sys
import os
import yaml
import logging
import json
from dotenv import load_dotenv

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

# Load environment
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from starlette.routing import Route

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .agent import OrchestratorAgent
from .executor import OrchestratorExecutor
from src.auth.token_broker import get_token_broker
from src.config import get_settings

logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.yaml"""
    config_path = os.path.join(project_root, 'config.yaml')

    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('orchestrator', {}), config

    return {}, {}


class TokenExtractMiddleware(BaseHTTPMiddleware):
    """Extract Bearer token from Authorization header."""

    def __init__(self, app, executor: OrchestratorExecutor):
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


# Global executor reference for route handlers
_executor = None


async def start_login(request: Request):
    """Start the OAuth login flow."""
    broker = get_token_broker()
    session = broker.create_session()

    scopes = [
        "hr:read", "hr:write",
        "it:read", "it:write",
        "approval:read", "approval:write",
        "booking:read", "booking:write"
    ]

    auth_url = broker.get_authorization_url(
        session_id=session.session_id,
        scopes=scopes
    )

    logger.info(f"Login started, session: {session.session_id}")
    return RedirectResponse(url=auth_url)


async def oauth_callback(request: Request):
    """OAuth2 callback - exchange code for delegated token."""
    global _executor
    broker = get_token_broker()

    code = request.query_params.get('code')
    state = request.query_params.get('state')

    if not code or not state:
        return JSONResponse({"status": "error", "error": "Missing code or state"}, status_code=400)

    try:
        session = await broker.handle_callback(code=code, state=state)

        # Store token in executor for future requests
        if session.delegated_token and _executor:
            _executor.set_auth_token(session.delegated_token)
            _executor.set_context_id(session.session_id)

        logger.info(f"OAuth callback success, session: {session.session_id}")

        return JSONResponse({
            "status": "success",
            "session_id": session.session_id,
            "message": "Authentication successful! You can now use the orchestrator."
        })

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "version": "1.0.0"})


async def api_demo(request: Request):
    """Process any user request — LLM decomposes it into agent tasks and executes them."""
    global _executor
    broker = get_token_broker()
    
    from src.log_broadcaster import log_and_broadcast
    
    # Get the demo token (from most recent session)
    token = broker.get_demo_token()
    
    if not token:
        return JSONResponse({
            "status": "error", 
            "error": "No authenticated session found. Please login first at /auth/login"
        }, status_code=401)
    
    # Set token in executor
    if _executor:
        _executor.set_auth_token(token)
    
    # Get user input from query params or POST body
    if request.method == "POST":
        body = await request.json()
        message = body.get("message", "")
    else:
        message = request.query_params.get('message', '')
    
    if not message:
        return JSONResponse({
            "status": "error",
            "error": "No message provided. Use ?message=<your request>",
            "examples": [
                "?message=Onboard John Doe as Software Engineer",
                "?message=Create HR profile and provision VPN for Jane Smith",
                "?message=Schedule orientation for the new marketing intern",
            ]
        }, status_code=400)
    
    log_and_broadcast(f"\n[REQUEST] {message}")
    log_and_broadcast(f"[TOKEN] Using delegated token: {token[:50]}...")
    
    try:
        # Ensure agents are discovered
        if not _executor.agent._discovered_agents:
            await _executor.agent.discover_agents()
        
        # LLM decomposes and executes the workflow
        result = await _executor.agent.process_workflow(
            user_input=message,
            access_token=token
        )
        
        return JSONResponse(result)
        
    except Exception as e:
        logger.error(f"Request failed: {e}")
        log_and_broadcast(f"\n[ERROR] {str(e)}")
        return JSONResponse({
            "status": "error",
            "error": str(e)
        }, status_code=500)


async def api_chat(request: Request):
    """Dynamic chat endpoint - routes user instructions using LLM."""
    global _executor
    broker = get_token_broker()
    
    from src.log_broadcaster import log_and_broadcast
    
    # Get the demo token (from most recent session)
    token = broker.get_demo_token()
    
    if not token:
        return JSONResponse({
            "status": "error", 
            "error": "No authenticated session found. Please login first at /auth/login"
        }, status_code=401)
    
    # Set token in executor
    if _executor:
        _executor.set_auth_token(token)
    
    # Get message from query params
    message = request.query_params.get('message', '')
    
    if not message:
        return JSONResponse({
            "status": "error",
            "error": "No message provided"
        }, status_code=400)
    
    log_and_broadcast(f"\n[CHAT REQUEST] {message[:80]}...")
    
    try:
        # Stream response from orchestrator (uses LLM routing)
        full_response = ""
        async for chunk in _executor.agent.stream(message, "chat-session", token):
            content = chunk.get('content', '')
            if content:
                full_response += content
        
        log_and_broadcast(f"\n[CHAT RESPONSE] {full_response[:80]}...")
        
        return JSONResponse({
            "status": "success",
            "message": message,
            "response": full_response,
            "token_preview": f"{token[:50]}..." if token else None
        })
    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        log_and_broadcast(f"\n[ERROR] Chat failed: {str(e)}")
        return JSONResponse({
            "status": "error",
            "error": str(e)
        }, status_code=500)


def create_app():
    """Create the Starlette application with A2A support."""
    global _executor
    
    agent_config, global_config = load_config()
    settings = get_settings()

    # Setup logging
    log_level = agent_config.get('logging', {}).get('level', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Server configuration
    host = agent_config.get('host', 'localhost')
    port = agent_config.get('port', 8000)

    # Create agent card
    agent_card = AgentCard(
        name="Onboarding Orchestrator",
        description="AI-powered employee onboarding coordinator",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="onboard_employee",
                name="Employee Onboarding",
                description="Process complete employee onboarding workflow",
                tags=["onboarding", "hr", "employee"],
                examples=["Onboard John Doe as Software Engineer"]
            ),
            AgentSkill(
                id="check_status",
                name="Check Status",
                description="Check onboarding request status",
                tags=["status", "check"],
                examples=["Check status of onboarding request"]
            )
        ]
    )

    # Setup executor and request handler
    executor = OrchestratorExecutor(agent_config)
    _executor = executor  # Store for route handlers

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore()
    )

    # Create A2A application
    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    app = a2a_server.build()

    # Add custom routes using Starlette's route_class
    custom_routes = [
        Route("/auth/login", start_login, methods=["GET"]),
        Route("/callback", oauth_callback, methods=["GET"]),
        Route("/health", health_check, methods=["GET"]),
        Route("/api/demo", api_demo, methods=["GET", "POST"]),
        Route("/api/chat", api_chat, methods=["GET"]),
    ]
    
    # Add routes to the app
    app.routes.extend(custom_routes)

    # Add token extraction middleware
    app.add_middleware(TokenExtractMiddleware, executor=executor)

    # Add CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    logger.info(f"📄 Agent Card: http://{host}:{port}/.well-known/agent-card.json")

    return app, host, port, log_level


def main():
    """Start the Orchestrator Agent server."""
    try:
        app, host, port, log_level = create_app()
        print(f"\n🚀 Starting Orchestrator Agent")
        print(f"   Server: http://{host}:{port}")
        print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")
        print(f"   OAuth Login: http://{host}:{port}/auth/login")
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
