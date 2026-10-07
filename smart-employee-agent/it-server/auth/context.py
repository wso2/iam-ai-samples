"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Per-Request Context Variables

  Populated from validated JWT claims by the MCP token verifier and the
  REST middleware, then read by service-layer code to attribute actions
  to the authenticated user.
"""

import contextvars

current_scopes: contextvars.ContextVar[list] = contextvars.ContextVar(
    "current_scopes", default=[]
)
current_token_info: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "current_token_info", default={}
)
current_user_sub: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_sub", default=None
)
current_user_first_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_first_name", default=""
)
current_user_last_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_last_name", default=""
)
