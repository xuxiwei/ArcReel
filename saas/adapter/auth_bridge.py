"""Verify control-plane JWTs and map claims for the workbench."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALLOWED_ALGORITHMS = ("HS256",)
_JWT_AUDIENCE = "arcreel-control-plane"
_JWT_ISSUER = "arcreel-auth"
_JWT_TYP = "access"


class AuthBridgeError(Exception):
    """Invalid control-plane token or misconfiguration."""


def get_control_plane_jwt_secret() -> str:
    secret = (
        os.environ.get("CONTROL_PLANE_JWT_SECRET", "").strip()
        or os.environ.get("JWT_SIGNING_SECRET", "").strip()
    )
    if not secret:
        raise AuthBridgeError(
            "CONTROL_PLANE_JWT_SECRET (or JWT_SIGNING_SECRET) is not configured"
        )
    if len(secret) < 32:
        raise AuthBridgeError("CONTROL_PLANE_JWT_SECRET must be at least 32 characters")
    return secret


def verify_control_plane_token(token: str) -> dict[str, Any] | None:
    """Decode a control-plane access token.

    Returns a payload with at least ``user_id``, ``org_id``, ``sub``.
    Returns ``None`` when the token is invalid/expired (caller maps to 401).
    Raises ``AuthBridgeError`` when SaaS secrets are missing.
    """
    try:
        secret = get_control_plane_jwt_secret()
        payload = jwt.decode(
            token,
            secret,
            algorithms=list(_ALLOWED_ALGORITHMS),
            audience=_JWT_AUDIENCE,
            issuer=_JWT_ISSUER,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except AuthBridgeError:
        raise
    except jwt.PyJWTError:
        return None

    if "purpose" in payload:
        return None
    if payload.get("typ") != _JWT_TYP:
        logger.warning("control-plane JWT rejected: unexpected typ")
        return None

    user_id = payload.get("user_id") or payload.get("sub")
    org_id = payload.get("org_id")
    if not user_id or not org_id:
        logger.warning("control-plane JWT missing user_id/org_id")
        return None

    return {
        **payload,
        "user_id": str(user_id),
        "org_id": str(org_id),
        "sub": str(user_id),
    }


EMBEDDED_AGENT_CLAIM = "embedded_agent"


def mint_embedded_agent_token(identity: Any, *, expiry_seconds: int) -> str:
    """Short-lived control-plane-format token for the Agent sandbox's own API calls.

    Carries the session's user/org so billing and isolation follow the tenant, plus
    ``embedded_agent: true`` so the workbench treats the caller as the Agent (not
    the creator) for creator-only operations.
    """
    now = int(time.time())
    payload = {
        "sub": identity.user_id,
        "user_id": identity.user_id,
        "org_id": identity.org_id,
        "aud": _JWT_AUDIENCE,
        "iss": _JWT_ISSUER,
        "typ": _JWT_TYP,
        "iat": now,
        "exp": now + int(expiry_seconds),
        EMBEDDED_AGENT_CLAIM: True,
    }
    return jwt.encode(payload, get_control_plane_jwt_secret(), algorithm="HS256")
