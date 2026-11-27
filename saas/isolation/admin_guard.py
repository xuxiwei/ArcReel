"""SaaS: instance-wide settings belong to platform admins, not to every signed-in user.

Upstream is single-user: whoever can sign in owns the instance, so routers for object
storage, Agent credentials, custom providers, system logs, the global asset library …
only require a signed-in user. In SaaS every registered user is a tenant, so these
routers get one of the guards below (mounted in ``server/app.py``):

- :data:`SAAS_ADMIN_ONLY` — every method needs a platform admin;
- :data:`SAAS_ADMIN_WRITES` — reads stay open (model pickers, catalogs the UI needs),
  writes and the listed sensitive reads need a platform admin.

"Platform admin" is the control plane's ``users.is_admin``, checked against the control
plane with the caller's own token (cached briefly), so revoking admin takes effect
without waiting for tokens to expire. The embedded Agent is never an admin. Self-hosted
mode is unchanged: every guard is a no-op.
"""

# No `from __future__ import annotations`: the guard closure's parameter annotations
# reference names imported inside saas_admin_guard(), which FastAPI cannot resolve from
# strings, so it would treat them as query parameters (422).

import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

_ADMIN_CACHE_TTL_SEC = 60.0
_ADMIN_CACHE_MAX = 1024
_admin_cache: dict[str, tuple[float, bool]] = {}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def clear_admin_cache() -> None:
    _admin_cache.clear()


async def _fetch_is_admin(access_token: str) -> bool:
    from saas.adapter.control_plane_client import ControlPlaneError, control_plane_user_request

    try:
        me = await control_plane_user_request("GET", "/v1/me", access_token=access_token)
    except ControlPlaneError as exc:
        if exc.status_code in (401, 403):
            return False
        logger.error("platform admin check failed: control plane %s", exc.status_code)
        raise HTTPException(status_code=503, detail="control_plane_unavailable") from exc
    return bool((me or {}).get("user", {}).get("is_admin"))


async def is_platform_admin(access_token: str) -> bool:
    key = hashlib.sha256(access_token.encode()).hexdigest()
    now = time.monotonic()
    cached = _admin_cache.get(key)
    if cached is not None and now - cached[0] < _ADMIN_CACHE_TTL_SEC:
        return cached[1]
    result = await _fetch_is_admin(access_token)
    if len(_admin_cache) >= _ADMIN_CACHE_MAX:
        _admin_cache.clear()
    _admin_cache[key] = (now, result)
    return result


def _compile(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


def saas_admin_guard(
    *,
    writes_only: bool,
    admin_reads: Iterable[str] = (),
    member_writes: Iterable[tuple[str, str]] = (),
) -> Callable[..., Awaitable[None]]:
    """Build a router dependency.

    ``admin_reads``: regexes of request paths whose reads also need an admin (secrets).
    ``member_writes``: ``(METHOD, path-regex)`` writes any member may still make.
    """
    from server.auth import EMBEDDED_AGENT_SUB, CurrentUser, oauth2_scheme_optional

    sensitive_reads = _compile(admin_reads)
    allowed_writes = tuple((method.upper(), re.compile(p)) for method, p in member_writes)

    async def guard(
        request: Request,
        user: CurrentUser,
        token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    ) -> None:
        if not is_saas():
            return
        method, path = request.method.upper(), request.url.path
        if writes_only:
            if method in _READ_METHODS and not any(p.search(path) for p in sensitive_reads):
                return
            if any(method == m and p.search(path) for m, p in allowed_writes):
                return
        if user.sub == EMBEDDED_AGENT_SUB or not token:
            raise HTTPException(status_code=403, detail="platform_admin_required")
        if not await is_platform_admin(token):
            raise HTTPException(status_code=403, detail="platform_admin_required")

    return guard


# Every method is platform-admin only (instance-wide state or other tenants' data).
SAAS_ADMIN_ONLY = saas_admin_guard(writes_only=False)

# Reads open to members; writes (and secret-bearing reads) need a platform admin.
SAAS_ADMIN_WRITES = saas_admin_guard(
    writes_only=True,
    admin_reads=(r"/credentials(/|$)", r"/providers/[^/]+/config$"),
    member_writes=(("POST", r"/system/config/recommendation-changes/acknowledge$"),),
)


def saas_usage_scope() -> Callable[..., Awaitable[None]]:
    """Usage router dependency: platform admins see every record, members only their own."""
    from server.auth import EMBEDDED_AGENT_SUB, CurrentUser, oauth2_scheme_optional

    from saas.isolation.usage_scope import set_usage_user

    async def scope(
        user: CurrentUser,
        token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    ) -> None:
        if not is_saas():
            return
        if user.sub == EMBEDDED_AGENT_SUB or not token:
            raise HTTPException(status_code=403, detail="usage_not_available")
        set_usage_user(None if await is_platform_admin(token) else user.id)

    return scope


SAAS_USAGE_SCOPE = saas_usage_scope()
