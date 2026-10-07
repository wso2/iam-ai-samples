"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  OBO (On-Behalf-Of) Flow Handling

  Generates PKCE authorization URLs for user consent and exchanges
  authorization codes for OBO tokens. Uses the Asgardeo SDK.
"""

import json
import os
import time
import logging
from html import escape
from urllib.parse import quote

import httpx

from asgardeo_ai import AgentAuthManager
from agent_auth import AgentAuth
from token_debug import dump_encoded

logger = logging.getLogger(__name__)

# All HR MCP scopes to request — Asgardeo grants only role-permitted ones.
# Deliberately no it_* scopes: this agent never calls the IT server itself,
# and asking for permissions it cannot use would inflate the consent screen.
OBO_SCOPES = [
    "openid", "profile",
    "hr_basic_mcp", "hr_self_mcp", "hr_read_mcp", "hr_approve_mcp",
]

# Origins the client may be served from. Doubles as the CORS allowlist in main.py
# and as the postMessage targets for the callback popup below.
# Asgardeo records consent per user, per application. Once granted, later
# authorizations redirect straight through and the popup just blinks — the
# token is still issued, but the consent screen (the thing this sample exists
# to show) never appears again. prompt=consent asks for it every time.
FORCE_CONSENT = os.getenv("OBO_PROMPT_CONSENT", "").lower() == "true"

# ─── Federated token sharing ────────────────────────────────────────────────
# Asgardeo can hand back the token its UPSTREAM identity provider issued, so
# the agent never needs its own Google OAuth client: the user signs in to
# Google at Asgardeo, and Asgardeo passes Google's access token through in the
# token response under `federated_tokens`.
#
# Only works on the code grant (which this flow is), and only for standard
# OIDC connections with ShareFederatedToken enabled on the authenticator.
FEDERATED_IDP_NAME = os.getenv("FEDERATED_IDP_NAME", "")
FEDERATED_TOKEN_SCOPE = os.getenv(
    "FEDERATED_TOKEN_SCOPE", "https://www.googleapis.com/auth/calendar.events"
)
SHARE_FEDERATED = bool(FEDERATED_IDP_NAME)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]


def _js_string(value: str) -> str:
    """JSON-encode a string for embedding in an inline <script>.

    json.dumps alone is not enough: a "</script>" inside the message would close
    the script element while the HTML is parsed, before JS ever sees the string.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _postmessage_js(payload_js: str) -> str:
    """JS that hands the OBO result back to the window that opened the popup.

    postMessage takes a single exact target origin, so we send once per allowed
    origin and let the browser drop the ones that don't match the opener. Never
    '*' — that would disclose the result to any page that opened this window.
    """
    return f"""    if (window.opener) {{
      {json.dumps(ALLOWED_ORIGINS)}.forEach(function (origin) {{
        window.opener.postMessage({payload_js}, origin);
      }});
    }}"""


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

    if SHARE_FEDERATED:
        # The IdP name keys the scope set and must match the connection's name
        # in Asgardeo exactly, or the scopes are silently ignored.
        auth_url += (
            f"&share_federated_token=true"
            f"&federated_token_scope={quote(FEDERATED_IDP_NAME)};"
            f"{quote(FEDERATED_TOKEN_SCOPE)}"
        )

    if FORCE_CONSENT and "prompt=" not in auth_url:
        # Appended rather than passed to the SDK, which exposes no parameter
        # for it. Harmless if the IdP ignores it.
        auth_url += ("&" if "?" in auth_url else "?") + "prompt=consent"

    logger.info(
        "Generated PKCE authorization URL for OBO flow%s",
        " (forcing the consent screen)" if FORCE_CONSENT else "",
    )
    return auth_url, state, code_verifier


class _Token:
    """Minimal stand-in for the SDK's OAuthToken.

    The SDK builds its dataclass field by field, so any extra field in the
    response — `federated_tokens` among them — is dropped before we ever see
    it. The exchange is therefore done directly here, mirroring exactly what
    the SDK posts, and the whole response is kept.
    """

    def __init__(self, body: dict):
        self.access_token = body.get("access_token", "")
        self.id_token = body.get("id_token")
        self.refresh_token = body.get("refresh_token")
        self.expires_in = body.get("expires_in")
        self.scope = body.get("scope")
        self.raw = body


async def exchange_code(agent_auth: AgentAuth, code: str, code_verifier: str):
    """Exchange authorization code for an OBO token.

    Returns (obo_token, scopes, expires_at, federated_tokens).
    """
    async with AgentAuthManager(
        agent_auth.asgardeo_config, agent_auth.agent_config
    ) as auth_manager:
        agent_token = await auth_manager.get_agent_token(["openid", "hr_basic_mcp"])

    # Presenting this as the actor token is what makes the result delegated:
    # its `sub` reappears as `act.sub` in the OBO token issued below.
    dump_encoded("[AGENT] Actor Token (becomes act.sub)", agent_token.access_token)

    cfg = agent_auth.asgardeo_config
    data = {
        "grant_type": "authorization_code",
        "client_id": cfg.client_id,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "actor_token": agent_token.access_token,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    elif getattr(cfg, "client_secret", None):
        # Mirrors the SDK: the secret is sent only when PKCE is not in play.
        data["client_secret"] = cfg.client_secret

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{str(cfg.base_url).rstrip('/')}/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"OBO token exchange failed: {resp.status_code} {resp.text[:300]}")

    body = resp.json()
    obo_token = _Token(body)
    scopes = (obo_token.scope or "").split()
    expires_at = time.time() + float(obo_token.expires_in or 3600)

    federated = body.get("federated_tokens") or []
    if federated:
        logger.info(
            "[FEDERATED] Asgardeo returned %d upstream token(s): %s",
            len(federated),
            ", ".join(f"{f.get('idp')}({f.get('scope', '')[:60]})" for f in federated),
        )
    elif SHARE_FEDERATED:
        logger.warning(
            "[FEDERATED] asked for a token from '%s' but none came back. The "
            "user may not have signed in through that connection, or "
            "ShareFederatedToken is not enabled on its authenticator.",
            FEDERATED_IDP_NAME,
        )

    logger.info(f"OBO token obtained (scopes: {scopes})")
    return obo_token, scopes, expires_at, federated


def google_grant_from(federated: list):
    """Build a Google grant from Asgardeo's federated token, if one is there.

    The upstream token has its own lifetime and no refresh token of its own —
    renewing it means going back through Asgardeo, not calling Google.
    """
    if not federated:
        return None
    import google_calendar

    for entry in federated:
        if FEDERATED_IDP_NAME and entry.get("idp") != FEDERATED_IDP_NAME:
            continue
        access = entry.get("accessToken") or entry.get("access_token")
        if not access:
            continue
        validity = float(entry.get("tokenValidityPeriod") or 3600)
        logger.info(
            "[FEDERATED >> Google] using the token Asgardeo obtained from '%s' "
            "(valid %ss, scope: %s)", entry.get("idp"), int(validity),
            entry.get("scope", "?"),
        )
        return google_calendar.GoogleGrant(
            refresh_token="",  # renewal goes through Asgardeo, not Google
            access_token=access,
            expires_at=time.time() + validity,
        )
    return None


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
""" + _postmessage_js("{ type: 'obo_success' }") + """
    setTimeout(() => window.close(), 2000);
  </script>
</body>
</html>"""
    else:
        message = error or "Unknown error"
        safe_error_html = escape(message)
        safe_error_js = _js_string(message)
        post_js = _postmessage_js("{ type: 'obo_failed', error: " + safe_error_js + " }")
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
{post_js}
  </script>
</body>
</html>"""
