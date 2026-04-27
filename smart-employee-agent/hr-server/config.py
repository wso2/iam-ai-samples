"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  HR Server Configuration

  Centralized environment loading and validation. Imported by both the
  MCP server and the REST API so they share a single source of truth.
"""

import os
from dotenv import load_dotenv

load_dotenv()

AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")          # MCP Client app client_id (audience for MCP tokens)
SPA_CLIENT_ID = os.getenv("SPA_CLIENT_ID")  # SPA app client_id (audience for browser REST tokens)
JWKS_URL = os.getenv("JWKS_URL")
SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "").lower() != "true"

if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError(
        "Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL"
    )

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]

PORT = int(os.getenv("HR_SERVER_PORT", os.getenv("PORT", "8000")))
HOST = os.getenv("HR_SERVER_HOST", "0.0.0.0")
