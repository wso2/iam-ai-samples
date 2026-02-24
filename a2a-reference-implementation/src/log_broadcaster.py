"""
Log broadcaster for visualizer.
Sends log messages to the WebSocket server for the frontend.
"""

import httpx
import asyncio
from typing import Optional

VISUALIZER_URL = "http://localhost:8200/log"

_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=2.0)
    return _client


def get_sync_client() -> httpx.Client:
    """Return a persistent sync client — created once, reused for all broadcast calls."""
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(timeout=1.0)
    return _sync_client


async def broadcast_log(message: str):
    """Send a log message to the visualizer server."""
    try:
        client = get_client()
        await client.post(VISUALIZER_URL, json={"message": message})
    except Exception:
        # Silently ignore if visualizer is not running
        pass


def broadcast_log_sync(message: str):
    """Synchronous wrapper for broadcasting logs. Reuses a persistent client to avoid
    creating a new TCP connection on every call (which was the main source of slowness)."""
    try:
        get_sync_client().post(VISUALIZER_URL, json={"message": message})
    except Exception:
        pass


# Simple print wrapper that also broadcasts
def log_and_broadcast(message: str):
    """Print message to stderr and also send to visualizer.
    
    IMPORTANT: Must use stderr, not stdout.
    MCP STDIO protocol reserves stdout exclusively for JSON-RPC messages.
    Any non-JSON output to stdout will corrupt the MCP protocol channel.
    """
    import sys
    print(message, file=sys.stderr)
    broadcast_log_sync(message)
