"""
Orchestrator Agent - HTTP Server Entry Point.
A2A server with OAuth and token broker integration.
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
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse, HTMLResponse
from starlette.routing import Route

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .agent import OrchestratorAgent
from .executor import OrchestratorExecutor
from src.auth.token_broker import get_token_broker
from src.auth.jwt_validator import get_jwt_validator
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


UNPROTECTED_PATHS = {"/auth/login", "/callback", "/health", "/.well-known/agent-card.json"}


class TokenExtractMiddleware(BaseHTTPMiddleware):
    """Validate Bearer token on every protected request."""

    def __init__(self, app, executor: OrchestratorExecutor):
        super().__init__(app)
        self.executor = executor

    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JSONResponse(
                {"status": "error", "error": "Authentication required. Please login at /auth/login"},
                status_code=401
            )

        token = auth_header[7:]
        try:
            validator = get_jwt_validator()
            await validator.validate(token)
        except Exception:
            return JSONResponse(
                {"status": "error", "error": "Invalid or expired token. Please login again."},
                status_code=401
            )

        self.executor.set_auth_token(token)
        return await call_next(request)


# Global executor reference for route handlers
_executor = None


async def start_login(request: Request):
    """Start the OAuth login flow."""
    broker = get_token_broker()
    session = broker.create_session()

    _, global_config = load_config()
    scopes = []
    for agent_cfg in global_config.get("agents", {}).values():
        scopes.extend(agent_cfg.get("required_scopes", []))
    scopes = list(dict.fromkeys(scopes))

    auth_url = broker.get_authorization_url(
        session_id=session.session_id,
        scopes=scopes
    )

    logger.info(f"Login started, session: {session.session_id}")
    return RedirectResponse(url=auth_url)


async def oauth_callback(request: Request):
    """OAuth2 callback - exchange code for delegated token."""
    broker = get_token_broker()

    code = request.query_params.get('code')
    state = request.query_params.get('state')

    if not code or not state:
        return JSONResponse({"status": "error", "error": "Missing code or state"}, status_code=400)

    try:
        session = await broker.handle_callback(code=code, state=state)
        logger.info(f"OAuth callback success, session: {session.session_id}")

        token = session.delegated_token
        html = f"""<!DOCTYPE html>
<html><head><title>Login Successful</title></head>
<body>
<script>
  localStorage.setItem('orch_token', {repr(token)});
  if (window.opener) {{
    window.opener.postMessage({{ type: 'AUTH_SUCCESS', token: {repr(token)} }}, 'http://localhost:8200');
    window.close();
  }} else {{
    document.body.innerHTML = '<h2>Login successful!</h2><p>You may close this tab and return to the visualizer.</p>';
  }}
</script>
</body></html>"""
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "version": "1.0.0"})


async def api_request(request: Request):
    """Process user request — requires valid Bearer token."""
    global _executor

    from src.log_broadcaster import log_and_broadcast

    token = _executor._current_token  # set and validated by middleware

    if request.method == "POST":
        body = await request.json()
        message = body.get("message", "")
    else:
        message = request.query_params.get('message', '')

    if not message:
        return JSONResponse(
            {"status": "error", "error": "No message provided. Use ?message=<your request>"},
            status_code=400
        )

    log_and_broadcast(f"\n[REQUEST] {message}")

    try:
        if not _executor.agent._discovered_agents:
            await _executor.agent.discover_agents()

        result = await _executor.agent.process_workflow(
            user_input=message,
            access_token=token
        )

        return JSONResponse(result)

    except Exception as e:
        import traceback
        logger.error(f"Request failed: {e}\n{traceback.format_exc()}")
        log_and_broadcast(f"\n[ERROR] {str(e)}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


def create_app():
    """Create the Starlette application with A2A support."""
    global _executor

    agent_config, global_config = load_config()
    settings = get_settings()

    log_level = agent_config.get('logging', {}).get('level', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    host = agent_config.get('host', 'localhost')
    port = agent_config.get('port', 8000)

    agent_card = AgentCard(
        name="Onboarding Orchestrator",
        description="AI-powered employee onboarding coordinator",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
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

    executor = OrchestratorExecutor(agent_config)
    _executor = executor

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

    custom_routes = [
        Route("/auth/login", start_login, methods=["GET"]),
        Route("/callback", oauth_callback, methods=["GET"]),
        Route("/health", health_check, methods=["GET"]),
        Route("/api/request", api_request, methods=["GET", "POST"]),
    ]
    app.routes.extend(custom_routes)

    app.add_middleware(TokenExtractMiddleware, executor=executor)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8200", "http://127.0.0.1:8200"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    logger.info(f"Agent Card: http://{host}:{port}/.well-known/agent-card.json")

    return app, host, port, log_level


def main():
    """Start the Orchestrator Agent server."""
    try:
        app, host, port, log_level = create_app()
        print(f"\nStarting Orchestrator Agent")
        print(f"   Server: http://{host}:{port}")
        print(f"   OAuth Login: http://{host}:{port}/auth/login")
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
