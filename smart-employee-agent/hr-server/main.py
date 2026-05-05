"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR Server — Single-Process Composition

  Wires the MCP app and the REST API into one Starlette ASGI app served
  by uvicorn. Both share the same in-memory store, JWT validator, and
  config. The REST routes win over the catch-all MCP mount.
"""

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount

import uvicorn

import config
from mcp_server.server import build_app as build_mcp_app
from rest_api.server import CORSMiddleware, routes as rest_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_app() -> Starlette:
    """Compose REST routes + MCP catch-all into one Starlette app with CORS."""
    mcp_app = build_mcp_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.router.lifespan_context(app):
            yield

    routes = [*rest_routes(), Mount("/", app=mcp_app)]

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(CORSMiddleware)
    return app


app = build_app()


if __name__ == "__main__":
    logger.info("Starting HR server on %s:%d", config.HOST, config.PORT)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
