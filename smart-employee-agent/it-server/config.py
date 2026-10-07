"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT Server Configuration

  Centralized environment loading and validation for the IT MCP server.
"""

import os
from dotenv import load_dotenv

load_dotenv()

AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")  # MCP Client app client_id (audience for MCP tokens)
# A token produced by RFC 8693 exchange is minted by the EXCHANGE application,
# so its `aud` is that client's id, not the MCP client's. Accept both, or every
# delegated A2A call fails audience validation before any scope is checked.
EXCHANGE_CLIENT_ID = os.getenv("EXCHANGE_CLIENT_ID", "")
JWKS_URL = os.getenv("JWKS_URL")
SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true"

if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError(
        "Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL"
    )

ACCEPTED_AUDIENCES = [a for a in (CLIENT_ID, EXCHANGE_CLIENT_ID) if a]

PORT = int(os.getenv("IT_SERVER_PORT", os.getenv("PORT", "8001")))
HOST = os.getenv("IT_SERVER_HOST", "0.0.0.0")

# uvicorn's per-request access line ("GET /api/leaves 200 OK"). Off by default:
# these logs are meant to be read on screen to follow an authorization flow,
# and one chat action produces several REST calls behind the scenes.
ACCESS_LOG = os.getenv("ACCESS_LOG", "").lower() == "true"
