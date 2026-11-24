"""Verify control-plane JWTs and map claims for the workbench."""

from __future__ import annotations

import logging
import os
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALLOWED_ALGORITHMS = ("HS256",)


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
            options={"require": ["exp", "iat"]},
        )
    except AuthBridgeError:
        raise
    except jwt.PyJWTError:
        return None

    if "purpose" in payload:
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
