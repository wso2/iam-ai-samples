"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  OBO (On-Behalf-Of) Flow Handling

  Generates PKCE authorization URLs for user consent and exchanges
  authorization codes for OBO tokens. Uses the Asgardeo SDK.
"""

import json
import time
import logging
from html import escape

from asgardeo_ai import AgentAuthManager
from agent_auth import AgentAuth

logger = logging.getLogger(__name__)

# All HR MCP scopes to request — Asgardeo grants only role-permitted ones
OBO_SCOPES = [
    "openid", "profile",
    "hr_basic_mcp", "hr_self_mcp", "hr_read_mcp", "hr_approve_mcp",
]


async def get_authorization_url(agent_auth: AgentAuth) -> tuple:
    """Generate PKCE authorization URL for OBO flow.

    Returns (auth_url, state, code_verifier).
    """
    async with AgentAuthManager(
        agent_auth.asgardeo_config, agent_auth.agent_config
    ) as auth_manager:
        auth_url, state, code_verifier = auth_manager.get_authorization_url_with_pkce(
            OBO_SCOPES
        )

    logger.info("Generated PKCE authorization URL for OBO flow")
    return auth_url, state, code_verifier


async def exchange_code(agent_auth: AgentAuth, code: str, code_verifier: str):
    """Exchange authorization code for OBO token.

    Returns (obo_token, scopes, expires_at).
    """
    async with AgentAuthManager(
        agent_auth.asgardeo_config, agent_auth.agent_config
    ) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid", "hr_basic_mcp"])
        obo_token = await auth_manager.get_obo_token(
            code,
            agent_token=agent_token,
            code_verifier=code_verifier,
        )

    scopes = []
    if hasattr(obo_token, "scope") and obo_token.scope:
        scopes = obo_token.scope.split()

    expires_at = time.time() + 3600
    if hasattr(obo_token, "expires_in") and obo_token.expires_in:
        expires_at = time.time() + obo_token.expires_in

    logger.info(f"OBO token obtained (scopes: {scopes})")
    return obo_token, scopes, expires_at


def callback_html(success: bool, error: str = None) -> str:
    """Generate HTML for the OBO callback popup page."""
    if success:
        return """<!DOCTYPE html>
<html>
<head><title>Authorization Successful</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; background: #f0fdf4; }
  .card { text-align: center; padding: 2rem; }
  .icon { font-size: 3rem; margin-bottom: 1rem; }
  h2 { color: #166534; margin-bottom: 0.5rem; }
  p { color: #6b7280; }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10003;</div>
    <h2>Authorization Successful</h2>
    <p>You can close this window. The assistant will now process your request.</p>
  </div>
  <script>
    if (window.opener) {
      window.opener.postMessage({ type: 'obo_success' }, '*');
    }
    setTimeout(() => window.close(), 2000);
  </script>
</body>
</html>"""
    else:
        message = error or "Unknown error"
        safe_error_html = escape(message)
        safe_error_js = json.dumps(message)
        return f"""<!DOCTYPE html>
<html>
<head><title>Authorization Failed</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; background: #fef2f2; }}
  .card {{ text-align: center; padding: 2rem; }}
  .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
  h2 {{ color: #991b1b; margin-bottom: 0.5rem; }}
  p {{ color: #6b7280; }}
</style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10007;</div>
    <h2>Authorization Failed</h2>
    <p>{safe_error_html}</p>
    <p>You can close this window and try again.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'obo_failed', error: {safe_error_js} }}, '*');
    }}
  </script>
</body>
</html>"""
