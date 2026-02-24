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
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

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

    # ── Approval endpoints (mounted at /it/approve/* and /it/pending/*) ──────
    from agents.it_agent import approval_store
    from starlette.responses import HTMLResponse, JSONResponse

    async def approve_endpoint(request: Request) -> HTMLResponse:
        """Admin clicks this link from their email to approve IT access."""
        token = request.path_params["token"]
        ok = await approval_store.approve(token)
        entry = await approval_store.get_pending(token)
        if ok and entry:
            name = entry.get("employee_name", "the employee")
            emp  = entry.get("employee_id", "")
            res  = ", ".join(entry.get("resources", []))
            html = f"""
            <!DOCTYPE html><html><head><meta charset=utf-8>
            <title>IT Access Approved</title>
            <style>body{{font-family:sans-serif;max-width:600px;margin:80px auto;text-align:center}}
             h1{{color:#22c55e}} p{{color:#555}}</style></head>
            <body>
             <h1>&#10003; Access Approved</h1>
             <p><strong>{name}</strong> ({emp})</p>
             <p>Approved resources: <strong>{res}</strong></p>
             <p>IT provisioning will proceed automatically.</p>
            </body></html>"""
            return HTMLResponse(html)
        entry = await approval_store.get_pending(token)
        status = entry["status"] if entry else "not found"
        html = f"""<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>
            <h2 style='color:#f59e0b'>Token status: {status}</h2>
            <p>This link may have already been used or has expired.</p></body></html>"""
        return HTMLResponse(html, status_code=400)

    async def reject_endpoint(request: Request) -> HTMLResponse:
        """Admin clicks this link to reject IT access."""
        token = request.path_params["token"]
        ok = await approval_store.reject(token)
        if ok:
            html = """<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>
                <h1 style='color:#ef4444'>&#10007; Access Rejected</h1>
                <p>IT provisioning has been cancelled.</p></body></html>"""
            return HTMLResponse(html)
        return HTMLResponse("Invalid or already-processed token", status_code=400)

    async def pending_status_endpoint(request: Request) -> JSONResponse:
        """Internal polling endpoint used by the IT Agent while waiting."""
        token = request.path_params["token"]
        entry = await approval_store.get_pending(token)
        if not entry:
            return JSONResponse({"status": "not_found"}, status_code=404)
        return JSONResponse({"status": entry["status"], "decided_at": entry.get("decided_at")})

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

    # Mount the IT REST API
    api_app = FastAPI(title="IT API", version="1.0.0")
    api_app.include_router(it_router, prefix="/it", tags=["IT"])

    # Approval routes (no auth — token IS the secret)
    from starlette.routing import Route
    approval_routes = [
        Route("/it/approve/{token}",         approve_endpoint),
        Route("/it/reject/{token}",          reject_endpoint),
        Route("/it/pending/{token}/status",  pending_status_endpoint),
    ]
    for route in approval_routes:
        app.routes.append(route)

    app.mount("/api", api_app)
    app.add_middleware(TokenExtractMiddleware, executor=executor)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    print(f"\n🚀 Starting IT Agent")
    print(f"   Server: http://{host}:{port}")
    print(f"   Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    print(f"   Approval endpoint: http://{host}:{port}/it/approve/{{token}}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
