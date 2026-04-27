"""
Authentication utilities (PKCE, etc.)
"""

import secrets
import hashlib
import base64
from dataclasses import dataclass

@dataclass
class PKCEChallenge:
    verifier: str
    challenge: str
    method: str = "S256"

def generate_pkce() -> PKCEChallenge:
    """Generate a PKCE challenge pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    return PKCEChallenge(verifier=verifier, challenge=challenge)
