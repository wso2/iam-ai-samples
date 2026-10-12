"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Google Calendar — Third-Party Delegated Access (Pattern 6)

  Uses the employee's Google access token shared by Asgardeo after OBO or
  CIBA consent. The agent calls Calendar directly, but never Google's OAuth
  token endpoint. A fresh federated token must be obtained through Asgardeo
  when this grant expires.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)
EVENTS_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
EVENT_WRITE_SCOPES = {
    CALENDAR_SCOPE,
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar",
}
REFRESH_BUFFER_SECONDS = 60


class GoogleCalendarError(Exception):
    """A Google grant or Calendar call failed."""


class GoogleGrant:
    """An upstream access token held only in the employee's agent session."""

    def __init__(self, access_token: str, expires_at: float, scope: str):
        self.access_token = access_token
        self.expires_at = expires_at
        self.scope = scope

    @property
    def is_fresh(self) -> bool:
        return bool(self.access_token) and time.time() < (self.expires_at - REFRESH_BUFFER_SECONDS)


class GoogleCalendarClient:
    """Write events using federated tokens; no separate Google OAuth client."""

    async def ensure_access_token(self, grant: GoogleGrant) -> str:
        if not grant.is_fresh:
            raise GoogleCalendarError(
                "Google authorization has expired. Authorize again through Google in Asgardeo."
            )
        if not EVENT_WRITE_SCOPES.intersection(grant.scope.split()):
            raise GoogleCalendarError(
                f"Google token is missing Calendar event access ({CALENDAR_SCOPE}); "
                f"granted scopes: {grant.scope or '(none)'}. "
                "Check the Google connection's allowed/requested scopes and grant Calendar consent."
            )
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
