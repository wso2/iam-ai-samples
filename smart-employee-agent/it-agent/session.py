"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Per-User Session Store (IT Service Desk)

  The IT Agent keeps sessions for the *people* who use the service desk
  directly — not for the HR Agent, which is stateless on this side and
  re-authorizes on every call.

  Each session holds the user's delegated (OBO) token, so the IT MCP server
  can authorize that human's own scopes rather than the agent's. It also
  records `home_org`: which identity domain vouched for this person. A user
  federated in from a partner organization is authenticated by that partner's
  provider, and their session says so.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Any


DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 8  # 8 hours of inactivity


@dataclass
class DeskSession:
    """Session state for one human using the IT service desk."""

    user_sub: str
    user_name: Optional[str] = None
    user_scopes: list[str] = field(default_factory=list)

    # Which identity provider / organization this person came from. "primary"
    # for a local user; the federated connection's name for a partner user.
    home_org: str = "primary"

    # Delegated token: sub = this user, act.sub = the IT Agent.
    obo_token: Optional[Any] = None
    obo_scopes: list[str] = field(default_factory=list)
    obo_expires_at: float = 0.0

    # In-progress OBO consent
    obo_code_verifier: Optional[str] = None
    obo_pkce_state: Optional[str] = None

    chat_history: list[dict] = field(default_factory=list)
    pending_message: Optional[str] = None

    last_accessed: float = field(default_factory=lambda: time.time())

    def touch(self) -> None:
        self.last_accessed = time.time()

    @property
    def has_valid_obo(self) -> bool:
        return self.obo_token is not None and time.time() < self.obo_expires_at

    @property
    def obo_expired(self) -> bool:
        return self.obo_token is not None and time.time() >= self.obo_expires_at

    @property
    def is_from_partner_org(self) -> bool:
        """True when this person's identity lives outside the primary org.

        Surfaced in the UI and the logs. Without it, federation is invisible:
        the token the agent receives looks identical either way, which is the
        architectural win and the demo problem at the same time.
        """
        return self.home_org != "primary"


class DeskSessionStore:
    """In-memory session store keyed by the user's `sub` claim."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self._sessions: dict[str, DeskSession] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, sub: str) -> Optional[DeskSession]:
        session = self._sessions.get(sub)
        if session:
            session.touch()
        return session

    def get_or_create(self, sub: str) -> DeskSession:
        self.prune_expired()
        if sub not in self._sessions:
            self._sessions[sub] = DeskSession(user_sub=sub)
        else:
            self._sessions[sub].touch()
        return self._sessions[sub]

    def find_by_obo_state(self, state: str) -> Optional[DeskSession]:
        """Find a session by its in-progress PKCE state.

        The consent popup returns via a browser redirect with no bearer token,
        so the state parameter is the only thing tying the callback back to the
        person who started it.
        """
        if not state:
            return None
        for session in self._sessions.values():
            if session.obo_pkce_state == state:
                return session
        return None

    def remove(self, sub: str) -> None:
        self._sessions.pop(sub, None)

    def prune_expired(self) -> int:
        if self._ttl_seconds <= 0:
            return 0
        cutoff = time.time() - self._ttl_seconds
        stale = [sub for sub, s in self._sessions.items() if s.last_accessed < cutoff]
        for sub in stale:
            del self._sessions[sub]
        return len(stale)

    def clear_all(self) -> None:
        self._sessions.clear()
