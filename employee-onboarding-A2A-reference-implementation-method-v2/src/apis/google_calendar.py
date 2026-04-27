"""
Google Calendar Utility
Handles creating Google Calendar events using a Service Account.
"""

import os
import uuid
import structlog
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = structlog.get_logger()

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# The shared Google Calendar to create events in
CALENDAR_ID = os.environ.get(
    "GOOGLE_CALENDAR_ID",
    "e700fbdb0b41857e762a4d6b07af44e1e93d564d6f2153ddaac53f12a6b95151@group.calendar.google.com"
)

# Default service account path
_DEFAULT_CREDS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', 'a2areferenceimp-ef2e4e0ce1b3.json'
)


def get_calendar_service():
    """Initialize the Google Calendar service using Service Account credentials."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", _DEFAULT_CREDS)
    creds_path = os.path.normpath(creds_path)

    if not os.path.exists(creds_path):
        logger.warning(f"Google Calendar credentials not found at {creds_path}. Running in mock mode.")
        return None

    try:
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to initialize Google Calendar service: {e}")
        return None


def create_calendar_event(
    title: str,
    description: str,
    start_iso: str,
    end_iso: str,
    attendee_email: str = None
) -> dict:
    """
    Creates a new Google Calendar event in the configured calendar.
    Falls back to mock mode if credentials are unavailable.
    """
    service = get_calendar_service()
    if not service:
        return {
            "success": True,
            "htmlLink": "https://calendar.google.com/calendar/r/eventedit?mock=true",
            "meetLink": "https://meet.google.com/mock-link",
            "mocked": True
        }

    event = {
        'summary': title,
        'description': description,
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
    }

    if attendee_email:
        event['attendees'] = [{'email': attendee_email}]

    try:
        # Note: conferenceDataVersion omitted - Meet links require Google Workspace
        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event
        ).execute()

        entry_points = created_event.get('conferenceData', {}).get('entryPoints', [])
        meet_link = entry_points[0].get('uri') if entry_points else None

        logger.info("calendar_event_created",
                    event_id=created_event.get('id'),
                    link=created_event.get('htmlLink'))

        return {
            "success": True,
            "htmlLink": created_event.get('htmlLink'),
            "meetLink": meet_link,
            "eventId": created_event.get('id'),
            "mocked": False
        }
    except HttpError as error:
        logger.error("calendar_api_error", error=str(error))
        return {"success": False, "error": str(error)}
    except Exception as e:
        logger.error("calendar_unknown_error", error=str(e))
        return {"success": False, "error": str(e)}
