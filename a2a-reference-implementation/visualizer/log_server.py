"""
Log Streaming Server for Token Flow Visualizer.
Wraps the main app and streams console output via WebSocket.
"""
import asyncio
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    os.system("pip install websockets")
    import websockets

from aiohttp import web
import aiohttp_cors

connected_clients = set()
log_buffer = []

async def broadcast(message: str):
    """Broadcast message to all connected WebSocket clients."""
    log_buffer.append(message)
    if len(log_buffer) > 500:
        log_buffer.pop(0)
    
    for ws in connected_clients.copy():
        try:
            await ws.send_str(message)
        except:
            connected_clients.discard(ws)

async def stream_logs():
    """Run main app and stream output."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.main",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(Path(__file__).parent.parent)
    )
    
    async for line in process.stdout:
        text = line.decode('utf-8', errors='replace').strip()
        if text:
            print(text)  # Also print to console
            await broadcast(text)

async def websocket_handler(request):
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    connected_clients.add(ws)
    print(f"[WS] Client connected. Total: {len(connected_clients)}")
    
    # Send buffered logs
    for log in log_buffer[-50:]:
        await ws.send_str(log)
    
    try:
        async for msg in ws:
            pass  # Just keep connection alive
    finally:
        connected_clients.discard(ws)
        print(f"[WS] Client disconnected. Total: {len(connected_clients)}")
    
    return ws

async def index_handler(request):
    """Serve the visualizer HTML."""
    html_path = Path(__file__).parent / "index.html"
    return web.FileResponse(html_path)

async def static_handler(request):
    """Serve static files."""
    filename = request.match_info['filename']
    file_path = Path(__file__).parent / filename
    if file_path.exists():
        return web.FileResponse(file_path)
    return web.Response(status=404)

async def init_app():
    """Initialize the aiohttp application."""
    app = web.Application()
    
    # CORS setup
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })
    
    # Routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/{filename}', static_handler)
    
    # Apply CORS
    for route in list(app.router.routes()):
        cors.add(route)
    
    return app

async def main():
    """Start the log streaming server."""
    print("=" * 60)
    print("  A2A Token Flow Visualizer")
    print("=" * 60)
    print(f"  Dashboard: http://localhost:8200")
    print(f"  WebSocket: ws://localhost:8200/ws")
    print("=" * 60)
    
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8200)
    await site.start()
    
    # Start the main app and stream logs
    await stream_logs()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Visualizer] Shutting down...")
