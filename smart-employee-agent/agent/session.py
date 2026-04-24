"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Per-User Session Store

  In-memory session store keyed by the user's `sub` claim from their JWT.
  Each session tracks OBO tokens, chat history, and in-progress OBO flows.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Any


DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 8  # 8 hours of inactivity


@dataclass
class UserSession:
    """Session state for a single authenticated user."""

    user_sub: str
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    user_scopes: list[str] = field(default_factory=list)

    # OBO token state
    obo_token: Optional[Any] = None
    obo_scopes: list[str] = field(default_factory=list)
    obo_expires_at: float = 0.0

    # Chat state
    chat_history: list[dict] = field(default_factory=list)
    pending_message: Optional[str] = None

    # In-progress OBO flow
    obo_code_verifier: Optional[str] = None
    obo_pkce_state: Optional[str] = None

    # Activity tracking for TTL-based eviction.
    last_accessed: float = field(default_factory=lambda: time.time())

    def touch(self) -> None:
        """Mark this session as recently accessed."""
        self.last_accessed = time.time()

    @property
    def has_valid_obo(self) -> bool:
        """OBO token exists and is not expired."""
        return self.obo_token is not None and time.time() < self.obo_expires_at

    @property
    def obo_expired(self) -> bool:
        """OBO token was previously obtained but has expired."""
        return self.obo_token is not None and time.time() >= self.obo_expires_at


class SessionStore:
    """In-memory session store keyed by user sub claim."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self._sessions: dict[str, UserSession] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, sub: str) -> Optional[UserSession]:
        """Get session by sub, returns None if not found."""
        session = self._sessions.get(sub)
        if session:
            session.touch()
        return session

    def get_or_create(self, sub: str) -> UserSession:
        """Get existing session or create a new one. Opportunistically prunes expired entries."""
        self.prune_expired()
        if sub not in self._sessions:
            self._sessions[sub] = UserSession(user_sub=sub)
        else:
            self._sessions[sub].touch()
        return self._sessions[sub]

    def find_by_obo_state(self, state: str) -> Optional[UserSession]:
        """Find a session by its in-progress OBO PKCE state."""
        if not state:
            return None
        for session in self._sessions.values():
            if session.obo_pkce_state == state:
                return session
        return None

    def remove(self, sub: str) -> None:
        """Remove a single user's session (e.g., on sign-out)."""
        self._sessions.pop(sub, None)

    def prune_expired(self) -> int:
        """Drop sessions inactive longer than the TTL. Returns the number pruned."""
        if self._ttl_seconds <= 0:
            return 0
        cutoff = time.time() - self._ttl_seconds
        stale = [sub for sub, s in self._sessions.items() if s.last_accessed < cutoff]
        for sub in stale:
            del self._sessions[sub]
        return len(stale)

    def clear_all(self):
        """Clear all sessions (used on data reset)."""
        self._sessions.clear()
