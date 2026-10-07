"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Google Calendar — Third-Party Delegated Access (Pattern 6)

  The agent writes an all-day entry to the employee's own Google Calendar when
  their leave is approved.

  The IAM point: this is a SECOND, independent delegation, to a different
  identity provider. Asgardeo has no authority over Google, so consenting to
  the agent in Asgardeo grants it nothing here — the user must separately
  authorize Google Calendar access, and can revoke it separately too.

      Pattern 3  user delegates their Asgardeo authority to the agent (OBO)
      Pattern 5  a second human delegates theirs, out-of-band (CIBA)
      Pattern 6  user delegates their GOOGLE authority to the agent

  Google's REST API is called directly with httpx — no google client library —
  so the token handling stays visible rather than hidden in an SDK.
"""

import logging
import time
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
EVENTS_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

# Only what is needed to add an entry. Not calendar.readonly, not full calendar.
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"

REFRESH_BUFFER_SECONDS = 60


class GoogleCalendarError(Exception):
    """A Google Calendar call failed in a way worth telling the user about."""


class GoogleGrant:
    """One user's Google delegation, held in memory alongside their session."""

    def __init__(self, refresh_token: str, access_token: str = "", expires_at: float = 0.0):
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.expires_at = expires_at

    @property
    def is_fresh(self) -> bool:
        return bool(self.access_token) and time.time() < (self.expires_at - REFRESH_BUFFER_SECONDS)


class GoogleCalendarClient:
    """Runs the Google OAuth dance and writes calendar entries."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def authorization_url(self, state: str) -> str:
        """Consent URL for the popup.

        access_type=offline + prompt=consent is what makes Google return a
        refresh token; without both, a returning user gets an access token only
        and the grant dies in an hour.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_SCOPE,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GoogleGrant:
        """Swap the authorization code for tokens."""
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(TOKEN_ENDPOINT, data=data)

        if resp.status_code != 200:
            raise GoogleCalendarError(f"Token exchange failed: {_describe(resp)}")

        body = resp.json()
        refresh = body.get("refresh_token")
        if not refresh:
            # Google withholds it if the user previously consented and we did
            # not force a fresh prompt.
            raise GoogleCalendarError(
                "Google did not return a refresh token. Revoke the app's access "
                "at myaccount.google.com/permissions and connect again."
            )
        return GoogleGrant(
            refresh_token=refresh,
            access_token=body.get("access_token", ""),
            expires_at=time.time() + float(body.get("expires_in", 3600)),
        )

    async def ensure_access_token(self, grant: GoogleGrant) -> str:
        """Return a usable access token, refreshing when it has aged out."""
        if grant.is_fresh:
            return grant.access_token

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": grant.refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(TOKEN_ENDPOINT, data=data)

        if resp.status_code != 200:
            # invalid_grant here usually means the user revoked access.
            raise GoogleCalendarError(f"Could not refresh Google access: {_describe(resp)}")

        body = resp.json()
        grant.access_token = body.get("access_token", "")
        grant.expires_at = time.time() + float(body.get("expires_in", 3600))
        logger.info("[GOOGLE] access token refreshed")
        return grant.access_token

    async def create_leave_event(
        self,
        grant: GoogleGrant,
        summary: str,
        start_date: str,
        end_date: str,
        description: str = "",
    ) -> dict:
        """Create an all-day event covering the leave.

        Google treats the all-day `end.date` as EXCLUSIVE, so a 5th-7th leave
        must be sent as end=8th or the last day silently goes missing.
        """
        access_token = await self.ensure_access_token(grant)
        exclusive_end = _day_after(end_date)

        event = {
            "summary": summary,
            "description": description,
            "start": {"date": start_date},
            "end": {"date": exclusive_end},
            "transparency": "opaque",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                EVENTS_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                json=event,
            )

        if resp.status_code not in (200, 201):
            raise GoogleCalendarError(f"Could not create the calendar entry: {_describe(resp)}")

        body = resp.json()
        logger.info(
            "[GOOGLE >> Calendar] event created id=%s %s..%s (end exclusive)",
            body.get("id"), start_date, exclusive_end,
        )
        return body


def _day_after(date_str: str) -> str:
    """YYYY-MM-DD one day later, for Google's exclusive all-day end date."""
    from datetime import date, timedelta

    y, m, d = (int(p) for p in date_str.split("-"))
    return (date(y, m, d) + timedelta(days=1)).isoformat()


def _describe(resp) -> str:
    """Readable detail from a Google error response."""
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or f"HTTP {resp.status_code}")[:200]
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)
    for key in ("error_description", "error", "message"):
        if body.get(key):
            return str(body[key])
    return f"HTTP {resp.status_code}"
