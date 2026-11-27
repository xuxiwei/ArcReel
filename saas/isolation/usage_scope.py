"""SaaS: usage records are scoped to the viewer — members see their own calls, platform admins see all.

``UsageRepository`` already funnels every read through ``_scope_query``; in SaaS it now adds
``user_id = <viewer>`` while :data:`_usage_user` is set. The usage router's dependency
(``saas.isolation.admin_guard.SAAS_USAGE_SCOPE``) sets it for members and leaves it unset for
platform admins. Writes (``start_call`` / ``finish_call`` …) do not go through ``_scope_query``.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_usage_user: ContextVar[str | None] = ContextVar("saas_usage_user", default=None)


def set_usage_user(user_id: str | None) -> None:
    _usage_user.set(user_id)


def current_usage_user() -> str | None:
    return _usage_user.get()


def scope_usage_query(stmt: Any, model: Any) -> Any:
    user_id = _usage_user.get()
    if user_id is None:
        return stmt
    column = getattr(model, "user_id", None)
    return stmt if column is None else stmt.where(column == user_id)
