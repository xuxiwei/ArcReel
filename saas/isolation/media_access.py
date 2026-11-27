"""SaaS: media URLs need the viewer's own organisation, carried by an HttpOnly cookie.

Upstream serves ``/api/v1/files/{project}/{path}`` and ``/api/v1/global-assets/...`` without
authentication because ``<img>`` / ``<video>`` / ``<audio>`` cannot send a Bearer token. In SaaS that
would let anyone who learns a project name and a path (forwarded link, browser history, logs) read
another organisation's media.

Every authenticated API call (``get_current_user``) refreshes a short-lived signed cookie
:data:`MEDIA_COOKIE` (org + user + expiry, HMAC with a key derived from the workbench token secret).
The browser sends it with media requests on the same domain, so the frontend needs no change. The
media routes resolve the project only inside the cookie's organisation; no cookie → 401, a project of
another organisation → 404. The embedded Agent gets no cookie. Self-hosted: unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, Response

from saas.adapter.mode import is_saas

MEDIA_COOKIE = "arcreel_media"
MEDIA_COOKIE_PATH = "/api/v1"
TTL_SECONDS = 12 * 3600
REFRESH_BELOW_SECONDS = 6 * 3600


def _key() -> bytes:
    from server.auth import get_token_secret

    return hashlib.sha256(b"arcreel-media-cookie:" + get_token_secret().encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_media_cookie(org_id: str, user_id: str, *, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + TTL_SECONDS)
    body = _b64(json.dumps({"o": org_id, "u": user_id, "e": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_media_cookie(value: str | None, *, now: float | None = None) -> dict[str, Any] | None:
    if not value or value.count(".") != 1:
        return None
    body, sig = value.split(".")
    expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        claims = json.loads(_unb64(body))
    except ValueError:
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("o"), str) or not isinstance(claims.get("e"), int):
        return None
    if claims["e"] <= (time.time() if now is None else now):
        return None
    return claims


def refresh_media_cookie(request: Request | None, response: Response | None, user: Any) -> None:
    """Called from ``get_current_user``: (re)issue the cookie when missing, stale or for another org."""
    if request is None or response is None or not is_saas():
        return
    from server.auth import EMBEDDED_AGENT_SUB

    org_id = getattr(user, "org_id", None)
    if not org_id or getattr(user, "sub", None) == EMBEDDED_AGENT_SUB:
        return
    claims = decode_media_cookie(request.cookies.get(MEDIA_COOKIE))
    if claims and claims["o"] == org_id and claims["e"] - time.time() > REFRESH_BELOW_SECONDS:
        return
    response.set_cookie(
        MEDIA_COOKIE,
        encode_media_cookie(org_id, str(getattr(user, "id", ""))),
        max_age=TTL_SECONDS,
        path=MEDIA_COOKIE_PATH,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def issue_media_cookie(request: Request, response: Response, *, org_id: str, user_id: str) -> None:
    """Set the cookie right away (login / register), so the first page's media never races the first API call."""
    if not is_saas() or not org_id:
        return
    response.set_cookie(
        MEDIA_COOKIE,
        encode_media_cookie(org_id, user_id),
        max_age=TTL_SECONDS,
        path=MEDIA_COOKIE_PATH,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def clear_media_cookie(response: Response) -> None:
    response.delete_cookie(MEDIA_COOKIE, path=MEDIA_COOKIE_PATH)


def media_org(request: Request) -> str | None:
    """SaaS: the organisation allowed to read media in this request (401 without a valid cookie).

    Self-hosted: ``None`` (upstream behaviour)."""
    if not is_saas():
        return None
    claims = decode_media_cookie(request.cookies.get(MEDIA_COOKIE))
    if claims is None:
        raise HTTPException(status_code=401, detail="media_session_required")
    return claims["o"]


def media_project_manager(request: Request) -> Any | None:
    """SaaS: the org-scoped ProjectManager for this media request; ``None`` when self-hosted."""
    org_id = media_org(request)
    if org_id is None:
        return None
    from saas.isolation.project_scope import _manager_for_org

    try:
        return _manager_for_org(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="media_session_required") from exc
