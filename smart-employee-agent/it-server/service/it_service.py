"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  IT Service Layer

  Business logic for the IT service desk, kept free of transport and auth
  concerns so the MCP layer stays thin.
"""

import logging

from service import store

logger = logging.getLogger(__name__)


async def get_policies(topic: str = "") -> list[dict]:
    """All IT policies, or those whose topic matches a case-insensitive substring."""
    if not topic:
        return store.IT_POLICIES
    needle = topic.lower()
    return [p for p in store.IT_POLICIES if needle in p["topic"].lower()]


async def get_service_status() -> list[dict]:
    """Current operational status of internal IT services."""
    return store.SERVICE_STATUS


async def get_software_catalog() -> list[dict]:
    """Licensed software available to employees."""
    return store.SOFTWARE_CATALOG


async def create_ticket(
    subject: str,
    category: str,
    requested_for: str,
    actor: str,
    owner_sub: str | None = None,
    home_org: str = "primary",
) -> dict:
    """File a support ticket. `actor` is the audit string for who filed it.

    `owner_sub` is the subject of the human the ticket belongs to, when one is
    known. It is what lets the queue be filtered to "my tickets" without
    relying on display names, which are neither unique nor stable.
    """
    ticket_id = store.next_ticket_id()
    ticket = {
        "ticket_id": ticket_id,
        "subject": subject,
        "category": category or "General",
        "status": "Open",
        "requested_for": requested_for or "Unknown",
        "created_by": actor,
        "owner_sub": owner_sub,
        "home_org": home_org,
        "resolution": None,
        "resolved_by": None,
    }
    store.tickets[ticket_id] = ticket
    logger.info("[AUDIT] Ticket %s created by %s (for %s)", ticket_id, actor, requested_for)
    return ticket


async def resolve_ticket(ticket_id: str, resolution: str, actor: str) -> dict:
    """Close a ticket with a resolution note.

    This is the action that only an IT service-desk admin may take. It is a
    distinct scope from raising a ticket precisely so that "can ask for help"
    and "can close someone else's request" are separable permissions.
    """
    key = ticket_id.strip().upper()
    ticket = store.tickets.get(key)
    if not ticket:
        return {"error": "not_found", "message": f"No ticket found with id '{ticket_id}'."}
    if ticket["status"] == "Resolved":
        return {
            "error": "invalid_status",
            "message": f"Ticket {key} is already resolved.",
        }
    if not resolution.strip():
        return {
            "error": "invalid_request",
            "message": "A resolution note is required to close a ticket.",
        }

    ticket["status"] = "Resolved"
    ticket["resolution"] = resolution.strip()
    ticket["resolved_by"] = actor
    logger.info("[AUDIT] Ticket %s resolved by %s", key, actor)
    return {"success": True, "ticket": ticket}


async def get_ticket(ticket_id: str) -> dict | None:
    return store.tickets.get(ticket_id.strip().upper())


async def list_tickets(requested_for: str = "", owner_sub: str | None = None) -> list[dict]:
    """Tickets, optionally narrowed to a person.

    `owner_sub` is an authorization filter applied by the caller when the
    requester may only see their own tickets; `requested_for` is a convenience
    name search. The subject filter wins, because a name can be typed by anyone
    while a subject comes from a validated token.
    """
    all_tickets = list(store.tickets.values())
    if owner_sub:
        return [t for t in all_tickets if t.get("owner_sub") == owner_sub]
    if not requested_for:
        return all_tickets
    needle = requested_for.lower()
    return [t for t in all_tickets if needle in (t.get("requested_for") or "").lower()]


def reset() -> None:
    store.reset()
