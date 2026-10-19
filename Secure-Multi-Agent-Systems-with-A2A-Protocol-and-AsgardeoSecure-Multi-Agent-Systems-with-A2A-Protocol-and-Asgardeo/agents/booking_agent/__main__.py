"""
Booking Agent - HTTP Server Entry Point.
Standard A2A server with token extraction middleware.
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .agent import BookingAgent
from .executor import BookingExecutor


def load_config():
    """Load configuration from config.yaml"""
    config_path = os.path.join(current_dir, '..', '..', 'config.yaml')
    config_path = os.path.abspath(config_path)
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('booking_agent', {}), config
    
    return {}, {}


class TokenExtractMiddleware(BaseHTTPMiddleware):
    """Extract Bearer token from Authorization header."""
    
    def __init__(self, app, executor: BookingExecutor):
        super().__init__(app)
        self.executor = executor
        self.logger = logging.getLogger(__name__)
    
    async def dispatch(self, request: Request, call_next):
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            self.executor.set_auth_token(token)
            self.logger.info(f"Token extracted: {token[:30]}...")
        else:
            self.executor.set_auth_token(None)
        
        return await call_next(request)


def main():
    """Start the Booking Agent server."""
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
        port = agent_config.get('port', 8001)
        
        logger.info(f"Starting Booking Agent")
        logger.info(f"Server: http://{host}:{port}")
        
        # Create agent card
        agent_card = AgentCard(
            name="Booking Agent",
            description="Travel booking service with mock data",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="flights",
                    name="Flight Search",
                    description="Search and book flights",
                    tags=["travel", "flights"],
                    examples=["Find flights to London"]
                ),
                AgentSkill(
                    id="hotels",
                    name="Hotel Search",
                    description="Search and book hotels",
                    tags=["travel", "hotels"],
                    examples=["Search hotels in London"]
                )
            ]
        )
        
        # Setup executor and request handler
        executor = BookingExecutor(agent_config)
        
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
        
        # Add token extraction middleware
        app.add_middleware(TokenExtractMiddleware, executor=executor)
        
        # Add CORS
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
        
        logger.info(f"📄 Agent Card: http://{host}:{port}/.well-known/agent-card.json")
        
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
