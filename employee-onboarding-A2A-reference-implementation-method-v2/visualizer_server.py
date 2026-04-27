"""
WebSocket Log Server for Visualizer.
Broadcasts token flow logs to the frontend.
Run with: python visualizer_server.py
"""

import asyncio
import logging
import sys
import os
from typing import Set

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from dotenv import load_dotenv
load_dotenv()

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute, Route, Mount
from starlette.websockets import WebSocket
from starlette.responses import JSONResponse, FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
import uvicorn

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connected WebSocket clients
clients: Set[WebSocket] = set()


async def websocket_handler(websocket: WebSocket):
    """Handle WebSocket connections from visualizer."""
    await websocket.accept()
    clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(clients)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from client: {data}")
    except Exception as e:
        logger.info(f"Client disconnected: {e}")
    finally:
        clients.discard(websocket)


async def broadcast_message(message: str):
    """Broadcast a message to all connected clients."""
    if not clients:
        return
    
    disconnected = set()
    for client in clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    
    clients.difference_update(disconnected)


async def log_endpoint(request):
    """HTTP endpoint to receive logs from agents and broadcast them."""
    try:
        body = await request.json()
        message = body.get("message", "")
        
        if message:
            await broadcast_message(message)
            logger.info(f"Broadcasted: {message[:80]}...")
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


async def health(request):
    return JSONResponse({"status": "ok", "clients": len(clients)})


async def serve_index(request):
    """Serve the visualizer index.html."""
    index_path = os.path.join(current_dir, "visualizer", "index.html")
    return FileResponse(index_path, media_type="text/html")


async def serve_css(request):
    """Serve styles.css."""
    css_path = os.path.join(current_dir, "visualizer", "styles.css")
    return FileResponse(css_path, media_type="text/css")


async def serve_js(request):
    """Serve app.js."""
    js_path = os.path.join(current_dir, "visualizer", "app.js")
    return FileResponse(js_path, media_type="application/javascript")


# Create app with explicit routes for static files
app = Starlette(
    routes=[
        WebSocketRoute("/ws", websocket_handler),
        Route("/log", log_endpoint, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/styles.css", serve_css, methods=["GET"]),
        Route("/app.js", serve_js, methods=["GET"]),
        Route("/", serve_index, methods=["GET"]),
    ]
)


def main():
    print("\n🎨 Starting Visualizer WebSocket Server")
    print("   WebSocket: ws://localhost:8200/ws")
    print("   Visualizer: http://localhost:8200/")
    print("   Log endpoint: POST http://localhost:8200/log")
    uvicorn.run(app, host="localhost", port=8200, log_level="info")


if __name__ == "__main__":
    main()
