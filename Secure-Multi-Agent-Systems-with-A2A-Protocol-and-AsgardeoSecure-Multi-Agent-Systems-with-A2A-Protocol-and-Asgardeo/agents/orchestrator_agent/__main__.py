"""
Orchestrator Agent - HTTP Server Entry Point.
Standard A2A server with OAuth callback.
"""

import sys
import os
import yaml
import logging
from dotenv import load_dotenv

# Load environment
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '..', '.env')
load_dotenv(env_path)

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .agent import OrchestratorAgent
from .executor import OrchestratorExecutor


def load_config():
    """Load configuration from config.yaml"""
    config_path = os.path.join(current_dir, '..', '..', 'config.yaml')
    config_path = os.path.abspath(config_path)
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('orchestrator_agent', {}), config
    
    return {}, {}


def main():
    """Start the Orchestrator Agent server."""
    try:
        agent_config, global_config = load_config()
        
        # Setup logging
        log_level = agent_config.get('logging', {}).get('level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        
        # Server configuration
        host = agent_config.get('host', 'localhost')
        port = agent_config.get('port', 8000)
        
        logger.info(f"Starting Orchestrator Agent")
        logger.info(f"Server: http://{host}:{port}")
        
        # Create agent card
        agent_card = AgentCard(
            name="Orchestrator Agent",
            description="A2A Orchestrator with Asgardeo authentication",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="booking",
                    name="Travel Booking",
                    description="Book flights and hotels",
                    tags=["travel", "booking"],
                    examples=["Book a flight to London"]
                )
            ]
        )
        
        # Setup executor and request handler
        executor = OrchestratorExecutor(agent_config)
        
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
            push_config_store=InMemoryPushNotificationConfigStore()
        )
        
        # Create A2A application
        server = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler
        )
        
        app = server.build()
        
        # Add CORS
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
        
        # Startup event to prefetch actor token
        @app.on_event("startup")
        async def startup_event():
            logger.info("🚀 Initiating startup sequence...")
            try:
                # specific to the user request: "recommend to run the agent token retrieval during the agent startup"
                token = await global_agent.ensure_actor_token()
                if token:
                    logger.info("✅ Orchestrator Agent successfully authenticated with Asgardeo on startup.")
                else:
                    logger.warning("⚠️ Failed to obtain Actor Token on startup. Will retry on first request.")
                
                # Discover agents on startup
                logger.info("🔍 Discovering downstream agents...")
                await global_agent.discover_agents()
                
            except Exception as e:
                logger.error(f"❌ Startup auth/discovery error: {e}")
        
        # Add OAuth callback endpoint
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse
        
        # Global agent instance for session management
        global_agent = executor.agent
        
        @app.route("/callback", methods=["GET"])
        async def callback_endpoint(request: Request):
            """OAuth callback endpoint."""
            code = request.query_params.get('code')
            state = request.query_params.get('state')
            
            if not code or not state:
                return JSONResponse({"error": "Missing code or state"}, status_code=400)
            
            logger.info(f"OAuth callback: code={code[:20]}... state={state[:20]}...")
            
            # Find context by state
            context_id = None
            for ctx_id, session in global_agent._sessions.items():
                if session.get('state') == state:
                    context_id = ctx_id
                    break
            
            if not context_id:
                return HTMLResponse("<h1>❌ Session not found</h1>")
            
            # Exchange code for token
            token = await global_agent.handle_callback(context_id, code, state)
            
            if token:
                return HTMLResponse("""
                    <html>
                    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1>✅ Authentication Successful!</h1>
                        <p>You can now make booking requests.</p>
                        <script>setTimeout(() => window.close(), 3000);</script>
                    </body>
                    </html>
                """)
            else:
                return HTMLResponse("<h1>❌ Token exchange failed</h1>")
        
        @app.route("/task", methods=["POST"])
        async def task_endpoint(request: Request):
            """Simple task endpoint for chat interface."""
            body = await request.json()
            message_parts = body.get('message', {}).get('parts', [])
            context_id = body.get('context_id', 'default')
            
            if not message_parts:
                return JSONResponse({"error": "No message"}, status_code=400)
            
            query = message_parts[0].get('text', '')
            
            response_text = ""
            async for chunk in global_agent.stream(query, context_id):
                if 'content' in chunk:
                    response_text = chunk['content']
            
            return JSONResponse({
                "message": {"parts": [{"type": "text", "text": response_text}]}
            })
        
        logger.info(f"📄 Agent Card: http://{host}:{port}/.well-known/agent-card.json")
        logger.info(f"🔄 Callback: http://{host}:{port}/callback")
        
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
