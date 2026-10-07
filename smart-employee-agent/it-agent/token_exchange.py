"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Token Exchange — Carrying a User's Authority Across a Second Agent Hop

  Pattern 4 has a known limitation: on the HR -> IT hop the user is context,
  not authority. The IT Agent acts on its own identity, so the IT resource
  server authorizes the *agent* and the user's name is only unverified data
  travelling alongside. An agent could name anyone.

  RFC 8693 token exchange closes that gap. Given

      subject_token   the user's delegated token   sub=user, act=HR Agent
      actor_token     the IT Agent's own token     sub=IT Agent

  the authorization server issues a token whose actor chain records BOTH hops:

      {
        "sub": "<user>",                     the authority being exercised
        "act": { "sub": "<IT Agent>",        who is exercising it now
                 "act": { "sub": "<HR Agent>" } }   who passed it along
      }

  The resource server can then authorize the *person*, while the audit trail
  still names every agent that carried the request, in order. Nothing has to
  be taken on trust from a forwarded display name.

  Called with direct HTTP because the SDK's token client implements only
  authorization_code and refresh_token.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"


class TokenExchangeError(Exception):
    """The exchange failed; the caller decides whether to fall back."""


class TokenExchangeClient:
    """Exchanges a user's delegated token for one that also names this agent."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str = "",
        ssl_verify: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.ssl_verify = ssl_verify

    @property
    def token_endpoint(self) -> str:
        return f"{self.base_url}/oauth2/token"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.client_id)

    async def exchange(
        self,
        subject_token: str,
        actor_token: str,
        scopes: list[str] | None = None,
    ) -> dict:
        """Swap (subject, actor) for a token carrying both in its actor chain.

        `subject_token` is whose authority is being exercised — the user's
        delegated token. `actor_token` is this agent, which becomes the new
        outermost actor, pushing the previous one down a level.
        """
        data = {
            "grant_type": GRANT_TYPE,
            "subject_token": subject_token,
            "subject_token_type": ACCESS_TOKEN_TYPE,
            "actor_token": actor_token,
            "actor_token_type": ACCESS_TOKEN_TYPE,
            "requested_token_type": ACCESS_TOKEN_TYPE,
            "client_id": self.client_id,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        if scopes:
            data["scope"] = " ".join(scopes)

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=self.ssl_verify) as client:
                resp = await client.post(
                    self.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as e:
            raise TokenExchangeError(f"Could not reach the token endpoint: {e}") from e

        if resp.status_code != 200:
            raise TokenExchangeError(_describe(resp))

        body = resp.json()
        if not body.get("access_token"):
            raise TokenExchangeError("Exchange succeeded but returned no access_token.")

        logger.info(
            "[EXCHANGE] delegated token issued (granted scopes: %s)",
            body.get("scope") or "(none)",
        )
        return body


def _describe(resp) -> str:
    """Readable detail from an error response.

    `unsupported_grant_type` here means token exchange is not enabled on the
    application; `invalid_client` usually means the exchange needs a
    confidential client and the configured one is public.
    """
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or f"HTTP {resp.status_code}")[:200]
    for key in ("error_description", "description", "message", "error"):
        if body.get(key):
            return f"{body[key]} (HTTP {resp.status_code})"
    return f"HTTP {resp.status_code}"
