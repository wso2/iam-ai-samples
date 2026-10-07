"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Google Grant Persistence

  Google refresh tokens survive restarts; the in-memory session that held them
  did not. That made the interesting part of the demo — the SECOND approval,
  where no link is needed because the user already consented — impossible to
  reach after any restart.

  Only the refresh token is kept. Access tokens are short-lived and are
  re-minted from it on demand, so there is no value in storing them and every
  reason not to.

  This writes a credential to disk in plaintext. Acceptable for a sample
  running on one machine; a real deployment encrypts it, or keeps it in a
  secret store keyed by user. The file is gitignored.
"""

import json
import logging
import os
import pathlib

logger = logging.getLogger(__name__)

# Alongside the agent, next to .env, and ignored by git for the same reason.
STORE_PATH = pathlib.Path(
    os.getenv("GRANT_STORE_PATH", pathlib.Path(__file__).parent / ".google_grants.json")
)


def _load_all() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text() or "{}")
    except (ValueError, OSError) as e:
        logger.warning("[GRANTS] could not read %s (%s) — starting empty", STORE_PATH, e)
        return {}


def save(sub: str, refresh_token: str) -> None:
    """Remember a user's Google refresh token across restarts."""
    if not sub or not refresh_token:
        return
    data = _load_all()
    data[sub] = refresh_token
    try:
        STORE_PATH.write_text(json.dumps(data, indent=2))
        # 0600: the file holds credentials, and the default umask does not.
        os.chmod(STORE_PATH, 0o600)
        logger.info("[GRANTS] stored Google grant for user(sub)=%s", sub)
    except OSError as e:
        logger.warning("[GRANTS] could not persist the grant for %s: %s", sub, e)


def forget(sub: str) -> None:
    """Drop a stored grant, e.g. when the user disconnects."""
    data = _load_all()
    if data.pop(sub, None) is not None:
        try:
            STORE_PATH.write_text(json.dumps(data, indent=2))
            logger.info("[GRANTS] forgot the Google grant for user(sub)=%s", sub)
        except OSError as e:
            logger.warning("[GRANTS] could not update the store: %s", e)


def restore_all(google_calendar_module) -> dict:
    """Rebuild grants from disk. Returns {sub: GoogleGrant}.

    The access token is left empty on purpose: it is minted from the refresh
    token on first use, so a stale one is never presented.
    """
    data = _load_all()
    grants = {
        sub: google_calendar_module.GoogleGrant(refresh_token=token)
        for sub, token in data.items()
        if token
    }
    if grants:
        logger.info(
            "[GRANTS] restored %d Google grant(s) from disk — those users need "
            "no reconnect", len(grants),
        )
    return grants
