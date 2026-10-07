"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  OBO Flow for the IT Service Desk (Pattern 7)

  Pattern 3 lets the HR Agent act with an employee's authority. This is the
  same mechanism on the IT Agent, and it exists for a specific reason.

  Under Pattern 4 the IT Agent acts purely as itself: the HR Agent forwards a
  person's name as context, and the IT MCP server authorizes the agent. That
  is fine for answering questions, but it means the agent can do anything its
  own role allows, for anyone. When a *person* uses the service desk directly
  — including someone whose identity lives in a partner organization — their
  own permissions must decide what happens.

  So the IT Agent exchanges the user's consent for a delegated token:
  `sub` is the human, `act.sub` is the IT Agent. The IT MCP server then
  enforces that human's scopes without knowing or caring how they logged in,
  or which identity provider vouched for them.
"""

import json
import os
import time
import logging
from html import escape

from asgardeo_ai import AgentAuthManager

from token_debug import dump_encoded

logger = logging.getLogger(__name__)

# Every IT scope worth asking for. Asgardeo grants only the subset the user's
# role actually permits, so requesting `it_resolve_mcp` for an ordinary
# employee is safe — it simply is not granted, and the privileged tool then
# refuses them at the resource server.
OBO_SCOPES = [
    "openid", "profile",
    "it_basic_mcp", "it_ticket_mcp", "it_resolve_mcp",
]

# Scopes the agent asks for on its own behalf when acting as the actor token.
ACTOR_SCOPES = ["openid", "it_basic_mcp"]

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]


def _js_string(value: str) -> str:
    """JSON-encode a string for embedding in an inline <script>.

    json.dumps alone is not enough: a "</script>" inside the message would
    close the script element during HTML parsing, before JS ever sees it.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _postmessage_js(payload_js: str) -> str:
    """JS handing the consent result back to the window that opened the popup.

    postMessage takes one exact target origin, so send once per allowed origin
    and let the browser drop the non-matching ones. Never '*' — that would
    disclose the result to any page that managed to open this window.
    """
    return f"""    if (window.opener) {{
      {json.dumps(ALLOWED_ORIGINS)}.forEach(function (origin) {{
        window.opener.postMessage({payload_js}, origin);
      }});
    }}"""


async def get_authorization_url(it_agent_auth) -> tuple:
    """Generate the PKCE authorization URL for the consent popup.

    Returns (auth_url, state, code_verifier).
    """
    async with AgentAuthManager(
        it_agent_auth.asgardeo_config, it_agent_auth.agent_config
    ) as auth_manager:
        auth_url, state, code_verifier = auth_manager.get_authorization_url_with_pkce(
            OBO_SCOPES
        )

    logger.info("[IT-OBO] generated PKCE authorization URL")
    return auth_url, state, code_verifier


async def exchange_code(it_agent_auth, code: str, code_verifier: str):
    """Exchange the authorization code for a delegated token.

    The agent's own token rides along as the actor token, which is what makes
    the result a delegated one rather than a plain user token — the IT MCP
    server sees `act.sub` and can record which agent carried the authority.

    Returns (obo_token, scopes, expires_at).
    """
    async with AgentAuthManager(
        it_agent_auth.asgardeo_config, it_agent_auth.agent_config
    ) as auth_manager:
        agent_token = await auth_manager.get_agent_token(ACTOR_SCOPES)
        # Its `sub` reappears as `act.sub` in the delegated token issued below.
        dump_encoded("[IT-AGENT] Actor Token (becomes act.sub)", agent_token.access_token)
        obo_token = await auth_manager.get_obo_token(
            code,
            agent_token=agent_token,
            code_verifier=code_verifier,
        )

    scopes = []
    if getattr(obo_token, "scope", None):
        scopes = obo_token.scope.split()

    expires_at = time.time() + 3600
    if getattr(obo_token, "expires_in", None):
        expires_at = time.time() + obo_token.expires_in

    logger.info("[IT-OBO] delegated token obtained (granted scopes: %s)", scopes or "(none)")
    return obo_token, scopes, expires_at


def callback_html(success: bool, error: str = None) -> str:
    """HTML for the consent popup's landing page."""
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
    <p>You can close this window. The IT service desk will continue.</p>
  </div>
  <script>
""" + _postmessage_js("{ type: 'it_obo_success' }") + """
    setTimeout(() => window.close(), 2000);
  </script>
</body>
</html>"""

    message = error or "Unknown error"
    post_js = _postmessage_js(
        "{ type: 'it_obo_failed', error: " + _js_string(message) + " }"
    )
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
    <p>{escape(message)}</p>
    <p>You can close this window and try again.</p>
  </div>
  <script>
{post_js}
  </script>
</body>
</html>"""
