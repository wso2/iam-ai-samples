"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT Server — Single-Process Composition

  Serves the IT MCP app plus a /reset endpoint for demo data, mirroring the
  HR server's shape but without a REST API (no browser talks to this service —
  only the IT Agent does).
"""

import logging

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

import uvicorn

import config
from mcp_server.server import build_app as build_mcp_app
from service import it_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset(request):
    """Restore demo data. Unauthenticated by design — demo convenience only,
    matching the HR server's /reset."""
    it_service.reset()
    logger.info("IT data reset to default state")
    return JSONResponse({"success": True, "message": "IT data reset to default state."})


def build_app() -> Starlette:
    """Compose the /reset route ahead of the MCP catch-all mount."""
    mcp_app = build_mcp_app()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.router.lifespan_context(app):
            yield

    routes = [Route("/reset", reset, methods=["POST"]), Mount("/", app=mcp_app)]
    return Starlette(routes=routes, lifespan=lifespan)


app = build_app()


if __name__ == "__main__":
    logger.info("Starting IT server on %s:%d", config.HOST, config.PORT)
    uvicorn.run(app, host=config.HOST, port=config.PORT, access_log=config.ACCESS_LOG)
