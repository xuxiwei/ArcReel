"""Provision control-plane SaaS users into the local workbench ``users`` table.

Workbench tables (batches/tasks/sessions/…) have ``user_id → users.id`` FKs.
SaaS auth uses control-plane UUIDs that are not seeded locally; without a
row insert, generation batch creation fails with FOREIGN KEY constraint.
"""

from __future__ import annotations

import logging
from threading import Lock

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

_ensured: set[str] = set()
_ensured_lock = Lock()


def _mark_ensured(user_id: str) -> None:
    with _ensured_lock:
        _ensured.add(user_id)


def _already_ensured(user_id: str) -> bool:
    with _ensured_lock:
        return user_id in _ensured


def clear_local_saas_user_cache() -> None:
    """Test helper: drop in-process provision cache."""
    with _ensured_lock:
        _ensured.clear()


async def ensure_local_saas_user(user_id: str, *, username: str | None = None) -> None:
    """Idempotently insert a local ``users`` row for a control-plane user id.

    ``username`` is preferred when known (login/register). Otherwise a stable
    placeholder ``saas:<user_id>`` is used so the unique username constraint holds.
    """
    uid = (user_id or "").strip()
    if not uid or _already_ensured(uid):
        return

    from lib.db import async_session_factory
    from lib.db.models.user import User

    # Control-plane usernames are stored lowercase; keep the local copy identical
    # so "Alice" and "alice" never become two local rows.
    preferred = (username or "").strip().lower() or f"saas:{uid}"
    preferred = preferred[:64]

    async with async_session_factory() as session:
        existing = await session.get(User, uid)
        if existing is not None:
            _mark_ensured(uid)
            return

        session.add(
            User(
                id=uid,
                username=preferred,
                role="user",
                is_active=True,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Concurrent insert, or username collision with another row.
            existing = await session.get(User, uid)
            if existing is not None:
                _mark_ensured(uid)
                return
            fallback = f"saas:{uid}"[:64]
            if fallback == preferred:
                logger.exception("failed to provision local SaaS user %s", uid)
                raise
            session.add(
                User(
                    id=uid,
                    username=fallback,
                    role="user",
                    is_active=True,
                )
            )
            await session.commit()

    _mark_ensured(uid)
    logger.info("provisioned local SaaS user id=%s username=%s", uid, preferred)


async def local_username(user_id: str) -> str | None:
    """Login name stored for a SaaS user id, or None when not provisioned yet."""
    from lib.db import async_session_factory
    from lib.db.models.user import User

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
    if user is None or user.username.startswith("saas:"):
        return None
    return user.username
