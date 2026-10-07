"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Signed Action Links

  A link emailed to someone who is not logged in cannot carry a bearer token,
  and must not be guessable. `?request_id=LR001` would let anyone who tried a
  few references trigger a calendar write for somebody else's leave.

  So each link carries a token that names the subject and the action, is
  signed with a server-side secret, expires, and can only be spent once. It
  authenticates the *link*, not the person: following it proves you received
  the mail, nothing more. That is why the only thing on the far side is an
  invitation to authenticate at Google — the link never grants access to
  anything by itself.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

# Regenerated on restart when unset, which invalidates outstanding links. Fine
# for a sample; a real deployment sets it so links survive a redeploy.
SECRET = os.getenv("ACTION_LINK_SECRET") or secrets.token_urlsafe(32)
DEFAULT_TTL_SECONDS = int(os.getenv("ACTION_LINK_TTL_SECONDS", str(7 * 24 * 3600)))

# Tokens already redeemed. In memory, so a restart forgets them — the expiry
# is the real bound. A persistent store would be needed to make single-use
# strict across restarts.
_spent: set[str] = set()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(SECRET.encode(), payload, hashlib.sha256).digest())


def create(action: str, subject: str, ttl_seconds: int = DEFAULT_TTL_SECONDS, **extra) -> str:
    """Mint a signed, expiring token describing one permitted action."""
    body = {
        "act": action,
        "sub": subject,
        "exp": int(time.time()) + ttl_seconds,
        "jti": secrets.token_urlsafe(8),
        **extra,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    return f"{_b64(raw)}.{_sign(raw)}"


def verify(token: str, action: str) -> dict | None:
    """Validate a token and mark it spent. Returns its payload, or None.

    Rejects anything whose signature does not match, whose action is not the
    one expected, that has expired, or that has already been used.
    """
    try:
        encoded, signature = token.split(".", 1)
        raw = _unb64(encoded)
    except Exception:
        logger.warning("[LINK] malformed token")
        return None

    # compare_digest, not ==, so a wrong signature cannot be found byte by byte
    # from response timing.
    if not hmac.compare_digest(signature, _sign(raw)):
        logger.warning("[LINK] bad signature — token was not minted here")
        return None

    try:
        body = json.loads(raw)
    except ValueError:
        return None

    if body.get("act") != action:
        logger.warning("[LINK] token is for %r, not %r", body.get("act"), action)
        return None
    if body.get("exp", 0) < time.time():
        logger.info("[LINK] token expired")
        return None
    if body.get("jti") in _spent:
        logger.info("[LINK] token already used")
        return None

    _spent.add(body["jti"])
    return body


def peek(token: str, action: str) -> dict | None:
    """Validate without spending — for showing a confirmation page first."""
    try:
        encoded, signature = token.split(".", 1)
        raw = _unb64(encoded)
    except Exception:
        return None
    if not hmac.compare_digest(signature, _sign(raw)):
        return None
    try:
        body = json.loads(raw)
    except ValueError:
        return None
    if body.get("act") != action or body.get("exp", 0) < time.time():
        return None
    if body.get("jti") in _spent:
        return None
    return body
