"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  CIBA Flow — Out-of-Band Approval for a Non-Interactive Agent (Pattern 5)

  Client Initiated Backchannel Authentication lets the agent obtain a user's
  authorization when that user is NOT in the session and has no browser here.
  The agent asks Asgardeo to reach the approver on their own device; the
  approver consents there; the agent polls until a token comes back.

  How this differs from the OBO popup (Pattern 3):

      Pattern 3  the user driving the chat approves, in a browser redirect
      Pattern 5  a DIFFERENT human approves, out-of-band, no browser involved

  Passing the agent's token as `actor_token` makes Asgardeo issue a delegated
  token: `sub` is the approver, `act.sub` is the agent. That is the same shape
  the HR MCP server already validates, so nothing downstream needs to change.

  The SDK implements only authorization_code and refresh_token, so the CIBA
  grant is issued here with direct calls to the Asgardeo endpoints.
"""

import asyncio
import json
import logging
import os
import time

import httpx

# Initiation can be slow when the CIBA authenticator has to reach the user
# (sending mail, waking a device). Configurable, because a too-short timeout
# looks identical to the IdP being broken.
HTTP_TIMEOUT = float(os.getenv("CIBA_HTTP_TIMEOUT", "60"))

logger = logging.getLogger(__name__)

# OpenID CIBA Core: the grant type has NO "oauth:" segment. The wrong value
# is accepted at /oauth2/ciba but rejected at /oauth2/token with
# "Unsupported grant_type value", long after the user was notified.
CIBA_GRANT_TYPE = "urn:openid:params:grant-type:ciba"

# Asgardeo's documented polling states.
PENDING = "authorization_pending"
SLOW_DOWN = "slow_down"
EXPIRED = "expired_token"
DENIED = "access_denied"

# Not from Asgardeo — our own marker for "the poll never reached the server".
TRANSIENT = "_transient_network_error"

# Fields every CIBA token response carries. Anything else is worth calling out
# by name — it is how a feature like federated token sharing would surface,
# and the SDK's typed model would otherwise discard it unseen.
_STANDARD_FIELDS = {
    "access_token", "refresh_token", "id_token", "token_type",
    "expires_in", "scope",
}


def _log_token_response(body: dict) -> None:
    """Log every field Asgardeo returned, not just the ones we consume.

    Token values are truncated unless DEBUG_TOKENS_RAW is on, so this is safe
    to leave enabled: it shows the SHAPE of the response without writing
    credentials to the log.
    """
    raw = os.getenv("DEBUG_TOKENS_RAW", "").lower() == "true"

    def show(v):
        text = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        if raw or len(text) <= 60:
            return text
        return f"{text[:60]}… ({len(text)} chars)"

    lines = ["[CIBA] token response — every field returned:"]
    for key in sorted(body):
        mark = "   " if key in _STANDARD_FIELDS else " * "
        lines.append(f"  {mark}{key:20} = {show(body[key])}")

    extras = sorted(set(body) - _STANDARD_FIELDS)
    if extras:
        lines.append(f"  (* non-standard fields: {', '.join(extras)})")
    else:
        lines.append("  (no non-standard fields — nothing beyond the usual OAuth set)")
    logger.info("\n".join(lines))

# A long poll over an unreliable network will drop requests. Keep going unless
# they fail repeatedly in a row, which means the network is genuinely down.
MAX_CONSECUTIVE_NETWORK_FAILURES = 5


class CibaError(Exception):
    """CIBA flow failed in a way the caller should surface to the user."""


class CibaResult:
    """Outcome of a completed or abandoned CIBA flow."""

    def __init__(self, status: str, token=None, detail: str = ""):
        self.status = status          # "approved" | "expired" | "denied" | "timeout"
        self.token = token            # OAuthToken-ish dict when approved
        self.detail = detail

    @property
    def approved(self) -> bool:
        return self.status == "approved"


class CibaClient:
    """Initiates and polls Asgardeo CIBA requests."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        ssl_verify: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.ssl_verify = ssl_verify

    @property
    def ciba_endpoint(self) -> str:
        return f"{self.base_url}/oauth2/ciba"

    @property
    def token_endpoint(self) -> str:
        return f"{self.base_url}/oauth2/token"

    async def initiate(
        self,
        login_hint: str,
        scopes: list[str],
        binding_message: str,
        actor_token: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Ask Asgardeo to reach the approver out-of-band.

        `login_hint` names the human who must approve. `binding_message` is what
        they will see on their device, so it must describe the actual action.
        `actor_token` (the agent's own token) is what makes the resulting token
        a delegated one, with the agent recorded in `act`.

        Returns the raw response: auth_req_id, expires_in, and often interval.
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(scopes),
            "login_hint": login_hint,
            "binding_message": binding_message,
        }
        if actor_token:
            data["actor_token"] = actor_token
        if extra:
            # CIBA has no /authorize call, so parameters that would normally
            # ride there (share_federated_token, federated_token_scope) have
            # nowhere obvious to go. Whether Asgardeo forwards them from the
            # initiation request into the authentication flow is undocumented
            # — passing them costs nothing and is worth knowing.
            data.update({k: v for k, v in extra.items() if v})

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT, verify=self.ssl_verify
            ) as client:
                resp = await client.post(
                    self.ciba_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as e:
            # Was uncaught, so a timeout escaped as a raw httpx traceback past
            # every CibaError handler. A network failure here is ordinary and
            # deserves the same clear message as a rejection.
            raise CibaError(
                f"Could not reach the CIBA endpoint ({type(e).__name__}). If this "
                f"is a timeout, the authenticator in the application's login flow "
                f"may not be one CIBA can drive — CIBA needs an authenticator "
                f"that can reach the user out-of-band, not a redirect-based one."
            ) from e

        if resp.status_code != 200:
            detail = _describe(resp)
            logger.error("CIBA initiation failed (%s): %s", resp.status_code, detail)
            raise CibaError(f"Could not start the approval request: {detail}")

        body = resp.json()
        auth_req_id = body.get("auth_req_id")
        if not auth_req_id:
            raise CibaError("Asgardeo did not return an auth_req_id.")

        logger.info(
            "[CIBA] initiated | approver=%s | expires_in=%ss | interval=%ss",
            login_hint, body.get("expires_in"), body.get("interval", 2),
        )
        return body

    async def poll_once(self, auth_req_id: str) -> tuple[str, dict]:
        """Poll the token endpoint once.

        Returns (state, body) where state is "approved" or one of the
        documented pending/terminal error codes.
        """
        data = {
            "grant_type": CIBA_GRANT_TYPE,
            "auth_req_id": auth_req_id,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=self.ssl_verify) as client:
                resp = await client.post(
                    self.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as e:
            # The auth_req_id is still valid and the user may already have
            # approved — losing one poll must not lose the whole flow.
            logger.warning("[CIBA] poll failed to reach the IdP (%s)", type(e).__name__)
            return TRANSIENT, {}

        body = {}
        try:
            body = resp.json()
        except ValueError:
            pass

        if resp.status_code == 200 and body.get("access_token"):
            return "approved", body
        return body.get("error", f"http_{resp.status_code}"), body

    async def await_approval(
        self,
        auth_req_id: str,
        timeout_seconds: float,
        interval_seconds: float = 2.0,
    ) -> CibaResult:
        """Poll until the approver responds, the request expires, or we give up.

        Honours `slow_down` by backing off, as the spec requires — polling
        faster after that signal can get the request rejected outright.
        """
        deadline = time.monotonic() + timeout_seconds
        interval = max(interval_seconds, 1.0)
        network_failures = 0

        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            state, body = await self.poll_once(auth_req_id)

            if state == TRANSIENT:
                network_failures += 1
                if network_failures >= MAX_CONSECUTIVE_NETWORK_FAILURES:
                    logger.error(
                        "[CIBA] %d consecutive poll failures — giving up",
                        network_failures,
                    )
                    return CibaResult(
                        "timeout",
                        detail="Lost contact with the identity provider while "
                               "waiting for the approver.",
                    )
                continue
            network_failures = 0

            if state == "approved":
                logger.info("[CIBA] approved by the out-of-band user")
                _log_token_response(body)
                return CibaResult("approved", token=body)
            if state == PENDING:
                continue
            if state == SLOW_DOWN:
                interval += 2.0
                logger.info("[CIBA] slow_down — backing off to %ss", interval)
                continue
            if state == EXPIRED:
                logger.warning("[CIBA] auth_req_id expired before approval")
                return CibaResult("expired", detail="The approval request expired.")
            if state == DENIED:
                logger.warning("[CIBA] approver denied the request")
                return CibaResult("denied", detail="The approver declined the request.")

            detail = body.get("error_description") or state
            logger.error("[CIBA] unexpected polling state: %s", detail)
            return CibaResult("denied", detail=str(detail))

        logger.warning("[CIBA] gave up waiting after %ss", timeout_seconds)
        return CibaResult(
            "timeout",
            detail=f"No response from the approver within {int(timeout_seconds)} seconds.",
        )


def _describe(resp) -> str:
    """Best-effort human-readable detail from an error response."""
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or f"HTTP {resp.status_code}")[:200]
    for key in ("error_description", "description", "message", "error"):
        if body.get(key):
            return str(body[key])
    return f"HTTP {resp.status_code}"
