"""Verify control-plane JWTs and map claims for the workbench.

Control-plane tokens
- Ed25519 (recommended): ``CONTROL_PLANE_JWT_PUBLIC_KEY_PATH`` (or the PEM itself in
  ``CONTROL_PLANE_JWT_PUBLIC_KEY``). The workbench holds only the public key, so even a
  fully compromised workbench cannot mint a token for another user or an admin.
- HS256 (legacy): shared ``CONTROL_PLANE_JWT_SECRET``. Used only when no public key is set.

Embedded-Agent tokens
- Minted and verified by the workbench alone with a key derived from its own token
  secret (issuer ``arcreel-workbench``). They never reach the control plane, which also
  refuses any token carrying the ``embedded_agent`` claim.
"""

from __future__ import annotations

import hashlib
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt

from saas.adapter import secret_env

logger = logging.getLogger(__name__)

_JWT_AUDIENCE = "arcreel-control-plane"
_JWT_ISSUER = "arcreel-auth"
_JWT_TYP = "access"

_AGENT_ISSUER = "arcreel-workbench"
_AGENT_AUDIENCE = "arcreel-workbench-agent"
_AGENT_TYP = "agent"
EMBEDDED_AGENT_CLAIM = "embedded_agent"


class AuthBridgeError(Exception):
    """Invalid control-plane token or misconfiguration."""


@lru_cache(maxsize=4)
def _read_public_key(path: str) -> str:
    try:
        pem = Path(path).read_text(encoding="ascii")
    except OSError as exc:
        raise AuthBridgeError(f"cannot read CONTROL_PLANE_JWT_PUBLIC_KEY_PATH {path}: {exc}") from exc
    if "PRIVATE KEY" in pem:
        raise AuthBridgeError("CONTROL_PLANE_JWT_PUBLIC_KEY_PATH points at a private key; give the workbench the public key only")
    return pem


def get_control_plane_public_key() -> str | None:
    """PEM of the control plane's Ed25519 verification key, or None in legacy HS256 mode."""
    inline = secret_env.get("CONTROL_PLANE_JWT_PUBLIC_KEY")
    if inline:
        return inline.replace("\\n", "\n")
    path = secret_env.get("CONTROL_PLANE_JWT_PUBLIC_KEY_PATH")
    if path:
        return _read_public_key(path)
    return None


def get_control_plane_jwt_secret() -> str:
    secret = secret_env.get("CONTROL_PLANE_JWT_SECRET") or secret_env.get("JWT_SIGNING_SECRET")
    if not secret:
        raise AuthBridgeError(
            "configure CONTROL_PLANE_JWT_PUBLIC_KEY_PATH (Ed25519) or CONTROL_PLANE_JWT_SECRET"
        )
    if len(secret) < 32:
        raise AuthBridgeError("CONTROL_PLANE_JWT_SECRET must be at least 32 characters")
    return secret


def _control_plane_key() -> tuple[str, str]:
    public = get_control_plane_public_key()
    if public:
        return public, "EdDSA"
    return get_control_plane_jwt_secret(), "HS256"


def _agent_key() -> str:
    """Workbench-only HMAC key for embedded-Agent tokens (derived; never the raw token secret)."""
    from server.auth import get_token_secret

    return hashlib.sha256(b"arcreel-embedded-agent:" + get_token_secret().encode()).hexdigest()


def _claims(payload: dict[str, Any]) -> dict[str, Any] | None:
    user_id = payload.get("user_id") or payload.get("sub")
    org_id = payload.get("org_id")
    if not user_id or not org_id:
        logger.warning("token missing user_id/org_id")
        return None
    return {**payload, "user_id": str(user_id), "org_id": str(org_id), "sub": str(user_id)}


def _verify_agent_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            _agent_key(),
            algorithms=["HS256"],
            audience=_AGENT_AUDIENCE,
            issuer=_AGENT_ISSUER,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != _AGENT_TYP or payload.get(EMBEDDED_AGENT_CLAIM) is not True:
        return None
    return _claims(payload)


def verify_control_plane_token(token: str) -> dict[str, Any] | None:
    """Decode a control-plane access token (or the workbench's own embedded-Agent token).

    Returns a payload with at least ``user_id``, ``org_id``, ``sub``.
    Returns ``None`` when the token is invalid/expired (caller maps to 401).
    Raises ``AuthBridgeError`` when no verification key is configured.
    """
    try:
        unverified_iss = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.PyJWTError:
        unverified_iss = None
    if unverified_iss == _AGENT_ISSUER:
        return _verify_agent_token(token)

    key, algorithm = _control_plane_key()
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=_JWT_AUDIENCE,
            issuer=_JWT_ISSUER,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        return None

    if "purpose" in payload:
        return None
    if payload.get("typ") != _JWT_TYP:
        logger.warning("control-plane JWT rejected: unexpected typ")
        return None
    if payload.get(EMBEDDED_AGENT_CLAIM) is not None:
        # Agent tokens are only ever minted by this workbench (issuer above).
        logger.warning("control-plane JWT rejected: carries the embedded-Agent claim")
        return None
    return _claims(payload)


def mint_embedded_agent_token(identity: Any, *, expiry_seconds: int) -> str:
    """Short-lived token for the Agent sandbox's own calls back into this workbench.

    Carries the session's user/org so billing and isolation follow the tenant, plus
    ``embedded_agent: true`` so the workbench treats the caller as the Agent (not the
    creator) for creator-only operations. Signed with a workbench-only key: the control
    plane cannot verify it and refuses the claim anyway.
    """
    now = int(time.time())
    payload = {
        "sub": identity.user_id,
        "user_id": identity.user_id,
        "org_id": identity.org_id,
        "aud": _AGENT_AUDIENCE,
        "iss": _AGENT_ISSUER,
        "typ": _AGENT_TYP,
        "iat": now,
        "exp": now + int(expiry_seconds),
        EMBEDDED_AGENT_CLAIM: True,
    }
    return jwt.encode(payload, _agent_key(), algorithm="HS256")
