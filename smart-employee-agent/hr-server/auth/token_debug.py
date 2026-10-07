"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  Token Claim Inspector (development only)

  Pretty-prints the DECODED claims of a token when DEBUG_TOKENS=true, so a
  delegation chain can be shown on screen without pasting a JWT into a
  third-party decoder.

  Two levels, deliberately separate:

    DEBUG_TOKENS=true      decoded claims only. Enough to tell the story, since
                           claims are what a resource server authorizes on.

    DEBUG_TOKENS_RAW=true  ALSO prints the encoded token, for pasting into
                           jwt.io. This writes a live credential to the log.
                           Anyone reading that log — or a screenshot, or a
                           pasted terminal dump — can replay it until it
                           expires. Use it on a throwaway tenant, and never
                           leave it on.

  Raw implies claims, so setting only DEBUG_TOKENS_RAW works. Both default to
  off, so production logs never grow this.
"""

import hashlib
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RAW = os.getenv("DEBUG_TOKENS_RAW", "").lower() == "true"
# Asking for the raw token implies wanting the claims too.
ENABLED = RAW or os.getenv("DEBUG_TOKENS", "").lower() == "true"

if RAW:
    logger.warning(
        "DEBUG_TOKENS_RAW is on — live bearer tokens will be written to this "
        "log. Do not use on a tenant you care about, and do not share the log."
    )

# Shown first, in this order, because they are what decides authorization.
_HIGHLIGHT = ("sub", "act", "aut", "scope", "aud", "iss", "exp")

# The MCP streamable-HTTP transport re-validates the token on EVERY request in
# a session — initialize, notifications, ListTools, CallTool, terminate — so a
# single question triggers half a dozen identical dumps. Remember which tokens
# have already been shown and print each one once. A genuinely new token (a
# refresh, a different user, a switch from agent to delegated) has a different
# fingerprint and still prints.
_DEDUPE_LIMIT = 64
_seen: "OrderedDict[str, bool]" = OrderedDict()


def _already_shown(label: str, claims: dict, token: str) -> bool:
    """True if this exact token has been dumped under this label before."""
    basis = token or json.dumps(claims, sort_keys=True, default=str)
    key = f"{label}:{hashlib.sha256(basis.encode()).hexdigest()[:16]}"
    if key in _seen:
        _seen.move_to_end(key)
        return True
    _seen[key] = True
    while len(_seen) > _DEDUPE_LIMIT:
        _seen.popitem(last=False)
    return False


def _fmt_exp(exp) -> str:
    """Absolute expiry plus how long is left, which is what you actually want."""
    try:
        when = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except (TypeError, ValueError):
        return str(exp)
    remaining = (when - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return f"{when.isoformat()} (EXPIRED)"
    mins, secs = divmod(int(remaining), 60)
    return f"{when.isoformat()} (in {mins}m {secs}s)"


def _actor_chain(act) -> list:
    """Every actor in a delegation chain, outermost (nearest the user) first.

    A single-hop OBO token has one entry. A nested chain — each agent recorded
    as having carried the previous one's authority — has several. Depth is
    capped so a malformed or hostile token cannot spin this.
    """
    chain = []
    while isinstance(act, dict) and len(chain) < 8:
        sub = act.get("sub")
        if not sub:
            break
        chain.append(sub)
        act = act.get("act")
    if not chain and act:
        chain.append(str(act))
    return chain


def dump_claims(label: str, claims: dict, token: str = "") -> None:
    """Log decoded token claims under `label`. No-op unless DEBUG_TOKENS=true.

    Pass `token` to have the encoded form printed as well when
    DEBUG_TOKENS_RAW=true. It is ignored otherwise.
    """
    if not ENABLED or not claims:
        return
    if _already_shown(label, claims, token):
        return

    chain = _actor_chain(claims.get("act"))

    lines = [f"╭─ {label} " + "─" * max(0, 62 - len(label))]

    if chain:
        # The whole point of a delegated token: more than one identity, one
        # call. `act` may itself nest an `act`, which is how a chain of agents
        # records that each one passed the authority along. Walk the whole
        # chain — showing only the innermost actor would name the wrong agent.
        carriers = "an agent" if len(chain) == 1 else f"{len(chain)} agents"
        lines.append(f"│ DELEGATED — a person's authority, carried by {carriers}")
        lines.append(f"│   sub{'':<12}= {claims.get('sub')}   (whose authority)")
        for depth, actor_sub in enumerate(chain, start=1):
            path = "act." * depth + "sub"
            note = "(carried by)" if depth == 1 else "(which was carried by)"
            lines.append(f"│   {path:<15}= {actor_sub}   {note}")
        # `aut` names what kind of principal the SUBJECT is, and it matters just
        # as much on a delegated token — it is how you tell a person's borrowed
        # authority from an agent's own.
        if claims.get("aut"):
            lines.append(f"│   {'aut':<15}= {claims.get('aut')}")
    else:
        lines.append("│ NOT DELEGATED — the caller acts as itself")
        lines.append(f"│   sub      = {claims.get('sub')}")
        if claims.get("aut"):
            lines.append(f"│   aut      = {claims.get('aut')}")

    scope = claims.get("scope") or ""
    lines.append(f"│ scopes     = {' '.join(scope.split()) or '(none)'}")
    lines.append(f"│ audience   = {claims.get('aud')}")
    lines.append(f"│ issuer     = {claims.get('iss')}")
    if claims.get("exp"):
        lines.append(f"│ expires    = {_fmt_exp(claims.get('exp'))}")

    others = {k: v for k, v in claims.items() if k not in _HIGHLIGHT}
    if others:
        lines.append("│ other claims:")
        for line in json.dumps(others, indent=2, default=str, sort_keys=True).splitlines():
            lines.append(f"│   {line}")

    lines.append("╰" + "─" * 63)

    if RAW and token:
        # Deliberately outside the box and on one unbroken line: a JWT wrapped
        # across box-drawing characters cannot be copied without hand-editing,
        # and a half-copied token fails verification in a confusing way.
        lines.append("")
        lines.append("  encoded token (CREDENTIAL — do not share, expires soon):")
        lines.append(token)

    logger.info("token claims\n%s", "\n".join(lines))


def dump_encoded(label: str, token: str) -> None:
    """Decode a token WITHOUT verifying, purely to display its claims.

    For a token this process just received from the IdP over TLS and is about
    to use. Verification happens at the resource server; re-doing it here would
    only obscure what this function is for.
    """
    if not ENABLED or not token:
        return
    try:
        import jwt
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        logger.info("[%s] could not decode token for display: %s", label, e)
        return
    dump_claims(label, claims, token)
